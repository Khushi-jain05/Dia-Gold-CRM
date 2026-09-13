"""Job-sheet generation: templates as data, rendered from job data (T-04).

Today the factory's job sheet is made by re-typing the system's output into a
Word template by hand. Here a template is an HTML body held in the database
with ``{{placeholders}}`` and repeating blocks; the engine fills it from the
job and prints it to PDF. When the client's Word format arrives (C-02) it is
reproduced by editing the template, not the code.

Placeholders
------------
Header:   job_no, sku, sku_desc, c_ref, ord_ref, order_no, order_date, client,
          delivery_date, metal, karat, colour, pcs, route, remark, photo,
          printed_on, printed_by, company
Blocks:   {{#steps}} seq, process, short, due_date, worker, status {{/steps}}
          {{#stones}} particulars, size, type, req_pcs, req_wt, bal_pcs,
                      bal_wt, unit {{/stones}}
          {{#findings}} particulars, pcs, weight {{/findings}}
Every seeded template is a marked PLACEHOLDER until the Word file lands.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.config import DATA_DIR
from diagold.db.models import (
    Account,
    Company,
    Job,
    ManufacturingProcess,
    Metal,
    Order,
    PrintLog,
    PrintTemplate,
    ProductSku,
    User,
)
from diagold.services import production

PRINT_DIR: Path = DATA_DIR / "prints"

_BLOCK = re.compile(r"{{#(\w+)}}(.*?){{/\1}}", re.S)
_VAR = re.compile(r"{{\s*(\w+)\s*}}")


def render(body: str, context: dict[str, Any]) -> str:
    """Fill a template body. Lists expand their block once per item; scalars
    are HTML-escaped except ``photo``, which is already an <img> tag."""
    def fill(text: str, ctx: dict[str, Any]) -> str:
        def block(m: re.Match) -> str:
            items = ctx.get(m.group(1)) or []
            return "".join(fill(m.group(2), {**ctx, **item}) for item in items)
        text = _BLOCK.sub(block, text)

        def var(m: re.Match) -> str:
            key = m.group(1)
            value = ctx.get(key, "")
            if value is None:
                return ""
            if key == "photo":
                return str(value)
            if isinstance(value, (date, datetime)):
                return value.strftime("%d-%b-%Y")
            return html.escape(str(value))
        return _VAR.sub(var, text)
    return fill(body, context)


def job_context(session: Session, job: Job, user_name: str = "") -> dict[str, Any]:
    sku = session.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
    order = session.get(Order, job.order_id) if job.order_id else None
    client = session.get(Account, job.account_id) if job.account_id else None
    metal = session.get(Metal, job.metal_id) if job.metal_id else None
    company = session.scalars(select(Company)).first()
    photo = ""
    if sku and sku.image_finished and Path(sku.image_finished).exists():
        photo = (f'<img src="file://{sku.image_finished}" width="140" '
                 f'alt="{html.escape(sku.sku_code)}">')
    elif sku and sku.image_design and Path(sku.image_design).exists():
        photo = f'<img src="file://{sku.image_design}" width="140">'
    rows = production.history_rows(session, job)
    started = {r.step.id: r for r in rows if r.issue is not None}
    steps = []
    for s in job.steps:
        p = session.get(ManufacturingProcess, s.process_id)
        r = started.get(s.id)
        status = "pending"
        if r is not None:
            status = "received" if r.receive is not None else "issued"
        steps.append({
            "seq": s.seq, "process": p.name if p else "", "short": (p.short_code if p else ""),
            "due_date": s.due_date, "worker": r.worker if r else "", "status": status,
        })
    stones = []
    for row in production.bag_ledger(session, job):
        req_pcs, req_wt = row["req"]
        bal_pcs, bal_wt = row["bal"]
        stones.append({
            "particulars": row.line.particulars, "size": row.line.size,
            "type": row.line.s_type, "unit": row.line.unit,
            "req_pcs": req_pcs, "req_wt": req_wt, "bal_pcs": bal_pcs, "bal_wt": bal_wt,
        })
    return {
        "job_no": job.job_no, "sku": sku.sku_code if sku else "",
        "sku_desc": sku.description if sku else "", "c_ref": job.c_ref,
        "ord_ref": order.ref if order else "", "order_no": order.order_no if order else "",
        "order_date": order.order_date if order else None,
        "client": client.name if client else "stock",
        "delivery_date": job.prod_del_date or (order.delivery_date if order else None),
        "metal": metal.name if metal else "", "karat": metal.print_on_tag if metal else "",
        "colour": job.colour, "pcs": job.pcs, "route": production.route_string(session, job),
        "remark": job.remark or (order.remark if order else ""), "photo": photo,
        "printed_on": datetime.now().strftime("%d-%b-%Y %H:%M"), "printed_by": user_name,
        "company": company.name if company else "Dia Gold",
        "steps": steps, "stones": stones,
        # Findings master is retired (S1 D2); the block stays so the Word
        # format can be reproduced once findings return.
        "findings": [],
    }


def templates_for(session: Session, kind: str) -> list[PrintTemplate]:
    return list(session.scalars(
        select(PrintTemplate).where(PrintTemplate.kind == kind,
                                    PrintTemplate.is_active.is_(True))
        .order_by(PrintTemplate.is_placeholder, PrintTemplate.name)
    ))


def render_job(session: Session, job: Job, template: PrintTemplate,
               user_name: str = "") -> str:
    return render(template.body, job_context(session, job, user_name))


def to_pdf(html_body: str, path: Path) -> Path:
    """Print HTML to a PDF file. Needs a Qt application to exist."""
    from PySide6.QtGui import QPageSize, QTextDocument
    from PySide6.QtPrintSupport import QPrinter

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = QTextDocument()
    doc.setHtml(html_body)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setOutputFileName(str(path))
    doc.print_(printer)
    return path


def print_job(session: Session, job: Job, template: PrintTemplate,
              user_id: int | None = None) -> Path:
    """Render, write the PDF, and log what was printed by whom (T-04 req 4)."""
    user = session.get(User, user_id) if user_id else None
    body = render_job(session, job, template, user.full_name if user else "")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = PRINT_DIR / f"{template.kind}_{job.job_no}_{stamp}.pdf"
    to_pdf(body, path)
    session.add(PrintLog(user_id=user_id, kind=template.kind, template_id=template.id,
                         job_id=job.id, order_id=job.order_id, file_path=str(path)))
    session.flush()
    return path


# --------------------------------------------------------------------------
# Placeholder templates - replaced field-for-field once the Word file lands
# --------------------------------------------------------------------------
_BANNER = ('<p style="color:#8F3A2C;font-weight:bold;border:1px solid #8F3A2C;'
           'padding:4px">PLACEHOLDER LAYOUT — awaiting the client\'s Word format '
           '(C-02). Fields are correct; the arrangement is not final.</p>')

_HEAD = """
<table width="100%" cellspacing="0" cellpadding="3">
<tr><td width="70%">
  <h2 style="margin:0">{{company}} — __TITLE__</h2>
  <p style="margin:2px 0"><b>Job No {{job_no}}</b> &nbsp; SKU {{sku}} &nbsp; {{sku_desc}}</p>
  <p style="margin:2px 0">Client: <b>{{client}}</b> &nbsp; Order {{order_no}} dt {{order_date}}
     &nbsp; C-Ref {{c_ref}} &nbsp; Ord-Ref {{ord_ref}}</p>
  <p style="margin:2px 0">Metal: {{metal}} &nbsp; Karat {{karat}} &nbsp; Colour {{colour}}
     &nbsp; Pcs <b>{{pcs}}</b> &nbsp; Delivery <b>{{delivery_date}}</b></p>
  <p style="margin:2px 0">Route: <tt>{{route}}</tt></p>
