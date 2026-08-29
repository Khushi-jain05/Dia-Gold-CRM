"""Authentication and permission helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import Role, RolePermission, User


@dataclass
class CurrentUser:
    """Lightweight session object held by the running app after login."""

    id: int
    username: str
    full_name: str
    is_superuser: bool
    role_name: str | None
    _view_keys: set[str] = field(default_factory=set)
    _edit_keys: set[str] = field(default_factory=set)

    def can_view(self, menu_key: str) -> bool:
        if self.is_superuser:
            return True
        # A grant on the group key implies access to all of its items.
        group = menu_key.split(".", 1)[0]
        return menu_key in self._view_keys or group in self._view_keys

    def can_edit(self, menu_key: str) -> bool:
        if self.is_superuser:
            return True
        group = menu_key.split(".", 1)[0]
        return menu_key in self._edit_keys or group in self._edit_keys


class AuthError(Exception):
    pass


def authenticate(session: Session, username: str, password: str) -> CurrentUser:
    user = session.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active or not user.check_password(password):
        raise AuthError("Invalid username or password.")

    user.last_login = datetime.utcnow()
    session.commit()

    view_keys: set[str] = set()
    edit_keys: set[str] = set()
    if user.role_id is not None:
        perms = session.scalars(
            select(RolePermission).where(RolePermission.role_id == user.role_id)
        ).all()
        for perm in perms:
            if perm.can_view:
                view_keys.add(perm.menu_key)
            if perm.can_edit:
                edit_keys.add(perm.menu_key)

    return CurrentUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name or user.username,
        is_superuser=user.is_superuser,
        role_name=user.role.name if user.role else None,
        _view_keys=view_keys,
        _edit_keys=edit_keys,
    )


def change_password(session: Session, user_id: int, old_pw: str, new_pw: str) -> None:
    user = session.get(User, user_id)
    if user is None or not user.check_password(old_pw):
        raise AuthError("Current password is incorrect.")
    if len(new_pw) < 4:
        raise AuthError("New password must be at least 4 characters.")
    user.set_password(new_pw)
    session.commit()
