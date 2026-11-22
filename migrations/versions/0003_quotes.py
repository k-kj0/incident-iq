"""quotes: uploaded quote documents with extraction and verification results"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quote_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("carrier", sa.String(256), nullable=True),
        sa.Column("extractor", sa.String(16), nullable=False),
        sa.Column("pages", sa.JSON, nullable=False),
        sa.Column("extraction", sa.JSON, nullable=False),
        sa.Column("verification", sa.JSON, nullable=False),
        sa.Column("rejected", sa.JSON, nullable=False),
        sa.Column("failed_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quote_documents_tenant_id", "quote_documents", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("quote_documents")
