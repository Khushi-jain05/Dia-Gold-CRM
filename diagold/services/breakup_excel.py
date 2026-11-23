"""The client's breakup Excel for a quotation and a sale invoice (23 Nov,
"Sample Invoice Quotation & sale invoice.xlsx").

Row 1 one line: Invoice No / Date / Client / CURR / Exc Rate. Row 2 the
three stone heads over their columns. Row 3: Sno, Image, SKU, GrossWt, Metal,
NetWt, FineWt, Mt Price, Mt Amount, then DIAMOND / POLKI / COLOR STONE blocks
of (name + size, Pcs, Cts, Price, Amount) side by side, Labour, TOTAL and
TOT FINE. Each piece takes five rows at least (one per stone when it has
more): its SKU, then StockID / the Stock No / Snap under it, the photo in
Image. Every amount is a live formula as in the sample - NetWt = GrossWt -
(the piece's carats / 5), Mt Amount = NetWt x Mt Price, a stone's Amount =
Cts x Price, Labour = NetWt x the labour rate, TOTAL = metal + stones +
labour. A SUM row under the pieces and the metal-rate note at the foot.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

BLOCKS = ("DIAMOND", "POLKI", "COLOR STONE")
PIECE_ROWS = 5


def _f(v: Any) -> float:
    try:
        return float(Decimal(str(v or 0)))
    except Exception:  # noqa: BLE001 - a stray text in a number field
        return 0.0


def stone_name(st: dict[str, Any]) -> str:
    """'POLKI 16-18', 'DIA. MIX', 'daank -' - the stone and its size, as the
    sample lists them."""
    label = (st.get("stone") or st.get("label") or "").strip()
    size = (st.get("size") or "").strip()
    if size and (label.endswith(" " + size) or label == size):
        return label
    return f"{label} {size or '-'}".strip()


def write(path: str, header: str, pieces: list[dict[str, Any]], *,
          title: str = "Sheet1", images: bool = True) -> None:
    """``pieces``: dicts with sno, sku, stock_no, photo, gross, metal, fine,
    metal_rate, labour_rate, labour_per ('gm' / 'pcs'), labour (amount, used
    when not per gram), extra (setting + other, added to the TOTAL), tag and
    stones (label / stone, size, s_type, pcs, weight, price, unit)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    from diagold.services.sales import stone_block

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E4E7EC")
    thin = Side(style="thin", color="B0B7C3")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

    piece_heads = ["Sno", "Image", "SKU", "GrossWt", "Metal", "NetWt", "FineWt", "Mt Price",
                   "Mt Amount"]
    start: dict[str, int] = {}
    col = len(piece_heads) + 1
    heads = list(piece_heads)
    for name in BLOCKS:
        start[name] = col
        heads += [name, "Pcs", "Cts", "Price", "Amount"]
        col += 5
    c_lab, c_tot, c_fine = col, col + 1, col + 2
    heads += ["Labour", "TOTAL", "TOT FINE"]
    last = c_fine

    ws.cell(1, 1, header).font = bold
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last)
    for name in BLOCKS:
        ws.cell(2, start[name], name)
        ws.merge_cells(start_row=2, start_column=start[name], end_row=2,
                       end_column=start[name] + 4)
    for c, h in enumerate(heads, start=1):
        ws.cell(3, c, h)
    for r in (2, 3):
        for c in range(1, last + 1):
            cell = ws.cell(r, c)
            cell.font = bold
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = box

    row = 4
    for p in pieces:
        by = {name: [st for st in p.get("stones") or [] if stone_block(st) == name]
              for name in BLOCKS}
        n = max([PIECE_ROWS] + [len(x) for x in by.values()])
        r0, r1 = row, row + n - 1
        ws.cell(r0, 1, p.get("sno"))
        ws.cell(r0, 2, p.get("sku") or "")
        ws.cell(r0, 3, p.get("sku") or "").font = bold
        ws.cell(r0 + 1, 3, "StockID")
        ws.cell(r0 + 2, 3, p.get("stock_no") or "")
        ws.cell(r0 + 3, 3, "Snap")
        ws.cell(r0 + 4, 3, "")
        ws.cell(r0, 4, _f(p.get("gross")))
        ws.cell(r0, 5, p.get("metal") or "")
        cts_refs, amt_refs = [], []
        for name in BLOCKS:
            c0 = start[name]
            for i, st in enumerate(by[name]):
                rr = r0 + i
                ws.cell(rr, c0, stone_name(st))
                ws.cell(rr, c0 + 1, int(_f(st.get("pcs"))))
                ws.cell(rr, c0 + 2, _f(st.get("weight")))
                ws.cell(rr, c0 + 3, _f(st.get("price")))
                per_pcs = (st.get("unit") or "ct").lower().startswith("pc")
                qty = f"{L(c0 + 1)}{rr}" if per_pcs else f"{L(c0 + 2)}{rr}"
                ws.cell(rr, c0 + 4, f"={qty} * {L(c0 + 3)}{rr}")
                cts_refs.append(f"{L(c0 + 2)}{rr}")
                amt_refs.append(f"{L(c0 + 4)}{rr}")
        ws.cell(r0, 6, f"={L(4)}{r0}- ((+{'+'.join(cts_refs)}) / 5)" if cts_refs
                else f"={L(4)}{r0}")
        ws.cell(r0, 7, round(_f(p.get("fine")), 5))
        ws.cell(r0, 8, _f(p.get("metal_rate")))
        ws.cell(r0, 9, f"={L(6)}{r0} * {L(8)}{r0}")
        rate = _f(p.get("labour_rate"))
        per = (p.get("labour_per") or "gm").lower()
        if rate and per.startswith(("g", "n")):
            ws.cell(r0, c_lab, f"={L(6)}{r0} *{rate:g}")
        else:
            ws.cell(r0, c_lab, _f(p.get("labour")))
        parts = [f"{L(9)}{r0}"] + amt_refs + [f"{L(c_lab)}{r0}"]
        extra = _f(p.get("extra"))
        ws.cell(r0, c_tot, "=" + "+".join(parts) + (f"+{extra:g}" if extra else ""))
        ws.cell(r0, c_tot).font = bold
        tag = p.get("tag") or ""
        ws.cell(r0, c_fine, int(tag) if str(tag).isdigit() else tag)
        if images and p.get("photo"):
            try:
                from openpyxl.drawing.image import Image as XLImage
                img = XLImage(p["photo"])
                img.width, img.height = 64, 64
                ws.add_image(img, f"{L(2)}{r0 + 1}")
            except Exception:  # noqa: BLE001 - no Pillow / unreadable image: no picture
                pass
        for rr in range(r0, r1 + 1):
            for c in range(1, last + 1):
                ws.cell(rr, c).border = box
        row = r1 + 1

    # The SUM row, as the sample: every figure column of the pieces.
    sums = [4, 6, 7, 8, 9] + [start[n] + k for n in BLOCKS for k in (1, 2, 3, 4)] + [c_lab, c_tot]
    for c in sums:
        ws.cell(row, c, f"=SUM({L(c)}4:{L(c)}{row - 1})" if row > 4 else 0).font = bold
    ws.cell(row + 2, 1, "NOTE: Metal Rate Will Be Charged as on Date of Payment").font = bold

    for c in range(1, last + 1):
        ws.column_dimensions[L(c)].width = 10
    ws.column_dimensions[L(2)].width = 12
    ws.column_dimensions[L(3)].width = 12
    for name in BLOCKS:
        ws.column_dimensions[L(start[name])].width = 22
    for r in ws.iter_rows(min_row=4, max_row=row):
        for cell in r:
            c = cell.column
            if c in (4, 6, 7) or any(c == start[n] + 2 for n in BLOCKS):
                cell.number_format = "0.000"
            elif c in (8, 9, c_lab, c_tot) or any(c in (start[n] + 3, start[n] + 4)
                                                     for n in BLOCKS):
                cell.number_format = "#,##0.00"
    ws.freeze_panes = ws.cell(4, 4)
    wb.save(path)
