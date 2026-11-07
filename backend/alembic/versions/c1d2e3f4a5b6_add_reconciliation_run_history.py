"""add reconciliation run history

Replaces the destructive "delete every result then rebuild" approach with an
auditable, run-based one:

* new ``reconciliation_runs`` table (one row per execution, with timestamps, the
  triggering user, a source-import watermark and the run's summary counts);
* ``reconciliation_results.run_id`` linking each line to the run that produced it;
* ``reconciliation_results.is_current`` so previous results are *superseded*
  rather than deleted and the latest run can be identified in one query.

Existing result rows are backfilled as ``is_current = true`` with ``run_id``
left ``NULL``; they are preserved and simply drop out of the default (current)
view on the next run.

Revision ID: c1d2e3f4a5b6
Revises: b7c2e1f4a6d9
Create Date: 2026-11-07 23:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: str | None = 'b7c2e1f4a6d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reconciliation_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('triggered_by_user_id', sa.Integer(), nullable=True),
        sa.Column('source_watermark', sa.Integer(), nullable=True),
        sa.Column('orders_reconciled', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('settlements_matched', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('unmatched_settlements', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('results_created', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('by_status', sa.JSON(), nullable=True),
        sa.Column('is_current', sa.Boolean(), server_default=sa.text('false'), nullable=False),
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
            ['triggered_by_user_id'], ['users.id'],
            name='fk_reconciliation_runs_triggered_by_user_id_users',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_runs'),
    )
    op.create_index(
        'ix_reconciliation_runs_triggered_by_user_id',
        'reconciliation_runs',
        ['triggered_by_user_id'],
        unique=False,
    )
    op.create_index(
        'ix_reconciliation_runs_is_current', 'reconciliation_runs', ['is_current'], unique=False
    )

    # Batch mode so the added foreign key and indexes also apply on SQLite, which
    # cannot add a foreign key with plain ALTER TABLE (it rebuilds the table).
    with op.batch_alter_table('reconciliation_results') as batch_op:
        batch_op.add_column(sa.Column('run_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('is_current', sa.Boolean(), server_default=sa.text('true'), nullable=False)
        )
        batch_op.create_index('ix_reconciliation_results_run_id', ['run_id'], unique=False)
        batch_op.create_index('ix_reconciliation_results_is_current', ['is_current'], unique=False)
        batch_op.create_foreign_key(
            'fk_reconciliation_results_run_id_reconciliation_runs',
            'reconciliation_runs',
            ['run_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    with op.batch_alter_table('reconciliation_results') as batch_op:
        batch_op.drop_constraint(
            'fk_reconciliation_results_run_id_reconciliation_runs', type_='foreignkey'
        )
        batch_op.drop_index('ix_reconciliation_results_is_current')
        batch_op.drop_index('ix_reconciliation_results_run_id')
        batch_op.drop_column('is_current')
        batch_op.drop_column('run_id')

    op.drop_index('ix_reconciliation_runs_is_current', table_name='reconciliation_runs')
    op.drop_index('ix_reconciliation_runs_triggered_by_user_id', table_name='reconciliation_runs')
    op.drop_table('reconciliation_runs')
