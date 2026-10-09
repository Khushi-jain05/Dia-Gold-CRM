"""Render the full test guide in plain English to a PDF.

    python docs/build-test-guide-en-pdf.py [out.pdf]

The same flow and the same expected figures as build-full-flow-pdf.py (the
Hinglish guide), written in simple English for testers who are new to the
app. Every figure was produced by the app on a fresh demo database.
"""
from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
_base = import_module("build-full-flow-pdf")
CSS, H1, H2, H3, BOX, render = _base.CSS, _base.H1, _base.H2, _base.H3, _base.BOX, _base.render

_n = 0


def step(title: str, rows: list[tuple[str, str]], checks: list[str], intro: str = "") -> str:
    global _n
    _n += 1
    body = H2.format(f"{_n}. {title}")
    if intro:
        body += f"<p>{intro}</p>"
    if rows:
        body += ("<table width='100%'><tr><th width='28%'>Where / Field</th>"
                 "<th>What to do</th></tr>")
        body += "".join(f"<tr><td>{f}</td><td>{v}</td></tr>" for f, v in rows) + "</table>"
    body += "".join(f"<p><span class='ok'>✔ You should see:</span> {c}</p>" for c in checks)
    return body


def part(title: str) -> str:
    return H3.format(title)


def mfg(process: str, karigar: str, iss: str, rcv: str, allow: str, expect: str,
        extra_iss: str = "", extra_rcv: str = "") -> str:
    """One process: Manufacturing ▸ Issue, then Manufacturing ▸ Received."""
    rows = [("Manufacturing ▸ Issue", f"Process <b>{process}</b> · Account <b>{karigar}</b> · "
                                       "<b>Show Pending</b> → tick your job → OK"),
            ("Issue line (green cells)", iss + (f" · Allow Loss % <b>{allow}</b>" if allow else "")
             + (f" · {extra_iss}" if extra_iss else "") + " → <b>Save</b> → Yes"),
            ("Manufacturing ▸ Received", f"Process <b>{process}</b> · Account <b>{karigar}</b> · "
                                          "<b>Show Pending</b> → tick your job → OK"),
            ("Receive line (green cells)", rcv + (f" · {extra_rcv}" if extra_rcv else "")
             + " → <b>Save</b> → Yes")]
    return step(f"{process} — {karigar}", rows, [expect])


