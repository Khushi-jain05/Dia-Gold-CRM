"""Account menu (5 Oct Session 4 §4.2-4.5, T-01 / T-02 / T-04): Group's,
Voucher Entry ▸ Receipt / Payment / Journal / Contra, Outstandings ▸
Receivables / Payables / Ledger, Day Book, Ledger, Trial Balance, More ▸
Cash Flow / Interest. Every figure comes from the postings (services.accounts).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from diagold.db.models import Account, AccountGroup, AccountVoucher, Location, Metal
from diagold.db.session import SessionLocal
from diagold.services import accounts as A
from diagold.services.production import ProductionError
from diagold.ui.confirm import confirm_save
from diagold.ui.crud import CrudSpec, CrudWidget, Field, auto_fit
from diagold.ui.production import TINT_RECEIVE, _Screen, _item, _pydate, _qdate, show_in_dialog
from diagold.ui.reports import Col, ReportSpec, ReportWidget, static
from diagold.ui.reports import build_specs as _report_specs

D = Decimal


# --------------------------------------------------------------------------
# Submenus
# --------------------------------------------------------------------------
SUBMENUS: dict[str, list[tuple[str, str]]] = {
    "account.voucher_entry": [("receipt", "Receipt"), ("payment", "Payment"),
                              ("journal", "Journal"), ("contra", "Contra")],
    "account.outstandings": [("receivables", "Receivables"), ("payables", "Payables"),
                             ("os_day_wise", "O/S Day Wise"), ("os_monthly", "O/S Monthly"),
                             ("ledger", "Ledger"), ("client_metal_os", "Client Metal O/S")],
    "account.more": [("cash_flow", "Cash Flow"), ("interest_receivable", "Interest Receivable"),
                     ("interest_payable", "Interest Payable")],
}
_HEAD = {"account.voucher_entry": "Voucher", "account.outstandings": "Outstanding",
         "account.more": "Accounts"}
PENDING_EXPLANATION: set[str] = set()


def sub_key(parent: str, key: str) -> str:
    return f"{parent}.{key}"


def sub_labels() -> dict[str, str]:
    return {sub_key(p, k): f"{_HEAD[p]} {label}" if p != "account.more" else label
            for p, items in SUBMENUS.items() for k, label in items}


def _builders() -> dict[str, Any]:
    from diagold.ui import interest
    return {
        "receipt": lambda u: AccountVoucherWidget("receipt", u),
        "payment": lambda u: AccountVoucherWidget("payment", u),
        "journal": lambda u: AccountVoucherWidget("journal", u),
        "contra": lambda u: AccountVoucherWidget("contra", u),
        "receivables": lambda u: ReportWidget(specs()["receivables"], u),
        "payables": lambda u: ReportWidget(specs()["payables"], u),
        "os_day_wise": lambda u: ReportWidget(specs()["os_day_wise"], u),
        "os_monthly": lambda u: ReportWidget(specs()["os_monthly"], u),
        "ledger": lambda u: ReportWidget(specs()["party_ledger"], u),
        "cash_flow": lambda u: ReportWidget(specs()["cash_flow"], u),
        "client_metal_os": lambda u: ReportWidget(_report_specs()["client_metal_os"], u),
        "interest_receivable": lambda u: interest.InterestWidget("receivable", u),
        "interest_payable": lambda u: interest.InterestWidget("payable", u),
    }


def has_screen(menu_key: str) -> bool:
    return menu_key.rsplit(".", 1)[1] in _builders()


def build_screen(menu_key: str, user=None) -> QWidget:
    return _builders()[menu_key.rsplit(".", 1)[1]](user)


# --------------------------------------------------------------------------
# Account Group Master
# --------------------------------------------------------------------------
def _reindex(widget, _sel) -> None:
    """Reindex: number the groups in tree order (parents first, by name)."""
    with SessionLocal() as s:
        groups = list(s.scalars(select(AccountGroup)))
        kids: dict[int | None, list[AccountGroup]] = {}
        for g in groups:
            kids.setdefault(g.parent_id, []).append(g)
        n = 0

        def walk(pid):
            nonlocal n
            for g in sorted(kids.get(pid, []), key=lambda g: g.name.lower()):
                n += 1
                g.index_no = n
                walk(g.id)
        walk(None)
        s.commit()
    widget.reload()
    QMessageBox.information(widget, "Reindex", f"{n} group(s) renumbered in tree order.")


def _open(widget, key: str) -> None:
    show_in_dialog(widget, ReportWidget(specs()[key]), specs()[key].title, (1200, 700))


def group_spec() -> CrudSpec:
    return CrudSpec(
        key="account.groups", title="Account Groups", model=AccountGroup, order_by="index_no",
        search_hint="Search groups…", singular_title="Account Group",
        fields=[
            Field("name", "Name", required=True),
            Field("code", "Code"),
            Field("parent_id", "Under", type="fk", fk_model=AccountGroup,
                  fk_label=lambda g: g.name),
            Field("sub_ledger_required", "Sub Ledger Required", type="bool"),
            Field("index_no", "Index", type="int"),
            Field("nature", "Nature", type="choice",
                  choices=["", "Assets", "Liabilities", "Income", "Expenses"]),
        ],
        extra_buttons=[("Reindex", _reindex),
                       ("O/S Monthly", lambda w, _s: _open(w, "os_monthly")),
                       ("O/S Day Wise", lambda w, _s: _open(w, "os_day_wise"))])


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def _parties(s) -> list[tuple[Any, str]]:
    return [(a.id, a.name) for a in s.scalars(select(Account).where(
        Account.is_active.is_(True)).order_by(Account.name))]


def _modes(_s) -> list[tuple[Any, str]]:
    return [("", "All modes"), ("Cash", "Cash"), ("Bill", "Bill"), ("Bank", "Bank"),
            ("Metal", "Metal")]


def _ledger_q(s, d0, d1, account=None, mode="", monthwise=True, **_k):
    return A.ledger(s, account, d0, d1, monthwise=monthwise, mode=mode or "")


def _ledger_drill(widget: ReportWidget, row: dict) -> None:
    """A month row opens that month voucher by voucher."""
    if row.get("_month"):
        from datetime import timedelta
        y, m = row["_month"]
        next_month = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        widget.set_dates(date(y, m, 1), next_month - timedelta(days=1))
        widget.option_boxes["monthwise"].setChecked(False)


def _ledger_graph(widget: ReportWidget) -> None:
    """Ctrl+G: the ledger month by month - debit, credit and closing."""
    from diagold.ui.charts import BarChart
    d0, d1 = widget.dates()
    with SessionLocal() as s:
        rows = A.ledger(s, widget.picker_boxes["account"].currentData(), d0, d1, monthwise=True)
    rows = [r for r in rows if r.get("_month")]
    labels = [r["particulars"][:3] + r["particulars"][-5:] for r in rows]
    vals = [(r["closing"] if r["drcr"] == "Dr" else -r["closing"]) for r in rows]
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.addWidget(BarChart(labels, vals, f"{widget.picker_boxes['account'].currentText()} — "
                           "closing by month (Dr up, Cr down)"))
    lay.addWidget(BarChart(labels, [r["debit"] or 0 for r in rows], "Debit by month"))
    show_in_dialog(widget, box, "Ledger graph", (900, 640))


def _tb_toggle(widget: ReportWidget) -> None:
    cb = widget.option_boxes["detailed"]
    cb.setChecked(not cb.isChecked())


def specs() -> dict[str, ReportSpec]:
    m = lambda k, l: Col(k, l, "measure", 2, total=True)            # noqa: E731
    k = Col
    out_cols = [k("date", "DATE"), k("ref_no", "REF NO"), k("vrtype", "TYPE"), k("vrno", "VR NO"),
                k("party", "PARTICULARS"), m("op_amt", "OP AMT"), m("pnd_amt", "PND AMT"),
                k("drcr", "Dr/Cr"), Col("c_day", "C-DAY", "measure", 0),
                Col("credit_days", "CR DAYS", "measure", 0), Col("overdue", "OVERDUE", "measure", 0),
                k("location", "LOCATION")]
    age_cols = [k("party", "PARTY")] + [m(lbl, lbl) for _lo, _hi, lbl in A.AGE_BUCKETS] + \
        [m("opening", "OPENING"), m("total", "TOTAL")]

    def month_cols(a, b):
        cols, y, mth = [k("party", "PARTY"), m("opening", "OPENING")], a.year, a.month
        while (y, mth) <= (b.year, b.month):
            key = f"{y}-{mth:02d}"
            cols.append(m(key, date(y, mth, 1).strftime("%b %Y").upper()))
            y, mth = (y + 1, 1) if mth == 12 else (y, mth + 1)
        return cols + [m("total", "TOTAL")]
    return {
        "party_ledger": ReportSpec(
            key="party_ledger", title="Ledger",
            columns=static([k("date", "DATE"), k("particulars", "PARTICULARS"),
                            k("vrtype", "TYPE"), k("vrno", "VR NO"), k("mode", "MODE"),
                            m("opening", "OPENING"), k("op_drcr", ""), m("debit", "DEBIT"),
                            m("credit", "CREDIT"), Col("closing", "CLOSING", "measure", 2),
                            k("drcr", "Dr/Cr"), Col("fine", "FINE", "measure", 3),
                            k("narration", "NARRATION")]),
            query=_ledger_q, pickers=[("account", "Account", _parties), ("mode", "Mode", _modes)],
            options={"monthwise": ("Month-wise", True)}, on_activate=_ledger_drill,
            graph=_ledger_graph,
            note="Month-wise as the legacy ledger opens; double-click a month to see it voucher "
                 "by voucher (or untick Month-wise). Ctrl+G draws it. Mode filters cash / bill / "
                 "bank / metal. Opening = the master's opening + everything before From."),
        "acc_day_book": ReportSpec(
            key="acc_day_book", title="Day Book (Accounts)",
            columns=static([k("date", "DATE"), k("vrtype", "TYPE"), k("voucher", "VOUCHER"),
                            k("vrno", "VR NO"), k("party", "PARTY"), k("mode", "MODE"),
                            m("amount", "AMOUNT"), m("cash", "CASH"), k("narration", "NARRATION")]),
            query=lambda s, a, b, **_k: A.day_book(s, a, b), group_by="date",
            filter_column="voucher", date_default="month",
            note="Every accounting voucher of the period - sales, returns, purchases, receipts, "
                 "payments, journals - grouped by day with day totals; Group by Voucher for the "
                 "totals by type."),
        "trial_balance": ReportSpec(
            key="trial_balance", title="Trial Balance",
            columns=static([k("particulars", "PARTICULARS"), m("opening", "OPENING"),
                            k("op_drcr", ""), m("debit", "DEBIT"), m("credit", "CREDIT"),
                            Col("closing", "CLOSING", "measure", 2), k("drcr", "Dr/Cr"),
                            k("group", "GROUP")]),
            query=lambda s, a, b, detailed=False, **_k: A.trial_balance(s, a, b, detailed=detailed),
            options={"detailed": ("Detailed", False)}, negative_key="_negative",
            actions=[("Detailed", "Ctrl+F1", _tb_toggle)],
            note="Group-wise; Detailed (Ctrl+F1) lists the accounts under each group. Red: the "
                 "masters' opening balances do not tally (Diff. in Opening Balances)."),
        "receivables": ReportSpec(
            key="receivables", title="Outstanding Receivables", columns=static(out_cols),
            query=lambda s, a, b, **_k: A.outstanding(s, a, b, side="receivable"),
            group_by="party", filter_column="party", negative_key="_negative", date_mode="to",
            note="Bill by bill: what each party still owes after receipts and returns knocked "
                 "off (oldest first unless allocated on the receipt). C-Day = days since the bill; "
                 "red = past its credit days. Cash sales never appear - they settle at once."),
        "payables": ReportSpec(
            key="payables", title="Outstanding Payables", columns=static(out_cols),
            query=lambda s, a, b, **_k: A.outstanding(s, a, b, side="payable"),
            group_by="party", filter_column="party", negative_key="_negative", date_mode="to",
            note="Bill by bill: what we still owe each supplier after payments and returns."),
        "os_day_wise": ReportSpec(
            key="os_day_wise", title="O/S Day Wise (Receivables)", columns=static(age_cols),
            query=lambda s, a, b, payable=False, **_k: A.ageing(
                s, a, b, side="payable" if payable else "receivable"),
            options={"payable": ("Payables", False)}, date_mode="to",
            note="Pending amount per party by age of the bill."),
        "os_monthly": ReportSpec(
            key="os_monthly", title="O/S Monthly (Receivables)", columns=month_cols,
            query=lambda s, a, b, payable=False, **_k: A.ageing(
                s, a, b, side="payable" if payable else "receivable", monthly=True),
            options={"payable": ("Payables", False)},
            note="Pending amount per party by the month of the bill."),
        "cash_flow": ReportSpec(
            key="cash_flow", title="Cash Flow",
            columns=lambda a, b: [k("date", "DATE"), k("kind", "KIND"), k("vrtype", "TYPE"),
                                  k("vrno", "VR NO"), k("party", "PARTY"), m("cash_in", "CASH IN"),
                                  m("cash_out", "CASH OUT"), m("net", "NET"),
                                  m("cash_sale", "CASH SALE"), m("cash_return", "CASH RETURN"),
                                  m("cash_received", "CASH RECEIVED"), m("cash_paid", "CASH PAID")],
            query=lambda s, a, b, by_day=False, **_k: A.cash_flow(s, a, b, by_day=by_day),
            options={"by_day": ("Summary by day", False)}, group_by="party", filter_column="kind",
            date_default="month",
            note="Every movement through Cash: cash sales, cash returns, cash received, cash "
                 "paid. Tick Summary by day for one row a day."),
    }


# --------------------------------------------------------------------------
# Voucher Entry
# --------------------------------------------------------------------------
class AccountVoucherWidget(_Screen):
    """Receipt / Payment: party, mode (Cash, Bank, Metal), amount, and the
    party's pending bills to knock off (oldest first unless typed). Journal /
    Contra: Dr / Cr lines that must balance."""

    def __init__(self, vr_type: str, user=None, parent=None):
        self.vr_type = vr_type
        super().__init__(A.ACC_TYPES[vr_type][1] + " Voucher", with_picker=False, parent=parent)
        self.user = user
        self.header.hide()
        self.vr = QLabel("")
        self.vr.setObjectName("H2")
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.ref = QLineEdit()
        self.ref.setPlaceholderText("Ref No")
        self.ref.setMaximumWidth(120)
        for w in (QLabel("Vr No"), self.vr, QLabel("Date"), self.date, self.ref):
            self.toolbar.addWidget(w)
        self.toolbar.addStretch(1)
        self.button("Add", self.new_voucher)
        self.button("Save", self.save, primary=True)
        self.button("Delete", self.delete_voucher)
        self.button("Print", self.print_voucher, secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)
        self._last_id: int | None = None
        with SessionLocal() as s:
            self._accounts = [(a.id, a.name, a.group_name) for a in s.scalars(
                select(Account).where(Account.is_active.is_(True)).order_by(Account.name))]
            self._metals = [(m.id, m.name) for m in s.scalars(select(Metal).order_by(Metal.name))]
            self._locs = [(l.id, l.name) for l in s.scalars(select(Location).order_by(Location.name))]
            A.nominal(s, "Cash"), A.nominal(s, "Bank")
            s.commit()
            self._accounts = [(a.id, a.name, a.group_name) for a in s.scalars(
                select(Account).where(Account.is_active.is_(True)).order_by(Account.name))]
        if vr_type in ("receipt", "payment"):
            self._build_party()
        else:
            self._build_lines()
        self.narration = QLineEdit()
        self.narration.setPlaceholderText("Narration")
        self.outer.addWidget(self.narration)
        self.status = QLabel("")
        self.outer.addWidget(self.status)
        # Saved vouchers of this type, newest first (9 Oct: a saved receipt
        # was nowhere to be seen). Pick a row for Print / Delete.
        self.saved_title = QLabel(f"<b>Saved {A.ACC_TYPES[vr_type][1]}s</b> — select a row to "
                                  "Print or Delete it")
        self.outer.addWidget(self.saved_title)
        self.saved = QTableWidget(0, 8)
        self.saved.setHorizontalHeaderLabels(["Vr No", "Date", "Party / Accounts", "Mode",
                                              "Amount", "Metal · Weight", "Ref", "Narration"])
        self.saved.verticalHeader().setVisible(False)
        self.saved.horizontalHeader().setStretchLastSection(True)
        self.saved.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.saved.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.saved.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.saved.setMinimumHeight(140)
        self.saved.setMaximumHeight(220)
        self.saved.itemSelectionChanged.connect(self._saved_selected)
        self.outer.addWidget(self.saved)
        self._saved_ids: list[int] = []
        self.refresh()

    def _fill_saved(self) -> None:
        with SessionLocal() as s:
            rows = []
            for v in s.scalars(select(AccountVoucher).where(AccountVoucher.vr_type == self.vr_type)
                               .order_by(AccountVoucher.vr_date.desc(),
                                         AccountVoucher.vr_no.desc()).limit(300)):
                if v.account_id:
                    a = s.get(Account, v.account_id)
                    party = a.name if a else ""
                else:
                    names = [s.get(Account, l.account_id) for l in v.lines]
                    party = ", ".join(n.name for n in names if n)[:80]
                metal = ""
                if v.mode == "Metal" and v.metal_id:
                    m = s.get(Metal, v.metal_id)
                    metal = f"{m.name if m else ''} · {D(str(v.weight)):.3f} g"
                amount = D(str(v.amount)) or sum((D(str(l.debit)) for l in v.lines), D(0))
                rows.append((v.id, [str(v.vr_no), f"{v.vr_date:%d-%m-%Y}", party,
                                    v.mode if v.vr_type in ("receipt", "payment") else "",
                                    f"{amount:,.2f}", metal, v.ref_no or "", v.narration or ""]))
        self._saved_ids = [r[0] for r in rows]
        self.saved.setRowCount(len(rows))
        for i, (_vid, vals) in enumerate(rows):
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if c in (0, 4):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.saved.setItem(i, c, it)
        self.saved.resizeColumnsToContents()
        self.saved_title.setText(f"<b>Saved {A.ACC_TYPES[self.vr_type][1]}s ({len(rows)})</b> — "
                                 "select a row to Print or Delete it")

    def _saved_selected(self) -> None:
        r = self.saved.currentRow()
        if 0 <= r < len(self._saved_ids):
            self._last_id = self._saved_ids[r]

    def _selected_saved(self) -> int | None:
        rows = self.saved.selectionModel().selectedRows() if self.saved.selectionModel() else []
        return self._saved_ids[rows[0].row()] if rows else None

    # -- receipt / payment ----------------------------------------------
    def _combo(self, items, editable=True) -> QComboBox:
        cb = QComboBox()
        cb.setEditable(editable)
        cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        cb.addItem("", None)
        for i, t, *_r in items:
            cb.addItem(t, i)
        if editable:
            cb.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        return cb

    def _build_party(self) -> None:
        row = QHBoxLayout()
        self.party = self._combo(self._accounts)
        self.party.setMinimumWidth(240)
        self.party.currentIndexChanged.connect(lambda _i: self._party_changed())
        self.cl_bal = QLabel("")
        self.cl_bal.setObjectName("Muted")
        self.mode = QComboBox()
        self.mode.addItems(["Cash", "Bank", "Metal"])
        self.mode.currentIndexChanged.connect(lambda _i: self._mode_changed())
        cash_like = [(i, t) for i, t, g in self._accounts
                     if g in ("Cash-In-Hand", "Bank Account", "Bangkok bank saving a/c")]
        self.book = self._combo(cash_like, editable=False)
        self._book_group = {i: g for i, _t, g in self._accounts}
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 1e12)
        self.amount.setDecimals(2)
        self.amount.setGroupSeparatorShown(True)
        for w in (QLabel("Party"), self.party, self.cl_bal, QLabel("Mode"), self.mode,
                  QLabel("Cash / Bank A/c"), self.book, QLabel("Amount"), self.amount):
            row.addWidget(w)
        row.addStretch(1)
        self.outer.insertLayout(2, row)
        mrow = QHBoxLayout()
        self.metal_box = QWidget()
        ml = QHBoxLayout(self.metal_box)
        ml.setContentsMargins(0, 0, 0, 0)
        self.loc = self._combo(self._locs, editable=False)
        self.metal = self._combo(self._metals, editable=False)
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0, 1e7)
        self.weight.setDecimals(3)
        self.metal_info = QLabel("")
        self.metal_info.setObjectName("Muted")
        for w in (QLabel("Location"), self.loc, QLabel("Metal"), self.metal, QLabel("Weight"),
                  self.weight, self.metal_info):
            ml.addWidget(w)
        for w in (self.metal, self.weight):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged).connect(
                lambda *_a: self._metal_value())
        mrow.addWidget(self.metal_box)
        mrow.addStretch(1)
        self.outer.insertLayout(3, mrow)
        bl = QHBoxLayout()
        lab = QLabel("Pending bills — type how much of each this voucher clears (green), or "
                     "leave blank: the amount goes to the oldest bills first.")
        lab.setObjectName("Muted")
        bl.addWidget(lab, 1)
        auto = QPushButton("Auto (oldest first)")
        auto.clicked.connect(self._auto)
        bl.addWidget(auto)
        self.outer.insertLayout(4, bl)
        self.bills = QTableWidget(0, 7)
        self.bills.setHorizontalHeaderLabels(["Date", "Type", "Vr No", "Ref", "Bill Amount",
                                              "Pending", "Allocate"])
        self.bills.verticalHeader().setVisible(False)
        auto_fit(self.bills)
        self.outer.addWidget(self.bills, 1)
        self._bills: list = []
        self._mode_changed()

    def _party_changed(self) -> None:
        pid = self.party.currentData()
        self.bills.setRowCount(0)
        self._bills = []
        if not pid:
            self.cl_bal.setText("")
            return
        side = "receivable" if self.vr_type == "receipt" else "payable"
        with SessionLocal() as s:
            bal, dc = A.party_closing(s, pid)
            self._bills = A.pending_bills(s, pid, side)
        self.cl_bal.setText(f"Cl Bal {bal:,.2f} {dc}")
        for b, p in self._bills:
            r = self.bills.rowCount()
            self.bills.insertRow(r)
            vals = [b.on.strftime("%d-%m-%Y") if b.kind != "opening" else "opening",
                    A.vr_code(b.kind) if b.kind != "opening" else "OPN",
                    b.no if b.kind != "opening" else "", b.ref, f"{b.amount:,.2f}", f"{p:,.2f}"]
            for c, v in enumerate(vals):
                it = _item(v, right=c >= 4)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.bills.setItem(r, c, it)
            al = _item("", TINT_RECEIVE, right=True)
            self.bills.setItem(r, 6, al)

    def _auto(self) -> None:
        left = D(str(round(self.amount.value(), 2)))
        for r, (b, p) in enumerate(self._bills):
            take = min(p, left) if left > 0 else D(0)
            self.bills.item(r, 6).setText(f"{take:.2f}" if take else "")
            left -= take

    def _mode_changed(self) -> None:
        metal = self.mode.currentText() == "Metal"
        self.metal_box.setVisible(metal)
        self.book.setEnabled(not metal)
        # By the ledger's group, not its name: the cash ledger is "Cash in Hand".
        want = "Cash-In-Hand" if self.mode.currentText() == "Cash" else "Bank Account"
        i = next((k for k in range(self.book.count())
                  if self._book_group.get(self.book.itemData(k)) == want), -1)
        if i >= 0 and not metal:
            self.book.setCurrentIndex(i)

    def _metal_value(self) -> None:
        if not self.metal.currentData():
            self.metal_info.setText("")
            return
        from diagold.services import inventory as INV, production
        with SessionLocal() as s:
            fine = INV.line_fine(s, self.metal.currentData(), self.weight.value())
            rate = production.metal_price(s, self.metal.currentData(), _pydate(self.date))
        value = (D(str(self.weight.value())) * rate).quantize(D("0.01"))
        self.metal_info.setText(f"fine {fine:.3f} · rate {rate:,.2f} · value {value:,.2f}")
        self.amount.setValue(float(value))

    # -- journal / contra -------------------------------------------------
    def _build_lines(self) -> None:
        bar = QHBoxLayout()
        for label, fn in (("Add Line", self._add_line), ("Remove Line", self._remove_line)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        self.outer.insertLayout(2, bar)
        self.lines = QTableWidget(0, 4)
        self.lines.setHorizontalHeaderLabels(["Account", "Debit", "Credit", "Narration"])
        self.lines.verticalHeader().setVisible(False)
        self.lines.itemChanged.connect(lambda _i: self._totals())
        auto_fit(self.lines)
        self.outer.addWidget(self.lines, 1)
        self.line_total = QLabel("")
        self.outer.addWidget(self.line_total)
        self._add_line()
        self._add_line()

    def _add_line(self) -> None:
        r = self.lines.rowCount()
        self.lines.insertRow(r)
        items = self._accounts
        if self.vr_type == "contra":
            items = [x for x in items if x[2] in ("Cash-In-Hand", "Bank Account",
                                                  "Bangkok bank saving a/c")]
        self.lines.setCellWidget(r, 0, self._combo(items))
        for c in (1, 2, 3):
            self.lines.setItem(r, c, _item("", TINT_RECEIVE, right=c in (1, 2)))

    def _remove_line(self) -> None:
        r = self.lines.currentRow()
        if r >= 0:
            self.lines.removeRow(r)
            self._totals()

    def _line_values(self) -> list[dict]:
        out = []
        for r in range(self.lines.rowCount()):
            cb = self.lines.cellWidget(r, 0)

            def num(c):
                t = (self.lines.item(r, c).text() if self.lines.item(r, c) else "").replace(",", "")
                try:
                    return D(t) if t.strip() else D(0)
                except Exception:  # noqa: BLE001
                    return D(0)
            out.append({"account_id": cb.currentData() if cb else None, "debit": num(1),
                        "credit": num(2), "narration": self.lines.item(r, 3).text()
                        if self.lines.item(r, 3) else ""})
        return out

    def _totals(self) -> None:
        if not hasattr(self, "line_total"):
            return
        ls = self._line_values()
        dr, cr = sum(l["debit"] for l in ls), sum(l["credit"] for l in ls)
        self.line_total.setText(f"<b>Debit {dr:,.2f} · Credit {cr:,.2f}</b>"
                                + ("" if dr == cr else "  — must be equal"))

    # -- common -------------------------------------------------------------
    def refresh(self) -> None:
        with SessionLocal() as s:
            self.vr.setText(str(A.next_vr_no(s, self.vr_type)))
        if hasattr(self, "saved"):
            self._fill_saved()

    def new_voucher(self) -> None:
        self.ref.clear()
        self.narration.clear()
        if self.vr_type in ("receipt", "payment"):
            self.party.setCurrentIndex(0)
            self.amount.setValue(0)
            self.weight.setValue(0)
        else:
            self.lines.setRowCount(0)
            self._add_line()
            self._add_line()
        self.refresh()

    def save(self) -> None:
        head = {"vr_date": _pydate(self.date), "ref_no": self.ref.text().strip(),
                "narration": self.narration.text().strip()}
        lines, alloc = None, None
        if self.vr_type in ("receipt", "payment"):
            head.update(account_id=self.party.currentData(), mode=self.mode.currentText(),
                        cash_account_id=self.book.currentData(),
                        amount=D(str(round(self.amount.value(), 2))),
                        metal_id=self.metal.currentData(), location_id=self.loc.currentData(),
                        weight=D(str(round(self.weight.value(), 3))))
            alloc = {}
            for r, (b, _p) in enumerate(self._bills):
                t = self.bills.item(r, 6).text().replace(",", "").strip()
                if t:
                    alloc[b.key] = D(t)
            what = f"{A.ACC_TYPES[self.vr_type][1]} of {head['amount']:,.2f}"
        else:
            lines = self._line_values()
            what = f"{A.ACC_TYPES[self.vr_type][1]} of {len(lines)} line(s)"
        if not confirm_save(self, what):
            return
        with SessionLocal() as s:
            try:
                v = A.post_voucher(s, self.vr_type, head, lines, alloc or None,
                                   user_id=getattr(self.user, "id", None))
                s.commit()
                vid, vr = v.id, v.vr_no
            except ProductionError as exc:
                s.rollback()
                QMessageBox.warning(self, "Cannot save", str(exc))
                return
        self.new_voucher()
        self._last_id = vid
        if vid in self._saved_ids:
            self.saved.selectRow(self._saved_ids.index(vid))
        self.status.setText(f"Saved {A.ACC_TYPES[self.vr_type][1]} Vr {vr} - it is at the top "
                            "of the list below.")

    def _pick(self, title: str) -> int | None:
        with SessionLocal() as s:
            rows = []
            for v in s.scalars(select(AccountVoucher).where(AccountVoucher.vr_type == self.vr_type)
                               .order_by(AccountVoucher.vr_no.desc()).limit(300)):
                a = s.get(Account, v.account_id) if v.account_id else None
                rows.append((v.id, f"Vr {v.vr_no}   {v.vr_date:%d-%m-%Y}   "
                             f"{a.name if a else ''}   {v.mode}   {D(str(v.amount)):,.2f}"))
        if not rows:
            QMessageBox.information(self, title, "Nothing saved yet.")
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(520, 360)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        for vid, t in rows:
            it = QListWidgetItem(t)
            it.setData(Qt.ItemDataRole.UserRole, vid)
            lst.addItem(it)
        lst.setCurrentRow(0)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted or lst.currentItem() is None:
            return None
        return lst.currentItem().data(Qt.ItemDataRole.UserRole)

    def delete_voucher(self) -> None:
        vid = self._selected_saved() or self._pick("Delete — pick the voucher")
        if vid is None:
            return
        if QMessageBox.question(self, "Delete", "Delete this voucher? Its postings and bill "
                                "knock-offs go; it is kept in the deletion log.") \
                != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            A.delete_voucher(s, s.get(AccountVoucher, vid), user_id=getattr(self.user, "id", None))
            s.commit()
        self.status.setText("Deleted.")
        self._last_id = None
        self.refresh()

    def print_voucher(self) -> None:
        vid = self._selected_saved() or self._last_id or self._pick("Print — pick the voucher")
        if vid is None:
            return
        from diagold.services import documents
        from diagold.db.models import AccountEntry
        with SessionLocal() as s:
            v = s.get(AccountVoucher, vid)
            es = list(s.scalars(select(AccountEntry).where(AccountEntry.ref_kind == v.vr_type,
                                                           AccountEntry.ref_no == v.vr_no)))
            rows = "".join(f"<tr><td>{e.ledger}</td><td align=right>{D(str(e.debit)):,.2f}</td>"
                           f"<td align=right>{D(str(e.credit)):,.2f}</td></tr>" for e in es)
            html = (f"<h2>{A.ACC_TYPES[v.vr_type][1]} Voucher — Vr {v.vr_no}</h2>"
                    f"<p>Date {v.vr_date:%d-%m-%Y} · Mode {v.mode} · Ref {v.ref_no or ''}</p>"
                    "<table border=1 cellspacing=0 cellpadding=4 width=100%><tr><th>Account</th>"
                    "<th>Debit</th><th>Credit</th></tr>" + rows + "</table>"
                    + (f"<p>Metal {D(str(v.weight)):.3f} g · fine {D(str(v.fine_wt)):.3f} @ "
                       f"{D(str(v.metal_rate)):,.2f}</p>" if v.mode == "Metal" else "")
                    + f"<p>{v.narration or ''}</p>")
            path = documents.PRINT_DIR / f"{v.vr_type}_{v.vr_no}.pdf"
        documents.to_pdf(html, path)
        QMessageBox.information(self, "Print", f"Saved {path}")
