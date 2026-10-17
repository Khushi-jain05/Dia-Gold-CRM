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
        # -- shipping (T-07) ------------------------------------------------
        "shipping_analysis": ReportSpec(
            key="shipping_analysis", title="Shiping Analysis",
            columns=static([Col("orddt", "OrdDt"), Col("ordno", "OrdNo"), Col("refno", "Refno"),
                            Col("account", "Account"), Col("jobno", "JobNo"), Col("sku", "SKU"),
                            _p("pcs", "Pcs"), Col("shipdt", "ShipDt"),
                            Col("days", "Days", "measure", 0), Col("ship_by", "Ship By"),
                            Col("tracking", "Tracking"), Col("vrno", "Sale Vr")]),
            query=lambda s, a, b, **_k: MIS.shipping_analysis(s, a, b),
            group_by="account", on_activate=_open_job,
            note="Every order line shipped: Days = ShipDt - OrdDt (order 29-08 shipped 05-09 "
                 "= 7). Ship date and tracking come from the sale's Dispatch / Tracking; a "
                 "part shipment is one row each."),
        "shipping_pending": ReportSpec(
            key="shipping_pending", title="Shiping Pending",
            columns=static([Col("orddt", "OrdDt"), Col("ordno", "OrdNo"), Col("refno", "Refno"),
                            Col("account", "Account"), Col("jobno", "JobNo"), Col("sku", "SKU"),
                            _p("ord_pcs", "Ord Pcs"), _p("bal_pcs", "Bal Pcs"),
                            Col("deldt", "Del Dt"), Col("days", "Days", "measure", 0),
                            Col("status", "Job Status")]),
            query=lambda s, a, b, **_k: MIS.shipping_pending(s, a, b),
            group_by="account", negative_key="_negative", on_activate=_open_job,
            note="Order lines with pieces still to ship and the days since the order; red = "
                 "past its delivery date. (Columns assumed - the legacy screen was not "
                 "opened, 9 Oct C-06.)"),
        # -- stock (T-05) ---------------------------------------------------
        "ready_stock_inward": ReportSpec(
            key="ready_stock_inward", title="Ready Stock Inward List",
            columns=static([Col("location", "LOCATION"), Col("date", "DATE"), Col("vrno", "VRNO"),
                            Col("fot", "FOT"), Col("from", "FROM"), Col("sku", "SKU"),
                            Col("metal", "METAL"), Col("size", "SIZE"), _p("pcs", "PCS"),
                            _w("g_wt", "G-WT"), _w("n_wt", "N-WT"), _m("cost", "COST"),
                            _m("net", "NET"), Col("tag", "TAG", "measure", 0, total=True),
                            Col("stockid", "STOCKID")]),
            query=lambda s, a, b, **_k: MIS.ready_stock_inward(s, a, b),
            filter_column="fot", negative_key="_negative", on_activate=_open_job,
            note="Legacy window: Ready Stock Inward. Every piece into ready stock - FOT MF "
                 "(MFG transfer), RO (opening), RP (bought in), SR (sales return), AR (back "
                 "from approval); meanings to confirm (9 Oct Q16). TAG = NET / 1,000. A piece "
                 "at TAG 0 is red; new pieces are refused at 0 (Tools ▸ Option ▸ Inventory)."),
        "range_wise_closing": ReportSpec(
            key="range_wise_closing", title="Range Wise Closing Stock",
            columns=static([Col("family", "Family"), Col("item", "Item"), Col("range", "RANGE"),
                            _p("pcs", "PCS"), _w("fine", "FINE"),
                            Col("tag", "TAG", "measure", 0, total=True)]),
            query=lambda s, a, b, **_k: MIS.range_wise_stock(s, a, b), date_mode="to",
            group_by="family", filter_column="family", negative_key="_negative",
            note="Legacy window: Closing Stock. Pieces in stock by family, item and price "
                 "RANGE - the bands are the Item master's 'Set Sales Price Range For M.I.S. "
                 "Report' (empty in legacy, so RANGE was 0 - 9 Oct Q2). Family '-' (red) = "
                 "an item with no family."),
        "range_wise_approval": ReportSpec(
            key="range_wise_approval", title="Range Wise Approval Stock",
            columns=static([Col("family", "Family"), Col("item", "Item"), Col("range", "RANGE"),
                            _p("pcs", "PCS"), _w("fine", "FINE"),
                            Col("tag", "TAG", "measure", 0, total=True)]),
            query=lambda s, a, b, **_k: MIS.range_wise_stock(s, a, b, status="on_approval"),
            date_mode="to", group_by="family", filter_column="family",
            note="The same as Range Wise Closing Stock for pieces out on approval (the legacy "
                 "menu item was not opened - columns assumed, 9 Oct C-06)."),
        "approval_out_counts": ReportSpec(
            key="approval_out_counts", title="Approval Out Counts",
            columns=static([Col("stock_no", "STOCK NO"), Col("sku", "SKU"), Col("item", "Item"),
                            Col("family", "Family"), _p("app_nos", "APP NOS"),
                            Col("mfg_date", "MFG DATE"), Col("age", "AGE", "measure", 0),
                            Col("tag", "TAG", "measure", 0, total=True),
                            Col("status", "STATUS")]),
            query=lambda s, a, b, **_k: MIS.approval_out_counts(s, a, b), date_mode="to",
            filter_column="status", on_activate=_open_job,
            note="Ageing of the pieces in stock or on approval: AGE = report date - MFG DATE "
                 "(01-04-2026 -> 09-10-2026 = 191); APP NOS = how many approvals the piece "
                 "went on. Opening pieces carry the opening date (true age unknown, Q17)."),
        "sold_labour": ReportSpec(
            key="sold_labour", title="Labour in Sales Register",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"), Col("refno", "REFNO"),
                            Col("account", "ACCOUNT"), Col("sku", "SKU"),
                            Col("labour", "LABOUR"), Col("price", "PRICE", "measure", 2),
                            Col("unit", "UNIT"), _m("amount", "AMOUNT"),
                            Col("jewelleryid", "JEWELLERYID"), Col("jobno", "JOBNO"),
                            Col("dup", "CHECK")]),
            query=lambda s, a, b, **_k: MIS.sold_labour(s, a, b), negative_key="_negative",
            group_by="account", on_activate=_open_job,
            note="Legacy window: Sold Labour. Labour on every piece sold: AMOUNT = PRICE x "
                 "net weight (1,200 x 15.303 = 18,363.60). A jewellery id sold twice with no "
                 "return between is red ('Sold twice' - 40243 on Vr 2 and Vr 11 in legacy)."),
        "in_approval_status": ReportSpec(
            key="in_approval_status", title="In-Approval Status",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"), Col("refno", "REFNO"),
                            Col("account", "ACCOUNT"), Col("stockno", "STOCKNO"),
                            Col("sku", "SKU"), Col("metal", "METAL"), _p("pcs", "PCS"),
                            _p("ret", "RETURN"), _p("sold", "SOLD"), _p("approval", "APPROVAL"),
                            _p("balance", "BALANCE")]),
            query=lambda s, a, b, **_k: MIS.in_approval_status(s, a, b),
            group_by="account", on_activate=_open_job,
            note="BALANCE = APPROVAL - RETURN - SOLD, from the same logic as Ready Stock "
                 "Approval Analysis. Off in the menu until the client says it is used (Q1)."),
        "goods_not_delivered": ReportSpec(
            key="goods_not_delivered", title="Goods Sold But Not Delivered",
            columns=static([Col("vrno", "VRNO"), Col("date", "DATE"), Col("sku", "SKU"),
                            Col("stockno", "STOCKNO"), _p("pcs", "PCS"),
                            _w("grosswt", "GROSSWT"), _w("netwt", "NETWT"), _m("total", "TOTAL"),
                            Col("party", "PARTY")]),
            query=lambda s, a, b, **_k: MIS.goods_not_delivered(s, a, b),
            group_by="party", on_activate=_open_job,
            note="Pieces sold whose sale has no Ship Date yet. Off in the menu until the client "
                 "says it is used (Q1)."),
        # -- stone (T-03) ---------------------------------------------------
        "stone_wise_inventory": ReportSpec(
            key="stone_wise_inventory", title="Stone Wise Inventory",
            columns=static([Col("location", "LOCATION"), Col("type", "TYPE"),
                            Col("stone", "STONE"), Col("size", "SIZE"), Col("lotno", "LOTNO"),
                            _p("op_pcs", "OP_PCS"), _w("op_wt", "OP_WT"), _p("in_pcs", "IN_PCS"),
                            _w("in_wt", "IN_WT"), _p("out_pcs", "OUT_PCS"),
                            _w("out_wt", "OUT_WT"), _p("cl_pcs", "CL_PCS"), _w("cl_wt", "CL_WT"),
                            Col("flag", "")]),
            query=lambda s, a, b, **k: MIS.stone_wise_inventory(s, a, b, **k),
            group_by="location", filter_column="location", negative_key="_negative",
            options={"only_negative": ("Only negatives", False)},
            note="Legacy window: Stone Wise Balance. Per location, type, stone and lot: "
                 "CL = OP + IN - OUT. A negative closing is red - clean up or start from "
                 "fresh opening balances (Data-Request 3e, 9 Oct C-02). Tools ▸ Option ▸ "
                 "Inventory decides whether a voucher may take a location below zero."),
        "stone_daily_touch": ReportSpec(
            key="stone_daily_touch", title="Stone Daily Touch Report",
            columns=static([Col("location", "LOCATION"), Col("type", "TYPE"),
                            Col("ssku", "SSKU"), Col("size", "SIZE"), Col("group", "GROUP"),
                            Col("stone", "STONE"), _p("bal_pcs", "BAL PCS"),
                            _w("bal_wt", "BAL WT"), Col("flag", "")]),
            query=lambda s, a, b, **k: MIS.stone_daily_touch(s, a, b, **k), date_mode="to",
            group_by="location", filter_column="location", negative_key="_negative",
            options={"only_negative": ("Only negatives", False)},
            note="Legacy window: Daily Touch Report. The stone balance on the day by "
                 "location; every negative line red (RAJAT JI DIA.(-2) -577,482 pcs in "
                 "legacy). Equals Stone Wise Inventory's closing on the same date."),
        "sold_stone": ReportSpec(
            key="sold_stone", title="Stone in Sales Register",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"), Col("refno", "REFNO"),
                            Col("account", "ACCOUNT"), Col("sku", "SKU"), Col("metal", "METAL"),
                            Col("ssku", "SSKU"), Col("barcode", "BARCODE"), Col("stone", "STONE"),
                            Col("shape", "SHAPE"), Col("quality", "QUALITY"), Col("size", "SIZE"),
                            Col("lotno", "LOTNO"), _p("pcs", "PCS"),
                            Col("cts", "CTS", "measure", 2, total=True),
                            Col("price", "PRICE", "measure", 2), Col("unit", "UNIT"),
                            _m("amount", "AMOUNT"), Col("location", "LOCATION")]),
            query=lambda s, a, b, **_k: MIS.sold_stone(s, a, b),
            group_by="account", filter_column="stone", on_activate=_open_job,
            note="Legacy window: Sold Stone. Every stone line of every sale (ready-stock "
                 "pieces and Sale ▸ Stone). AMOUNT = CTS x PRICE (TALLA JEWELLERS NSE-1942 "
                 "POLKI 16-18 3.09 ct @22,500 = 69,525)."),
        "stone_sku_balance": ReportSpec(
            key="stone_sku_balance", title="Stone Summery",
            columns=static([Col("ssku", "SSKU"), _w("receipt", "RECEIPT"),
                            _w("rep_rtn", "REP.RTN"), _w("wip", "WIP"), _w("on_job", "ON JOB"),
                            _w("sold", "SOLD"), _w("ret", "RETURN"),
                            _w("bal_in_hand", "BAL IN HAND"), _w("client_bal", "CLIENT BAL"),
                            Col("group", "GROUP")]),
            query=lambda s, a, b, **_k: MIS.stone_sku_balance(s, a, b),
            date_default="month", filter_column="group", negative_key="_negative",
            note="Legacy window: Stone SKU Balance (carats). RECEIPT / REP.RTN in the period; "
                 "WIP = in job bags, ON JOB = with karigars or set in pieces in work; SOLD = "
                 "Stone in Sales Register for the same dates (they reconcile); BAL IN HAND = "
                 "loose at the locations; CLIENT BAL = out on stone approval."),
        # -- production (T-04) ----------------------------------------------
        "setting_analysis": ReportSpec(
            key="setting_analysis", title="Stone Setting Analysis",
            columns=static([Col("iss_dt", "ISS DT"), Col("worker", "WORKER"), Col("sku", "SKU"),
                            Col("jobno", "JOBNO"), Col("metal", "METAL"), Col("item", "Item"),
                            Col("pcs", "PCS", "measure", 1, total=True),
                            _w("iss_gwt", "ISS G-WT"), _w("iss_nwt", "ISS N-WT"),
                            _w("iss_stwt", "ISS ST-WT"), Col("rtn_dt", "RTN DT"),
                            _w("rtn_gwt", "RTN G-WT"), _w("rtn_nwt", "RTN-N-WT"),
                            _w("use_stwt", "USE ST WT"), _p("use_pcs", "USE PCS"),
                            _w("alwloss", "ALWLOSS"), _w("losswt", "LOSSWT"),
                            _m("labour", "LABOUR"), _w("wast_rec", "WAST REC")]),
            query=lambda s, a, b, **_k: MIS.setting_analysis(s, a, b),
            group_by="worker", filter_column="worker", on_activate=_open_job,
            note="Legacy window: Setting Analysis. Every issue to a setter with its return: "
                 "USE ST = stones sent less those handed back; LOSSWT = ISS N-WT - RTN N-WT "
                 "(negative = gain); ALWLOSS = allowed % of the weight; WAST REC = LOSSWT - "
                 "ALWLOSS. What USE PCS / WAST REC mean to the owner is asked (9 Oct Q9)."),
        "refining_analysis": ReportSpec(
            key="refining_analysis", title="Refining Analysis",
            columns=static([Col("process", "PROCESS"), Col("worker", "WORKER"),
                            _w("net_fine", "NET FINE"), _w("scrap_fine", "SCRAP FINE"),
                            _w("loss_fine", "LOSS FINE"), _w("dust", "DUST"),
                            Col("loss_pct", "LOSS %", "measure", 2,
                                ratio=("loss_fine", "net_fine"))]),
            query=lambda s, a, b, **_k: MIS.refining_analysis(s, a, b),
            group_by="process", filter_column="process", date_default="month",
            note="Fine of the net issued, scrap, loss and dust per process and worker over "
                 "the receipts of the period. LOSS % = LOSS FINE / NET FINE x 100 (PrePolish "
                 "POLISH 356.685 / 9,639.689 = 3.70 %), worked again on each process total; "
                 "blank where nothing weighed was issued."),
        "rejection_register": ReportSpec(
            key="rejection_register", title="Rejection Register",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"), Col("ord_no", "ORD NO"),
                            _p("ord_pcs", "ORD PCS"), Col("del_dt", "DEL DT"),
                            Col("worker", "WORKER"), Col("process", "PROCESS"),
                            Col("jobno", "JOBNO"), Col("sku", "SKU"),
                            _p("explod_pcs", "EXPLOD PCS"), _w("rej_wt", "REJ WT"),
                            _p("rej_pcs", "REJ PCS"), Col("ord_ref", "ORD REF"),
                            Col("line_po", "LINE PO"), Col("type", "TYPE"),
                            Col("remark", "REMARK")]),
            query=lambda s, a, b, **_k: MIS.rejection_register(s, a, b),
            date_default="today", on_activate=_open_job,
            note="Pieces / weight rejected on manufacturing receipts, with the order. Off in "
                 "the menu until the client says it is used (Tools ▸ Option, 9 Oct Q1)."),
        "kundan_register": ReportSpec(
            key="kundan_register", title="KM Register",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"), Col("jobno", "JOBNO"),
                            Col("account", "ACCOUNT"), Col("sku", "SKU"), Col("metal", "METAL"),
                            _w("gross", "GROSS"), _w("ghat", "GHAT"),
                            Col("ghat_wast", "GHAT-WAST%"), _w("kundan", "KUNDAN"),
                            _w("otherwt", "OTHERWT"), Col("oth_wast", "OTH-WAST%"),
                            Col("fine_pct", "FINE%"), _w("total_fine", "TOTAL FINE"),
                            _m("net_lab", "NET LAB"), _w("netwt", "NETWT")]),
            query=lambda s, a, b, **_k: MIS.kundan_register(s, a, b),
            on_activate=_open_job,
            note="Legacy window: Kundan Register (empty in legacy). Receipts on a Kundan "
                 "process; GHAT / KUNDAN weights and wastage % wait for the client to explain "
                 "kundan work. Off in the menu until confirmed (9 Oct Q1)."),
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
    ("Ledger Bal", None),
    ("In-Approval Status", "in_approval_status"),
    ("Sales Return Profit[Metal]", "sales_return_profit_metal"),
)


