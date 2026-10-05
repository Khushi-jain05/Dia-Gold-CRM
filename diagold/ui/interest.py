"""Interest (5 Oct §4.2 More ▸ Interest Calculations, Exception ▸ Interest on
Cost / Sales; T-10). Built from the legacy menu; whether and how the client
uses it is to be confirmed (Q5) - so it is a report only, nothing is posted.

* Interest Receivable / Payable: on each bill outstanding past its credit
  days plus a grace, pending x rate % p.a. x overdue days / 365.
* Interest on Cost / on Sales: on each piece in stock, its cost (or tag
  price) x rate % p.a. x days in stock / 365.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from diagold.ui.reports import Col, ReportSpec, ReportWidget, static

D = Decimal


def bill_interest(s, d0: date, d1: date, side: str, rate: Decimal, grace: int) -> list[dict]:
    from diagold.services import accounts as A
    rows = []
    for r in A.outstanding(s, d0, d1, side=side):
        if r["c_day"] is None or r["pnd_amt"] <= 0:
            continue
        over = r["c_day"] - (r["credit_days"] or 0) - grace
        if over <= 0:
            continue
        interest = (r["pnd_amt"] * rate / 100 * over / 365).quantize(D("0.01"))
        rows.append({**r, "over_days": over, "rate": rate, "interest": interest})
    return rows


def stock_interest(s, d0: date, d1: date, basis: str, rate: Decimal) -> list[dict]:
    from diagold.services import manufacturing as MF
    rows = []
    for r in MF.ready_stock(s, d1):
        since = r["date"] or d1
        days = max((d1 - since).days, 0)
        amount = r["cost"] if basis == "cost" else r["price"]
        rows.append({**r, "days": days, "base": amount, "rate": rate,
                     "interest": (amount * rate / 100 * days / 365).quantize(D("0.01"))})
    return rows


class InterestWidget(QWidget):
    """Rate % p.a. (and grace days on bills) above the shared report grid."""

    def __init__(self, kind: str, user=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Interest rate % p.a."))
        self.rate = QDoubleSpinBox()
        self.rate.setRange(0, 100)
        self.rate.setValue(18.0)
        row.addWidget(self.rate)
        self.grace = QSpinBox()
        self.grace.setRange(0, 365)
        if kind in ("receivable", "payable"):
            row.addWidget(QLabel("Grace days after credit days"))
            row.addWidget(self.grace)
        row.addStretch(1)
        lay.addLayout(row)
        m = lambda k, l: Col(k, l, "measure", 2, total=True)      # noqa: E731
        if kind in ("receivable", "payable"):
            cols = [Col("party", "PARTY"), Col("date", "DATE"), Col("vrtype", "TYPE"),
                    Col("vrno", "VR NO"), m("pnd_amt", "PENDING"), Col("c_day", "DAYS", "measure", 0),
                    Col("credit_days", "CR DAYS", "measure", 0),
                    Col("over_days", "OVERDUE DAYS", "measure", 0), Col("rate", "RATE %", "measure", 2),
                    m("interest", "INTEREST")]
            query = lambda s, a, b, **_k: bill_interest(                     # noqa: E731
                s, a, b, kind, D(str(self.rate.value())), self.grace.value())
            title = "Interest " + ("Receivable" if kind == "receivable" else "Payable")
        else:
            cols = [Col("stock_no", "STOCK NO"), Col("sku", "SKU"), Col("location", "LOCATION"),
                    Col("date", "IN STOCK FROM"), Col("days", "DAYS", "measure", 0),
                    m("base", "COST" if kind == "cost" else "PRICE"),
                    Col("rate", "RATE %", "measure", 2), m("interest", "INTEREST")]
            query = lambda s, a, b, **_k: stock_interest(                    # noqa: E731
                s, a, b, kind, D(str(self.rate.value())))
            title = "Interest on " + ("Cost" if kind == "cost" else "Sales")
        spec = ReportSpec(key=f"interest_{kind}", title=title, columns=static(cols), query=query,
                          date_mode="to", group_by="party" if kind in ("receivable", "payable")
                          else None,
                          note="Built from the legacy menu; how the client charges interest is "
                               "to be confirmed (Q5) - a report only, nothing is posted. "
                               "Change the rate / grace and press Run.")
        self.report = ReportWidget(spec, user)
        lay.addWidget(self.report, 1)
