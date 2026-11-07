"""Reserve idempotency keys in the same transaction as ticket creation."""
from alembic import op
import sqlalchemy as sa

revision = '0009_ticket_idempotency'
down_revision = '0008_ticket_review_lock'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ticket_create_requests',
        sa.Column('actor_scope', sa.String(100), primary_key=True),
        sa.Column('key_hash', sa.String(64), primary_key=True),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table('ticket_create_requests')
