"""Initial schema: owners and analyses

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owners",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("save_by_default", sa.Boolean(), nullable=False),
        sa.Column("share_by_default", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_owners_token_hash", "owners", ["token_hash"], unique=True)

    op.create_table(
        "analyses",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.String(32), sa.ForeignKey("owners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("saved", sa.Boolean(), nullable=False),
        sa.Column("shared", sa.Boolean(), nullable=False),
        sa.Column("r", sa.Integer(), nullable=False),
        sa.Column("g", sa.Integer(), nullable=False),
        sa.Column("b", sa.Integer(), nullable=False),
        sa.Column("hex", sa.String(7), nullable=False),
        sa.Column("lab_l", sa.Float(), nullable=False),
        sa.Column("lab_a", sa.Float(), nullable=False),
        sa.Column("lab_b", sa.Float(), nullable=False),
        sa.Column("lch_c", sa.Float(), nullable=False),
        sa.Column("lch_h", sa.Float(), nullable=False),
        sa.Column("ita", sa.Float(), nullable=False),
        sa.Column("shade_key", sa.String(16), nullable=False),
        sa.Column("shade_label", sa.String(32), nullable=False),
        sa.Column("shade_alternative", sa.String(32), nullable=True),
        sa.Column("undertone_key", sa.String(16), nullable=False),
        sa.Column("undertone_label", sa.String(48), nullable=False),
        sa.Column("undertone_note", sa.String(200), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_label", sa.String(16), nullable=False),
        sa.Column("n_samples", sa.Integer(), nullable=False),
        sa.Column("skin_fraction", sa.Float(), nullable=False),
        sa.Column("region_method", sa.String(24), nullable=False),
        sa.Column("algorithm_version", sa.String(16), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("palette", sa.JSON(), nullable=False),
    )
    op.create_index("ix_analyses_owner_id", "analyses", ["owner_id"])
    op.create_index("ix_analyses_expires_at", "analyses", ["expires_at"])
    op.create_index("ix_analyses_saved", "analyses", ["saved"])
    op.create_index("ix_analyses_shared", "analyses", ["shared"])


def downgrade() -> None:
    op.drop_table("analyses")
    op.drop_table("owners")