def mis_keys() -> tuple[str, ...]:
    return tuple(k for _n, k in MIS_LIST if k)


def whatsapp_log_spec() -> ReportSpec:
    """Tools ▸ WhatsApp Log (9 Oct T-08): every dispatch message - number,
    status, attempts, error - with Retry Failed."""
    from diagold.db.session import SessionLocal
    from diagold.services import whatsapp as WA

    def retry(widget) -> None:
        with SessionLocal() as s:
            n = WA.retry_failed(s)
            s.commit()
        widget.status.setText(f"Retried {n} failed message(s).")
        widget.run()
    return ReportSpec(
        key="whatsapp_log", title="WhatsApp Log",
        columns=static([Col("time", "TIME"), Col("party", "PARTY"), Col("voucher", "VOUCHER"),
                        Col("number", "NUMBER"), Col("status", "STATUS"),
                        Col("attempts", "TRIES", "measure", 0), Col("provider", "PROVIDER"),
                        Col("error", "ERROR"), Col("body", "MESSAGE")]),
        query=lambda s, a, b, **_k: WA.message_log(s, a, b), date_default="month",
        filter_column="status", negative_key="_negative",
        actions=[("Retry Failed", "", retry)],
        note="Dispatch messages to customers. Sandbox = logged, not sent (Tools ▸ Option ▸ "
             "Others ▸ WhatsApp). Delivered / read receipts need the Cloud API webhook on a "
             "server - until then a message shows as sent.")
