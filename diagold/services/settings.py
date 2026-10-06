"""Key/value settings, and the menu flags built on them (T-07).

The client said only two Production-Planning items are used day to day and
the rest should be dropped - but has not yet named the two (C-01). So every
item is a switch in configuration: the ones demonstrated and explained on the
call are on by default, the rest are off, and when the client answers the
menu is trimmed here, not in code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    # 2 Oct D3: Purchase holds Opening Stock, Ready Items (+ Return), Metal and
    # Stones; the rest is pending the client's word (C-03 / Q5).
    "purchase.metal_debit_note": "Purchase ▸ Debit Note (Metal) - until confirmed (2 Oct C-03)",
    "purchase.stone_debit_note": "Purchase ▸ Debit Note (Stone) - until confirmed (2 Oct C-03)",
    "purchase.parts_moulds": "Purchase ▸ Parts / Moulds - until confirmed (2 Oct C-03)",
    "purchase.settings": "Purchase ▸ Settings - not discussed (2 Oct)",
    # Manufacturing items the PDF keeps (2 Oct §4.2) but nobody has explained
    # yet (Extra Issue: 28 Sept Q8; Stamping / Engraving and Repair Issue:
    # 28 Sept C-04) - off until they are, so the menu shows only what works.
    "manufacturing.repair_issue": "Manufacturing ▸ Repair Issue - to be explained (28 Sept C-04)",
    "manufacturing.extra_issue": "Manufacturing ▸ Extra Issue - to be explained (28 Sept Q8)",
    "manufacturing.stamping_engraving": "Manufacturing ▸ Stamping / Engraving List - to be "
                                        "explained (28 Sept C-04)",
    # Inventory items the 2 Oct recording lost - to be re-explained (C-05).
    "inventory.parts_mould": "Inventory ▸ Parts / Mould - not discussed (2 Oct)",
    "inventory.physical_stock": "Inventory ▸ Physical Stock - to be re-explained (2 Oct C-05)",
    "inventory.ready_item_receipt": "Inventory ▸ Ready Item Receipt - to be re-explained (2 Oct C-05)",
    # Screens open as tabs here, so the legacy window arrangement has nothing to do.
    "window.cascade": "Window ▸ Cascade - screens open as tabs, nothing to arrange",
    "window.tile": "Window ▸ Tile - screens open as tabs, nothing to arrange",
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
    # 5 Oct T-05 - legacy Option "Client wise price chart applicable" (False).
    "sale.client_chart": ("Client wise price chart applicable - a sale ticks \"Prices From "
                          "Client Chart\" when the client is on a chart", False),
    "ui.confirm_save": ("Ask \"Save? Yes / No\" before every save", True),
    "loss.charge_all": ("Worker ledger: karigar is charged for ALL loss, not only the excess "
                        "over the allowed % (to confirm - 28 Sept Q3)", False),
}
_MENU_PREFIX = "menu."


def get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.scalar(select(AppSetting).where(AppSetting.key == key))
    return row.value if row is not None else default


def set_setting(session: Session, key: str, value: str, user: str = "") -> None:
    """Store a value; who changed it and when is kept when it changes."""
    from datetime import datetime
    row = session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        session.add(AppSetting(key=key, value=value, changed_by=user,
                               changed_at=datetime.now()))
    elif row.value != value:
        row.value = value
        row.changed_by, row.changed_at = user, datetime.now()
    session.flush()


def changed_info(session: Session, key: str) -> tuple[str, Any]:
    row = session.scalar(select(AppSetting).where(AppSetting.key == key))
    return (row.changed_by, row.changed_at) if row is not None else ("", None)


# --------------------------------------------------------------------------
# Tools > Option settings tree (5 Oct §4.6, T-11): the legacy sections with
# Particulars / Value / Description; values are typed (bool / text / choice).
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Setting:
    section: str
    key: str
    label: str
    kind: str                  # bool / text / choice
    default: str
    description: str
    choices: tuple[tuple[str, str], ...] = ()


SECTIONS: tuple[str, ...] = ("Item SKU", "Order & Quotation", "Purchase", "Production Planning",
                             "Manufacturing", "Costing", "Inventory", "Accounts", "Sales",
                             "Others")
SETTINGS_TREE: tuple[Setting, ...] = (
    Setting("Order & Quotation", "opt.cref_applicable", "C-ref Applicable", "bool", "0",
            "Client reference used in quotation / order or not (the order print shows C-Ref "
            "only when on)"),
    Setting("Order & Quotation", "opt.add_sku_description", "Add SKU Description", "bool", "1",
            "Add the SKU description at order entry and on the order print"),
    Setting("Order & Quotation", "opt.show_price_in_print", "Show/Hide Price in PrintOut",
            "bool", "1", "Price on the order confirmation print"),
    Setting("Order & Quotation", "flag.sale.client_chart", "Client wise price chart applicable",
            "bool", "0", "Use the client's price chart (sale / approval tick Prices From "
                         "Client Chart for a client on a chart)"),
    Setting("Production Planning", "flag.pp.return_other_classes",
            "Return to Inventory: Metal / Mould / Finding classes", "bool", "0",
            "Show the other classes on Rtn To Inv"),
    Setting("Manufacturing", "loss.allowance_basis", "Loss allowance worked on", "choice",
            "issued", "Allowance % x the weight issued (5 Oct) or received back",
            (("issued", "Weight issued"), ("received", "Weight received back"))),
    Setting("Manufacturing", "flag.loss.charge_all", "Charge the karigar for all loss", "bool",
            "0", "On = every gram lost is owed, not only the excess over the allowed %"),
    Setting("Costing", "pricing.tag_display", "Tag price on the tag", "choice", "thousands",
            "How the tag prints the price (3,05,330.12 -> 305)",
            (("thousands", "In thousands (305)"), ("full", "Full price"))),
    Setting("Costing", "opt.subcontract_costing", "Sub-Contract Costing Enable", "bool", "0",
            "Sub-contract costing (not used yet - to confirm)"),
    Setting("Inventory", "inventory.negative_stock", "When a location would go below zero",
            "choice", "warn", "Warn then allow / block the save / allow silently",
            (("warn", "Warn, then allow"), ("block", "Block the save"),
             ("allow", "Allow silently"))),
    Setting("Sales", "opt.multi_currency", "Allow Multi-Currency", "bool", "1",
            "Currency choice on the sale voucher"),
    Setting("Others", "flag.ui.confirm_save", "Ask \"Save? Yes / No\" before every save",
            "bool", "1", "Legacy asks before every save"),
    Setting("Others", "opt.backup_path", "Backup Path", "text", "",
            "Folder Tools > Backup writes to (empty = DiaGoldBackups in your home folder)"),
    Setting("Others", "opt.prompt_metal_prices", "Prompt Daily Metal Prices", "bool", "0",
            "At login, open Daily Metal Rate when today's rate is not entered"),
    Setting("Others", "opt.show_export_window", "Show Export Window", "bool", "1",
            "Show the export window after the client name (legacy; kept for the client)"),
    Setting("Others", "opt.digicat_id", "DIGICAT id", "text", "1202", "DIGICAT membership ID"),
    Setting("Others", "opt.printer_name", "Printer Name", "text", "",
            "Printer for barcode / RFID tags (e.g. \\\\rohit\\ZD4212) - Tag Print picks it"),
)
SETTING_BY_KEY = {st.key: st for st in SETTINGS_TREE}


def opt(key: str, session: Session | None = None) -> str:
    """A settings-tree value (its default when never set)."""
    default = SETTING_BY_KEY[key].default if key in SETTING_BY_KEY else ""
    if session is not None:
        return get_setting(session, key, default)
    with SessionLocal() as s:
        return get_setting(s, key, default)


def opt_on(key: str, session: Session | None = None) -> bool:
    return opt(key, session) == "1"


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
