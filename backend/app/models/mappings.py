"""Reusable, partner-specific column mappings.

A mapping translates a partner's own column headers into the platform's
canonical field names. Once a human has approved one for a given source type and
partner, later uploads from the same partner reuse it instead of asking again.
"""

from typing import Any

from sqlalchemy import ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import portable_enum
from app.models.enums import ImportSourceType


class ImportColumnMapping(Base, TimestampMixin):
    """An approved mapping of partner headers to canonical fields.

    Scoped by ``source_type`` + ``partner``: exactly one approved mapping exists
    per pair, and re-approving a mapping replaces it.
    """

    __tablename__ = "import_column_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source_type", "partner", name="uq_import_column_mappings_source_type_partner"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    source_type: Mapped[ImportSourceType] = mapped_column(
        portable_enum(ImportSourceType, "import_source_type"),
        nullable=False,
    )
    partner: Mapped[str] = mapped_column(String(64), nullable=False)

    #: Canonical field name -> the partner's column header.
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<ImportColumnMapping id={self.id} source_type={self.source_type} "
            f"partner={self.partner!r}>"
        )
