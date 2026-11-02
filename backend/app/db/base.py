"""Declarative base class shared by all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models.

    Alembic autogenerate discovers models through this metadata.
    """
