"""add qrcode to devices

Revision ID: b8e2d4f6a91c
Revises: a3f9c1d27e44
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.core.config import BASE_URL


# revision identifiers, used by Alembic.
revision: str = 'b8e2d4f6a91c'
down_revision: Union[str, Sequence[str], None] = 'a3f9c1d27e44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('devices', sa.Column('qrcode', sa.String(length=255), nullable=True))

    conn = op.get_bind()
    devices_table = sa.table(
        'devices',
        sa.column('id', sa.Integer),
        sa.column('mac_address', sa.String),
        sa.column('qrcode', sa.String),
    )
    for device_id, mac_address in conn.execute(sa.select(devices_table.c.id, devices_table.c.mac_address)):
        conn.execute(
            devices_table.update()
            .where(devices_table.c.id == device_id)
            .values(qrcode=f"{BASE_URL}/qrcode/{mac_address}")
        )

    op.alter_column('devices', 'qrcode', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('devices', 'qrcode')
