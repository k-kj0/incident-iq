"""gtm: accounts, raw records, dead letters"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gtm_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("canonical_name", sa.String(256), nullable=False),
        sa.Column("name_key", sa.String(256), nullable=False),
        sa.Column("domain", sa.String(253), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("employee_count", sa.Integer, nullable=True),
        sa.Column("owners", sa.JSON, nullable=False),
        sa.Column("signals", sa.JSON, nullable=False),
        sa.Column("last_touch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "domain", name="uq_gtm_accounts_tenant_domain"),
    )
    op.create_index("ix_gtm_accounts_tenant_id", "gtm_accounts", ["tenant_id"])
    op.create_index("ix_gtm_accounts_name_key", "gtm_accounts", ["name_key"])

    op.create_table(
        "gtm_raw_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("gtm_accounts.id"), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("match_method", sa.String(16), nullable=False),
        sa.Column("match_score", sa.Float, nullable=False),
        sa.Column("needs_review", sa.Boolean, nullable=False),
        sa.Column("review_candidate_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "source", "source_record_id",
                            name="uq_gtm_raw_tenant_source_record"),
    )
    op.create_index("ix_gtm_raw_records_tenant_id", "gtm_raw_records", ["tenant_id"])
    op.create_index("ix_gtm_raw_records_account_id", "gtm_raw_records", ["account_id"])

    op.create_table(
        "gtm_dead_letters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gtm_dead_letters_tenant_id", "gtm_dead_letters", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("gtm_dead_letters")
    op.drop_table("gtm_raw_records")
    op.drop_table("gtm_accounts")
