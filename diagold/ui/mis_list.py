"""The legacy Reports ▸ M.I.S. Reports list (9 Oct §4.3) - kept apart so the
report engine can read it without importing the report specs."""
from __future__ import annotations

# The legacy M.I.S. Reports list in its order (9 Oct §4.3): (menu name, spec
# key or None while not built / awaiting the client's ranking C-06).
MIS_LIST: tuple[tuple[str, str | None], ...] = (
    ("Sales Analysis", "sales_analysis"),
    ("Stone Wise Inventory", "stone_wise_inventory"),
    ("Ready Stock Inward List", "ready_stock_inward"),
    ("Stone Setting Analysis", "setting_analysis"),
    ("Stone Daily Touch Report", "stone_daily_touch"),
    ("WIP Repair Items", "wip_repair_items"),
    ("Repair Register", "repair_register"),
    ("Rejection Register", "rejection_register"),
    ("Designer Analysis", None),
    ("Sales Analysis[Item Wise]", "sales_mis"),
    ("Closing Stock As SET", None),
    ("Refining Analysis", "refining_analysis"),
    ("Metal Summary", "metal_summary"),
    ("Stone in Sales Register", "sold_stone"),
    ("Labour in Sales Register", "sold_labour"),
    ("KM Register", "kundan_register"),
    ("Shiping Analysis", "shipping_analysis"),
    ("Shiping Pending", "shipping_pending"),
    ("Day Wise Sales [MetalValue]", "day_wise_sales"),
    ("Approval Out Counts", "approval_out_counts"),
    ("Stock for Merchandising", None),
    ("Range Wise Closing Stock", "range_wise_closing"),
    ("Range Wise Approval Stock", "range_wise_approval"),
    ("DAK Return Register", None),
    ("MFG TR [only Repair]", "mfg_tr_repair"),
    ("MFG TR Stone[only Repair]", "mfg_tr_repair_stones"),
    ("Goods Sold But Not Delivered", "goods_not_delivered"),
    ("FOB Custom Invoice", None),
    ("Sales Profit[Metal]", "sales_profit_metal"),
    ("Stone Summery", "stone_sku_balance"),
    ("Sales [Voucher Wise]", "sales_voucher_wise"),
    ("Ledger Bal", "ledger_bal"),
    ("In-Approval Status", "in_approval_status"),
    ("Sales Return Profit[Metal]", "sales_return_profit_metal"),
)


def mis_keys() -> tuple[str, ...]:
    return ("mis_index",) + tuple(k for _n, k in MIS_LIST if k)
