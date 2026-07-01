"""Auth routes — register + login, backed by the database. Login is rate-limited."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth, schemas
from app.database import get_db
from app.limits import limiter
from app.models import InviteCode, User

router = APIRouter(prefix="/auth", tags=["auth"])


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
    if user is None or not auth.verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(subject=user.username)
    return schemas.Token(access_token=token)
