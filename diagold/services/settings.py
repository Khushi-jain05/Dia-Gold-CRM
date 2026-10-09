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
    Setting("Others", "opt.subcontract_costing", "Sub-Contract Costing Enable", "bool", "0",
            "Sub-contract costing (not used yet - to confirm)"),
    Setting("Inventory", "inventory.negative_stock", "When a location would go below zero",
            "choice", "warn", "Warn then allow / block the save / allow silently",
            (("warn", "Warn, then allow"), ("block", "Block the save"),
             ("allow", "Allow silently"))),
    Setting("Others", "opt.multi_currency", "Allow Multi-Currency", "bool", "1",
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
    Setting("Others", "opt.printer_name", "Printer Name", "text", "\\\\rohit\\ZD4212",
            "Printer for barcode / RFID tags (e.g. \\\\rohit\\ZD4212) - Tag Print picks it"),
)


def _legacy(section: str, label: str, kind: str, default: str, desc: str,
            choices: tuple[tuple[str, str], ...] = (), used: bool | str = False) -> Setting:
    """A row of the client's own Tools > Option (screenshots of 9 Oct), with
    the client's value. Rows the app does not act on yet say so."""
    import re as _re
    key = "legacy." + _re.sub(r"[^a-z0-9]+", "_", f"{section} {label}".lower()).strip("_")
    tail = {True: "", False: " (as in the old system; not used yet)",
            "fixed": " (the app always works this way; the switch is not used yet)"}[used]
    return Setting(section, key, label, kind, default, desc + tail, choices)


