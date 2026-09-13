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
})
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
    """Is this menu item shown? Only Production-Planning items are switchable
    for now; everything else follows the menu definition."""
    if not menu_key.startswith("production_planning."):
        return True
    default = "1" if menu_key in PP_DEFAULT_VISIBLE else "0"
    if session is not None:
        return get_setting(session, _MENU_PREFIX + menu_key, default) == "1"
    with SessionLocal() as s:
        return get_setting(s, _MENU_PREFIX + menu_key, default) == "1"


def set_menu_visible(session: Session, menu_key: str, visible: bool) -> None:
    set_setting(session, _MENU_PREFIX + menu_key, "1" if visible else "0")
