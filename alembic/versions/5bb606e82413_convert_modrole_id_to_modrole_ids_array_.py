"""convert modrole_id to modrole_ids array, add moduser_ids array

Revision ID: 5bb606e82413
Revises: d4c03104fd60
Create Date: 2026-07-21 22:26:44.930975

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5bb606e82413"
down_revision: Union[str, Sequence[str], None] = "d4c03104fd60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the new array columns as nullable so we can backfill row by row
    #    before locking them down.
    op.add_column(
        "config", sa.Column("modrole_ids", ARRAY(sa.BigInteger()), nullable=True)
    )
    op.add_column(
        "config", sa.Column("moduser_ids", ARRAY(sa.BigInteger()), nullable=True)
    )

    # 2. Backfill: wrap the existing scalar modrole_id into a single-element
    #    array (or an empty array if it was NULL). moduser_ids has no
    #    scalar predecessor, so every row starts empty.
    op.execute(
        """
        UPDATE config
        SET modrole_ids = CASE
                WHEN modrole_id IS NOT NULL THEN ARRAY[modrole_id]
                ELSE ARRAY[]::bigint[]
            END,
            moduser_ids = ARRAY[]::bigint[]
        """
    )

    # 3. Every row now has a value — tighten to NOT NULL with a default
    #    for future inserts.
    op.alter_column(
        "config", "modrole_ids", nullable=False, server_default=sa.text("'{}'")
    )
    op.alter_column(
        "config", "moduser_ids", nullable=False, server_default=sa.text("'{}'")
    )

    # 4. Drop the now-migrated scalar column.
    op.drop_column("config", "modrole_id")


def downgrade() -> None:
    # Recreate the scalar column, taking the first element back out of
    # modrole_ids. NOTE: this is lossy if a guild ever selected more than
    # one role — only the first (Postgres arrays are 1-indexed) survives.
    op.add_column("config", sa.Column("modrole_id", sa.BigInteger(), nullable=True))
    op.execute(
        """
        UPDATE config
        SET modrole_id = modrole_ids[1]
        WHERE array_length(modrole_ids, 1) > 0
        """
    )
    op.drop_column("config", "modrole_ids")
    op.drop_column("config", "moduser_ids")
