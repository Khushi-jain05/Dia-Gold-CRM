"""WhatsApp messages sent to customers (9 Oct Session 5 A4, T-08 / TR6).

Every message - sent, sandboxed or failed - is one row, so the office can see
what each customer was told, retry a failure and resend on request."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from diagold.db.models.base import Base, PKMixin


class WhatsAppMessage(Base, PKMixin):
    __tablename__ = "whatsapp_messages"

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    ref_kind: Mapped[str] = mapped_column(String(24), default="", index=True)   # rs_sale
    ref_no: Mapped[int | None] = mapped_column(nullable=True, index=True)
    to_number: Mapped[str] = mapped_column(String(20), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(16), default="sandbox")
    # queued / sent / delivered / read / failed / sandbox / skipped
    status: Mapped[str] = mapped_column(String(12), default="queued")
    provider_id: Mapped[str] = mapped_column(String(120), default="")
    error: Mapped[str] = mapped_column(String(300), default="")
    attempts: Mapped[int] = mapped_column(default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    STATUSES = ("queued", "sent", "delivered", "read", "failed", "sandbox", "skipped")
