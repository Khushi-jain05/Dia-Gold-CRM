"""Render the tester's walkthrough to a PDF (run: python docs/build-test-script-pdf.py)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagold.services.documents import to_pdf  # noqa: E402

CSS = """
<style>
body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #1B211E; }
h1 { font-size: 20pt; margin: 0 0 4px 0; }
h2 { font-size: 12.5pt; margin: 16px 0 4px 0; color: #0E6B54; }
p { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 6px 0; }
th, td { border: 1px solid #C9CFCA; padding: 4px 6px; vertical-align: top; font-size: 9.5pt; }
th { background: #EEF1EE; text-align: left; }
.ok { color: #0E6B54; font-weight: bold; }
.muted { color: #5C6661; font-size: 9pt; }
.box { background: #F2EBD6; padding: 6px 8px; margin: 6px 0; }
</style>
"""


def step(n: int, title: str, rows: list[tuple[str, str]], checks: list[str], intro: str = "") -> str:
    body = f"<h2>{n}. {title}</h2>"
    if intro:
        body += f"<p>{intro}</p>"
    if rows:
        body += "<table><tr><th width='28%'>Field / Column</th><th>Bharo (type this)</th></tr>"
        body += "".join(f"<tr><td>{f}</td><td>{v}</td></tr>" for f, v in rows) + "</table>"
    body += "".join(f"<p><span class='ok'>✔ Check:</span> {c}</p>" for c in checks)
    return body


HTML = CSS + """
<h1>Dia Gold CRM v0.5.0 — Test Script</h1>
<p class='muted'>Login: <b>admin</b> / <b>admin</b>. Steps ko isi order me karo — har screen agli screen me dikhti hai
(Order → Jobs → Route → Vouchers → Bag → Return → Reports). Sample data pehle se hai: jobs 28350 (Ruby Singh), 25006, 27751.</p>
<div class='box'><b>Bug kaise report karein:</b> screen ka naam · kya dabaya · kya expect tha · kya hua · screenshot.</div>
""" + step(1, "Master ▸ Account → + New  (ek karigar)", [
    ("Code", "RAHUL"), ("Name", "RAHUL JI"), ("Type", "Worker"), ("Group", "Accounts Payable")],
    ["Save ke baad ye naam Job History me Worker dropdown me aayega."],
) + step(2, "Master ▸ Metal → + New", [
    ("Code / Name", "TEST22 / 22KT TEST 916"), ("Purity / Fineness", "916"), ("Colour", "Y"),
    ("Mining Metal Ratio grid", "GOLD 91.600 · ALLOY 8.400")],
    ["Pehle ALLOY 8.3 daal ke Save → refuse hoga (total 100 nahi). 8.4 karke Save → chalega."],
) + step(3, "SKU ▸ Stone SKU → + New", [
    ("Stone Sku", "RUBY OVAL 5*4"), ("Stone", "RUBY"), ("Shape / Size", "OVAL / 5*4"),
    ("Cost Price / Sale Price", "800 / 1200"), ("Per", "Cts"), ("Wt/Pcs", "0.25")],
    ["Save. Phir row select karke <b>Make A Copy</b> → 'RUBY OVAL 5*4 (copy)' khulega; Size 6*4 karke Save."],
) + step(4, "SKU ▸ Product SKU Master → + New", [
    ("SKU", "RG-9001"), ("Description", "Ruby ring"), ("Item", "ring (Family khud aayega)"),
    ("Metal", "14KT CASTING 590 (Fineness khud aayega)"), ("Gross Wt / Net Wt", "5.200 / 4.100"),
    ("Stone Info grid", "SSKU RUBY OVAL 5*4 → Cost/Sale/Per khud bhar jayenge; Pcs 4, Weight 1.000")],
    ["Save → Stone Amount 1,200.00, Mt Rate, Metal Amount, TOTAL RS khud calculate.",
     "Dobara RG-9001 naam se New banao → 'already in use' message."],
) + step(5, "Production Planning ▸ Order → + New", [
    ("Date", "aaj"), ("Ord Type", "Customer"), ("Customer", "KK JEWELS"), ("Ref", "TEST-1"),
    ("Delivery Date", "aaj + 10 din"),
    ("SKU Lines row 1", "SKU RG-9001 → Desc/Metal/weights khud; Pcs 2"),
    ("SKU Lines row 2", "SKU NS-2968, Pcs 1")],
    ["Save → Ord No khud milega; 2 jobs allot hue (Job Mapping me dikhenge).",
     "Customer khali chhod ke Save → refuse."],
) + step(6, "Production Planning ▸ Job Mapping", [],
    ["'Pending Jobs For Definition' me apne 2 naye jobs. Pehla select → Process Group Default → <b>Apply Group</b> → 11 steps → <b>Save Route</b>.",
     "<b>Copy To All</b> → doosre job pe bhi route.",
     "<b>Add Step</b> → Repair HM → Save Route (repair step insert)."],
    "Order save hote hi jobs yahan aate hain.",
) + step(7, "Production Planning ▸ Stone Issue on Job-Card → + New", [
    ("Job No", "apna naya job (RG-9001 wala)"), ("Date", "aaj"),
    ("Stones row", "Location Primary · SSKU EMERALD PEAR 6*4 (Size/Wt khud) · Pcs 4 · Weight 1.200")],
    ["Save. Dobara same, Pcs 999 → refuse: 'Primary holds only …'."],
) + step(8, "Production Planning ▸ Job History  (ya F11)", [
    ("Job No", "apna job number type → Enter"),
    ("+ Issue", "Step 3 · CASTING, Worker RAHUL JI, Pcs 1, Gross 5.200, Net 5.200 → Save"),
    ("+ Receive", "wahi step, Worker RAHUL JI, Gross 5.150, Net 5.150 → Save")],
    ["Row me <b>Loss 0.050</b> dikhega.",
     "+ Receive bina weight → refuse ('carries metal…'). Worker khali → refuse.",
     "+ Issue step 1 · CAD weight ke saath → refuse ('design only').",
     "<b>Add Comments</b> → note neeche dikhega. <b>Print</b> → PDF banega."],
) + step(9, "Production Planning ▸ Job Card Bag", [
    ("Job No", "apna job"), ("EMERALD PEAR 6*4 line", "Bal 4 / 1.200 dikhna chahiye")],
    ["Select → <b>Issue to Worker</b> 2 pcs, RAHUL JI → Bal 2.",
     "<b>Return to Stock</b> 1 pc → Bal 1, Primary +1.",
     "Issue to Worker 10 → refuse.",
     "<b>Stones in Job Cards</b> / <b>Bag Balance Report</b> → Export CSV."],
) + step(10, "Production Planning ▸ Inv Return – Stone", [
    ("Job No", "apna job"), ("Show Pending", "EMERALD PEAR line, Bal 1"),
    ("Return Pcs / Type / Location", "1 / Returned / Primary")],
    ["<b>Save</b> → voucher number milega, neeche 'Return vouchers on this job' me entry, bag khali."],
) + step(11, "Production Planning ▸ Printing Options", [
    ("Job No", "apna job, 'this job only'"), ("Prints", "Job Sheet ✓, Stone Requirements ✓")],
    ["<b>Print</b> → 'Open print folder' me 2 PDF."],
) + step(12, "Production Planning ▸ Opening Stone Balances", [
    ("Location", "RAJAT JI"), ("Stone SKU", "RUBY OVAL 5*4"), ("Pcs / Weight", "100 / 25")],
    ["Value <b>khud</b> 20,000 (25 × 800) → <b>Add opening</b>."],
) + step(13, "Production Planning ▸ Reports — har report kholo", [
    ("Job Analysis", "25006 sabse upar, bada OVERDAYS; 'Late deliveries only' tick → 27751 (21 din)"),
    ("Process Analysis", "Show bar me CST tick → sirf casting group + subtotal"),
    ("Job Card Analysis – Stone", "Primary × COLOR STONE / POLKI; RAJAT JI opening 100; line pe double-click → vouchers"),
    ("Job Stock Analysis", "27751 = 21 days; footer me average / median"),
    ("Inv Rtn Stone Day Book", "step 10 wala return"),
    ("Job O/s – Stone", "apna job, PND columns"),
    ("Data Quality", "groups me exceptions")],
    ["Har report pe: <b>Group</b> dropdown, <b>Auto Filter</b> (column select karke), <b>Export</b>, <b>Print</b>."],
) + step(14, "Tools ▸ Option", [],
    ["'Job Card Bag' untick → Save → menu se gayab. Wapas tick → wapas."],
) + "<p class='muted'>Jo bhi galat mile — screenshot ke saath bhej do.</p>"

if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "DiaGold-Test-Script-v0.5.0.pdf"
    to_pdf(HTML, out)
    print(out)
