"""Authentication request and response schemas.

These models define exactly what leaves the API. ``User.password_hash`` is not
part of ``UserRead`` (and ``extra="forbid"`` is not needed because ORM objects
are read by attribute) so a digest can never be serialised into a response.
"""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Credentials submitted to ``POST /api/auth/login``."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class RoleRead(BaseModel):
    """The role granted to a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class UserRead(BaseModel):
    """Public representation of a user. Never includes credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
    role: RoleRead