B = "bool"
LEGACY_SETTINGS: tuple[Setting, ...] = (
    _legacy("Item SKU", "SKU Currency", "text", "Rs",
            "This Currency is Use For Costing in SKU Master or Design Master"),
    _legacy("Item SKU", "Default Price Type", "text", "0",
            "This Price Type Will Be Show in SKU Master Or Design Master"),
    _legacy("Item SKU", "Manual Net Wt Entry", B, "0", "Net Wt Entry Calculation By Auto Or Manual"),
    _legacy("Item SKU", "Allow Stone Breakage %", B, "1", "Define Allow Stone Breakage % in Sku Master"),
    _legacy("Item SKU", "Default Metal Loss %", "text", "0", "Set Default Metal Loss %"),
    _legacy("Item SKU", "Default Avg Loss %", "text", "0", "Set Default Avg Loss %"),
    _legacy("Item SKU", "Default Stone Breakage %", "text", "0", "Set Default Stone Breakage %"),
    _legacy("Item SKU", "Manual G-Wt and N-Wt", B, "0", "Manual G-Wt and N-Wt"),
    _legacy("Purchase", "Ready Stock Purc Use Overheads %", B, "0",
            "Ready Stock Purc can be define Overheads %"),
    _legacy("Purchase", "Add Discount Column in Metal Purchase", B, "0",
            "Add Discount Column in Metal Purchase"),
    _legacy("Purchase", "Add Discount Column in Stone Purchase", B, "0",
            "Add Discount Column in Stone Purchase"),
    _legacy("Purchase", "Lock Re-Purchase of same SKU", B, "0", "True : Lock Re-Purchase of same SKU"),
    _legacy("Purchase", "UnLock Purchase of Readystock", B, "0",
            "True : UnLock Purchase of Readystock if Locked"),
    _legacy("Production Planning", "Starting Job No", "text", "25001",
            "Define Starting Job Number - the first job number when no job exists yet",
            used=True),
    _legacy("Production Planning", "Print Mould Image on Job sheet", B, "0",
            "Job Sheet Mould Images Print or Not"),
    _legacy("Production Planning", "Use X Check Function", B, "0", "Inventory X Check Enable or Disable"),
    _legacy("Production Planning", "Print Order Information on Job Sheet", B, "1",
            "Job Sheet Order Information Print or Not"),
    _legacy("Production Planning", "Set Job Mapping Manual", B, "1", "Set Job Mapping Default Value"),
    _legacy("Production Planning", "Print SType in Stone Catalouge", B, "0",
            "In-House --> Stone Catalouge Print SType"),
    _legacy("Manufacturing", "Mfg Loss % Calculation Method", "choice", "2",
            "0 : On Issue Wt  1 : On Use Wt  2 : On Return Wt. The loss allowance here is worked as "
            "set in 'Loss allowance worked on' above (5 Oct verified on issued weight) - asked",
            (("0", "0 : On Issue Wt"), ("1", "1 : On Use Wt"), ("2", "2 : On Return Wt"))),
    _legacy("Manufacturing", "Stone Entry At MFG Return", B, "1",
            "Stone Entry at the time of Setting Return", used="fixed"),
    _legacy("Manufacturing", "Use Outside Casting", B, "1", "Provision to outside casting/waxing"),
    _legacy("Manufacturing", "Print Order Dtls", B, "0", "Print Order Detail in Iss/Rtn Mfg Vouchers"),
    _legacy("Manufacturing", "Print Image", "choice", "1",
            "Print Picture in Iss/Rtn Mfg Vouchers",
            (("0", "0 : None"), ("1", "1 : Sku Image"), ("2", "2 : Process Image"))),
    _legacy("Manufacturing", "Worker Wise Sett Price", B, "0", "Define Worker Wise Setting Price in "
            "Setting Master"),
    _legacy("Manufacturing", "Waxing Issue Wt/Pcs", B, "0",
            "False : Calculate by Specific Gravity; True : Comes Metalwt From Mould"),
    _legacy("Manufacturing", "MFG Return Voucher Print With allow Dtls", B, "0",
            "False : Do not print allow Dtls; True : Print Allow Loss Wt, Allow % and allow"),
    _legacy("Manufacturing", "MFG Return Save Negative Loss Wt", B, "1",
            "False : Do not Save Negative Loss Wt; True : Save Negative Loss Wt", used="fixed"),
    _legacy("Manufacturing", "MFG Return Save Negative Gross Wt and Net Wt", B, "1",
            "False : Do not Save Negative Gross Wt and Net Wt; True : Save Negative"),
    _legacy("Manufacturing", "Add Allow Loss Value in WIP Costing", B, "0",
            "True : Add Allow Loss Value in WIP Costing"),
    _legacy("Costing", "Metal Price Comes From Metal Master", B, "1",
            "At the time of Qc to Ready Stock Metal Price Comes From Metal Rate", used="fixed"),
    _legacy("Costing", "Stone Price comes From SSKU Master (Sales Price)", B, "1",
            "At the time of Qc to Ready Stock Stone Price Comes From Stone SKU (sale price)",
            used="fixed"),
    _legacy("Costing", "Labour comes From SKU Master", B, "1",
            "At the time of Qc to Ready Stock Labour Comes From SKU Master"),
    _legacy("Costing", "Metal Price In Fine", B, "0", "Use Fine Wt To Calculate Metal Amount"),
    _legacy("Costing", "Metal Loss Add in Metal Amount", B, "1", "Add Loss % in Metal Amount"),
    _legacy("Costing", "Qc To Ready Trans Def Currency", "choice", "1", "0 : Base Curr  1 : SKU Curr",
            (("0", "0 : Base Curr"), ("1", "1 : SKU Curr"))),
    _legacy("Costing", "Qc To Ready Trans Add Stone Break Wt", B, "0",
            "Qc To Ready Trans Add Stone Break Wt"),
    _legacy("Costing", "Costing", B, "1", "Costing"),
    _legacy("Costing", "Breakage % In Qc To Ready Stock", B, "1", "Breakage % In Qc To Ready Stock"),
    _legacy("Costing", "Stone Price comes From SSKU Master (Cost Price)", B, "1",
            "At the time of Qc to Ready Stock Stone Price Comes From Stone SKU (cost price)"),
    _legacy("Costing", "Cut of Date For Mould", "text", "30/04/2014", "Cut of Date For Mould (dd/MM/yyyy)"),
    _legacy("Costing", "Cut of Date For Stone", "text", "30/04/2014", "Cut of Date For Stone (dd/MM/yyyy)"),
    _legacy("Inventory", "Prompt Tag Printing When Stock Entry", B, "1",
            "Ready Stock Entry, Print Tag After Save (the Tag List opens after an MFG transfer)",
            used=True),
    _legacy("Inventory", "Worker Metal Ledger Adjust by Actual Loss", B, "0",
            "True : Worker Metal Ledger Adjust by Actual Loss; False : Adjust by allowance"),
    _legacy("Inventory", "Load Stone is Selected", B, "1", "At the Time of load Stone comes as Selected"),
    _legacy("Inventory", "Daily Breakup Closing Value", B, "0",
            "True : Show Day Wise Closing; False : Show Record Wise Closing"),
    _legacy("Inventory", "Negative Stock Control", B, "0",
            "True : Can Not Issue When stock is not Available; False : You Can (see 'When a location "
            "would go below zero' above)"),
    _legacy("Inventory", "Metal Issue/Receipt with Tunch", B, "0", "True : Show Tunch Column"),
    _legacy("Inventory", "Metal Issue/Receipt Iss Tunch", B, "0",
            "True : Iss Tunch wt and in worker a/c add actual wt."),
    _legacy("Inventory", "Issue on JobCard Auto Fill", B, "0", "True : Issue on JobCard Auto Fill Req. Inv."),
    _legacy("Sales", "Lock Costing on Sale", B, "0", "Sales Costing is Disable"),
    _legacy("Sales", "ReCosting On Sale", B, "1", "In Sales Get Price From Stock Only"),
    _legacy("Sales", "Discount in Sale", B, "0", "Add Discount column in Sale"),
    _legacy("Sales", "Use Tag Price In Sale", B, "1", "Sales From Tag Price"),
    _legacy("Sales", "Weight Wise Sale", B, "0", "Weight Wise Sale"),
    _legacy("Sales", "Manual Sale", B, "0", "At the time of sale enter manualy"),
    _legacy("Sales", "Use Markup in Sale", B, "0", "True: Markup  False: Margin"),
    _legacy("Sales", "Sale By Sales Closing Stock", B, "0", "Sale By Sales Closing Stock"),
    _legacy("Sales", "Mt Price Comes From Order", B, "1", "Metal Price Comes From Order"),
    _legacy("Sales", "Loss % Comes From Order", B, "1", "Loss % Comes From Order"),
    _legacy("Sales", "Stone Price Comes From SSKU Master", B, "0", "Stone Price Comes From SSKU Master"),
    _legacy("Sales", "Labour Comes From SKU Master", B, "1", "Labour From SKU Master In Sales And Approvals"),
    _legacy("Sales", "Add Loss % in Fine Metal", B, "0", "Add Loss % in Fine Metal"),
    _legacy("Sales", "Warning when same SKU Send again as Approval", B, "0",
            "Same SKU Send again as Approval which was returned as App Return"),
    _legacy("Sales", "Approval Margin %", "text", "0", "Set Approval Margin %"),
    _legacy("Sales", "CALC For Cost", "text", "0", "CALC For Cost"),
    _legacy("Sales", "CALC For MRP", "text", "0", "CALC For MRP"),
    _legacy("Sales", "CALC For Export", "text", "0", "CALC For Export"),
    _legacy("Sales", "Hide Price Column", B, "0", "Hide Price Column"),
    _legacy("Sales", "Show Desc Column", B, "0", "Show SKU Description Column"),
)
SETTINGS_TREE = SETTINGS_TREE + LEGACY_SETTINGS
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
