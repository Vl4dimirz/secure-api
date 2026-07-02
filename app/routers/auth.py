"""Auth routes — register + login + logout, backed by the database."""
import jwt
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth, schemas
from app.database import get_db
from app.limits import limiter
from app.models import InviteCode, RevokedToken, User

router = APIRouter(prefix="/auth", tags=["auth"])

# A throwaway bcrypt hash to verify against when the username doesn't exist, so
# login always does the same bcrypt work whether or not the user is real —
# closes the timing side-channel that leaks which usernames exist. Computed once.
_DUMMY_HASH = auth.hash_password("timing-attack-dummy-password")


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(
    request: Request,
    payload: schemas.UserCreate,
    db: AsyncSession = Depends(get_db),
):
    # Invite-only + SINGLE-USE + fail-closed. The code must exist in the table and
    # still be unused; consuming it here means it can't be shared/reused to spin up
    # more accounts against the paid AI endpoint.
    result = await db.execute(
        select(InviteCode).where(
            InviteCode.code == payload.code, InviteCode.used_at.is_(None)
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or already-used registration code",
        )

    existing = await db.execute(select(User).where(User.username == payload.username))
    if existing.scalar_one_or_none() is not None:
        # Don't consume the code on a name clash — let them retry a different name.
        raise HTTPException(status_code=400, detail="Username already taken")

    invite.used_at = datetime.now(timezone.utc)
    invite.used_by = payload.username
    user = User(username=payload.username, hashed_password=auth.hash_password(payload.password))
    db.add(user)
    await db.commit()
    return {"username": user.username}


@router.post("/login", response_model=schemas.Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    # Always run bcrypt (against a dummy hash if the user is missing) so the
    # response time doesn't reveal whether the username exists.
    hashed = user.hashed_password if user is not None else _DUMMY_HASH
    password_ok = auth.verify_password(form.password, hashed)
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(subject=user.username)
    return schemas.Token(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(auth.oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the presented token — its `jti` is denylisted until it expires, so
    it stops working immediately (JWTs are otherwise valid until expiry)."""
    try:
        payload = auth.decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti:
        expires_at = (
            datetime.fromtimestamp(exp, tz=timezone.utc) if exp else datetime.now(timezone.utc)
        )
        db.add(RevokedToken(jti=jti, expires_at=expires_at))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()  # already revoked - fine, still logged out
    return Response(status_code=status.HTTP_204_NO_CONTENT)
