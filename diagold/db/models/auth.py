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

    mobile_number: Mapped[str] = mapped_column(String(32), default="")  # used for SMS

    # Per-user switches carried over from the legacy User Rights screen.
    hide_costing_in_item_search: Mapped[bool] = mapped_column(Boolean, default=False)
    disable_column_width: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_mfg_labour_allow_loss: Mapped[bool] = mapped_column(Boolean, default=False)
    hide_sale_in_item_search: Mapped[bool] = mapped_column(Boolean, default=False)
    disable_snap: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_sku_copy: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_loss_exceed_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_item_search: Mapped[bool] = mapped_column(Boolean, default=False)
    stock_transfer_lock: Mapped[bool] = mapped_column(Boolean, default=False)

    # Back-dated voucher controls, also per user.
    days_allowed_back_dated_voucher: Mapped[int] = mapped_column(default=0)
    apply_cutoff_date_back_dated_voucher: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    role: Mapped[Role | None] = relationship(back_populates="users")
    permissions: Mapped[list["UserPermission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    # Order matters for the User Rights screen and the export.
    PER_USER_FLAGS: tuple[tuple[str, str], ...] = (
        ("hide_costing_in_item_search", "Hide Costing in Item Search"),
        ("disable_column_width", "Disable Column Width"),
        ("lock_mfg_labour_allow_loss", "Lock Mfg Labour & Allow Loss"),
        ("hide_sale_in_item_search", "Hide Sale in Item Search"),
        ("disable_snap", "Disable Snap"),
        ("allow_sku_copy", "Allow SKU Copy"),
        ("actual_loss_exceed_lock", "Actual Loss Exceed Lock"),
        ("lock_item_search", "Lock Item Search"),
        ("stock_transfer_lock", "Stock Transfer Lock"),
    )

    def set_password(self, raw: str) -> None:
        self.password_hash = hash_password(raw)

    def check_password(self, raw: str) -> bool:
        return verify_password(raw, self.password_hash)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.username


class UserPermission(Base, PKMixin):
    """One (user, master) grant with the five legacy action flags.

    Rights are per USER x per MASTER x per ACTION - not per role. Absence of a
    row means no access at all (deny by default), so a newly created user can
    see nothing until rights are granted.
    """

    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "master_key", name="uq_user_master"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    master_key: Mapped[str] = mapped_column(String(64))

    can_display: Mapped[bool] = mapped_column(Boolean, default=False)
    can_add: Mapped[bool] = mapped_column(Boolean, default=False)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    can_print: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="permissions")

    # The five actions, in the order the legacy screen shows them.
    ACTIONS: tuple[tuple[str, str], ...] = (
        ("can_display", "Display"),
        ("can_add", "Add New"),
        ("can_edit", "Edit"),
        ("can_delete", "Delete"),
        ("can_print", "Print"),
    )
