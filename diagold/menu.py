"""The application menu structure.

This mirrors ``HEADING OR SUB HEADING.xlsx`` exactly - 14 main headings, each
with the sub-headings the client listed. ``key`` values are stable identifiers
used to look up the screen to open (see ``diagold/ui/registry.py``) and to
check User Rights permissions.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str


@dataclass(frozen=True)
class MenuGroup:
    key: str
    label: str
    items: list[MenuItem] = field(default_factory=list)


def _g(key: str, label: str, items: list[tuple[str, str]]) -> MenuGroup:
    return MenuGroup(key, label, [MenuItem(f"{key}.{ik}", il) for ik, il in items])


MENU: list[MenuGroup] = [
    _g("master", "Master", [
        ("company", "Company"),
        ("user_right", "User Right"),
        ("currency", "Currency"),
        ("account", "Account"),
        ("metal", "Metal"),
        ("findings", "Findings"),
        ("parts_mould", "Parts / Mould"),
        ("sku_info", "SKU Info"),
        ("stone_info", "Stone Info"),
        ("manufacturing", "Manufacturing"),
        ("other", "Other"),
    ]),
    _g("sku", "SKU", [
        ("stone_packet", "Stone SKU / Packet No"),
        ("product_sku_master", "Product SKU Master"),
        ("sku_view", "SKU View"),
    ]),
    _g("quotation", "Quotation", [
        ("quotation", "Quotation"),
        ("day_book", "Day Book"),
        ("setting", "Setting"),
    ]),
    _g("mrp", "MRP", [
        ("mrp", "MRP"),
        ("purchase_order", "Purchase Order"),
    ]),
    _g("production_planning", "Production Planning", [
        ("wip_job_card", "WIP Job Card"),
        ("job_card", "Job Card"),
        ("job_mapping", "Job Mapping"),
        ("in_house", "In-House"),
        ("job_card_bag", "Job Card Bag"),
        ("job_history", "Job History"),
        ("printing_options", "Printing Options"),
        ("inv_return", "Inv Return"),
        ("day_book", "Day Book"),
        ("reports", "Reports"),
    ]),
    _g("manufacturing", "Manufacturing", [
        ("waxing", "Waxing"),
        ("issue", "Issue"),
        ("received", "Received"),
        ("repair_issue", "Repair Issue"),
        ("extra_issue", "Extra Issue"),
        ("issue_day_book", "Issue Day Book"),
        ("received_day_book", "Received Day Book"),
        ("job_costing", "Job Costing"),
        ("mfg_transfer", "MFG Transfer"),
        ("pending_mfg_transfer", "Pending for MFG Transfer"),
        ("mfg_transfer_day_book", "MFG Transfer Day Book"),
        ("stamping_engraving", "Stamping / Engraving List"),
        ("reports", "Reports"),
    ]),
    _g("purchase", "Purchase", [
        ("opening_stock", "Opening Stock"),
        ("metal", "Metal"),
        ("metal_debit_note", "Debit Note (Metal)"),
        ("parts_moulds", "Parts / Moulds"),
        ("stones", "Stones"),
        ("stone_debit_note", "Debit Note (Stone)"),
        ("ready_items", "Ready Items"),
        ("ready_item_return", "Ready Item Return"),
        ("approval", "Approval"),
        ("approval_return", "Approval Return"),
        ("settings", "Settings"),
        ("stone_approval", "Stone Approval"),
        ("stone_app_return", "Stone App Return"),
        ("reports", "Reports"),
    ]),
    _g("inventory", "Inventory", [
        ("metal", "Metal"),
        ("stone", "Stone"),
        ("parts_mould", "Parts / Mould"),
        ("physical_stock", "Physical Stock"),
        ("stock_transfer", "Stock Transfer"),
        ("ready_item_receipt", "Ready Item Receipt"),
        ("reports", "Reports"),
    ]),
    _g("sale", "Sale", [
        ("ready_stock", "Ready Stock"),
        ("metal", "Metal"),
        ("stone", "Stone"),
        ("approval", "Approval"),
    ]),
    _g("account", "Account", [
        ("groups", "Groups"),
        ("voucher_entry", "Voucher Entry"),
        ("outstandings", "Outstandings"),
        ("day_book", "Day Book"),
        ("ledger", "Ledger"),
        ("trial_balance", "Trial Balance"),
        ("more", "More"),
    ]),
    _g("tools", "Tools", [
        ("option", "Option"),
        ("backup", "Backup"),
        ("read_barcode", "Read Barcode"),
        ("stock_reconciliation", "Stock Reconciliation"),
        ("client_stone_price", "Client Wise Stone Price"),
        ("client_labour_price", "Client Wise Labour Price"),
        ("client_setting_price", "Client Wise Setting Price"),
        ("register_complaint", "Register a Complaint"),
        ("gatepass", "Gatepass"),
        ("advance_options", "Advance Options"),
        ("change_password", "Change Password"),
    ]),
    _g("reports", "Reports", [
        ("all_reports", "All Reports"),
    ]),
    _g("window", "Window", [
        ("cascade", "Cascade"),
        ("tile", "Tile"),
        ("close_all", "Close All"),
    ]),
]

MENU_BY_KEY: dict[str, MenuGroup] = {g.key: g for g in MENU}

ALL_ITEM_KEYS: list[str] = [item.key for g in MENU for item in g.items]
