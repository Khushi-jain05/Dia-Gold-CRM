"""Audit log for admin corrections (5 Oct §4.13, T-11): every utility that
changes saved data records who, when, what, why, and the before / after."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from diagold.db.models.base import Base, PKMixin


class AuditLog(Base, PKMixin):
    __tablename__ = "audit_log"

    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_name: Mapped[str] = mapped_column(String(80), default="")
    kind: Mapped[str] = mapped_column(String(40), index=True)
    ref: Mapped[str] = mapped_column(String(80), default="")
    reason: Mapped[str] = mapped_column(String(200), default="")
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
