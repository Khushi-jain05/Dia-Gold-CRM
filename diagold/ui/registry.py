"""Maps a menu key to the widget that should open for it."""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QWidget

from diagold.menu import MENU_BY_KEY
from diagold.services.auth import CurrentUser
from diagold.ui.crud import CrudWidget
from diagold.ui import inventory as inventory_ui
from diagold.ui.manufacturing import ItemSearchWidget, MfgTransferWidget, ProcessVoucherWidget
from diagold.ui.permissions import PermissionMatrixWidget
from diagold.ui.placeholder import PlaceholderWidget
from diagold.ui.production import (
    JobBagWidget,
    JobHistoryWidget,
    JobMappingWidget,
    OpeningStockWidget,
    OptionsWidget,
    PrintingOptionsWidget,
    StoneReturnWidget,
)
from diagold.ui.reports import ReportsHub, ReportWidget, build_specs
from diagold.ui.specs import SPECS

# Menu keys that get a real screen but not via a plain CrudSpec.
_CUSTOM: dict[str, Callable[[CurrentUser], QWidget]] = {
    "master.user_right": lambda user: PermissionMatrixWidget(user),
    "production_planning.job_mapping": lambda user: JobMappingWidget(user),
    "production_planning.job_card_bag": lambda user: JobBagWidget(user),
    "production_planning.job_history": lambda user: JobHistoryWidget(user),
    "production_planning.printing_options": lambda user: PrintingOptionsWidget(user),
    "production_planning.inv_return": lambda user: StoneReturnWidget(user),
    "production_planning.opening_stone": lambda user: OpeningStockWidget(user),
    "production_planning.day_book": lambda user: ReportsHub(user, first="order_day_book"),
    "production_planning.reports": lambda user: ReportsHub(user),
    "tools.option": lambda user: OptionsWidget(user),
    "manufacturing.mfg_transfer": lambda user: MfgTransferWidget(user),
    "manufacturing.item_search": lambda user: ItemSearchWidget(user),
    "manufacturing.issue": lambda user: ProcessVoucherWidget("issue", user),
    "manufacturing.received": lambda user: ProcessVoucherWidget("receive", user),
    "manufacturing.issue_day_book":
        lambda user: ReportWidget(build_specs()["issue_day_book"], user),
    "manufacturing.received_day_book":
        lambda user: ReportWidget(build_specs()["received_day_book"], user),
    "manufacturing.pending_mfg_transfer":
        lambda user: ReportWidget(build_specs()["pending_mfg_transfer"], user),
    "manufacturing.mfg_transfer_day_book":
        lambda user: ReportWidget(build_specs()["mfg_transfer_day_book"], user),
    "manufacturing.reports": lambda user: ReportsHub(user, first="pending_mfg_transfer"),
    "inventory.reports": lambda user: ReportsHub(user, first="metal_analysis"),
}

# Screens reached from a button rather than the workbook's menu - the legacy
# "Item Search" link sits at the top right of every screen.
EXTRA_SCREENS: dict[str, str] = {"manufacturing.item_search": "Item Search",
                                  **inventory_ui.sub_labels()}
# Menu items that open a submenu rather than a screen (Inventory ▸ Metal ▸ …).
SUBMENUS = {parent: [(inventory_ui.sub_key(parent, k), label) for k, label in items]
            for parent, items in inventory_ui.SUBMENUS.items()}


def _group_label(menu_key: str) -> str:
    group = MENU_BY_KEY.get(menu_key.split(".", 1)[0])
    return group.label if group else menu_key

def _item_label(menu_key: str) -> str:
    if menu_key in EXTRA_SCREENS:
        return EXTRA_SCREENS[menu_key]
    group = MENU_BY_KEY.get(menu_key.split(".", 1)[0])
    if group:
        for item in group.items:
            if item.key == menu_key:
                return item.label
    return menu_key


def build_widget(menu_key: str, user: CurrentUser) -> QWidget:
    if menu_key in _CUSTOM:
        return _CUSTOM[menu_key](user)
    if menu_key.rsplit(".", 1)[0] in SUBMENUS:
        return inventory_ui.build_screen(menu_key, user)

    spec = SPECS.get(menu_key)
    if spec is not None:
        return CrudWidget(
            spec,
            can_edit=user.can_edit(menu_key),
            rights=user.rights,
        )

    return PlaceholderWidget(_item_label(menu_key), _group_label(menu_key))


def has_real_screen(menu_key: str) -> bool:
    if menu_key.rsplit(".", 1)[0] in SUBMENUS:
        return menu_key.rsplit(".", 1)[1] not in inventory_ui.PENDING_EXPLANATION
    return menu_key in _CUSTOM or menu_key in SPECS or menu_key in SUBMENUS
