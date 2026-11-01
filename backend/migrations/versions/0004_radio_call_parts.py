"""radio calls: how many transmissions were joined into each recording

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01 04:10:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('radio_recordings') as batch_op:
        batch_op.add_column(sa.Column('parts', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('radio_recordings') as batch_op:
        batch_op.drop_column('parts')
