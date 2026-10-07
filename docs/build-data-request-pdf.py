"""Render the client data request (what we need for go-live) to a PDF.

    python docs/build-data-request-pdf.py [out.pdf]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

_guide = import_module("build-full-flow-pdf")
CSS, H1, H3, render = _guide.CSS, _guide.H1, _guide.H3, _guide.render

URGENT = "<b style='color:#B3261E'>Urgent</b>"
NEEDED = "<b style='color:#7A5B00'>Needed for go-live</b>"
LATER = "<span class='muted'>When convenient</span>"
RECEIVED = "<b style='color:#0E6B54'>Received ✓</b>"

SECTIONS: list[tuple[str, str, list[tuple[str, str, str, str]]]] = [
    ("1. Masters", "Access to the legacy database (SERVER2\\ERP → Diagold26) is the easiest - we can "
     "take every list below from there. If that is not possible, Excel exports of each list.", [
        ("1a", "Accounts", "All clients, suppliers and karigars - code, name, group, city, GSTIN, "
                           "credit days", URGENT),
        ("1b", "Metals", "Name and purity (title) of every metal", URGENT),
        ("1c", "Locations", "Every location, including karigar locations and \"Virtual\"", URGENT),
        ("1d", "Stone master", "Every SSKU with size, shape, quality and group (Diamond / Polki / "
                               "Colour Stone)", URGENT),
        ("1e", "Product SKUs", "SKU code, item, family, style, metal; photos if available", URGENT),
        ("1f", "Other lists", "Items, Family, Colours, Setting Types", URGENT),
    ]),
    ("2. Price charts", "", [
        ("2a", "Stone price - chart \"A\"", "Received (299 rows), now in the system. Please confirm it "
                                            "is chart \"A\", and tell us what the \"SPrice\" column "
                                            "holds (0 in every row).", RECEIVED),
        ("2b", "Labour and Setting price", "Client Wise Labour Price and Setting Price sheets, in the "
                                           "same format as the stone sheet", NEEDED),
        ("2c", "MANNU BHAI stone sheet", "Only if it is different from \"A\"", NEEDED),
        ("2d", "Tools ▸ Option values", "Every section (a screenshot is enough)", NEEDED),
    ]),
    ("3. Opening balances", "All on the go-live (cut-over) date.", [
        ("3a", "Go-live date", "The date from which the new system takes over", URGENT),
        ("3b", "Party balances", "Each party: money (Dr / Cr) and fine metal", NEEDED),
        ("3c", "Metal stock", "Per location, grams by metal", NEEDED),
        ("3d", "Stone stock", "Per location: Diamond / Polki / Colour Stone - pcs, carats, value",
         NEEDED),
        ("3e", "Negative balances", "Your screens show Primary 24KT Gold −320.891 g, RAJAT JI stones "
                                    "in minus, and \"Diff. in Opening Balances\" ₹14,75,75,841 in the "
                                    "Trial Balance. Clean up first, or start from fresh opening "
                                    "balances?", NEEDED),
    ]),
    ("4. Work in progress on the go-live date", "", [
        ("4a", "Open job cards", "Job no, order, SKU, current process, karigar, weight", NEEDED),
        ("4b", "Job bags", "Stones still in each job's bag", NEEDED),
        ("4c", "Karigar balances", "Each karigar's metal and stone balance", NEEDED),
        ("4d", "Ready stock", "Every piece with stock no (barcode), weights, price, tag", NEEDED),
        ("4e", "On approval", "Pieces out on approval, and with which party", NEEDED),
        ("4f", "Pending bills", "To receive and to pay, bill-wise", NEEDED),
    ]),
    ("5. Formats and samples", "", [
        ("5a", "Client layouts", "One Sale Invoice and one Packing List in your client layout", LATER),
        ("5b", "Format-2 and Excel invoice", "One Format-2 print; the Excel invoice file of Vr 1225",
         LATER),
        ("5c", "Job sheet", "The Word job-sheet format, with one filled example", LATER),
        ("5d", "Design / CAD images", "Folder and file naming used for images", LATER),
    ]),
]


def html() -> str:
    out = [CSS, H1.format("Dia Gold CRM — Data we need for go-live"),
           "<p class='muted'>Namaste Rohit ji. The new system is ready for testing on sample data. "
           "To move to your real data we need the items below. Excel exports are fine for "
           "everything. Please reply with the number and the file, e.g. \"1a — attached\", "
           "\"3a — 1 Nov\".</p>"]
    for title, intro, rows in SECTIONS:
        out.append(H3.format(title))
        if intro:
            out.append(f"<p>{intro}</p>")
        out.append("<table width='100%'><tr><th width='6%'>#</th><th width='22%'>What</th>"
                   "<th>Details</th><th width='17%'>Priority</th></tr>")
        out += [f"<tr><td><b>{n}</b></td><td>{what}</td><td>{d}</td><td>{p}</td></tr>"
                for n, what, d, p in rows]
        out.append("</table>")
    out.append("<p style='margin-top:10px'><b>Section 1 matters most</b> - once the masters arrive, "
               "everything else fits in quickly.</p><p>Thank you!</p>")
    return "".join(out)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    out = (Path(sys.argv[1]) if len(sys.argv) > 1
           else Path.home() / "Downloads" / "DiaGold-Data-Request.pdf")
    print(render(html(), out))
