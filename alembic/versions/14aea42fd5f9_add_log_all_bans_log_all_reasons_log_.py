"""add log_all_bans, log_all_reasons, log_bans_override, log_reasons_override

Revision ID: 14aea42fd5f9
Revises: 5bb606e82413
Create Date: 2026-07-21 22:45:31.251629

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "14aea42fd5f9"
down_revision: Union[str, Sequence[str], None] = "5bb606e82413"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column(
            "log_all_bans", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "config",
        sa.Column(
            "log_all_reasons", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "config",
        sa.Column(
            "log_bans_override",
            sa.String(),
            nullable=False,
            server_default="--no-log",
        ),
    )
    op.add_column(
        "config",
        sa.Column(
            "log_reasons_override",
            sa.String(),
            nullable=False,
            server_default="--no-reason",
        ),
    )


def downgrade() -> None:
    op.drop_column("config", "log_reasons_override")
    op.drop_column("config", "log_bans_override")
    op.drop_column("config", "log_all_reasons")
    op.drop_column("config", "log_all_bans")
