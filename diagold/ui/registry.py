"""Maps a menu key to the widget that should open for it."""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QWidget

from diagold.menu import MENU_BY_KEY
from diagold.services.auth import CurrentUser
from diagold.ui.crud import CrudWidget
from diagold.ui.permissions import PermissionMatrixWidget
from diagold.ui.placeholder import PlaceholderWidget
from diagold.ui.specs import SPECS

# Menu keys that get a real screen but not via a plain CrudSpec.
_CUSTOM: dict[str, Callable[[CurrentUser], QWidget]] = {
    "master.user_right": lambda user: PermissionMatrixWidget(user),
}


def _group_label(menu_key: str) -> str:
    group = MENU_BY_KEY.get(menu_key.split(".", 1)[0])
    return group.label if group else menu_key

def _item_label(menu_key: str) -> str:
    group = MENU_BY_KEY.get(menu_key.split(".", 1)[0])
    if group:
        for item in group.items:
            if item.key == menu_key:
                return item.label
    return menu_key


def build_widget(menu_key: str, user: CurrentUser) -> QWidget:
    if menu_key in _CUSTOM:
        return _CUSTOM[menu_key](user)

    spec = SPECS.get(menu_key)
    if spec is not None:
        return CrudWidget(spec, can_edit=user.can_edit(menu_key))

    return PlaceholderWidget(_item_label(menu_key), _group_label(menu_key))


def has_real_screen(menu_key: str) -> bool:
    return menu_key in _CUSTOM or menu_key in SPECS
