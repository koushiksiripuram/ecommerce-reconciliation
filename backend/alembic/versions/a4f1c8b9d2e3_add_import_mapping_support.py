"""add import mapping support

Brings the database schema in line with the import pipeline models:

* new ``import_column_mappings`` table (reusable, partner-specific mappings);
* ``import_batches.column_mapping`` (the approved mapping used for a batch);
* ``raw_imported_records.normalized_data`` (canonical projection of a row);
* widened ``import_source_type`` / ``import_batch_status`` value sets, including
  the ``cod_remittances`` and ``freight_invoices`` source types and the
  ``uploaded`` / ``mapping_required`` batch states.

Revision ID: a4f1c8b9d2e3
Revises: 533d946dd507
Create Date: 2026-11-07 18:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f1c8b9d2e3'
down_revision: str | None = '533d946dd507'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Enum value sets before and after this migration. Kept self-contained so the
# migration does not drift if the application enums change later.
_OLD_SOURCE_TYPE = sa.Enum(
    'orders', 'settlements', 'returns', 'claims',
    name='import_source_type', native_enum=False, create_constraint=True,
)
_NEW_SOURCE_TYPE = sa.Enum(
    'orders', 'settlements', 'cod_remittances', 'freight_invoices', 'returns', 'claims',
    name='import_source_type', native_enum=False, create_constraint=True,
)
_OLD_BATCH_STATUS = sa.Enum(
    'pending', 'processing', 'completed', 'failed',
    name='import_batch_status', native_enum=False, create_constraint=True,
)
_NEW_BATCH_STATUS = sa.Enum(
    'uploaded', 'mapping_required', 'processing', 'completed', 'failed',
    name='import_batch_status', native_enum=False, create_constraint=True,
)

_SOURCE_TYPE_CHECK = (
    "source_type IN ('orders', 'settlements', 'cod_remittances', "
    "'freight_invoices', 'returns', 'claims')"
)
_BATCH_STATUS_CHECK = (
    "status IN ('uploaded', 'mapping_required', 'processing', 'completed', 'failed')"
)


def upgrade() -> None:
    op.create_table(
        'import_column_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column(
            'source_type',
            sa.Enum(
                'orders', 'settlements', 'cod_remittances', 'freight_invoices', 'returns', 'claims',
                name='import_source_type', native_enum=False, create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column('partner', sa.String(length=64), nullable=False),
        sa.Column('mapping', sa.JSON(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'], ['users.id'],
            name='fk_import_column_mappings_created_by_user_id_users',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_import_column_mappings'),
        sa.UniqueConstraint(
            'source_type', 'partner',
            name='uq_import_column_mappings_source_type_partner',
        ),
    )
    op.create_index(
        'ix_import_column_mappings_created_by_user_id',
        'import_column_mappings',
        ['created_by_user_id'],
        unique=False,
    )

    op.add_column('import_batches', sa.Column('column_mapping', sa.JSON(), nullable=True))
    op.add_column(
        'raw_imported_records',
        sa.Column('normalized_data', sa.JSON(), nullable=True),
    )

    # Batch mode so the enum change also applies on SQLite (which cannot drop a
    # constraint or alter a column type with plain ALTER TABLE). On PostgreSQL
    # the statements run directly.
    #
    # Batch mode re-applies the application's ``ck_%(table_name)s_%(constraint_name)s``
    # naming convention, so the constraint is referenced by its bare token
    # (``import_source_type``) which resolves to ``ck_import_batches_import_source_type``.
    with op.batch_alter_table('import_batches') as batch_op:
        batch_op.drop_constraint('import_source_type', type_='check')
        batch_op.drop_constraint('import_batch_status', type_='check')
        batch_op.alter_column(
            'source_type',
            existing_type=_OLD_SOURCE_TYPE,
            type_=_NEW_SOURCE_TYPE,
            existing_nullable=False,
        )
        batch_op.alter_column(
            'status',
            existing_type=_OLD_BATCH_STATUS,
            type_=_NEW_BATCH_STATUS,
            existing_nullable=False,
            existing_server_default='pending',
            server_default='uploaded',
        )
        batch_op.create_check_constraint('import_source_type', _SOURCE_TYPE_CHECK)
        batch_op.create_check_constraint('import_batch_status', _BATCH_STATUS_CHECK)


def downgrade() -> None:
    with op.batch_alter_table('import_batches') as batch_op:
        batch_op.drop_constraint('import_source_type', type_='check')
        batch_op.drop_constraint('import_batch_status', type_='check')
        batch_op.alter_column(
            'source_type',
            existing_type=_NEW_SOURCE_TYPE,
            type_=_OLD_SOURCE_TYPE,
            existing_nullable=False,
        )
        batch_op.alter_column(
            'status',
            existing_type=_NEW_BATCH_STATUS,
            type_=_OLD_BATCH_STATUS,
            existing_nullable=False,
            existing_server_default='uploaded',
            server_default='pending',
        )
        batch_op.create_check_constraint(
            'import_source_type',
            "source_type IN ('orders', 'settlements', 'returns', 'claims')",
        )
        batch_op.create_check_constraint(
            'import_batch_status',
            "status IN ('pending', 'processing', 'completed', 'failed')",
        )
        # Batch mode is required on SQLite, which cannot drop a column directly.
        batch_op.drop_column('column_mapping')

    with op.batch_alter_table('raw_imported_records') as batch_op:
        batch_op.drop_column('normalized_data')

    op.drop_index('ix_import_column_mappings_created_by_user_id', table_name='import_column_mappings')
    op.drop_table('import_column_mappings')
