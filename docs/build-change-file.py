"""Render the change file for the client after the 2 October session (T-01).

    python docs/build-change-file.py [out.pdf]

Everything changed since the meeting, where to find it, what was built on an
assumption and needs a yes / no, and what is still waiting - with screenshots
of the new screens (docs/screens-2oct/), so Rohit ji can check and reply with
corrections (2 Oct B4 / D4).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "screens-2oct"
FONT = "Helvetica Neue"
CSS = """
<style>
p { margin: 2px 0; }
table { border-collapse: collapse; margin: 3px 0 6px 0; }
th, td { border: 1px solid #C9CFCA; padding: 3px 5px; vertical-align: top; }
th { background: #EEF1EE; text-align: left; font-weight: 600; }
.muted { color: #5C6661; }
</style>
"""
H1 = "<p style='font-size:16pt; font-weight:700; margin:0 0 3px 0'>{}</p>"
H2 = ("<p style='font-size:11pt; font-weight:700; color:#0E6B54; margin:12px 0 3px 0'>"
      "{}</p>")
BOX = ("<table width='100%' style='margin:4px 0'><tr><td style='background:#F2EBD6; "
       "border:none; padding:6px 8px'>{}</td></tr></table>")


def table(head: list[str], rows: list[list[str]], widths: list[int] | None = None) -> str:
    w = widths or []
    th = "".join(f"<th{f' width={w[i]}%' if i < len(w) else ''}>{h}</th>"
                 for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table width='100%'><tr>{th}</tr>{body}</table>"


def shot(name: str, caption: str) -> str:
    path = SHOTS / name
    if not path.exists():
        return ""
    return (f"<p style='margin:8px 0 2px 0'><b>{caption}</b></p>"
            f"<p><img src='{path}' width='520'></p>")


DONE = [
    ["1", "<b>Job Costing</b> (you said it is required)",
     "Manufacturing ▸ Job Costing. One row per finished job: metal, stones, setting + STD labour, "
     "margin, price, tag, stock no. Double-click opens the <b>Job Costing Sheet</b> with the photo, "
     "Export To Excel, Print and WIP Costing. Ctrl+F1 stone group wise, Ctrl+P Excel job costing, "
     "Ctrl+W Excel WIP costing. Your BANG-52 sheet is reproduced exactly: grand total "
     "2,51,239.91, tag 251, 19.66 per gm."],
    ["2", "<b>Waxing</b> removed", "Hidden from Manufacturing (you said it is not used). It can be "
     "brought back in Tools ▸ Option if ever needed."],
    ["3", "<b>Approval only in Sale</b>", "Purchase now has Opening Stock, Metal, Stones, Ready "
     "Items and Ready Item Return. Approval / Approval Return are under Sale ▸ Ready Stock."],
    ["4", "<b>Ready Stock Sale</b>", "Sale ▸ Ready Stock ▸ Sale. Scan a barcode (a wrong one says "
     "\"Item not found\") or type a SKU, Show Stock, <b>From Order</b> (Pending Orders with Fill "
     "Balance Pcs / Fill Stock Qty), Read Barcode From Approval. Metal at the day's rate, stones, "
     "setting, labour = rate × net weight. Credit days and due date, salesperson, bank. Stone "
     "Breakup per line. Account Information Dr customer / Cr Sales A/c. Add / Edit / Save / Delete, "
     "Print."],
    ["5", "<b>Excel Invoice in your format</b>", "On the sale: per piece the metal, then Diamond / "
     "Polki / Colour Stone blocks side by side, labour and total - all as Excel formulas - and the "
     "note \"Metal Rate Will Be Charged as on Date of Payment\". Your invoice 1225 figures come out "
     "the same (DIA 36,000; Polki 59,160; colour stone 14,428.50; labour 13,189.20)."],
    ["6", "<b>Sale Return, Approval, Approval Return</b>", "A piece on approval can only be returned "
     "or sold to that party. Reports: Ready Stock Approval Register / Balance / Analysis, Sale "
     "Register."],
    ["7", "<b>Metal Sale, Stone Sale / Approval</b>", "Sale ▸ Metal (e.g. 24KT 10 g @ 15,050 = "
     "1,50,500) and Sale ▸ Stone ▸ Sale / Approval / Approval Return. Metal Sale Register, Stone "
     "Sale Register (with Lot No), Stone Approval Register / Analysis."],
    ["8", "<b>Repair</b>", "Order has a <b>Repair</b> tick; Repair List picks existing pieces as "
     "its lines. Sale ▸ Ready Stock ▸ Ready Repair Issue sends pieces to repair for a party. "
     "Repair Register shows what is out and for how many days."],
    ["9", "<b>MFG Ready Stock Transfer</b>", "Choose the Location the pieces go into; "
     "<b>Split Jobs</b> gives one Stock No per piece; Tag Print, Excel Format, Format-2; a saved "
     "transfer can be edited or deleted."],
    ["10", "<b>Loss and WIP registers</b>", "Inventory ▸ Reports ▸ Registers: Metal Loss Register "
     "(loss per step against the allowance), Stone Loss Register, Dust Register, WIP Register "
     "(WIP with a karigar / PND waiting), WIP Register process summary (every process, pending and "
     "WIP, karigars working), WIP Stone."],
    ["11", "<b>Purchase</b>", "Ready Items purchase brings pieces in with new barcodes (weights, "
     "tunch, stones, labour, cert, HUID; bill date / number / account / amount; Dr Purchase / Cr "
     "supplier), with BreakUp Sheet, Packing List, Picture Invoice, St. Summ., Tag Print, SKU "
     "Search. Ready Item Return. Opening Stock ▸ Ready Items / Metal / Stone."],
    ["12", "<b>Stock Transfer / Stock Melting</b>", "Inventory ▸ Stock Transfer with the four panes "
     "you showed (Ready Stock Outward, Metal, Stone, Ready Stock Transfer); Stock Melting, Stock "
     "Location Transfer, Barcode, Print 2, Melting List, Transfer Reg. <i>Built from your screen - "
     "please check the rules (item B5).</i>"],
    ["13", "<b>Stone Issue by cert / lot</b>", "Read Cert/Lot, Stone Import, JobNo on lines, DC "
     "Print, Tag, Register; Create Outstanding Issue For Cert and Worker Adjustment are recorded."],
    ["14", "<b>Daily Metal Rate</b>", "Each rate keeps who entered it and when; Rate As On Date "
     "shows every metal's rate on any day. Vouchers keep the rate they were made with."],
    ["15", "<b>Barcode on the home screen</b>", "Dashboard ▸ BARCODE READ: Stock ID / SKU opens "
     "Item Search, Job No opens Job History."],
    ["16", "<b>Every report</b>", "Export to Excel (numbers, not text), F1 Show All, F12 More "
     "Reports. Every voucher: Save? Yes / No."],
    ["17", "<b>Also done</b>", "Issue / Received vouchers can be edited and deleted; Attach Doc on "
     "receipts, sales and inventory vouchers; Cl Bal on the sale; TXT Import / Export of barcodes; "
     "Item Search shows a barcode's whole history (made, sold, approval, repair, transfer); Check "
     "Bal on metal issue; Show O/S on stone receipt; purchases and sales post Dr / Cr (Account "
     "Information on each voucher, Account Ledger report)."],
    ["18", "<b>Menus trimmed</b>", "Items not used or not yet explained are off: Waxing, Purchase "
     "Approval / Debit Notes / Parts / Moulds / Settings, Inventory Parts / Mould / Physical Stock / "
     "Ready Item Receipt, Manufacturing Repair Issue / Extra Issue / Stamping, Window Cascade / "
     "Tile. Any of them comes back from Tools ▸ Option."],
]

CONFIRM = [
    ["B1", "Tag price = grand total ÷ 1,000 (2,51,239.91 → 251; 3,05,330 → 305). Is that the rule?"],
    ["B2", "Margin % is one figure from the Margin master (50%). Is it ever per customer "
     "(\"Prices From Client Chart\")?"],
    ["B3", "Labour = rate × net weight (1,200 × 10.991 = 13,189.20). Is it ever per piece?"],
    ["B4", "The invoice uses the day's metal rate when it is made. The note says metal is charged at "
     "the payment-date rate - how is the bill settled then?"],
    ["B5", "Stock Transfer: we move a location's stock by In / Out only and record the loss "
     "columns for the loss registers. Is that how losses are booked? Stock Melting = a ready piece "
     "out, its metal and stones back in?"],
    ["B6", "Split Jobs shares the weights, cost and price equally between the pieces. Correct?"],
    ["B7", "Repair: the old piece's stone detail is not carried into the repair job. Correct? "
     "Is there a charge, and does a repair go through a route like a job?"],
    ["B8", "Job Costing shows the setting paid to the karigar beside STD labour (as your BANG-52 "
     "sheet did). Should the MFG transfer's Setting Amount carry it too?"],
]

WAITING = [
    ["Print formats", "Which of the 13 sale print formats you use (we built Invoice and the Excel "
     "Invoice). Format-2 with WhatsApp share, Estimate, Summary etc. follow your list."],
    ["Purchase", "Debit Note (Metal / Stone), Parts / Moulds purchase, Stone Approval / Stone App "
     "Return - are they used? Purchase ▸ Settings, Show Ords and From Ft.Tr on the purchase screen."],
    ["Sale", "DIGICAT Quote, RFID reading, As MRP, Prices From Client Chart, F10 SKU Curr, Sale ▸ "
     "Ready Stock ▸ Settings, the \"App\" button, the \"Oth FineWt\" column, and the actions Export "
     "Docs, Catalog 4×8, Cert Stones, PIC Folder, Avg St Price. The second Excel layout (the "
     "\"Ready Stock Sale\" workbook with a per-piece Summary block) - is it used?"],
    ["Manufacturing", "Repair Issue, Extra Issue, Stamping / Engraving List - one line each on what "
     "they do (they are off in the menu until then)."],
    ["Inventory", "Physical Stock, Ready Item Receipt, Load Metal / Stone, Issue On Tree, Conversion, "
     "Adjustment, Worker Recovery, WIP Rtn, Bhav Cut - please explain each in one line."],
    ["Locations", "What is the \"Virtual\" location?"],
    ["Job Card Bag", "The \"Back\" column, and Order \"Priority\" - still to answer from 11 Sept."],
]


def build() -> str:
    parts = [CSS, H1.format("Dia Gold CRM — changes for your check"),
             "<p class='muted'>After the meeting of 2 October 2026 · prepared 3 October 2026</p>",
             BOX.format("Rohit ji, as promised on the call: everything changed since our meeting, "
                        "where to find it, and what we need you to confirm. Please reply with the "
                        "item number and what to change - one line is enough (for example: "
                        "\"B1 - yes\", \"4 - salesperson not needed\")."),
             H2.format("A. What is built — please try it"),
             table(["#", "What", "Where / how"], DONE, [6, 22, 72]),
             H2.format("B. Built on an assumption — please say yes or correct it"),
             table(["#", "Question"], CONFIRM, [6, 94]),
             H2.format("C. Waiting for you before we build"),
             table(["Area", "What we need"], WAITING, [14, 86]),
             H2.format("D. Screens"),
             shot("02_job_costing.png", "Manufacturing ▸ Job Costing"),
             shot("03_costing_sheet.png", "Job Costing Sheet"),
             shot("04_ready_stock_sale.png", "Sale ▸ Ready Stock ▸ Sale"),
             shot("09_mfg_transfer.png", "Manufacturing ▸ MFG Transfer (Location, Split Jobs)"),
             shot("05_wip_summary.png", "WIP Register — process summary"),
             shot("06_metal_loss.png", "Metal Loss Register"),
             shot("08_ready_items.png", "Purchase ▸ Ready Items"),
             shot("07_stock_transfer.png", "Inventory ▸ Stock Transfer"),
             shot("10_order_repair.png", "Order list - Repair List"),
             shot("01_dashboard.png", "Home screen - BARCODE READ"),
             "<p class='muted'>Thank you - Khushi Jain, Pradeep Sharma, Prem Golani</p>"]
    return "".join(parts)


def render(html: str, out: Path) -> Path:
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
    from PySide6.QtPrintSupport import QPrinter
    out.parent.mkdir(parents=True, exist_ok=True)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                      QPageLayout.Orientation.Portrait,
                                      QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter))
    printer.setOutputFileName(str(out))
    doc = QTextDocument()
    font = QFont(FONT)
    font.setPointSizeF(9)
    doc.setDefaultFont(font)
    doc.setDocumentMargin(0)
    doc.setHtml(html)
    doc.print_(printer)
    return out


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path.home() / "Downloads" / "DiaGold-Change-File-2Oct.pdf"
    print(render(build(), out))
