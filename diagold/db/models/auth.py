"""Authentication & authorisation models - the Master > User Right module.

Password hashing uses PBKDF2-HMAC-SHA256 from the standard library so there is
no third-party crypto dependency.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin

_PBKDF2_ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


class Role(Base, PKMixin, TimestampMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")
    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.name


class RolePermission(Base, PKMixin):
    """A single (role, menu-item) grant. Presence of a row == permission granted."""

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "menu_key", name="uq_role_menu"),)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    menu_key: Mapped[str] = mapped_column(String(120))
    can_view: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=True)

    role: Mapped[Role] = relationship(back_populates="permissions")


class User(Base, PKMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    role: Mapped[Role | None] = relationship(back_populates="users")

    def set_password(self, raw: str) -> None:
        self.password_hash = hash_password(raw)

    def check_password(self, raw: str) -> bool:
        return verify_password(raw, self.password_hash)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.username
