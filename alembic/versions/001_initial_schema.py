"""initial schema (create_all compatible)

Revision ID: 001
Revises:
Create Date: 2026-11-19

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from autoexectool.storage.models import Base

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
