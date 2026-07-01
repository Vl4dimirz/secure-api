"""Auth routes — register + login, backed by the database. Login is rate-limited."""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth, schemas
from app.config import settings
from app.database import get_db
from app.limits import limiter
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    # Invite-only, fail-closed: if no codes are configured, registration is shut.
    # compare_digest is constant-time, so a wrong code can't be timing-guessed.
    valid = settings.valid_codes()
    accepted = any(secrets.compare_digest(payload.code, c) for c in valid)
    if not valid or not accepted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing registration code",
        )
    existing = await db.execute(select(User).where(User.username == payload.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Username already taken")
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
