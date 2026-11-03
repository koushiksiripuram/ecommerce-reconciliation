"""add password hash to users

Adds the Argon2id password digest column required for authentication.

Revision ID: 533d946dd507
Revises: 6e9f95855415
Create Date: 2026-11-03 14:51:08.509438

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '533d946dd507'
down_revision: str | None = '6e9f95855415'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode so the change also applies on SQLite, which cannot add or drop
    # a column with plain ALTER TABLE. On PostgreSQL the statements run directly.
    #
    # The column is NOT NULL by design: the application always writes a hash.
    # This is safe because no user rows can exist yet — the only way to create a
    # user is the `python -m app.cli create-user` command introduced with this
    # change, and the table is empty until it is run.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_hash")
