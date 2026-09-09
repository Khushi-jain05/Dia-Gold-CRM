"""Authentication and permission helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import User
from diagold.services.rights import RightsSet, load_rights, master_for_menu_key


@dataclass
class CurrentUser:
    """Lightweight session object held by the running app after login."""

    id: int
    username: str
    full_name: str
    is_superuser: bool
    role_name: str | None
    rights: RightsSet = field(default_factory=RightsSet)

    # -- per-master authorisation ---------------------------------------
    def master_for(self, menu_key: str) -> str | None:
        """The rights master a screen belongs to, if it is governed by one."""
        return master_for_menu_key(menu_key)

    def _allows(self, menu_key: str, action: str) -> bool:
        master = master_for_menu_key(menu_key)
        if master is None:
            # Screens outside the master module are not part of the client's
            # rights model yet; they follow the login itself.
            return True
        return self.rights.allows(master, action)

    def can_view(self, menu_key: str) -> bool:
        return self._allows(menu_key, "display")

    def can_add(self, menu_key: str) -> bool:
        return self._allows(menu_key, "add")

    def can_edit(self, menu_key: str) -> bool:
        return self._allows(menu_key, "edit")

    def can_delete(self, menu_key: str) -> bool:
        return self._allows(menu_key, "delete")

    def can_print(self, menu_key: str) -> bool:
        return self._allows(menu_key, "print")


class AuthError(Exception):
    pass


def authenticate(session: Session, username: str, password: str) -> CurrentUser:
    user = session.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active or not user.check_password(password):
        raise AuthError("Invalid username or password.")

    user.last_login = datetime.utcnow()
    session.commit()

    return CurrentUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name or user.username,
        is_superuser=user.is_superuser,
        role_name=user.role.name if user.role else None,
        rights=load_rights(session, user),
    )


def change_password(session: Session, user_id: int, old_pw: str, new_pw: str) -> None:
    user = session.get(User, user_id)
    if user is None or not user.check_password(old_pw):
        raise AuthError("Current password is incorrect.")
    if len(new_pw) < 4:
        raise AuthError("New password must be at least 4 characters.")
    user.set_password(new_pw)
    session.commit()
