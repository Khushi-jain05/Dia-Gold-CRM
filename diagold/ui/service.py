"""Register a Complaint and Gatepass helpers (5 Oct §4.14, T-10)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QInputDialog, QLabel, QMessageBox
from sqlalchemy import select

from diagold.db.models import Account, Complaint, GatePass, Job, StockItem
from diagold.db.session import SessionLocal
from diagold.ui.reports import Col, ReportSpec, ReportWidget, static


def complaint_lookup(widget, comp) -> None:
    """JOB# / STOCK# / SKU -> the job's process history and the piece's
    voucher history."""
    from diagold.services import production, sales
    from diagold.ui.production import show_in_dialog
    if comp is None:
        QMessageBox.information(widget, "Lookup", "Select a complaint first.")
        return
    parts = []
    with SessionLocal() as s:
        c = s.get(Complaint, comp.id)
        item = s.scalar(select(StockItem).where(StockItem.stock_no == c.stock_no)) \
            if c.stock_no else None
        job = s.scalar(select(Job).where(Job.job_no == c.job_no)) if c.job_no else None
        if job is None and item is not None and item.job_id:
            job = s.get(Job, item.job_id)
        if job is not None:
            parts.append(f"<h3>Job {job.job_no} - process history</h3><table border=1 "
                         "cellspacing=0 cellpadding=3><tr><th>Process</th><th>Worker</th>"
                         "<th>Issued</th><th>Received</th><th>Loss</th></tr>")
            for r in production.history_rows(s, job):
                parts.append(f"<tr><td>{r.process.name if r.process else ''}</td>"
                             f"<td>{r.worker}</td>"
                             f"<td>{r.issue.vr_date if r.issue else ''}</td>"
                             f"<td>{r.receive.vr_date if r.receive else ''}</td>"
                             f"<td>{r.loss if r.loss is not None else ''}</td></tr>")
            parts.append("</table>")
        if item is not None:
            parts.append(f"<h3>Stock No {item.stock_no} - voucher history</h3><table border=1 "
                         "cellspacing=0 cellpadding=3><tr><th>Date</th><th>Type</th>"
                         "<th>Vr No</th><th>Party</th><th>Location</th></tr>")
            for h in sales.piece_history(s, item):
                parts.append(f"<tr><td>{h['date']}</td><td>{h['vrtype']}</td><td>{h['vrno']}"
                             f"</td><td>{h['party']}</td><td>{h['location']}</td></tr>")
            parts.append("</table>")
    lbl = QLabel("".join(parts) or "No Job # or Stock # on this complaint (or not found).")
    lbl.setWordWrap(True)
    show_in_dialog(widget, lbl, "Complaint - history", (760, 520))


def complaint_close(widget, comp) -> None:
    if comp is None:
        return
    text, ok = QInputDialog.getText(widget, "Close complaint", "Resolution:")
    if not ok:
        return
    with SessionLocal() as s:
        c = s.get(Complaint, comp.id)
        c.status, c.closed_on, c.resolution = "Closed", date.today(), text.strip()[:200]
        s.commit()
    widget.reload()


def _complaint_rows(s, a, b, **_k) -> list[dict]:
    rows = []
    for c in s.scalars(select(Complaint).where(Complaint.comp_date >= a,
                                               Complaint.comp_date <= b)
                       .order_by(Complaint.comp_no)):
        acct = s.get(Account, c.account_id) if c.account_id else None
        for l in c.lines or [None]:
            rows.append({"comp_no": c.comp_no, "date": c.comp_date, "from": c.comp_from,
                         "account": acct.name if acct else "", "job_no": c.job_no or "",
                         "stock_no": c.stock_no or "", "sku": c.sku,
                         "complaint": c.complaint, "comp_type": l.comp_type if l else "",
                         "detail": l.complaint if l else "",
                         "person": l.related_person if l else "", "status": c.status,
                         "closed_on": c.closed_on, "resolution": c.resolution,
                         "_negative": c.status == "Open"})
    return rows


def complaint_register(widget, _sel) -> None:
    from diagold.ui.production import show_in_dialog
    spec = ReportSpec(
        key="complaint_register", title="Complaint Register",
        columns=static([Col("comp_no", "COMP NO"), Col("date", "DATE"), Col("from", "FROM"),
                        Col("account", "ACCOUNT"), Col("job_no", "JOB#"),
                        Col("stock_no", "STOCK#"), Col("sku", "SKU"),
                        Col("complaint", "COMPLAINT"), Col("comp_type", "COMP. TYPE"),
                        Col("detail", "DETAIL"), Col("person", "RELATED PERSON"),
                        Col("status", "STATUS"), Col("closed_on", "CLOSED"),
                        Col("resolution", "RESOLUTION")]),
        query=_complaint_rows, group_by="status", filter_column="status",
        negative_key="_negative", note="Open complaints in red.")
    show_in_dialog(widget, ReportWidget(spec), spec.title, (1200, 600))


def gatepass_photo(widget, gp) -> None:
    if gp is None:
        QMessageBox.information(widget, "Photo", "Select a gate pass first.")
        return
    from diagold.ui.attachments import AttachDocDialog
    AttachDocDialog("gatepass", gp.gp_no, f"Gate Pass {gp.gp_no}", parent=widget).exec()


def gatepass_print(widget, gp) -> None:
    from diagold.services import attachments, documents
    if gp is None:
        QMessageBox.information(widget, "Print", "Select a gate pass first.")
        return
    with SessionLocal() as s:
        g = s.get(GatePass, gp.id)
        photos = [a.file_path for a in attachments.list_for(s, "gatepass", g.gp_no)]
        rows = [("GP #", g.gp_no), ("Date", f"{g.gp_date:%d-%m-%Y}"),
                ("Box Weight", f"{Decimal(str(g.box_weight or 0)):.3f}"), ("Box Pcs", g.box_pcs),
                ("Box Description", g.box_description), ("Destination", g.destination),
                ("Delivery Remark", g.delivery_remark), ("Packed By", g.packed_by),
                ("Delivered By", g.delivered_by), ("Sealed Number", g.sealed_no),
                ("Received By", g.received_by),
                ("Received On", f"{g.received_date:%d-%m-%Y}" if g.received_date else ""),
                ("Receipt Remark", g.receipt_remark),
                ("Confirmed", "YES" if g.confirmed else "")]
        html = ("<h2>Gate Pass</h2><table border=1 cellspacing=0 cellpadding=4>"
                + "".join(f"<tr><th align=left>{k}</th><td>{v}</td></tr>" for k, v in rows)
                + "</table>" + "".join(f"<p><img src='{p}' height=160></p>" for p in photos))
        path = documents.PRINT_DIR / f"gatepass_{g.gp_no}.pdf"
    documents.to_pdf(html, path)
    QMessageBox.information(widget, "Print", f"Saved {path}")


def gatepass_register(widget, _sel) -> None:
    from diagold.ui.production import show_in_dialog

    def rows(s, a, b, **_k):
        return [{"gp_no": g.gp_no, "date": g.gp_date, "destination": g.destination,
                 "box_pcs": g.box_pcs, "box_weight": Decimal(str(g.box_weight or 0)),
                 "packed_by": g.packed_by, "delivered_by": g.delivered_by,
                 "sealed_no": g.sealed_no, "received_by": g.received_by,
                 "confirmed": "YES" if g.confirmed else "", "_negative": not g.confirmed}
                for g in s.scalars(select(GatePass).where(GatePass.gp_date >= a,
                                                          GatePass.gp_date <= b)
                                   .order_by(GatePass.gp_no))]
    spec = ReportSpec(
        key="gatepass_register", title="Gate Pass Register",
        columns=static([Col("gp_no", "GP#"), Col("date", "DATE"),
                        Col("destination", "DESTINATION"),
                        Col("box_pcs", "BOX PCS", "measure", 0, total=True),
                        Col("box_weight", "BOX WT", "measure", 3, total=True),
                        Col("packed_by", "PACKED BY"), Col("delivered_by", "DELIVERED BY"),
                        Col("sealed_no", "SEALED NO"), Col("received_by", "RECEIVED BY"),
                        Col("confirmed", "CONFIRMED")]),
        query=rows, filter_column="destination", negative_key="_negative",
        note="Not yet confirmed received in red.")
    show_in_dialog(widget, ReportWidget(spec), spec.title, (1100, 560))
