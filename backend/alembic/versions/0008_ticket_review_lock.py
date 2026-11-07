"""Track first admin review and lock reporter content edits afterward."""
from alembic import op
import sqlalchemy as sa

revision = "0008_ticket_review_lock"
down_revision = "0007_password_invitations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("reviewed_by_employee_id", sa.Integer(), nullable=True))
    # Historical reads were not recorded. Only backfill proven admin actions.
    op.execute("""
        UPDATE tickets AS ticket
        SET reviewed_at = first_review.changed_at,
            reviewed_by_employee_id = first_review.actor_employee_id
        FROM (
            SELECT DISTINCT ON (ticket_id) ticket_id, changed_at, actor_employee_id
            FROM ticket_status_history WHERE actor_role = 'admin'
            ORDER BY ticket_id, changed_at, id
        ) AS first_review
        WHERE ticket.id = first_review.ticket_id
    """)


def downgrade():
    op.drop_column("tickets", "reviewed_by_employee_id")
    op.drop_column("tickets", "reviewed_at")
