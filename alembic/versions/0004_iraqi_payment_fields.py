"""add iraqi payment metadata fields

Revision ID: 0004_iraqi_payment_fields
Revises: 0003_learning_quizzes_certificates
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_iraqi_payment_fields"
down_revision: Union[str, None] = "0003_learning_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return index_name in {index.get("name") for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "wallet_transactions", "payment_method"):
        op.add_column("wallet_transactions", sa.Column("payment_method", sa.String(), nullable=True))
    if not _has_column(inspector, "wallet_transactions", "payer_phone"):
        op.add_column("wallet_transactions", sa.Column("payer_phone", sa.String(), nullable=True))
    if not _has_column(inspector, "wallet_transactions", "provider_payload"):
        op.add_column("wallet_transactions", sa.Column("provider_payload", sa.Text(), nullable=True))

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "wallet_transactions", "ix_wallet_transactions_payment_method"):
        op.create_index("ix_wallet_transactions_payment_method", "wallet_transactions", ["payment_method"], unique=False)
    if not _has_index(inspector, "wallet_transactions", "ix_wallet_transactions_payer_phone"):
        op.create_index("ix_wallet_transactions_payer_phone", "wallet_transactions", ["payer_phone"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_index(inspector, "wallet_transactions", "ix_wallet_transactions_payer_phone"):
        op.drop_index("ix_wallet_transactions_payer_phone", table_name="wallet_transactions")
    if _has_index(inspector, "wallet_transactions", "ix_wallet_transactions_payment_method"):
        op.drop_index("ix_wallet_transactions_payment_method", table_name="wallet_transactions")
    if _has_column(inspector, "wallet_transactions", "provider_payload"):
        op.drop_column("wallet_transactions", "provider_payload")
    if _has_column(inspector, "wallet_transactions", "payer_phone"):
        op.drop_column("wallet_transactions", "payer_phone")
    if _has_column(inspector, "wallet_transactions", "payment_method"):
        op.drop_column("wallet_transactions", "payment_method")
