"""Add the optional display name to analyses

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("name", sa.String(40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.drop_column("name")
