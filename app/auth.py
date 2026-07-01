"""Auth core — password hashing (bcrypt) + JWT tokens + the current-user dependency.

Two security fundamentals live here:
  * Passwords are NEVER stored in plain text — only a bcrypt hash (salted, slow).
  * Access is proven with a signed JWT, verified on every protected request.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": subject, "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency that protects a route — decodes + verifies the JWT, or 401s."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exc
        return username
    except jwt.PyJWTError:
        raise credentials_exc
