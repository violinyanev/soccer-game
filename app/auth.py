import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Request
from fastapi.responses import RedirectResponse

SECRET_KEY = os.getenv("SECRET_KEY", "insecure-default-change-me")
ALGORITHM = "HS256"
# Sessions last 7 days
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "user_id": user_id,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

def get_current_user(request: Request) -> Optional[dict]:
    """Return the JWT payload dict or None if not logged in / invalid token."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    return decode_token(token)


def login_required(request: Request) -> dict:
    """Dependency: returns user payload or raises a redirect to /login."""
    user = get_current_user(request)
    if not user:
        # Raise an exception that main.py exception handler converts to redirect
        from fastapi import HTTPException
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


def set_auth_cookie(response, user_id: int, username: str, is_admin: bool):
    token = create_access_token(user_id, username, is_admin)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )


def clear_auth_cookie(response):
    response.delete_cookie("access_token")
