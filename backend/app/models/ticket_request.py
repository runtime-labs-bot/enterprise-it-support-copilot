"""Durable ticket-create reservations, committed with the ticket and history."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TicketCreateRequest(Base):
    __tablename__ = 'ticket_create_requests'
    actor_scope: Mapped[str] = mapped_column(String(100), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