HTML = CSS + H1.format("Dia Gold CRM — Full Test Guide (English)") + """
<p class='muted'>This guide tests the whole app, one step after another: masters, buying stock, an order,
every manufacturing step, ready stock, sale, approval, repair, purchase, stock transfer, reports,
accounts, price charts, stock tools, dashboards and tools. Each step says <b>where to go</b>, <b>what to
do</b>, and <b>what you should see</b>. You do not need to know the app — just follow the steps in order.</p>
""" + BOX.format("""<b>You need:</b> a Windows PC and the file <b>DiaGoldCRM-Windows-x64.zip</b>.
All testing happens on a separate <b>DEMO database</b> — your real data is never touched. The demo already has:
gold rate (24K 14,713 / g, so 14KT 590 = 8,680.67 / g), labour 1,200 / g, margin 50%, karigar CHAND KUMAR
HAZRA, supplier SHRIKANT, customer KK JEWELS, demo jobs 28854–28856, and the client's master lists and
stone price sheets (A and MANNU BHAI).""") + part("0. Install and open the app") + step(
    "Unzip (first time only)", [
        ("Zip file", "Right-click <b>DiaGoldCRM-Windows-x64.zip</b> → <b>Extract All…</b> → Extract"),
        ("Folder", "The new folder has <b>DiaGoldCRM.exe</b> and two files: "
                   "<b>Open DEMO (testing).bat</b> and <b>Reset DEMO and open.bat</b>")],
    ["Keep this folder on the Desktop. Always open the app from here."],
) + step(
    "Open the demo", [
        ("Double-click", "<b>Reset DEMO and open.bat</b> (starts a clean demo)"),
        ("Blue Windows warning", "<b>More info</b> → <b>Run anyway</b> (only the first time)"),
        ("Login", "User <b>admin</b> · Password <b>admin</b> → Enter")],
    ["The window title says <b>DEMO DATA (testing)</b>. The bottom bar shows the <b>DiaGoldDemo</b> folder. "
     "If you do not see this, close the app — you opened the real data.",
     "To start testing again from zero, use <b>Reset DEMO and open.bat</b>."],
) + step(
    "How the app works (2 minutes)", [], [], intro="<ul><li>" + "</li><li>".join([
     "The <b>menu bar</b> at the top: Master, Production Planning, Manufacturing, Purchase, Inventory, Sale, "
     "Account, Tools, Reports. Click a menu to see its list; items with ▸ open a sub-menu.",
     "Each screen opens in a <b>tab</b>. Click × on the tab to close it.",
     "List screens (Order, Purchase …): <b>+ New</b> → fill the form → <b>Save</b>. Every save asks "
     "<b>\"Save? Yes / No\"</b> — click <b>Yes</b>.",
     "In voucher grids you can type in the <b>green cells</b>: double-click the cell, type, press Enter.",
     "<b>Show Pending</b> = the list of work still to do → tick → OK.",
     "Shortcuts: <b>Ctrl+F</b> = go to any screen by name · <b>F11</b> = Job History · <b>F12</b> = all reports · "
     "<b>Ctrl+I</b> = Item Search · in reports <b>F1</b> = show all.",
     "Print and Excel buttons save a file — the message shows where."]) + "</li></ul>",
) + BOX.format("""<b>Your job number:</b> in step 14 you save an order and the app gives a new Job No
(<b>28857</b> on a fresh demo). Write it down — use that same job in every step after.
Do not use the demo jobs (28854–28856) or 28853 for your steps.<br>
<b>Do not skip steps</b> — each step makes the data the next step needs. If something is missing from a list,
a step before was missed.""") + BOX.format(
    """<b>To report a problem:</b> step number · screen · what you clicked · what you expected · what happened ·
a screenshot.""") + part("A. Masters — the rates and people the test uses") + step(
    "Master ▸ Daily Metal Rate", [],
    ["<b>14KT 590</b> and <b>24KT Gold</b> — date 25-09-2026, rate <b>14,713</b> (24K fine rate).",
     "This rate gives the MFG Transfer metal rate: 14,713 × 0.590 = <b>8,680.67</b>."],
) + step(
    "Master ▸ Labour", [],
    ["14KT 590 → <b>1,200</b> per gram, on net weight, from 01-09-2026."],
) + step(
    "Master ▸ Set Margins", [],
    ["<b>DEMO TAG 50</b> — tag margin <b>50%</b> (tag price = cost × 1.5)."],
) + step(
    "Master ▸ Setting Type", [],
    ["<b>Polki 30.00</b> and <b>Diam 3.00</b> per piece — setting labour comes from here."],
) + step(
    "Master ▸ Account → + New (a new karigar)", [
        ("Code", "RAHUL"), ("Name", "RAHUL JI"), ("Type", "Worker")],
    ["After Save, RAHUL JI is in the Account list of Manufacturing ▸ Issue (used in the HandMade step)."],
) + step(
    "Master ▸ Account → + New (a new supplier)", [
        ("Code", "TESTSUP"), ("Name", "TEST SUPPLIER"),
        ("Type", "<b>Accounts</b> (there is no separate supplier type)"),
        ("Group", "<b>Accounts Payable</b>"),
        ("Phone / City / GSTIN", "9876543210 / Mumbai / 27ABCDE1234F1Z5 (optional)"),
        ("Opening Balance", "leave empty")],
    ["TEST SUPPLIER is in the Accounts list, type Accounts.",
     "It now shows in the <b>Supplier</b> list of Inventory ▸ Stone / Metal ▸ Purchase.",
     "Try saving with Code or Name empty → the app refuses."],
) + part("B. Inventory — buy stock from the supplier, give metal to a karigar") + step(
    "Inventory ▸ Stone ▸ Purchase → + New", [
        ("Supplier", "<b>TEST SUPPLIER</b>"), ("Ref No", "TEST-ST"),
        ("Line 1", "Location <b>Primary</b> · SSKU <b>POLKI 12-14</b> · Pcs <b>20</b> · Weight <b>1.600</b> · Price "
                   "<b>8100</b> · Per Cts · Lot No <b>LOT-7</b>"),
        ("Line 2", "Location <b>Primary</b> · SSKU <b>EMERALD PEAR 3*4</b> · Pcs <b>10</b> · Weight <b>1.000</b> · "
                   "Price <b>2000</b> · Per Cts")],
    ["Amounts fill in: line 1 <b>12,960.00</b>, line 2 <b>2,000.00</b>; summary 2 lines · 30 pcs · 2.600 ct · "
     "<b>14,960.00</b>.",
     "Save gives a Vr No. Select the row → <b>Print</b> → PDF."],
) + step(
    "Inventory ▸ Metal ▸ Purchase → + New", [
        ("Supplier", "<b>TEST SUPPLIER</b>"), ("Ref No", "TEST-MT"),
        ("Line", "Location <b>RAJESH JI</b> · Metal <b>14KT 590</b> · Colour Y · Weight <b>50.000</b> · Price "
                 "<b>8680.67</b>")],
    ["Amount <b>4,34,033.50</b>; after Save, Fine <b>29.500</b> (50 × 0.590).",
     "Select the row → <b>Attach Doc</b> → Add… → any PDF / photo → it shows in the list and opens.",
     "<b>Reports ▸ Inventory ▸ Account Ledger</b> → TEST SUPPLIER: SP Cr <b>14,960.00</b>, MP Cr "
     "<b>4,34,033.50</b>, balance <b>4,48,993.50 Cr</b>."],
) + step(
    "Inventory ▸ Metal ▸ Issue Outside / Worker → + New", [
        ("Account (worker)", "CHAND KUMAR HAZRA"),
        ("Line", "Location <b>RAJESH JI</b> · Metal <b>14KT 590</b> · Weight <b>2.000</b>")],
    ["After Save, Fine <b>1.180</b>.",
     "Try a new voucher with Weight <b>500</b> → warning 'This takes stock below zero'. Click No — it does not save."],
) + step(
    "Inventory ▸ Metal ▸ Receipt → + New", [
        ("Account (worker)", "CHAND KUMAR HAZRA"),
        ("Line", "Location <b>RAJESH JI</b> · Metal <b>14KT 590</b> · Weight <b>1.800</b> · Wastage % <b>2.5</b>")],
    ["After Save, Wastage Wt <b>0.045</b>.",
     "CHAND still holds from this: 2.000 − 1.800 − 0.045 = <b>0.155 g</b>."],
) + part("C. Order → Job → Route → Stones") + step(
    "Production Planning ▸ Order → + New", [
        ("Ord Type / Customer", "Customer / <b>KK JEWELS</b>"), ("Ref", "<b>TEST-1</b>"),
        ("Terms", "<b>15 days</b>"), ("Priority", "<b>High</b>"), ("Delivery Date", "today + 10 days"),
        ("SKU Lines row 1", "SKU <b>NS-1430</b> · Metal <b>14KT 590</b> · Colour <b>Y</b> · Size <b>7</b> · C-Ref "
                            "<b>TEST-C</b> · Pcs <b>1</b>")],
    ["Save gives an Ord No and <b>1 job</b>. Write down the Job No (28857 on a fresh demo).",
     "Save with no Customer → refused. Pcs 0 → refused."],
) + step(
    "Production Planning ▸ Job Mapping", [
        ("Pending Jobs", "select your job"),
        ("Process Group", "<b>Default</b> → <b>Apply Group</b> → <b>Save Route</b>")],
    ["11 steps: CAD CAM CS HM COL PP ST FP fs Meena Puwai. Your job leaves the Pending list."],
) + step(
    "Production Planning ▸ Stone Issue on Job-Card → + New", [
        ("Job No", "your job"),
        ("Stones row 1", "Location <b>Primary</b> · SSKU <b>POLKI 12-14</b> · Pcs <b>10</b> · Weight <b>0.800</b> · "
                         "S Type <b>Polki</b>"),
        ("Stones row 2", "Location <b>Primary</b> · SSKU <b>EMERALD PEAR 3*4</b> · Pcs <b>5</b> · Weight "
                         "<b>0.500</b> · S Type <b>CS</b>")],
    ["It saves. The same issue with Pcs <b>999</b> is refused ('Primary holds only …')."],
) + step(
    "Production Planning ▸ Job Card Bag", [
        ("Job No", "your job"), ("POLKI 12-14 line", "select → <b>Setting Type</b> → <b>Polki</b>")],
    ["POLKI 12-14: Rcvd <b>10 / 0.800</b>, Bal 10, Setting <b>Polki</b>. EMERALD PEAR: Rcvd <b>5 / 0.500</b>.",
     "Return to Stock <b>50</b> pcs → refused."],
) + part("D. Manufacturing — Issue and Receive for every process") + """
<p>Each process uses two screens: <b>Manufacturing ▸ Issue</b> and <b>Manufacturing ▸ Received</b>. On both,
choose the Process and the Account, then click <b>Show Pending</b> — only jobs whose next step is this process
appear. Type in the green cells.</p>
""" + mfg("CAD", "Office", "no weight (design step — weight cells are locked)", "no weight", "",
          "Show Pending again → your job is no longer at CAD. <b>Print Voucher</b> opens the voucher.") + mfg(
    "CAMMING", "Office", "no weight", "no weight", "",
    "Job History shows CAD and CAMMING rows, with no weight.") + mfg(
    "CASTING", "CHAND KUMAR HAZRA", "GrossWt <b>13.500</b> · NetWt <b>13.500</b>",
    "GrossWt <b>13.200</b> · NetWt <b>13.200</b>", "0",
    "On Received, choosing CHAND shows his <b>Mt Bal</b>. Job History CASTING: Loss <b>0.300</b> · <b>2.22%</b>.") + mfg(
    "HandMade", "RAHUL JI", "GrossWt <b>13.200</b> · NetWt <b>13.200</b>",
    "GrossWt <b>13.100</b> · NetWt <b>13.100</b> (wrong on purpose — the next step fixes it)", "3.5",
    "It saves. Iss Finding <b>0.050</b>, Iss Mould <b>0.100</b>. On Received, <b>Attach Doc</b> → add a file.",
    extra_iss="select the line → <b>F4</b> Finding <b>0.050</b> → Enter · <b>F7</b> Mould <b>0.100</b> → Enter") + step(
    "Fix a mistake — edit a saved voucher", [
        ("Manufacturing ▸ Received", "Process <b>HandMade</b> → <b>Edit</b> → RAHUL JI's voucher → OK"),
        ("Line", "GrossWt <b>13.000</b> · NetWt <b>13.000</b> → <b>Save</b> → Yes")],
    ["Job History HandMade: Loss <b>0.200</b> · <b>1.52%</b>, allowed 3.5% of the issued 13.200 = <b>0.462</b>."],
) + mfg(
    "COLOUR", "FACTORY", "GrossWt <b>13.000</b> · NetWt <b>13.000</b>",
    "GrossWt <b>13.000</b> · NetWt <b>13.000</b>", "0", "Loss <b>0.000</b>.") + mfg(
    "PrePolish", "BUDDHA POL", "GrossWt <b>13.000</b> · NetWt <b>13.000</b>",
    "GrossWt <b>12.900</b> · NetWt <b>12.900</b>", "0.35", "Loss <b>0.100</b> · <b>0.77%</b>.") + mfg(
    "Setting", "rakesh sarkar", "GrossWt <b>12.900</b> · NetWt <b>12.900</b>",
    "GrossWt <b>13.080</b> · NetWt <b>12.850</b>", "3",
    "Setting labour <b>₹240</b> = 8 Polki set × ₹30. Job Card Bag: POLKI Iss 10, Back <b>2 / 0.160</b>; "
    "EMERALD Iss 5, Bal 0.",
    extra_iss="select the line → <b>F3 Stone</b> → POLKI 12-14 <b>10</b>, EMERALD PEAR <b>5</b> → OK",
    extra_rcv="select the line → <b>F3</b> → POLKI 12-14 <b>2</b> back → OK") + mfg(
    "Final Polish", "BUDDHA POL", "GrossWt <b>13.080</b> · NetWt <b>12.850</b>",
    "GrossWt <b>12.990</b> · NetWt <b>12.760</b>", "0.35", "Loss <b>0.090</b> · <b>0.70%</b>.") + mfg(
    "final setting", "akshay j", "GrossWt <b>12.990</b> · NetWt <b>12.760</b>",
    "GrossWt <b>12.970</b> · NetWt <b>12.740</b>", "0", "Loss <b>0.020</b>.") + mfg(
    "Meena", "JAGDISH PRA", "GrossWt <b>12.970</b> · NetWt <b>12.740</b>",
    "GrossWt <b>12.950</b> · NetWt <b>12.720</b>", "", "Loss <b>0.020</b>.") + mfg(
    "Puwai", "JAGDISH PRA", "GrossWt <b>12.950</b> · NetWt <b>12.720</b>",
    "GrossWt <b>12.930</b> · NetWt <b>12.700</b>", "",
    "Loss <b>0.020</b>. This was the last step — the job is now <b>Pending for MFG Transfer</b>.") + step(
    "Manufacturing ▸ Issue / Received — other buttons", [],
    ["<b>Day Book</b> → today's vouchers, grouped by process. <b>Statement</b> → Worker Metal Ledger.",
     "<b>Delete</b> on your CASTING receipt → refused: <i>\"delete the later voucher first\"</i>. Nothing is deleted."],
) + part("E. Job History — the full story of one job") + step(
    "Production Planning ▸ Job History (F11)", [("Job No", "your job")],
    ["11 rows; issue side <b>pink</b>, receive side <b>green</b>. Losses 0.300 · 0.200 · 0.000 · 0.100 · 0.050 · "
     "0.090 · 0.020 · 0.020 · 0.020 → total <b>0.800 g</b>.",
     "Setting row Labour <b>240.00</b>. Double-click a pink cell → issue voucher; green cell → receipt.",
     "<b>Show Pending</b> → nothing pending (job complete)."],
) + part("F. MFG Transfer → Stock → Tag → Item Search") + step(
    "Manufacturing ▸ Pending for MFG Transfer", [],
    ["Your job is in the list. <b>F10</b> on its row opens its Job Bag."],
) + step(
    "Manufacturing ▸ MFG Transfer", [("Show Pending", "tick your job → OK (prices fill in)")],
    ["Title 590 · Loss% <b>6.30</b> · N-Wt <b>12.700</b> · FineWt <b>7.493</b> · Metal Rate <b>8,680.67</b> · "
     "Metal Amount <b>1,10,244.51</b>.",
     "Stone Amount <b>6,184.00</b> (Polki 0.640 ct × 8,100 = 5,184 + Emerald 0.500 ct × 2,000 = 1,000).",
     "Labour 1,200 × 12.700 = <b>15,240.00</b>. Total <b>1,31,668.51</b> · Margin 50% <b>65,834.26</b> · "
     "Price <b>1,97,502.77</b> · Tag <b>197</b>.",
     "Double-click a grey cell → <b>Cost Break-up</b>. <b>Print</b> → PDF · <b>Excel Format</b> → .xlsx."],
) + step(
    "MFG Transfer → Save", [("Save", "Yes")],
    ["You get a Stock No and the <b>Tag List</b> opens. Try Print Tag Price on / off, Detail, Print Selected, "
     "Print All, Create Txt."],
) + step(
    "Sale ▸ Reports ▸ Ready Stock", [],
    ["Your piece: Primary · cost <b>1,31,668.51</b> · price <b>1,97,502.77</b> · tag <b>197</b>."],
) + step(
    "Item Search (top right, or Ctrl+I)", [("Search", "your Stock No, Job No or NS-1430 → Enter")],
    ["Piece card: client, order, G-Wt 12.930, N-Wt 12.700, cost / price / tag; stones; value summary.",
     "The top grid is the <b>barcode history</b>: MF (made)."],
) + step(
    "Item Search → Delete History &amp; Purchase (correction)", [("Reason", "test correction")],
    ["The piece leaves stock; the job is back in <b>Pending for MFG Transfer</b>.",
     "Do MFG Transfer again → Show Pending → Save → Stock No (<b>1</b> again on a fresh demo). From now on this "
     "is <b>your piece</b>."],
) + part("G. Stones") + step(
    "Job Card Bag — return the 2 extra Polki to stock", [
        ("Job No", "your job"), ("POLKI 12-14 line", "select → <b>Return to Stock</b> → 2 pcs → Location Primary")],
    ["POLKI Bal <b>0</b>."],
) + part("H. Reports — is everything linked?") + step(
    "Inventory ▸ Metal ▸ Reports ▸ Metal Analysis", [],
    ["RAJESH JI · 14KT 590: Inward <b>252.800</b>, Outward <b>3.625</b>, Closing <b>249.175</b>. Primary · 24KT Gold "
     "<b>800.000</b>. Double-click a row → that location's ledger."],
) + step(
    "Reports ▸ Inventory ▸ Worker Balance (Metal)", [],
    ["CHAND KUMAR HAZRA · 14KT 590 — see the balance; RAHUL JI −0.262 (checked again in part S)."],
) + step(
    "Reports ▸ Karigar ▸ Worker Metal Ledger", [],
    ["CHAND KUMAR HAZRA closing <b>1.545 g</b>; Manufacturing ▸ Issue with CHAND shows <b>Mt Bal 1.545 g</b> — "
     "the same.",
     "RAHUL JI: ISS 13.200 · RTN 13.000 · Loss 0.200 · allowed 0.462 · Balance <b>−0.262</b> (the allowance was more "
     "than the real loss)."],
) + step(
    "Reports ▸ Karigar ▸ Worker Stone Ledger / Setting Labour Statement", [],
    ["rakesh sarkar on your job: ISS POLKI <b>10</b> · ISS EMERALD <b>5</b> · BACK POLKI <b>2</b> · SET POLKI <b>8</b> · "
     "SET EMERALD <b>5</b>. Setting labour: POLKI set 8 × 30 = <b>240.00</b>."],
) + step(
    "Open every other report", [],
    ["Issue / Received Day Book · Pending for MFG Transfer · MFG Transfer Day Book · Metal / Stone Day Book · "
     "Job Analysis · Process Analysis.",
     "On each report try: Search · Group · Auto Filter · Adv. Filter · Set Column · <b>Export</b> · <b>Print</b>."],
) + part("I. Job Costing") + step(
    "Manufacturing ▸ Job Costing", [("Run", "keep the dates → Run")],
    ["Your job: G-Wt <b>12.930</b> · N-Wt <b>12.700</b> · Metal <b>1,10,244.51</b> · Stone <b>6,184.00</b> · Labour "
     "<b>15,480.00</b> (setting 240 + 15,240) · Total <b>1,31,908.51</b> · Price <b>1,97,862.77</b> · Tag <b>197</b>.",
     "<b>Ctrl+F1</b> → Diamond / Polki / Colour Stone columns. <b>Ctrl+P</b> → Excel.",
     "Double-click your job → Costing Sheet. <b>Export To Excel</b> → the amounts are formulas."],
) + part("J. MFG Transfer — Edit and prints") + step(
    "Manufacturing ▸ MFG Transfer → Edit", [
        ("Edit", "Vr 1 → OK"), ("Margin % (green)", "<b>40</b> → Enter → <b>Save</b> → Yes")],
    ["Item Search: price <b>1,84,335.91</b>, tag <b>184</b>, same Stock No.",
     "Edit again → Margin % <b>50</b> → Save → price back to <b>1,97,502.77</b>, tag <b>197</b>."],
) + step(
    "MFG Transfer — prints", [],
    ["<b>Format-2</b> → PDF with each piece's cost break-up. <b>Tag Print</b> → tags PDF. <b>Excel Format</b> → .xlsx."],
) + part("K. Sale — Approval, Sale, Excel Invoice, Return") + step(
    "Sale ▸ Ready Stock ▸ Approval", [
        ("Account", "<b>KK JEWELS</b>"), ("Read Barcode / SKU here", "your Stock No (<b>1</b>) → Enter"),
        ("Save", "Yes")],
    ["Line: Metal Amount <b>1,10,244.51</b> · Fine With Loss <b>7.965</b> · Stone <b>6,184.00</b> · Labour "
     "<b>15,240.00</b> · Total <b>1,31,668.51</b>.",
     "Barcode <b>99999</b> → <i>\"Item not found\"</i>.",
     "Sale ▸ Reports ▸ <b>Ready Stock Approval Balance</b> → KK JEWELS · your piece · days 0."],
) + step(
    "Sell the approval piece to someone else (must be refused)", [
        ("Sale ▸ Ready Stock ▸ Sale", "Account <b>FACTORY</b> · barcode <b>1</b> → Enter")],
    ["Message: <i>\"Stock No 1 is out on approval with KK JEWELS …\"</i>. Click <b>Add</b> to clear."],
) + step(
    "Sale ▸ Ready Stock ▸ Approval Return", [
        ("Account", "<b>KK JEWELS</b> → <b>Show App</b> → tick your piece → OK"), ("Save", "Yes")],
    ["The piece is back in stock. Approval Balance is empty."],
) + step(
    "Sale ▸ Ready Stock ▸ Sale — From Order", [
        ("Account", "<b>KK JEWELS</b>"), ("Credit Days", "<b>30</b>"),
        ("From Order", "your order's row (Ref <b>TEST-1</b>) → type <b>1</b> in its green <b>Take</b> cell → OK"),
        ("Save", "Yes")],
    ["Total <b>1,31,668.51</b>. After Save, <b>Cl Bal 1,31,668.51 Dr</b>.",
     "From Order again → your order is no longer listed (it is shipped)."],
) + step(
    "Excel Invoice and Print", [("Excel Invoice", "save → open in Excel")],
    ["Your piece's row: Metal <b>1,10,244.51</b> · POLKI <b>5,184</b> · EMERALD <b>1,000</b> · Labour <b>15,240</b> · "
     "TOTAL <b>1,31,668.51</b>. Amount cells are formulas.",
     "<b>Print</b> → invoice PDF. <b>Catalog</b> → photo PDF."],
) + step(
    "Sale ▸ Ready Stock ▸ Sale Return", [
        ("Account", "<b>KK JEWELS</b> → <b>Sold Pieces</b> → your piece → OK"), ("Save", "Yes")],
    ["The piece is back in stock. KK's <b>Cl Bal 0.00</b>.",
     "Item Search → history: <b>MF · RA · RAR · RS · RSR</b>."],
) + part("L. Repair") + step(
    "Production Planning ▸ Order → + New (repair order)", [
        ("Ord Type / Customer", "Customer / <b>KK JEWELS</b>"), ("Repair", "<b>tick</b>"),
        ("SKU Lines", "leave empty"), ("Save", "Yes")],
    ["With Repair ticked it saves with no lines."],
) + step(
    "Order list → Repair List", [("Order", "select the repair order → <b>Repair List</b> → tick your piece → OK")],
    ["The order gets a line: NS-1430 · Gross <b>12.930</b> · Metal <b>1,10,244.51</b>, and a new job."],
) + step(
    "Sale ▸ Ready Stock ▸ Ready Repair Issue", [
        ("Account", "<b>KK JEWELS</b>"), ("Barcode", "<b>1</b> → Enter"), ("Save", "Yes")],
    ["Sale ▸ Reports ▸ <b>Repair Register</b> → KK JEWELS · piece 1 · <b>Out for repair</b>.",
     "Then <b>Delete</b> this voucher → the piece is back in stock (needed for later steps)."],
) + part("M. Purchase — Ready Items, Return, Opening Stock") + step(
    "Purchase ▸ Ready Items", [
        ("Supplier", "<b>TEST SUPPLIER</b>"), ("Bill Number", "<b>B-56</b>"),
        ("SKU Search", "NS-1430 → OK"),
        ("Add Piece", "Location Primary · Metal <b>14KT 590</b> · Gross <b>10.000</b> · Net <b>8.000</b> · Labour Rate "
                      "<b>1200</b> · <b>Stones…</b> → POLKI 12-14 · Pcs 2 · Cts 0.160 · Price 8100 → OK → OK"),
        ("Save", "Yes")],
    ["Line: Metal <b>69,445.36</b> · Stones <b>1,296.00</b> · Labour <b>9,600.00</b> · Total <b>80,341.36</b>.",
     "After Save: <i>New Stock No 2</i>. TEST SUPPLIER balance <b>5,29,334.86 Cr</b>."],
) + step(
    "Purchase ▸ Ready Item Return", [
        ("Supplier", "<b>TEST SUPPLIER</b> → <b>Show Stock</b> → tick Stock No <b>2</b> → OK"), ("Save", "Yes")],
    ["Piece 2 goes back. TEST SUPPLIER balance <b>4,48,993.50 Cr</b>. Item Search 2 → status <i>returned</i>."],
) + step(
    "Purchase ▸ Opening Stock", [
        ("Ready Items", "Add Piece: NS-1430 · Primary · 14KT 590 · Gross <b>5</b> · Net <b>4</b> → Save"),
        ("Metal", "+ New → Primary · <b>24KT Gold</b> · Weight <b>5</b> → Save")],
    ["The opening piece gets Stock No <b>3</b>; no accounting entry."],
) + part("N. Metal Sale, Stone Sale / Approval") + step(
    "Sale ▸ Metal → + New", [
        ("Account", "<b>KK JEWELS</b>"),
        ("Line", "Primary · <b>24KT Gold</b> · Colour Y · Weight <b>10</b> · Price <b>15050</b>"), ("Save", "Yes")],
    ["Amount <b>1,50,500.00</b>. Metal Analysis → Primary 24KT Gold <b>795.000</b> (800 + 5 − 10)."],
) + step(
    "Sale ▸ Stone ▸ Sale / Approval / Approval Return", [
        ("Sale", "KK JEWELS · Primary · POLKI 12-14 · Pcs 2 · Weight 0.160 → Save (amount 1,296)"),
        ("Approval", "KK JEWELS · Primary · EMERALD PEAR 3*4 · Pcs 4 · Weight 0.400 → Save"),
        ("Approval Return", "KK JEWELS · Primary · EMERALD PEAR 3*4 · Pcs 1 · Weight 0.100 → Save")],
    ["Sale ▸ Reports ▸ <b>Stone Approval Analysis</b> → EMERALD: out 4 · back 1 · balance <b>3 / 0.300</b>.",
     "KK's Cl Bal <b>1,51,796.00 Dr</b>."],
) + part("O. Inventory — Stock Transfer, Melting, Stone Issue by Lot") + step(
    "Inventory ▸ Stock Transfer → Stock Location Transfer", [
        ("Metal / Stone", "<b>Stone</b> · Item <b>POLKI 12-14</b>"), ("From → To", "<b>Primary</b> → <b>RAJESH JI</b>"),
        ("Sent", "Pcs <b>5</b> · Weight <b>0.400</b>"), ("Loss", "Pcs <b>1</b> · Weight <b>0.080</b> · Price 8100"),
        ("Save", "Yes")],
    ["RAJESH JI gets <b>4 / 0.320</b>. Stone Loss Register → 1 pc · 0.080 · <b>648.00</b>."],
) + step(
    "Stock Transfer → Stock Melting", [
        ("Add", "new voucher"), ("Stock Melting", "Stock No <b>1</b> → OK"), ("Save", "Yes")],
    ["The piece is <b>melted</b>; metal and stones come back to Primary.",
     "<b>Delete</b> this voucher → the piece is back in stock (undo test)."],
) + step(
    "Inventory ▸ Stone ▸ Issue Outside / Worker → Read Cert/Lot", [
        ("Read Cert/Lot", "<b>LOT-7</b> → OK (a filled line opens)"),
        ("Form", "Account <b>CHAND KUMAR HAZRA</b> · Pcs <b>2</b> · Weight <b>0.160</b> → Save")],
    ["Inventory ▸ Stone ▸ Receipt → <b>Show O/S</b> → CHAND: POLKI 12-14 <b>2 / 0.160</b> still out."],
) + part("P. Registers and other reports") + step(
    "Inventory ▸ Reports ▸ Registers", [],
    ["<b>Metal Loss Register</b>: 9 rows for your job; HandMade allowed 0.462.",
     "<b>WIP Register</b>, <b>Process Summary</b>, <b>WIP Stone</b>, <b>Dust Register</b> open and run."],
) + step(
    "Dashboard, F12, Daily Metal Rate", [],
    ["Dashboard ▸ BARCODE READ: <b>1</b> → Item Search; <b>28857</b> → Job History.",
     "<b>F12</b> → type 'worker metal' → Enter → Worker Metal Ledger."],
) + part("Q. Settings and menu") + step(
    "Tools ▸ Option", [],
    ["<b>Settings</b> tab ▸ Others ▸ <b>Ask \"Save? Yes / No\"</b> = False → Save → no popup on save; set back to True.",
     "Settings ▸ Inventory ▸ <b>When a location would go below zero</b> = <b>Block the save</b> → the 500 g issue is "
     "refused; set back to <b>Warn, then allow</b>.",
     "<b>Menu</b> tab: untick Production Planning items → Save → they leave the menu; tick them back."],
) + step(
    "Look and feel", [],
    ["All modules are in the top menu. Each report opens full width in its own tab.",
     "<b>Ctrl+F</b> → type 'job his' → Job History opens."],
) + part("R. Accounts") + step(
    "Account Groups and Trial Balance", [
        ("Account ▸ Groups", "look at the tree → <b>Reindex</b>"),
        ("Account ▸ Trial Balance", "From 01-04 · To today → Show; then <b>Ctrl+F1</b> (Detailed)")],
    ["Trial Balance: total Dr = total Cr."],
) + step(
    "Receivables, and a cash receipt (oldest bill first)", [
        ("Account ▸ Outstandings ▸ Receivables", "As on today"),
        ("Account ▸ Voucher Entry ▸ Receipt", "Account <b>KK JEWELS</b> · Mode <b>Cash</b> · Amount <b>50000</b> → "
         "<b>Auto FIFO</b> → Save")],
    ["Before: KK owes MS 1 <b>1,50,500.00</b> and SS 1 <b>1,296.00</b>; balance <b>1,51,796.00 Dr</b>.",
     "After: MS 1 pending <b>1,00,500.00</b>; KK balance <b>1,01,796.00 Dr</b>."],
) + step(
    "Metal receive (settle in gold)", [
        ("Account ▸ Voucher Entry ▸ Receipt", "KK JEWELS · Mode <b>Metal</b> · Metal <b>24KT Gold</b> · Location "
         "<b>Primary</b> · Weight <b>2</b> → Save")],
    ["Rate <b>14,713</b> → Amount <b>29,426.00</b>; KK balance <b>72,370.00 Dr</b>.",
     "Account ▸ More ▸ <b>Cash Flow</b> shows the 50,000 cash receipt."],
) + step(
    "Ledger, Day Book, Client Metal O/S", [
        ("Account ▸ Ledger", "KK JEWELS → Show; double-click a month; <b>Ctrl+G</b> graph"),
        ("Account ▸ Day Book", "today"),
        ("Account ▸ Outstandings ▸ Client Metal O/S", "As on today")],
    ["Client Metal O/S KK JEWELS: FINE O/S <b>8.000</b> (10 g sold − 2 g received), AMT O/S <b>72,370.00</b>."],
) + part("S. Karigar and client metal / stone balances") + step(
    "Worker Metal Ledger and Worker Balance (Metal)", [
        ("Reports ▸ Karigar ▸ Worker Metal Ledger", "this year"),
        ("Reports ▸ Inventory ▸ Worker Balance (Metal)", "As on today")],
    ["GROUP column shows Worker / Client. RAHUL JI's RTN row: ALW L WT <b>0.462</b>, ALW L FINE <b>0.273</b>.",
     "Worker Balance: RAHUL JI balance <b>−0.262</b>; KK JEWELS (Client) 24KT Gold balance <b>8.000</b>.",
     "Tools ▸ Option ▸ Settings ▸ Manufacturing ▸ 'Loss allowance worked on' = Weight received back → allowed "
     "becomes 0.455. Set it back to 'Weight issued'."],
) + step(
    "Stone balances and summaries", [
        ("Reports ▸ Stone ▸ Location Wise Stone Balance", "Location <b>Primary</b>"),
        ("Reports ▸ Stone ▸ Stone Summary", "As on today"),
        ("Reports ▸ Inventory ▸ Metal Summary", "As on today")],
    ["Primary POL: Opening <b>225.000 / 900</b>, Closing <b>231.640 / 983</b>; CS Closing <b>229.200 / 942</b>.",
     "Worker Balance (Stone): KK JEWELS EMERALD PEAR 3*4 closing <b>3</b> pcs.",
     "Metal Summary: RAJESH JI 14KT 590 INV <b>249.175</b>."],
) + part("T. Client price chart (MANNU BHAI)") + step(
    "Use a price chart on a sale", [
        ("Tools ▸ Client Wise Labour Price", "choose MANNU BHAI (Per Grm Price 1,175)"),
        ("Master ▸ Account ▸ KK JEWELS", "Price Chart = <b>MANNU BHAI</b> → Save"),
        ("Tools ▸ Option ▸ Settings ▸ Order & Quotation", "Client wise price chart applicable = <b>True</b> → Save"),
        ("Sale ▸ Ready Stock ▸ Sale", "Account KK JEWELS → scan barcode <b>1</b> (do not save)")],
    ["'Prices From Client Chart (MANNU BHAI)' is ticked; Labour Rate <b>1,175</b>, Labour <b>14,922.50</b>; "
     "Stone Amount <b>10,466.00</b> (MANNU BHAI's sheet: POLKI 12-14 0.640 × 14,400 + EMERALD PEAR 0.500 × 2,500); "
     "Total <b>1,35,633.01</b>. Untick → back to 1,200 / 15,240 / 6,184 / 1,31,668.51.",
     "Tools ▸ Client Wise Stone Price ▸ MANNU BHAI has <b>282</b> rows (POLKI 12-14 <b>14,400</b>).",
     "Labour Price → Add Row: Family <b>Diamond Jewellery</b>, From G-Wt 10, To 20, SalePrice 900 → Save → scan "
     "again: Labour <b>11,430.00</b>, Total <b>1,32,140.51</b>."],
) + part("U. Stock tools") + step(
    "Stock Reconciliation", [
        ("Tools ▸ Stock Reconciliation", "New Count → scan <b>1</b> (Enter), then <b>999999</b>")],
    ["In Stock Show: Stock 1. Not scanned: Stock <b>3</b>. Not found: 999999. Scanning 1 again → '(1 already "
     "scanned)'. Export To Excel → 3 sheets."],
) + step(
    "Stock View, SKU Status, Closing Stock, Barcode Catalog", [
        ("Tools ▸ Stock View", "All Stock → Filter; Stone Info ▸ SSKU <b>POLKI</b> → Filter"),
        ("Sale ▸ Reports ▸ SKU Status", "SKU <b>NS-1430</b>"),
        ("Sale ▸ Reports ▸ Ready Closing Stock", "select a row → Ctrl+S (Catalog), Ctrl+T (Tag Print)"),
        ("Tools ▸ Barcode Catalog", "By SKU → NS-1430 → Enter → Catalog 4x8")],
    ["Stock View: All = 3 pieces; POLKI filter = Stock 1.",
     "SKU Status: Stock 1 (In-Stock), Stock 2 (Returned), Stock 3 (In-Stock), plus the jobs in work."],
) + part("V. Sales reports and dashboards") + step(
    "Registers", [
        ("Sale ▸ Reports", "Sales Register / Sales Return Register / Sales Profit Analysis / Purchase - Sales "
                           "Analysis / Today's Daybook")],
    ["Sales Register: KK JEWELS 1,31,668.51, RETURN <b>Y</b>. Today's Daybook: every voucher, stones under each "
     "piece."],
) + step(
    "Sales Dashboard and Business Dashboard", [
        ("Reports ▸ Sales Dashboard", "By Client · Value → Show"),
        ("Reports ▸ Business Dashboard", "open the 4 tabs")],
    ["KK JEWELS net <b>0.00</b> (sale − return). Bar chart + table.",
     "Department Pending, Daily Output, Daily Sale & Return, Bills Due."],
) + part("W. Tools — settings, corrections, backup, complaint, gate pass") + step(
    "Option, Advance Options, Audit Log", [
        ("Tools ▸ Option ▸ Settings", "Others ▸ DIGICAT id = 1203 → Save"),
        ("Tools ▸ Advance Options ▸ Job Card Corrections", "Job <b>28854</b> → C Ref 'TEST' → Update C Ref with "
         "no Reason → then type Reason 'test' and try again"),
        ("Tools ▸ Advance Options ▸ Declarations", "Sale Ready Stock line 1 'Subject to Jaipur jurisdiction' → Save"),
        ("Tools ▸ Audit Log", "today")],
    ["Settings show 'Changed by / at' with your name and time.",
     "Without a reason the correction is <b>refused</b>; with a reason it saves. Audit Log shows before → after.",
     "A sale print shows the declaration at the bottom."],
) + step(
    "Backup, Complaint, Gate Pass", [
        ("Tools ▸ Backup", "Backup Now"),
        ("Tools ▸ Register a Complaint", "+ New: From Customer, JOB# 28854, 'stone loose' → Save → Lookup History"),
        ("Tools ▸ Gatepass", "+ New: Destination 'Mumbai office', Box Pcs 3 → Save → Print → Register")],
    ["A dated backup file in the list. Lookup History shows the job's steps. Gate pass PDF; unconfirmed rows are red."],
) + part("X. Split step and Item Search") + step(
    "One step for two karigars (0.4 + 0.6)", [
        ("Job History", "Job <b>28350</b> → + Issue → Split share <b>0.4</b>, karigar A, Net 10 → Save; + Issue → "
         "share empty (the 0.6 left), karigar B, Net 5 → Save")],
    ["Worker column 'A (0.4 pc)', 'B (0.6 pc)'. A third issue is refused: 'already out in full'.",
     "Receive B → still on the same step; WIP <b>0.4</b>. Receive A → the step is done."],
) + step(
    "Item Search", [("Any screen", "<b>Ctrl+I</b> → Stock No <b>1</b>")],
    ["Status In-Stock / Primary; 'This SKU Stock: made <b>3</b>, left <b>2</b>'; Print, Cert Excel, Costing Sheet."],
) + part("Y. Fixes of 6–7 Oct and the client's data") + step(
    "The app must not close (crash fix)", [
        ("Reports ▸ Karigar ▸ Worker Metal Ledger", "while it shows 'Running…', click the tab's <b>×</b>"),
        ("Account ▸ Outstandings ▸ Client Metal O/S", "double-click KK JEWELS → close the popup at once; do it 5 "
         "times quickly")],
    ["The app <b>stays open</b> (before the fix it closed)."],
) + step(
    "Everything fits a laptop screen (1366 × 768)", [
        ("Sale ▸ Ready Stock ▸ Sale", "open"), ("Tools ▸ Stock View", "open"), ("Tools ▸ Option", "Menu tab")],
    ["Sale: the buttons wrap onto two lines; nothing is cut; no sideways scrolling.",
     "Stock View: <b>Filter</b> at the top; the filters scroll.",
     "Long lists scroll; nothing is cut at the bottom."],
) + step(
    "Report grid — two-level group, Ctrl+E, Set Column", [
        ("Reports ▸ Karigar ▸ Worker Metal Ledger", "Group = <b>GROUP</b> · then = <b>WORKER</b>"),
        ("Same report", "<b>Ctrl+E</b>; then hide a column with Set Column"),
        ("Close and reopen the app", "same report")],
    ["'GROUP : Client' / 'GROUP : Worker', each worker inside, a Total at both levels.",
     "Ctrl+E saves an Excel file. The hidden column stays hidden."],
) + step(
    "Sales Register and Ready Closing Stock shortcuts", [
        ("Sale ▸ Reports ▸ Sales Register", "<b>F9</b>; select a row → <b>Ctrl+C</b>"),
        ("Sale ▸ Reports ▸ Ready Closing Stock", "<b>Ctrl+F1</b>")],
    ["F9 shows / hides the A/C ID column. Ctrl+C makes a Catalog PDF.",
     "Closing Stock: Stock 1 POL <b>5,184.00</b>, CS <b>1,000.00</b>; Ctrl+F1 shows / hides these columns."],
) + step(
    "The client's stone price sheet (price type A)", [
        ("Tools ▸ Client Wise Stone Price", "choose <b>A</b>"),
        ("Master ▸ Account ▸ KK JEWELS", "Price Chart = <b>A</b> → Save"),
        ("Sale ▸ Ready Stock ▸ Sale", "Account KK JEWELS → scan <b>1</b> (do not save)"),
        ("Client Wise Stone Price ▸ A", "<b>Export Excel</b>, then <b>Import Excel</b> the same file")],
    ["A has <b>299</b> rows: AMETHYST CABS 250 … POLKI 6-8 <b>10,750</b> … POLKI 12-14 <b>15,000</b>.",
     "Sale: Stone Amount <b>10,850.00</b> (POLKI 0.640 × 15,000 + EMERALD 0.500 × 2,500); Labour stays "
     "<b>15,240.00</b>; Total <b>1,36,334.51</b>.",
     "Import: '299 stone price(s) imported'."],
) + step(
    "The client's master sheet and locations", [
        ("Master ▸ Account", "search <b>A B JEWELS</b>, then <b>SWARNVILLA</b>"),
        ("Master ▸ Metal", "find <b>22KT GOLD 92.25</b> and <b>9KT GOLD</b>"),
        ("Master ▸ Location", "look at the list"),
        ("Tools ▸ Advance Options ▸ Masters Excel", "<b>Masters Excel</b> → save; then <b>Import Masters Excel</b> "
         "the same file")],
    ["A B JEWELS is a client (Sundry Debtors); SWARNVILLA is a vendor (Accounts Payable).",
     "22KT GOLD 92.25 has purity 92.25; 9KT GOLD 37.5.",
     "Locations include <b>vishal ji</b> and <b>VISHAL JIDISMENTAL</b>.",
     "Import says every count is 0 — nothing is added twice.",
     "Karigars (All Department Worker sheet): Master ▸ Account → <b>ABHIJEET DAS</b> is a Worker, Department "
     "<b>Setting</b>, In-house ticked; <b>AJAY BABU</b> is HandMade, In-house <b>not</b> ticked (outside); "
     "Manufacturing ▸ Issue's Account list has all the karigars."],
) + ("<p class='muted'>If anything is wrong, send: the step number, what you did, what you expected, what you saw, "
     "and a screenshot. To start again from zero: <b>Reset DEMO and open.bat</b>.</p>")


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    out = (Path(sys.argv[1]) if len(sys.argv) > 1
           else Path.home() / "Downloads" / "DiaGold-Test-Guide-English.pdf")
    print(render(HTML, out))
