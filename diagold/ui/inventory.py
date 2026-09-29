"""Inventory ▸ Metal and Inventory ▸ Stone (28 Sept §4.11-4.12, T-01).

Each is a submenu of the top menu, like the legacy sub-menu; every voucher
opens in its own tab. Purchase, Issue Outside / Worker and
Receipt are built on one voucher table (see services.inventory); Stone ▸
Issue On Job Card is the Production-Planning screen itself. Items the client
has not yet explained (Issue On Tree, Conversion, Bhav Cut …, C-04) open a
page that says so rather than guessing.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from diagold.db.models import Account, InvVoucher, InvVoucherLine, Location, Metal, StoneSku
from diagold.services import inventory as INV
from diagold.ui.crud import ChildSpec, CrudSpec, CrudWidget, Field

_account_label = lambda a: f"{a.code} - {a.name}"          # noqa: E731
_location_label = lambda l: f"{l.code} - {l.name}"         # noqa: E731
_metal_label = lambda m: f"{m.code} - {m.name}".strip(" -")  # noqa: E731
_stone_label = lambda s: s.sku_code                        # noqa: E731


def _dec(v) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else Decimal("0")


def _summary(material: str):
    def fn(rows: list[dict]) -> str:
        wt = sum((_dec(r.get("weight")) for r in rows), Decimal("0"))
        amt = sum((_dec(r.get("pcs") if (r.get("unit") or "").lower().startswith("pc")
                        else r.get("weight")) * _dec(r.get("price")) for r in rows),
                  Decimal("0"))
        pcs = sum(int(r.get("pcs") or 0) for r in rows)
        unit = "g" if material == "metal" else "ct"
        return f"{len(rows)} line(s) · {pcs} pcs · {wt:.3f} {unit} · amount {amt:,.2f}"
    return fn


def _fill_weight_amount(grid, row: int, _value) -> None:
    """Amount follows weight x price while typing (recomputed on save too)."""
    unit = (grid.cell_value(row, "unit") or "").lower()
    qty = grid.cell_value(row, "pcs") if unit.startswith("pc") else grid.cell_value(row, "weight")
    grid.set_cell_value(row, "amount", _dec(qty) * _dec(grid.cell_value(row, "price")))


def voucher_spec(vr_type: str) -> CrudSpec:
    vt = INV.VOUCHER_TYPES[vr_type]
    metal = vt.material == "metal"

    def prepare(values: dict, children: dict, session) -> None:
        if not values.get("vr_no"):
            values["vr_no"] = INV.next_vr_no(session, vr_type)
        for n, r in enumerate(children.get("lines", []), start=1):
            r["sno"] = n
            INV.fill_line(session, vr_type, r)

    def validate(values: dict, children: dict) -> str | None:
        from diagold.db.session import SessionLocal
        with SessionLocal() as s:
            return INV.check_lines(s, vr_type, values.get("account_id"),
                                   children.get("lines", []))

    def warn(values: dict, children: dict, session) -> str | None:
        short = INV.shortfalls(session, vr_type, children.get("lines", []),
                               bool(values.get("is_opening")))
        if not short or INV.negative_mode(session) != "warn":
            return None
        return "This takes stock below zero:\n" + "\n".join(short)

    def saved(v, _children, session) -> None:
        INV.post_voucher(session, v)

    def before_delete(v, session) -> None:
        INV.delete_voucher(session, v)

    line_fields = [
        Field("sno", "SNo", type="int", default=1),
        Field("location_id", "Location", type="fk", fk_model=Location,
              fk_label=_location_label),
        Field("mt_type", "Type", type="choice", choices=["Actual"], default="Actual"),
    ]
    if metal:
        line_fields += [
            Field("metal_id", "Metal", type="fk", fk_model=Metal, fk_label=_metal_label),
            Field("colour", "Colour", type="choice", choices=["Y", "W", "R", ""], default="Y"),
            Field("pcs", "Pcs", type="int"),
            Field("weight", "Weight (g)", type="float", decimals=3,
                  on_change=_fill_weight_amount),
            Field("fine_wt", "Fine", type="float", decimals=3, readonly=True),
            Field("price", "Price", type="float", decimals=2, on_change=_fill_weight_amount),
            Field("unit", "Unit", type="choice", choices=["Gms"], default="Gms"),
            Field("amount", "Amount", type="float", decimals=2, readonly=True),
        ]
        if vr_type == "metal_receipt":
            line_fields += [
                Field("wastage_pct", "Wastage %", type="float", decimals=3),
                Field("wastage_wt", "Wastage Wt", type="float", decimals=3),
            ]
        if vr_type == "metal_issue":
            line_fields += [Field("job_no", "Job No", type="int")]
    else:
        line_fields += [
            Field("stone_sku_id", "SSKU", type="fk", fk_model=StoneSku, fk_label=_stone_label),
            Field("particulars", "Particulars"),
            Field("size", "Size"),
            Field("pcs", "Pcs", type="int", on_change=_fill_weight_amount),
            Field("weight", "Weight (ct)", type="float", decimals=3,
                  on_change=_fill_weight_amount),
            Field("price", "Price", type="float", decimals=2, on_change=_fill_weight_amount),
            Field("unit", "Per", type="choice", choices=["Cts", "Pcs"], default="Cts"),
            Field("amount", "Amount", type="float", decimals=2, readonly=True),
            Field("s_type", "S Type"),
        ]
    line_fields += [Field("remark", "Remark")]

    head = [
        Field("vr_no", "Vr No", type="int", readonly=True),
        Field("vr_date", "Date", type="date", default=date.today, required=True),
        Field("account_id", "Supplier" if vt.party == "supplier" else "Account (worker)",
              type="fk", fk_model=Account, fk_label=_account_label, required=True),
        Field("ref_no", "Ref No"),
    ]
    if vt.party == "supplier":
        head += [Field("currency_code", "Currency", type="choice",
                       choices=["INR", "USD", "AED", "EUR"], default="INR", in_list=False),
                 Field("salesperson", "Salesperson", in_list=False),
                 Field("place_of_supply", "Place of Supply", in_list=False)]
    if vr_type in ("metal_issue", "stone_issue"):
        head += [Field("is_opening", "Opening", type="bool", default=False, in_list=False,
                       help_text="The karigar already held this when the system started - "
                                 "no location is reduced (assumption, 28 Sept C-04)."),
                 Field("touch_xray", "Touch / X-Ray", type="bool", default=False,
                       in_list=False),
                 Field("create_os", "Create O/S", type="bool", default=False, in_list=False)]
    if vr_type in ("metal_receipt", "stone_receipt"):
        head += [Field("department", "Department", in_list=False),
                 Field("recovery", "Recovery Vr", type="bool", default=False, in_list=False),
                 Field("recovery_adj", "Recovery Adj. Vr", type="bool", default=False,
                       in_list=False)]
    head += [
        Field("remark", "Narration", in_list=False),
        Field("lines", "Lines", type="child",
              help_text=("Each line leaves its Location." if vt.direction < 0 else
                         "Each line comes into its Location.")
              + (" Fine = weight × the metal's title, worked out on save."
                 if metal else " Price defaults to the Stone SKU's cost price.")
              + (" Wastage % of the weight received is allowed to the karigar "
                 "(how wastage is settled: 28 Sept C-04)." if vr_type == "metal_receipt"
                 else ""),
              child=ChildSpec(model=InvVoucherLine, fk_attr="voucher_id", order_by="sno",
                              summary=_summary(vt.material), height=200,
                              row_template={"mt_type": "Actual",
                                            "unit": "Gms" if metal else "Cts"},
                              fields=line_fields)),
    ]
    def print_voucher(widget, selected) -> None:
        """Print the selected voucher to PDF (28 Sept T-01: every voucher prints)."""
        from PySide6.QtWidgets import QMessageBox

        from diagold.db.session import SessionLocal
        from diagold.services import documents
        if selected is None:
            QMessageBox.information(widget, "Print", "Select a voucher first.")
            return
        with SessionLocal() as s:
            v = s.get(InvVoucher, selected.id)
            acct = s.get(Account, v.account_id) if v.account_id else None
            rows = []
            for l in v.lines:
                loc = s.get(Location, l.location_id) if l.location_id else None
                item = (s.get(Metal, l.metal_id).name if l.metal_id else
                        s.get(StoneSku, l.stone_sku_id).sku_code if l.stone_sku_id
                        else l.particulars)
                rows.append(f"<tr><td>{l.sno}</td><td>{loc.name if loc else ''}</td>"
                            f"<td>{item}</td><td>{l.size or ''}</td><td align=right>{l.pcs}</td>"
                            f"<td align=right>{_dec(l.weight):.3f}</td>"
                            f"<td align=right>{_dec(l.fine_wt):.3f}</td>"
                            f"<td align=right>{_dec(l.price):,.2f}</td>"
                            f"<td align=right>{_dec(l.amount):,.2f}</td></tr>")
            html = (f"<h2>{vt.title} — Vr {v.vr_no}</h2>"
                    f"<p>Date {v.vr_date:%d-%m-%Y} · {acct.name if acct else ''}"
                    f"{' · Ref ' + v.ref_no if v.ref_no else ''}</p>"
                    "<table border=1 cellspacing=0 cellpadding=4><tr><th>#</th><th>Location"
                    "</th><th>Item</th><th>Size</th><th>Pcs</th><th>Weight</th><th>Fine</th>"
                    "<th>Price</th><th>Amount</th></tr>" + "".join(rows) + "</table>"
                    f"<p>{v.remark or ''}</p>")
            path = documents.PRINT_DIR / f"{vr_type}_{v.vr_no}.pdf"
        documents.to_pdf(html, path)
        QMessageBox.information(widget, "Print", f"Saved {path}")

    return CrudSpec(
        key=f"inventory.{vr_type}", title=vt.title, model=InvVoucher, fields=head,
        extra_buttons=[("Print", print_voucher)],
        order_by="-vr_no", date_field="vr_date", search_hint="Search by ref, narration…",
        editable=False, before_save=prepare, after_save=saved, validate=validate,
        warn=warn, before_delete=before_delete, fixed={"vr_type": vr_type},
        form_width=1180, singular_title=vt.title,
    )


class _NotYet(QWidget):
    def __init__(self, title: str, why: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        h = QLabel(title)
        h.setObjectName("H1")
        lay.addWidget(h)
        t = QLabel(why)
        t.setWordWrap(True)
        t.setObjectName("Muted")
        lay.addWidget(t)
        lay.addStretch(1)


_UNEXPLAINED = ("Opened on the 28 Sept call but not explained, so it is not built on a "
                "guess. It is on the Inventory walkthrough agenda (C-04) - once the client "
                "says what it does and what it posts, it becomes a voucher like the others.")


# Inventory ▸ Metal and Inventory ▸ Stone open as submenus of the top menu,
# in the legacy order - each voucher in its own full-width tab, so every
# column of its grid is in view (29 Sept: the side list squeezed them).
SUBMENUS: dict[str, list[tuple[str, str]]] = {
    "inventory.metal": [
        ("metal_purchase", "Purchase"), ("_load", "Load Metal"),
        ("metal_issue", "Issue Outside / Worker"), ("_tree", "Issue On Tree"),
        ("metal_receipt", "Receipt"), ("_jobcard", "Issue On Job Card"),
        ("_conv", "Conversion"), ("_adj", "Adjustment"), ("_daybook", "DayBook"),
        ("_recov", "Worker Recovery"), ("_wip", "WIP Rtn"), ("_lena", "Bhav Cut [Lena]"),
        ("_dena", "Bhav Cut [Dena]"), ("_reports", "Reports"),
    ],
    "inventory.stone": [
        ("stone_purchase", "Purchase"), ("_load", "Load Stone"),
        ("stone_issue", "Issue Outside / Worker"), ("stone_receipt", "Receipt"),
        ("_jobcard", "Issue On Job Card"), ("_extra", "Extra Issue On Job Card"),
        ("_wip", "WIP Rtn"), ("_daybook", "Day Book"), ("_reports", "Reports"),
    ],
}
# Sub-screens that are only a note until the client explains them (C-04).
PENDING_EXPLANATION = {"_load", "_tree", "_conv", "_adj", "_recov", "_wip", "_lena",
                       "_dena", "_extra"}


def sub_key(parent: str, key: str) -> str:
    return f"{parent}.{key}"


def sub_labels() -> dict[str, str]:
    """menu key -> tab label, e.g. inventory.metal.metal_purchase -> Metal Purchase."""
    out = {}
    for parent, items in SUBMENUS.items():
        head = "Metal" if parent.endswith("metal") else "Stone"
        for key, label in items:
            out[sub_key(parent, key)] = f"{head} {label}"
    return out


def build_screen(menu_key: str, user=None) -> QWidget:
    """The screen for one Inventory sub-menu item."""
    parent, key = menu_key.rsplit(".", 1)
    material = "metal" if parent.endswith("metal") else "stone"
    label = dict(SUBMENUS[parent])[key]
    rights = getattr(user, "rights", None)
    if key in INV.VOUCHER_TYPES:
        return CrudWidget(voucher_spec(key), rights=rights)
    if key == "_jobcard" and material == "stone":
        from diagold.ui.specs import SPECS
        return CrudWidget(SPECS["production_planning.stone_issue"], rights=rights)
    if key == "_daybook":
        from diagold.ui.reports import ReportWidget, build_specs
        return ReportWidget(build_specs()[f"inv_{material}_day_book"], user)
    if key == "_reports":
        from diagold.ui.reports import ReportsHub
        return ReportsHub(user, first="metal_analysis" if material == "metal"
                          else "job_card_analysis_stone")
    if key == "_jobcard":
        return _NotYet(label, "Metal against a job card is issued with the job step "
                              "itself (Job History ▸ + Issue, or Show Pending for several "
                              "jobs on one voucher). A separate metal voucher against a "
                              "job card waits for the client to say how it differs "
                              "(28 Sept C-04).")
    if key == "_extra":
        return _NotYet(label, "Asked at 36:25 on the 28 Sept call; the answer was not "
                              "audible (Q8). " + _UNEXPLAINED)
    return _NotYet(label, _UNEXPLAINED)
