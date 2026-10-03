"""Key/value settings, and the menu flags built on them (T-07).

The client said only two Production-Planning items are used day to day and
the rest should be dropped - but has not yet named the two (C-01). So every
item is a switch in configuration: the ones demonstrated and explained on the
call are on by default, the rest are off, and when the client answers the
menu is trimmed here, not in code.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import AppSetting
from diagold.db.session import SessionLocal

# Production-Planning items shown until the client names the two that
# survive. Demonstrated and explained: Job Mapping, Job Card Bag, Job History,
# Printing Options, Inv Return - plus Order and Stone Issue, which feed them.
# Hidden until confirmed: WIP Job Card, Job Card, In-House, Day Book, Reports.
PP_DEFAULT_VISIBLE: frozenset[str] = frozenset({
    "production_planning.order",
    "production_planning.stone_issue",
    "production_planning.job_mapping",
    "production_planning.job_card_bag",
    "production_planning.job_history",
    "production_planning.printing_options",
    "production_planning.inv_return",
    # 18 Sept: the client walked every report and asked for two of them to
    # replace his Google Sheet, so Reports (and the opening-balance screen
    # they depend on) are on.
    "production_planning.reports",
    "production_planning.opening_stone",
})

# Menu items outside Production Planning that are switched off by default but
# kept in the code, so the client can bring one back from Tools > Option
# (2 Oct Session 3, TR8 - "hidden by configuration, not deleted").
MENU_DEFAULT_HIDDEN: dict[str, str] = {
    "manufacturing.waxing": "Manufacturing ▸ Waxing - \"not of any use\" (2 Oct D2)",
    "purchase.approval": "Purchase ▸ Approval - approvals are on the sale side (2 Oct D3)",
    "purchase.approval_return": "Purchase ▸ Approval Return - sale side only (2 Oct D3)",
    "purchase.stone_approval": "Purchase ▸ Stone Approval - until confirmed (2 Oct C-03)",
    "purchase.stone_app_return": "Purchase ▸ Stone App Return - until confirmed (2 Oct C-03)",
}

# Behaviour switches (Tools > Option). Metal / mould / finding returns are
# "not used, never needed" (18 Sept D1) - off unless the client says otherwise.
FLAGS: dict[str, tuple[str, bool]] = {
    "pp.return_other_classes": ("Return to Inventory: show Metal / Mould / Finding classes", False),
    # 28 Sept Q3: off = the karigar owes only loss beyond the allowed %, as
    # the legacy Worker Ledger shows; on = every gram lost is owed.
    # Negative stock (28 Sept Q6) is a three-way choice, kept as the setting
    # "inventory.negative_stock" = block / warn / allow (default warn).
    # Legacy asks "Save? Yes / No" before every save; staff expect it.
    "ui.confirm_save": ("Ask \"Save? Yes / No\" before every save", True),
    "loss.charge_all": ("Worker ledger: karigar is charged for ALL loss, not only the excess "
                        "over the allowed % (to confirm - 28 Sept Q3)", False),
}
_MENU_PREFIX = "menu."


def get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.scalar(select(AppSetting).where(AppSetting.key == key))
    return row.value if row is not None else default


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    session.flush()


def menu_visible(menu_key: str, session: Session | None = None) -> bool:
    """Is this menu item shown? Production-Planning items and the ones in
    MENU_DEFAULT_HIDDEN are switchable; everything else follows the menu."""
    if menu_key in MENU_DEFAULT_HIDDEN:
        default = "0"
    elif not menu_key.startswith("production_planning."):
        return True
    else:
        default = "1" if menu_key in PP_DEFAULT_VISIBLE else "0"
    if session is not None:
        return get_setting(session, _MENU_PREFIX + menu_key, default) == "1"
    with SessionLocal() as s:
        return get_setting(s, _MENU_PREFIX + menu_key, default) == "1"


def set_menu_visible(session: Session, menu_key: str, visible: bool) -> None:
    set_setting(session, _MENU_PREFIX + menu_key, "1" if visible else "0")


def flag(key: str, default: bool | None = None, session: Session | None = None) -> bool:
    if default is None:
        default = FLAGS.get(key, ("", False))[1]
    d = "1" if default else "0"
    if session is not None:
        return get_setting(session, "flag." + key, d) == "1"
    with SessionLocal() as s:
        return get_setting(s, "flag." + key, d) == "1"


def set_flag(session: Session, key: str, on: bool) -> None:
    set_setting(session, "flag." + key, "1" if on else "0")
