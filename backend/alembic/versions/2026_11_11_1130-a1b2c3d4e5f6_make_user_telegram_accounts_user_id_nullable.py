"""make_user_telegram_accounts_user_id_nullable

Revision ID: a1b2c3d4e5f6
Revises: 5108008f56e9
Create Date: 2026-11-11 11:30:00.000000+00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "5108008f56e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make user_telegram_accounts.user_id nullable to support unlinked accounts."""
    op.alter_column(
        "user_telegram_accounts",
        "user_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    """Revert user_telegram_accounts.user_id to NOT NULL."""
    op.alter_column(
        "user_telegram_accounts",
        "user_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
