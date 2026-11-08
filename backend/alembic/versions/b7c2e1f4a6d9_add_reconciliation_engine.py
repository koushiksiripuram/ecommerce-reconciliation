"""add reconciliation engine

Brings the schema in line with the reconciliation engine:

* new ``freight_rate_cards`` table (configurable courier/zone/slab tariffs);
* ``settlement_records.order_reference`` (the order id a payout line settles,
  used as the join key when matching settlements back to orders);
* ``reconciliation_results`` freight, TCS/TDS and structured ``issues`` columns;
* a rewritten ``reconciliation_status`` value set (``settled``, ``short_paid``,
  ``unpaid_past_due``, ``pending``, ``missing_in_orders``).

Revision ID: b7c2e1f4a6d9
Revises: a4f1c8b9d2e3
Create Date: 2026-11-07 22:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2e1f4a6d9'
down_revision: str | None = 'a4f1c8b9d2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ``reconciliation_results.status`` is a VARCHAR + CHECK constraint. The
# migration widens the VARCHAR length and swaps the CHECK constraint by hand, so
# the column type is declared as a plain ``String``.
#
# Do NOT pass an ``Enum(..., create_constraint=True)`` to ``alter_column`` here:
# Alembic would additionally emit the type's own DROP/ADD CONSTRAINT around the
# ALTER, duplicating the explicit statements below and failing on PostgreSQL
# with "constraint ... does not exist".
_OLD_STATUS = sa.String(length=21)  # longest old value: 'missing_in_settlement'
_NEW_STATUS = sa.String(length=17)  # longest new value: 'missing_in_orders'

_OLD_STATUS_CHECK = (
    "status IN ('matched', 'amount_mismatch', 'missing_in_settlement', "
    "'missing_in_orders', 'partial', 'unmatched')"
)
_NEW_STATUS_CHECK = (
    "status IN ('settled', 'short_paid', 'unpaid_past_due', 'pending', "
    "'missing_in_orders')"
)


def upgrade() -> None:
    op.create_table(
        'freight_rate_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('courier', sa.String(length=64), nullable=False),
        sa.Column('zone', sa.String(length=32), nullable=False),
        sa.Column(
            'service_type',
            sa.Enum('forward', 'reverse', name='freight_service_type', native_enum=False, create_constraint=True),
            server_default='forward',
            nullable=False,
        ),
        sa.Column(
            'payment_type',
            sa.Enum('prepaid', 'cod', name='freight_payment_type', native_enum=False, create_constraint=True),
            server_default='prepaid',
            nullable=False,
        ),
        sa.Column(
            'min_weight_grams',
            sa.Numeric(precision=10, scale=3),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('max_weight_grams', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('rate', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_freight_rate_cards')),
        sa.UniqueConstraint(
            'courier', 'zone', 'service_type', 'payment_type', 'min_weight_grams',
            name='uq_freight_rate_cards_slab',
        ),
    )
    op.create_index(op.f('ix_freight_rate_cards_courier'), 'freight_rate_cards', ['courier'], unique=False)

    op.add_column('settlement_records', sa.Column('order_reference', sa.String(length=128), nullable=True))
    op.create_index(
        op.f('ix_settlement_records_order_reference'),
        'settlement_records',
        ['order_reference'],
        unique=False,
    )

    # Batch mode so the enum change and the added columns also apply on SQLite,
    # which cannot alter a column type with plain ALTER TABLE. On PostgreSQL the
    # statements run directly.
    #
    # Batch mode re-applies the application's ``ck_%(table_name)s_%(constraint_name)s``
    # naming convention, so the constraint is referenced by its bare token
    # (``reconciliation_status``).
    with op.batch_alter_table('reconciliation_results') as batch_op:
        batch_op.drop_constraint('reconciliation_status', type_='check')
        batch_op.alter_column(
            'status',
            existing_type=_OLD_STATUS,
            type_=_NEW_STATUS,
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column('expected_freight_amount', sa.Numeric(precision=14, scale=2), server_default=sa.text('0'), nullable=False)
        )
        batch_op.add_column(
            sa.Column('actual_freight_amount', sa.Numeric(precision=14, scale=2), server_default=sa.text('0'), nullable=False)
        )
        batch_op.add_column(
            sa.Column('tcs_amount', sa.Numeric(precision=14, scale=2), server_default=sa.text('0'), nullable=False)
        )
        batch_op.add_column(
            sa.Column('tds_amount', sa.Numeric(precision=14, scale=2), server_default=sa.text('0'), nullable=False)
        )
        batch_op.add_column(sa.Column('issues', sa.JSON(), nullable=True))
        batch_op.create_check_constraint('reconciliation_status', _NEW_STATUS_CHECK)


def downgrade() -> None:
    with op.batch_alter_table('reconciliation_results') as batch_op:
        batch_op.drop_constraint('reconciliation_status', type_='check')
        batch_op.alter_column(
            'status',
            existing_type=_NEW_STATUS,
            type_=_OLD_STATUS,
            existing_nullable=False,
        )
        batch_op.drop_column('issues')
        batch_op.drop_column('tds_amount')
        batch_op.drop_column('tcs_amount')
        batch_op.drop_column('actual_freight_amount')
        batch_op.drop_column('expected_freight_amount')
        batch_op.create_check_constraint('reconciliation_status', _OLD_STATUS_CHECK)

    op.drop_index(op.f('ix_settlement_records_order_reference'), table_name='settlement_records')
    # Batch mode is required on SQLite, which cannot drop a column directly.
    with op.batch_alter_table('settlement_records') as batch_op:
        batch_op.drop_column('order_reference')

    op.drop_index(op.f('ix_freight_rate_cards_courier'), table_name='freight_rate_cards')
    op.drop_table('freight_rate_cards')
