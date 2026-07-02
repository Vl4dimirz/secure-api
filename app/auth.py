"""Auth core — password hashing (bcrypt) + JWT tokens + the current-user dependency.

Two security fundamentals live here:
  * Passwords are NEVER stored in plain text — only a bcrypt hash (salted, slow).
  * Access is proven with a signed JWT, verified on every protected request, and
    checked against a revocation list so a logged-out token stops working.
"""
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import RevokedToken

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    # jti = a unique token id, so a single token can be revoked on logout.
    payload = {"sub": subject, "iat": now, "exp": expire, "jti": secrets.token_urlsafe(16)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Dependency that protects a route — verifies the JWT and that it hasn't
    been revoked, or 401s."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise credentials_exc

    username = payload.get("sub")
    jti = payload.get("jti")
    if username is None:
        raise credentials_exc

    if jti is not None:
        revoked = await db.execute(select(RevokedToken.id).where(RevokedToken.jti == jti))
        if revoked.scalar_one_or_none() is not None:
            raise credentials_exc  # token was logged out
    return username
