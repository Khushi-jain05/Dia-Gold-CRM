"""Per-user, per-master, per-action authorisation.

The client's legacy User Rights screen grants each USER a set of flags on each
MASTER: Display, Add New, Edit, Delete, Print. This module owns that model.

Two rules from the requirements shape everything here:

* **Deny by default.** A master with no explicit grant is not accessible, so a
  newly created user can see nothing until rights are given.
* **Enforce below the UI.** Hiding a button is not enough - :func:`require`
  is called by the data layer, so a caller that bypasses the screen entirely
  is still refused.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import User, UserPermission

# The masters the rights screen lists, in the legacy order. Each maps to the
# menu key of its screen, or None where the screen is not built yet - the
# grant still exists so rights can be configured ahead of the screen landing.
#
# "Findings" is deliberately absent: the client confirmed they do not use it
# (decision D2), so it is neither in the navigation nor in the rights matrix.
MASTERS: tuple[tuple[str, str | None], ...] = (
    ("Company", "master.company"),
    ("User Rights", "master.user_right"),
    ("Currency", "master.currency"),
    ("Account", "master.account"),
    ("Metal", "master.metal"),
    ("Parts/Mould", "master.parts_mould"),
    ("Item", "sku.product_sku_master"),
    ("Family Category", "master.family_category"),
    ("Colour", "master.colour"),
    ("Item Size", None),               # pending Q2
    ("Stone Group", None),             # T-06, pending Q1
    ("Stone", "master.stone_info"),
    ("Shape", None),                   # T-06
    ("Type", None),                    # T-06
    ("Quality", None),                 # T-06
    ("Size", None),                    # T-06
    ("Setting Type", "master.setting_type"),
    ("MFG Process", "master.manufacturing"),
    ("Set Default Process", "master.default_process"),
    ("Labour", "master.labour"),
    ("Location", "master.location"),
    ("Set Margins", "master.set_margins"),
    ("Daily Metal Rates", "master.daily_metal_rate"),
    ("Daily Labour Rates", "master.daily_labour_rate"),
)

MASTER_NAMES: tuple[str, ...] = tuple(name for name, _ in MASTERS)
_KEY_TO_MASTER: dict[str, str] = {key: name for name, key in MASTERS if key}

ACTIONS: tuple[tuple[str, str], ...] = UserPermission.ACTIONS


class PermissionDenied(PermissionError):
    """Raised when a user attempts something their rights do not allow."""


@dataclass
class Perms:
    """The five action flags for one master."""

    display: bool = False
    add: bool = False
    edit: bool = False
    delete: bool = False
    print: bool = False

    def allows(self, action: str) -> bool:
        return bool(getattr(self, action, False))


@dataclass
class RightsSet:
    """Everything the running session needs to authorise a user."""

    is_superuser: bool = False
    by_master: dict[str, Perms] = field(default_factory=dict)

    def perms(self, master: str) -> Perms:
        if self.is_superuser:
            return Perms(True, True, True, True, True)
        return self.by_master.get(master, Perms())  # deny by default

    def allows(self, master: str, action: str) -> bool:
        return self.perms(master).allows(action)


def master_for_menu_key(menu_key: str) -> str | None:
    """The rights master a screen belongs to, or None if it is not governed."""
    return _KEY_TO_MASTER.get(menu_key)


def load_rights(session: Session, user: User) -> RightsSet:
    rows = session.scalars(
        select(UserPermission).where(UserPermission.user_id == user.id)
    ).all()
    return RightsSet(
        is_superuser=bool(user.is_superuser),
        by_master={
            r.master_key: Perms(r.can_display, r.can_add, r.can_edit,
                                r.can_delete, r.can_print)
            for r in rows
        },
    )


def require(rights: RightsSet, master: str | None, action: str) -> None:
    """Raise :class:`PermissionDenied` unless the action is allowed.

    Called from the data layer, so bypassing the UI does not bypass the check.
    A master of ``None`` is one the rights model does not govern.
    """
    if master is None or rights.allows(master, action):
        return
    label = dict(ACTIONS).get(f"can_{action}", action.title())
    raise PermissionDenied(
        f"You do not have '{label}' permission on {master}."
    )


def grant_all(session: Session, user_id: int) -> None:
    """Give a user every right on every master (used for the admin seed)."""
    existing = {
        p.master_key
        for p in session.scalars(
            select(UserPermission).where(UserPermission.user_id == user_id)
        )
    }
    for name in MASTER_NAMES:
        if name in existing:
            continue
        session.add(UserPermission(
            user_id=user_id, master_key=name, can_display=True, can_add=True,
            can_edit=True, can_delete=True, can_print=True,
        ))


def copy_rights(session: Session, from_user_id: int, to_user_id: int) -> int:
    """Replicate one user's whole matrix onto another. Returns rows written.

    The legacy system has a "Make A Copy" button and admins rely on it when
    onboarding staff.
    """
    if from_user_id == to_user_id:
        return 0
    source = session.scalars(
        select(UserPermission).where(UserPermission.user_id == from_user_id)
    ).all()
    for stale in session.scalars(
        select(UserPermission).where(UserPermission.user_id == to_user_id)
    ):
        session.delete(stale)
    session.flush()
    for row in source:
        session.add(UserPermission(
            user_id=to_user_id, master_key=row.master_key,
            can_display=row.can_display, can_add=row.can_add,
            can_edit=row.can_edit, can_delete=row.can_delete,
            can_print=row.can_print,
        ))
    session.flush()
    return len(source)


def export_matrix(session: Session, user_id: int | None = None) -> str:
    """The rights matrix as CSV - one row per user x master."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Username", "Full Name", "Master"] + [a[1] for a in ACTIONS])

    stmt = select(User).order_by(User.username)
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    for user in session.scalars(stmt):
        granted = {p.master_key: p for p in user.permissions}
        for name in MASTER_NAMES:
            p = granted.get(name)
            writer.writerow(
                [user.username, user.full_name, name]
                + [("Yes" if p and getattr(p, attr) else "No") for attr, _ in ACTIONS]
            )
    return out.getvalue()
