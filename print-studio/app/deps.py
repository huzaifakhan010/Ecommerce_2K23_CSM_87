"""Authentication / authorisation dependencies."""
from typing import Optional

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.models import User
from app.security import decode_access_token

_BEARER = {"WWW-Authenticate": "Bearer"}


def get_current_user(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization:
        raise AppError(401, "not_authenticated", "Missing Authorization header.", headers=_BEARER)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AppError(401, "not_authenticated", "Use 'Authorization: Bearer <token>'.", headers=_BEARER)
    try:
        payload = decode_access_token(token.strip())
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise AppError(401, "invalid_token", "The token is invalid or expired.", headers=_BEARER)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "invalid_token", "The token is invalid or expired.", headers=_BEARER)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    # The role is read from the database on every request, so demoting an admin takes effect immediately.
    if user.role != "admin":
        raise AppError(403, "forbidden", "Administrator role required.")
    return user
