"""AI endpoint — an authed, rate-limited, quota-capped bridge to Claude.

This is the "AI" in *Secure AI Backend*. An LLM call is a paid, abusable resource,
so it gets the full security treatment rather than being left open:

- Auth required — no anonymous access to a billed model (JWT via get_current_user).
- Rate limited — unmetered AI calls are a billing-DoS; cap requests per client.
- Per-account quota — each account gets a fixed trial budget (settings.ai_call_quota);
  a leaked/shared account still can't burn tokens forever.
- Input length capped by the schema — bounds tokens (= cost) spent per request.
- API key read from env/config — never hardcoded, never returned to the client.
- Errors are swallowed into a generic message — never leak the key, stack, or
  upstream provider details to the caller.
"""
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth, schemas
from app.config import settings
from app.database import get_db
from app.limits import limiter
from app.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/summarize", response_model=schemas.SummarizeResponse)
@limiter.limit("10/minute")
async def summarize(
    request: Request,
    payload: schemas.SummarizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(auth.get_current_user),
):
    result = await db.execute(select(User).where(User.username == current_user))
    user = result.scalar_one_or_none()
    if user is None:  # token valid but account gone
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")

    # Quota check comes first — an exhausted account is refused before we ever
    # touch the paid model.
    if user.ai_calls_used >= settings.ai_call_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI trial quota exhausted. Contact the owner for more access.",
        )

    if not settings.anthropic_api_key:
        # Fail clearly instead of 500-ing when the server has no key configured.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI is not configured on this server.",
        )

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.ai_model,
            max_tokens=300,
            system=(
                "You are a concise summarizer. Reply with a short, faithful summary "
                "in 2-3 sentences. No preamble, no bullet points."
            ),
            messages=[{"role": "user", "content": payload.text}],
        )
        summary = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ).strip()
        if not summary:
            raise ValueError("empty completion")
    except Exception:
        # Never surface the raw provider error (could leak quota/key/model detail).
        # A failed call doesn't burn the user's quota.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service is temporarily unavailable. Please try again.",
        )

    # Only a successful call spends a quota unit.
    user.ai_calls_used += 1
    await db.commit()
    return schemas.SummarizeResponse(
        summary=summary,
        calls_remaining=max(0, settings.ai_call_quota - user.ai_calls_used),
    )
