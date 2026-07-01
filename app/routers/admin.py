"""Admin API — issue and manage invite codes without hand-editing .env.

Gated by a single admin token (env ADMIN_TOKEN), checked in constant time and
fail-closed: if no token is configured the whole /admin surface is disabled.
Kept separate from user JWT auth on purpose — this is an operator capability.
"""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.config import settings
from app.database import get_db
from app.models import InviteCode

router = APIRouter(prefix="/admin", tags=["admin"])

# Unambiguous alphabet (no 0/O/1/I) so issued codes are easy to read out loud.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


async def require_admin(x_admin_token: str = Header(default="")):
    expected = settings.admin_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured.",
        )
    if not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )


def _new_code(prefix: str) -> str:
    left = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    right = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    return f"{prefix}-{left}-{right}"


@router.post(
    "/invite-codes",
    response_model=schemas.GeneratedCodes,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def generate_codes(
    payload: schemas.GenerateCodesRequest, db: AsyncSession = Depends(get_db)
):
    created: list[str] = []
    for _ in range(payload.count):
        # Retry on the astronomically rare collision so we never insert a dup.
        for _attempt in range(5):
            code = _new_code(payload.prefix)
            exists = await db.execute(select(InviteCode).where(InviteCode.code == code))
            if exists.scalar_one_or_none() is None:
                db.add(InviteCode(code=code))
                created.append(code)
                break
    await db.commit()
    return schemas.GeneratedCodes(created=created)


@router.get(
    "/invite-codes",
    response_model=list[schemas.InviteCodeStatus],
    dependencies=[Depends(require_admin)],
)
async def list_codes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InviteCode).order_by(InviteCode.id.desc()))
    return result.scalars().all()


@router.delete(
    "/invite-codes/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def revoke_code(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InviteCode).where(InviteCode.code == code))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Code not found")
    if invite.used_at is not None:
        # A used code already minted an account; revoking it changes nothing.
        raise HTTPException(status_code=400, detail="Code already used; cannot revoke")
    await db.delete(invite)
    await db.commit()
    return None
