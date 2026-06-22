"""add avatar to devices

Revision ID: a3f9c1d27e44
Revises: 157778a682fe
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c1d27e44'
down_revision: Union[str, Sequence[str], None] = '157778a682fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('devices', sa.Column('avatar', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('devices', 'avatar')