</td><td width="30%" align="right">{{photo}}</td></tr>
</table>
"""

def _head(title: str) -> str:
    return _HEAD.replace("__TITLE__", title)


_STEPS = """
<h3>Process route</h3>
<table width="100%" border="1" cellspacing="0" cellpadding="3">
<tr style="background:#eee"><th>#</th><th>Process</th><th>Due</th><th>Worker</th>
<th>Issued G / N</th><th>Received G / N</th><th>Loss</th><th>Sign</th></tr>
{{#steps}}<tr><td>{{seq}}</td><td>{{process}}</td><td>{{due_date}}</td><td>{{worker}}</td>
<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>{{/steps}}
</table>
"""

_STONES = """
<h3>Stone requirements</h3>
<table width="100%" border="1" cellspacing="0" cellpadding="3">
<tr style="background:#eee"><th>Stone</th><th>Size</th><th>Type</th>
<th>Req Pcs</th><th>Req Wt</th><th>In bag Pcs</th><th>In bag Wt</th><th>Unit</th></tr>
{{#stones}}<tr><td>{{particulars}}</td><td>{{size}}</td><td>{{type}}</td>
<td align="right">{{req_pcs}}</td><td align="right">{{req_wt}}</td>
<td align="right">{{bal_pcs}}</td><td align="right">{{bal_wt}}</td><td>{{unit}}</td></tr>{{/stones}}
</table>
"""

_FOOT = '<p style="color:#666;font-size:8pt">Printed {{printed_on}} by {{printed_by}}</p>'

DEFAULT_TEMPLATES: dict[str, tuple[str, str]] = {
    "job_sheet": ("Job Sheet (placeholder)",
                  _BANNER + _head("Job Sheet") + _STEPS + _STONES
                  + "<p>Remark: {{remark}}</p>" + _FOOT),
    "job_request": ("Job Request (placeholder)",
                    _BANNER + _head("Job Request")
                    + "<p>Requested for production. Remark: {{remark}}</p>" + _FOOT),
    "stone_req": ("Stone Requirements (placeholder)",
                  _BANNER + _head("Stone Requirements") + _STONES + _FOOT),
    "finding_req": ("Finding Requirements (placeholder)",
                    _BANNER + _head("Finding Requirements")
                    + '<table width="100%" border="1" cellspacing="0" cellpadding="3">'
                      '<tr style="background:#eee"><th>Finding</th><th>Pcs</th><th>Weight</th></tr>'
                      '{{#findings}}<tr><td>{{particulars}}</td><td>{{pcs}}</td>'
                      '<td>{{weight}}</td></tr>{{/findings}}</table>'
                      "<p><i>The Findings master is retired (Session 1, D2); this "
                      "block fills once findings are back in scope.</i></p>" + _FOOT),
    "blank_front": ("Blank Process Sheet (placeholder)",
                    _BANNER + _head("Process Sheet") + _STEPS + _FOOT),
    "blank_back": ("Blank Process Sheet Back (placeholder)",
                   _BANNER + '<h2>Job {{job_no}} — notes</h2>'
                   '<table width="100%" border="1" cellspacing="0" cellpadding="14">'
                   + "".join('<tr><td>&nbsp;</td></tr>' for _ in range(12))
                   + "</table>" + _FOOT),
}


def seed_templates(session: Session) -> None:
    """One placeholder per print kind, added only where the kind has none."""
    existing = set(session.scalars(select(PrintTemplate.kind)).all())
    for kind, (name, body) in DEFAULT_TEMPLATES.items():
        if kind in existing:
            continue
        session.add(PrintTemplate(name=name, kind=kind, body=body,
                                  is_placeholder=True, is_active=True))
