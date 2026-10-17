"""M.I.S. Reports (9 Oct Session 5 §4.3-§4.29).

The legacy Reports ▸ M.I.S. Reports list, built on the shared report grid
(5 Oct T-12). Each spec keeps the legacy menu name as its title and the
legacy window title as a subtitle in the note (UX2), so users recognise it.
"""
from __future__ import annotations

from diagold.services import repair as REP
from diagold.ui.reports import Col, ReportSpec, static


def _m(k, l):
    return Col(k, l, "measure", 2, total=True)


def _w(k, l, red=False):
    return Col(k, l, "measure", 3, total=True, red=red)


def _p(k, l):
    return Col(k, l, "measure", 0, total=True)


def _open_job(widget, row) -> None:
    widget.open_job(row)


def specs() -> dict[str, ReportSpec]:
    return {
        # -- repair traceability (T-06) -------------------------------------
        "wip_repair_items": ReportSpec(
            key="wip_repair_items", title="WIP Repair Items",
            columns=static([Col("date", "DATE"), Col("job_no", "NEW JOBNO"), Col("sku", "SKU"),
                            Col("item", "ITEM"), Col("metal", "METAL"),
                            Col("old_stock_no", "OLD STOCK NO"), _w("old_g", "OLD G-WT"),
                            _w("old_n", "OLD N-WT"), Col("ord_no", "ORD NO"),
                            Col("status", "STATUS")]),
            query=lambda s, a, b, **_k: REP.wip_repair_items(s, a, b),
            on_activate=_open_job,
            note="Legacy window: WIP Repair. Repair jobs still on the floor - each new job "
                 "number with the Stock No it was made from (e.g. 09-10-2026: sales returns "
                 "41672 / 44907 / 44593 / 44473 became jobs 29360-29363)."),
        "mfg_tr_repair": ReportSpec(
            key="mfg_tr_repair", title="MFG TR [only Repair]",
            columns=static([Col("vrno", "VRNO"), Col("date", "DATE"), Col("sku", "SKU"),
                            Col("metal", "METAL"), Col("job_no", "JOBNO"),
                            Col("stock_no", "STOCKNO"), _w("g_wt", "GR-WT"),
                            _w("n_wt", "NET-WT"), _w("fine_wt", "FINE-WT"),
                            _w("old_g", "OLD G-WT", red=True), _w("old_n", "OLD N-WT", red=True),
                            _w("old_fine", "OLD FINE", red=True),
                            Col("old_stock_no", "OLD STOCKNO"), _w("diff_g", "DIFF G"),
                            _w("diff_n", "DIFF N"), _w("diff_fine", "DIFF FINE")]),
            query=lambda s, a, b, **_k: REP.mfg_tr_repair(s, a, b), date_default="month",
            on_activate=_open_job,
            note="Legacy window: MFG Tr. Register[Only Repair]. Repaired pieces back in "
                 "stock under a new Stock No; the old weights in red and the difference "
                 "(weight added or removed in repair). E.g. Vr 1047 NS-2513: 47.580 / "
                 "18.414 / 10.864 against 56.072 / 16.924 / 9.985."),
        "mfg_tr_repair_stones": ReportSpec(
            key="mfg_tr_repair_stones", title="MFG TR Stone[only Repair]",
            columns=static([Col("vrno", "VRNO"), Col("date", "DATE"), Col("sku", "SKU"),
                            Col("metal", "METAL"), Col("job_no", "JOBNO"),
                            Col("stock_no", "STOCKNO"), Col("group", "GROUP"),
                            Col("ssku", "SSKU"), Col("stone", "STONE"), Col("size", "SIZE"),
                            _p("pcs", "PCS"), _w("weight", "WEIGHT"), Col("status", "STATUS")]),
            query=lambda s, a, b, **_k: REP.mfg_tr_repair_stones(s, a, b),
            date_default="month", filter_column="status", on_activate=_open_job,
            note="Legacy window: MFG Tr. Register Stone[Only Repair]. The stones of each "
                 "repaired piece: OLD = carried from the old piece, NEW = issued in the "
                 "repair job. Carrying the old stones is Tools ▸ Option ▸ Manufacturing ▸ "
                 "'Repair: carry the old stones forward' (to confirm, 9 Oct Q5)."),
    }


# The legacy M.I.S. Reports list in its order (9 Oct §4.3): (menu name, spec
# key or None while not built / awaiting the client's ranking C-06).
MIS_LIST: tuple[tuple[str, str | None], ...] = (
    ("Sales Analysis", None),
    ("Stone Wise Inventory", None),
    ("Ready Stock Inward List", None),
    ("Stone Setting Analysis", None),
    ("Stone Daily Touch Report", None),
    ("WIP Repair Items", "wip_repair_items"),
    ("Repair Register", "repair_register"),
    ("Rejection Register", None),
    ("Designer Analysis", None),
    ("Sales Analysis[Item Wise]", None),
    ("Closing Stock As SET", None),
    ("Refining Analysis", None),
    ("Metal Summary", "metal_summary"),
    ("Stone in Sales Register", None),
    ("Labour in Sales Register", None),
    ("KM Register", None),
    ("Shiping Analysis", None),
    ("Shiping Pending", None),
    ("Day Wise Sales [MetalValue]", None),
    ("Approval Out Counts", None),
    ("Stock for Merchandising", None),
    ("Range Wise Closing Stock", None),
    ("Range Wise Approval Stock", None),
    ("DAK Return Register", None),
    ("MFG TR [only Repair]", "mfg_tr_repair"),
    ("MFG TR Stone[only Repair]", "mfg_tr_repair_stones"),
    ("Goods Sold But Not Delivered", None),
    ("FOB Custom Invoice", None),
    ("Sales Profit[Metal]", None),
    ("Stone Summery", None),
    ("Sales [Voucher Wise]", None),
    ("Ledger Bal", None),
    ("In-Approval Status", None),
    ("Sales Return Profit[Metal]", None),
)


def mis_keys() -> tuple[str, ...]:
    return tuple(k for _n, k in MIS_LIST if k)
