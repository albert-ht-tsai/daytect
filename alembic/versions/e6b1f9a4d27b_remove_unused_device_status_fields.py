"""remove unused device status fields

Revision ID: e6b1f9a4d27b
Revises: c1a7f3e58d22
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6b1f9a4d27b'
down_revision: Union[str, Sequence[str], None] = 'c1a7f3e58d22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('devices', 'device_type')
    op.drop_column('devices', 'bluetooth_status')
    op.drop_column('devices', 'sync_status')
    op.drop_column('devices', 'last_sync_at')
    op.drop_column('devices', 'illustration_key')
    op.drop_column('devices', 'alert_muted_until')
    op.drop_column('devices', 'alert_remind_later_minutes')
    op.drop_column('devices', 'alert_last_triggered_at')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('devices', sa.Column('alert_last_triggered_at', sa.DateTime(), nullable=True))
    op.add_column('devices', sa.Column('alert_remind_later_minutes', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('devices', sa.Column('alert_muted_until', sa.DateTime(), nullable=True))
    op.add_column('devices', sa.Column('illustration_key', sa.String(length=50), nullable=False, server_default='daytect_band_default'))
    op.add_column('devices', sa.Column('last_sync_at', sa.DateTime(), nullable=True))
    op.add_column('devices', sa.Column('sync_status', sa.String(length=20), nullable=False, server_default='not_synced'))
    op.add_column('devices', sa.Column('bluetooth_status', sa.String(length=20), nullable=False, server_default='disconnected'))
    op.add_column('devices', sa.Column('device_type', sa.String(length=50), nullable=False, server_default='wearable'))
