"""drop the unused Starlink byte counters (usage estimates were removed)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01 05:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('starlink_samples') as batch_op:
        batch_op.drop_column('down_bytes')
        batch_op.drop_column('up_bytes')


def downgrade() -> None:
    with op.batch_alter_table('starlink_samples') as batch_op:
        batch_op.add_column(sa.Column('down_bytes', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('up_bytes', sa.Float(), nullable=False, server_default='0'))
