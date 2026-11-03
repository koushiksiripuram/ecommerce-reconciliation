"""User and role models."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.imports import ImportBatch, UploadedFile


class Role(Base, TimestampMixin):
    """A role granted to a user, e.g. ``finance_executive`` or ``co_founder``."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"


class User(Base, TimestampMixin):
    """A platform user belonging to exactly one role.

    Credential storage is intentionally omitted: authentication is out of scope
    for this milestone.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )

    role: Mapped["Role"] = relationship(back_populates="users")
    uploaded_files: Mapped[list["UploadedFile"]] = relationship(
        back_populates="uploaded_by",
        foreign_keys="UploadedFile.uploaded_by_user_id",
    )
    import_batches: Mapped[list["ImportBatch"]] = relationship(
        back_populates="created_by",
        foreign_keys="ImportBatch.created_by_user_id",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
