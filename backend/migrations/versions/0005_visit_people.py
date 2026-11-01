"""visits: several people per booking, plus "others coming"

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01 05:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'reservation_people',
        sa.Column('reservation_id', sa.Integer(), sa.ForeignKey('reservations.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    )
    with op.batch_alter_table('reservations') as batch_op:
        batch_op.add_column(sa.Column('others', sa.String(length=200), nullable=True))
    # Existing stays: the person who booked is the one coming.
    op.execute("INSERT INTO reservation_people (reservation_id, user_id) "
               "SELECT id, user_id FROM reservations WHERE kind = 'stay'")


def downgrade() -> None:
    with op.batch_alter_table('reservations') as batch_op:
        batch_op.drop_column('others')
    op.drop_table('reservation_people')
