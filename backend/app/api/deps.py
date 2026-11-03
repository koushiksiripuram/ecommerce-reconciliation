"""FastAPI dependencies for authentication and role-based authorisation.

The access token is read from the HttpOnly cookie first (how the browser sends
it) and from an ``Authorization: Bearer`` header second, so non-browser clients
and tests can authenticate the same way.
"""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.roles import RoleName
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "bearer "

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_UNAUTHORIZED_HEADERS,
    )


def _extract_token(request: Request) -> str | None:
    """Return the access token from the cookie or the Authorization header."""
    cookie_token = request.cookies.get(get_settings().auth_cookie_name)
    if cookie_token:
        return cookie_token

    header = request.headers.get(AUTHORIZATION_HEADER)
    if header and header.lower().startswith(BEARER_PREFIX):
        return header[len(BEARER_PREFIX) :].strip() or None

    return None


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the authenticated user or raise 401.

    The role is eagerly loaded so it stays available while the response is
    serialised, after the request-scoped session has been closed.
    """
    token = _extract_token(request)
    if token is None:
        raise _unauthorized("Not authenticated")

    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        # Covers malformed, tampered, wrong-signature and expired tokens.
        raise _unauthorized("Invalid or expired token") from None

    subject = payload.get("sub")
    if not subject or not str(subject).isdigit():
        raise _unauthorized("Invalid or expired token")

    user = db.scalar(
        select(User).options(selectinload(User.role)).where(User.id == int(subject))
    )
    if user is None:
        raise _unauthorized("Invalid or expired token")

    return user


#: Dependency that yields the authenticated user.
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: RoleName) -> Callable[[User], User]:
    """Build a dependency that only allows the given roles.

    Authenticated users with any other role receive 403; callers without a valid
    token still receive 401 from :func:`get_current_user`.
    """
    allowed_names = {role.value for role in allowed}

    def dependency(user: CurrentUser) -> User:
        if user.role.name not in allowed_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return dependency
