"""M.I.S. Reports (9 Oct Session 5 §4.3-§4.29).

The legacy Reports ▸ M.I.S. Reports list, built on the shared report grid
(5 Oct T-12). Each spec keeps the legacy menu name as its title and the
legacy window title as a subtitle in the note (UX2), so users recognise it.
"""
from __future__ import annotations

from diagold.services import mis as MIS
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


def _purity_cols() -> list[Col]:
    return [Col("vrno", "VRNO"), Col("date", "DATE"), Col("client", "CLIENT"),
            Col("stockno", "STOCKNO"), Col("sku", "SKU"), Col("metal", "METAL"),
            Col("purity", "PURITY", "measure", 2), Col("sold_purity", "SOLD PURITY", "measure", 2),
            _w("grosswt", "GROSSWT"), _w("net_wt", "NET WT"), _w("sold_fine", "SOLD FINE"),
            _w("actual_fine", "ACTUAL FINE"), _w("diff_fine", "DIFF FINE"), Col("ret", "RETURN")]


def specs() -> dict[str, ReportSpec]:
    return {
        # -- sales (T-02) ---------------------------------------------------
        "sales_analysis": ReportSpec(
            key="sales_analysis", title="Sales Analysis",
            columns=static([Col("vrdate", "VRDATE"), Col("vrno", "VRNO"), Col("type", "TYPE"),
                            Col("client", "CLIENT"), Col("sku", "SKU"), Col("metal", "METAL"),
                            _p("s_pcs", "S_PCS"), _w("s_gwt", "S_GWT"), _w("s_nwt", "S_NWT"),
                            _m("s_amt", "S_AMT"), _p("sr_pcs", "SR_PCS"),
                            _w("sr_gwt", "SR_GWT"), _w("sr_nwt", "SR_NWT"),
                            _m("sr_amt", "SR_AMT")]),
            query=lambda s, a, b, **_k: MIS.sales_analysis(s, a, b), filter_column="type",
            on_activate=_open_job,
            note="One row per piece sold (S) or returned (SR); the sale in the S_ columns, the "
                 "return in the SR_ columns, so the total row shows gross sale and return "
                 "(net = S - SR). Auto Filter on TYPE."),
        "sales_mis": ReportSpec(
            key="sales_mis", title="Sales Analysis[Item Wise]",
            columns=static([Col("block", "BLOCK"), Col("particulars", "PARTICULARS"),
                            _p("pcs", "PCS"), _w("grosswt", "GROSSWT"), _w("netwt", "NETWT"),
                            _m("total", "TOTAL")]),
            query=lambda s, a, b, **_k: MIS.sales_mis(s, a, b), group_by="block",
            filter_column="block", show_total=False, keep_group_order=True,
            note="Legacy window: Sales MIS. Sales in five blocks - Item, Metal, Party, Sales "
                 "Person, SKU - each with its total (every block totals the same sales). "
                 "Sales Person comes from the sale voucher; blank shows (none)."),
        "sales_voucher_wise": ReportSpec(
            key="sales_voucher_wise", title="Sales [Voucher Wise]",
            columns=static([Col("date", "DATE"), Col("group", "GROUP"), Col("party", "PARTY"),
                            Col("vrno", "VRNO"), Col("refno", "REFNO"), _p("pcs", "PCS"),
                            _w("grosswt", "GROSSWT"), _w("netwt", "NETWT"),
                            _w("finewt", "FINEWT"), _w("stone", "STONE"),
                            _m("mt_value", "MT. VALUE"), _m("st_value", "ST. VALUE"),
                            _m("lab_value", "LAB. VALUE"), _m("total_value", "TOTAL VALUE"),
                            _m("inv_value", "INV. VALUE"), Col("ship_by", "SHIP BY"),
                            Col("ship_no", "SHIP NO")]),
            query=lambda s, a, b, **_k: MIS.sales_voucher_wise(s, a, b),
            group_by="party", filter_column="group",
            note="Legacy window: Sales Summery. One row per sale voucher - metal, stone and "
                 "labour value, invoice value and how it shipped. Opens on the financial "
                 "year (the legacy opened on 30-12-1899 and showed nothing)."),
        "day_wise_sales": ReportSpec(
            key="day_wise_sales", title="Day Wise Sales [MetalValue]",
            columns=static([Col("date", "DATE"), Col("party", "PARTY"), _w("finewt", "FINEWT"),
                            _m("gold_value", "GOLD VALUE"), _m("sale_amt", "SALE AMT")]),
            query=lambda s, a, b, **k: MIS.day_wise_sales(s, a, b, **k),
            date_default="month", options={"by_party": ("Party wise", False)},
            note="Legacy window: Bullion Sales. Per day, in date order: fine weight sold, its "
                 "value at the day's fine (24K) rate and the sale amount. Tick Party wise for "
                 "one row per day and party. Sales only - whether returns belong here is "
                 "asked (9 Oct Q15)."),
        "sales_profit_metal": ReportSpec(
            key="sales_profit_metal", title="Sales Profit[Metal]",
            columns=static(_purity_cols()),
            query=lambda s, a, b, **_k: MIS.sales_profit_metal(s, a, b),
            date_default="month", group_by="client", filter_column="ret",
            negative_key="_negative", on_activate=_open_job,
            note="Legacy window: Sales Metal Profit. SOLD FINE = NET x SOLD PURITY / 1000; "
                 "ACTUAL FINE = NET x PURITY / 1000; DIFF = SOLD - ACTUAL (8.228 x 0.590 = "
                 "4.855). RETURN Yes = the piece came back later."),
        "sales_return_profit_metal": ReportSpec(
            key="sales_return_profit_metal", title="Sales Return Profit[Metal]",
            columns=static(_purity_cols()[:-1]),
            query=lambda s, a, b, **_k: MIS.sales_return_profit_metal(s, a, b),
            date_default="month", group_by="client", negative_key="_negative",
            on_activate=_open_job,
            note="The same as Sales Profit [Metal] for pieces returned on a sale return."),
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
    ("Sales Analysis", "sales_analysis"),
    ("Stone Wise Inventory", None),
    ("Ready Stock Inward List", None),
    ("Stone Setting Analysis", None),
    ("Stone Daily Touch Report", None),
    ("WIP Repair Items", "wip_repair_items"),
    ("Repair Register", "repair_register"),
    ("Rejection Register", None),
    ("Designer Analysis", None),
    ("Sales Analysis[Item Wise]", "sales_mis"),
    ("Closing Stock As SET", None),
    ("Refining Analysis", None),
    ("Metal Summary", "metal_summary"),
    ("Stone in Sales Register", None),
    ("Labour in Sales Register", None),
    ("KM Register", None),
    ("Shiping Analysis", None),
    ("Shiping Pending", None),
    ("Day Wise Sales [MetalValue]", "day_wise_sales"),
    ("Approval Out Counts", None),
    ("Stock for Merchandising", None),
    ("Range Wise Closing Stock", None),
    ("Range Wise Approval Stock", None),
    ("DAK Return Register", None),
    ("MFG TR [only Repair]", "mfg_tr_repair"),
    ("MFG TR Stone[only Repair]", "mfg_tr_repair_stones"),
    ("Goods Sold But Not Delivered", None),
    ("FOB Custom Invoice", None),
    ("Sales Profit[Metal]", "sales_profit_metal"),
    ("Stone Summery", None),
    ("Sales [Voucher Wise]", "sales_voucher_wise"),
    ("Ledger Bal", None),
    ("In-Approval Status", None),
    ("Sales Return Profit[Metal]", "sales_return_profit_metal"),
)


def mis_keys() -> tuple[str, ...]:
    return tuple(k for _n, k in MIS_LIST if k)
