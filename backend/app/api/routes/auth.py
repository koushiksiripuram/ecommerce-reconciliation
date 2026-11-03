"""Authentication endpoints.

The access token is returned as an HttpOnly cookie rather than in the response
body, so client-side JavaScript can never read it (mitigating token theft via
XSS). The JSON body only carries the public user profile.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    normalize_email,
    verify_password,
    verify_password_dummy,
)
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

# Deliberately identical for "no such user" and "wrong password" so the response
# cannot be used to discover which email addresses have accounts.
INVALID_CREDENTIALS_DETAIL = "Invalid email or password"


def _set_access_token_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Authenticate a user and issue an access-token cookie."""
    email = normalize_email(payload.email)
    user = db.scalar(select(User).options(selectinload(User.role)).where(User.email == email))

    if user is None:
        # Equalise timing with the password-verification path.
        verify_password_dummy(payload.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )

    _set_access_token_cookie(response, create_access_token(user.id, user.role.name))
    return user


@router.get("/me", response_model=UserRead)
def read_current_user(user: CurrentUser) -> User:
    """Return the profile of the authenticated user."""
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Clear the access-token cookie. Safe to call without being authenticated."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
