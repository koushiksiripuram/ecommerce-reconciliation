"""Reusable SQLAlchemy column types."""

from enum import Enum as PyEnum

from sqlalchemy import Enum as SAEnum


def portable_enum(enum_class: type[PyEnum], name: str) -> SAEnum:
    """Build an ``Enum`` column type backed by ``VARCHAR`` + ``CHECK``.

    ``native_enum=False`` avoids PostgreSQL native enum types (which require
    extra DDL to create, alter or drop). ``values_callable`` makes SQLAlchemy
    persist each member's ``.value`` (``"pending"``) instead of its ``.name``
    (``"PENDING"``), which is what the declared server defaults use.
    """
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )
