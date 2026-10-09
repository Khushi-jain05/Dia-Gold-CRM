"""Render the full-flow test guide (the whole CRM, step by step) to a PDF.

    python docs/build-full-flow-pdf.py [out.pdf]

One new job taken from order to ready stock through every screen built so
far (Masters, Inventory, Production Planning, Manufacturing, Reports, and the
5 Oct Accounts / price chart / stock tools / dashboards / Tools in parts R-X), with
what to type at each step and the figure each screen should show. The job
uses the same inputs as demo job DEMO-C, whose figures are checked by the
acceptance scripts, so every expected number below is one the app produced.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


# Qt's HTML renderer sizes <h1>/<h2>/<h3> by its own scale whatever the CSS
# says, and takes the body font from the platform (13pt on a Mac), which is
# what made the first print look oversized. Headings are therefore plain
# paragraphs with explicit sizes, and the default font is set on the document
# (see render()).
FONT = "Helvetica Neue"
CSS = f"""
<style>
p {{ margin: 2px 0; }}
table {{ border-collapse: collapse; margin: 3px 0 5px 0; }}
th, td {{ border: 1px solid #C9CFCA; padding: 3px 5px; vertical-align: top; }}
th {{ background: #EEF1EE; text-align: left; font-weight: 600; }}
.ok {{ color: #0E6B54; font-weight: 600; }}
.muted {{ color: #5C6661; }}
</style>
"""
H1 = "<p style='font-size:15pt; font-weight:700; margin:0 0 3px 0'>{}</p>"
H2 = ("<p style='font-size:10.5pt; font-weight:700; color:#0E6B54; "
      "margin:10px 0 3px 0'>{}</p>")
H3 = ("<p style='font-size:10pt; font-weight:700; color:#7A5B00; margin:14px 0 2px 0'>"
      "{}</p>")
BOX = "<table width='100%' style='margin:4px 0'><tr><td style='background:#F2EBD6; border:none; padding:5px 7px'>{}</td></tr></table>"

_n = 0


def step(title: str, rows: list[tuple[str, str]], checks: list[str], intro: str = "") -> str:
    global _n
    _n += 1
    body = H2.format(f"{_n}. {title}")
    if intro:
        body += f"<p>{intro}</p>"
    if rows:
        body += ("<table width='100%'><tr><th width='28%'>Field / Column</th>"
                 "<th>Bharo (type this)</th></tr>")
        body += "".join(f"<tr><td>{f}</td><td>{v}</td></tr>" for f, v in rows) + "</table>"
    body += "".join(f"<p><span class='ok'>✔ Check:</span> {c}</p>" for c in checks)
    return body


def part(title: str) -> str:
    return H3.format(title)


def mfg(process: str, karigar: str, iss: str, rcv: str, allow: str, expect: str,
        extra_iss: str = "", extra_rcv: str = "") -> str:
    """One process: Manufacturing ▸ Issue, then Manufacturing ▸ Received."""
    rows = [("Manufacturing ▸ Issue", f"Process <b>{process}</b> · Account <b>{karigar}</b> · "
                                       "<b>Show Pending</b> → apna job tick → OK"),
            ("Issue line (green cells)", iss + (f" · Allow Loss % <b>{allow}</b>" if allow else "")
             + (f" · {extra_iss}" if extra_iss else "") + " → <b>Save</b> → Yes"),
            ("Manufacturing ▸ Received", f"Process <b>{process}</b> · Account <b>{karigar}</b> · "
                                          "<b>Show Pending</b> → apna job tick → OK"),
            ("Receive line (green cells)", rcv + (f" · {extra_rcv}" if extra_rcv else "")
             + " → <b>Save</b> → Yes")]
    return step(f"{process} — {karigar}", rows, [expect])


HTML = CSS + """
""" + H1.format("Dia Gold CRM — Full Test Guide") + """
<p class='muted'>Poore CRM ka testing guide — Order se Ready Stock, phir Sale, Approval, Repair, Purchase,
Stock Transfer, saare Reports, 5 Oct ke Accounts, price chart, stock tools, dashboards aur Tools (R–X), aur
6–7 Oct ke fixes (Y) tak. Har step pe: kahan jaana hai, kya type karna hai, aur screen pe kya aana
chahiye. Jisne app pehle kabhi nahi chalaya, wo bhi shuru se aakhir tak kar sake — bas step order me chalein.</p>
""" + BOX.format("""<b>Kya chahiye:</b> Windows PC, aur <b>DiaGoldCRM-Windows-x64.zip</b> (jo file bheji hai).
Testing ek <b>alag DEMO database</b> pe hoti hai — asli data ko kuch nahi hota. Demo me pehle se: rates
(24K fine 14,713/g → 14KT 590 = 8,680.67/g), labour 1,200/g, margin 50%, karigar CHAND KUMAR HAZRA,
supplier SHRIKANT, customer KK JEWELS, demo jobs 28854–28856, aur client ki master lists aur stone price
sheet.""") + part("0. Install aur app kholna") + step(
    "Zip kholna (sirf pehli baar)", [
        ("Zip file", "<b>DiaGoldCRM-Windows-x64.zip</b> pe right-click → <b>Extract All…</b> → Extract"),
        ("Folder", "Naye folder me <b>DiaGoldCRM.exe</b> aur do files dikhengi: "
                   "<b>Open DEMO (testing).bat</b> aur <b>Reset DEMO and open.bat</b>")],
    ["Folder Desktop pe rakh lo — har baar wahin se kholna hai."],
) + step(
    "Demo kholna", [
        ("Double-click", "<b>Open DEMO (testing).bat</b>"),
        ("Windows ka blue warning aaye", "<b>More info</b> → <b>Run anyway</b> (pehli baar hi aata hai)"),
        ("Login", "User <b>admin</b> · Password <b>admin</b> → Enter")],
    ["Window ke title me <b>DEMO DATA (testing)</b> likha ho. Neeche status bar me <b>DiaGoldDemo</b> folder ka "
     "path. Ye na dikhe to band karo — asli data khul gaya hai.",
     "Testing dobara shuru se karni ho: <b>Reset DEMO and open.bat</b> → demo saaf ho kar naye sire se ban jaata hai.",
     "(Mac pe: project folder me <b>python -m diagold.demo --reset</b>.)"],
) + step(
    "App kaise chalta hai — 2 minute", [],
    ["Upar <b>menu bar</b>: Master, Production Planning, Manufacturing, Purchase, Inventory, Sale, Reports … "
     "Kisi pe click → list; ▸ wale pe mouse le jao → andar ka submenu.",
     "Har screen ek <b>tab</b> me khulti hai. Tab ka × → band. Window ▸ Close All → sab band (Dashboard chhod ke).",
     "List wali screens (Order, Purchase …): <b>+ New</b> → form bharo → <b>Save</b>. Har save pe "
     "<b>\"Save? Yes / No\"</b> aata hai — <b>Yes</b>.",
     "Voucher grids me <b>green cells</b> me type kar sakte ho: cell pe double-click (ya type shuru karo) → value → Enter.",
     "<b>Show Pending</b> = jo kaam baaki hai uski list → tick → OK. Dropdown me naam type karke bhi chun sakte ho.",
     "Shortcuts: <b>Ctrl+F</b> = Go to screen (naam type karo) · <b>F11</b> = Job History · <b>F12</b> = saare reports "
     "ki list · reports me <b>F1</b> = Show All.",
     "Dashboard pe <b>BARCODE READ</b>: Stock No / SKU likh ke Enter → Item Search; Job No → Job History.",
     "Koi print / Excel ka button file save karta hai — message me file ka path aata hai."],
) + """
""" + BOX.format("""<b>Aapka job:</b> step 14 me order save hote hi ek naya Job No milega (fresh demo me
<b>28857</b>). Wahi number likh lein — step 15 se aakhir tak har jagah wahi job chunna hai. Demo jobs
(28854–28856) aur BANG-577 (28853) pe apne steps mat karein.<br>
<b>Har Save pe</b> "Save? Yes / No" popup aana chahiye — Yes dabayein. <b>Steps skip na karein</b> —
har step agle step ko data deta hai. Koi cheez dropdown / Show Pending me na mile to pichhla step reh gaya.""") + """
""" + BOX.format("""<b>Bug report:</b> step number · screen · kya dabaya · kya expect tha · kya hua · screenshot.""") + """
""" + part("A. Masters — jo rates aur log flow use karega") + step(
    "Master ▸ Daily Metal Rate", [],
    ["List me <b>14KT 590</b> aur <b>24KT Gold</b> — date 25-09-2026, rate <b>14,713</b> (24K fine rate).",
     "Ye hi rate MFG Transfer me Metal Rate 14,713 × 0.590 = <b>8,680.67</b> banata hai."],
) + step(
    "Master ▸ Labour", [],
    ["14KT 590 → <b>1,200</b> Per Gram, Net Weight, effective 01-09-2026."],
) + step(
    "Master ▸ Set Margins", [],
    ["Set <b>DEMO TAG 50</b> — Tag Margin <b>50%</b> (tag price = cost × 1.5)."],
) + step(
    "Master ▸ Setting Type", [],
    ["<b>Polki 30.00</b>, <b>Diam 3.00</b> per piece — setting labour yahi se banta hai."],
) + step(
    "Master ▸ Account → + New (ek naya karigar)", [
        ("Code", "RAHUL"), ("Name", "RAHUL JI"), ("Type", "Worker")],
    ["Save → Manufacturing ▸ Issue ke Account dropdown me RAHUL JI dikhega (step 21 — HandMade — me use hoga)."],
) + step(
    "Master ▸ Account → + New (ek naya supplier — jisse maal khareedenge)", [
        ("Code", "TESTSUP"), ("Name", "TEST SUPPLIER"),
        ("Type", "<b>Accounts</b> (supplier ka alag type nahi hai — Accounts hi chunein)"),
        ("Group", "<b>Accounts Payable</b>"),
        ("Phone / City / GSTIN", "9876543210 / Mumbai / 27ABCDE1234F1Z5 (optional)"),
        ("Opening Balance", "khaali chhodein")],
    ["Save → Accounts list me <b>TEST SUPPLIER</b>, Type Accounts.",
     "Inventory ▸ Stone / Metal ▸ Purchase ke <b>Supplier</b> dropdown me ab TEST SUPPLIER dikhega "
     "(step 10 aur 11 me isi se purchase hogi).",
     "Code ya Name khaali karke Save → refuse."],
) + part("B. Inventory — supplier se stock andar lao, karigar ko do") + step(
    "Inventory ▸ Stone ▸ Purchase → + New", [
        ("Supplier", "<b>TEST SUPPLIER</b> (step 9 wala)"), ("Ref No", "TEST-ST"),
        ("Line 1", "Location <b>Primary</b> · SSKU <b>POLKI 12-14</b> · Pcs <b>20</b> · Weight <b>1.600</b> · Price <b>8100</b> · Per Cts · Lot No <b>LOT-7</b>"),
        ("Line 2", "Location <b>Primary</b> · SSKU <b>EMERALD PEAR 3*4</b> · Pcs <b>10</b> · Weight <b>1.000</b> · Price <b>2000</b> · Per Cts")],
    ["Amount khud: line 1 <b>12,960.00</b>, line 2 <b>2,000.00</b>; neeche summary 2 lines · 30 pcs · 2.600 ct · amount <b>14,960.00</b>.",
     "Save → Vr No khud. Row select → <b>Print</b> → PDF."],
) + step(
    "Inventory ▸ Metal ▸ Purchase → + New", [
        ("Supplier", "<b>TEST SUPPLIER</b>"), ("Ref No", "TEST-MT"),
        ("Line", "Location <b>RAJESH JI</b> · Metal <b>14KT 590</b> · Colour Y · Weight <b>50.000</b> · Price <b>8680.67</b>")],
    ["Amount <b>4,34,033.50</b>; Save ke baad Fine <b>29.500</b> (50 × 0.590).",
     "Row select → <b>Attach Doc</b> → Add… → koi bhi PDF / photo (supplier ka bill) → list me dikhe, "
     "Open se khule.",
     "<b>Reports ▸ Inventory ▸ Account Ledger</b> (FY dates) → <b>TEST SUPPLIER</b>: SP Cr "
     "<b>14,960.00</b>, MP Cr <b>4,34,033.50</b>, balance <b>4,48,993.50 Cr</b>. "
     "<b>Purchase A/c</b> me dono Dr; uska closing <b>1,47,24,327.50 Dr</b> (demo purchases ke saath).",
     "Supplier ka hisaab: har purchase pe Dr Purchase A/c, Cr supplier — khud banta hai."],
) + step(
    "Inventory ▸ Metal ▸ Issue Outside / Worker → + New", [
        ("Account (worker)", "CHAND KUMAR HAZRA"),
        ("Line", "Location <b>RAJESH JI</b> · Metal <b>14KT 590</b> · Weight <b>2.000</b>")],
    ["Save → Fine <b>1.180</b>.",
     "Ek aur try: naya voucher, Weight <b>500</b> → 'This takes stock below zero' warning aayega "
     "(Tools ▸ Option me default = warn). No dabao — save nahi hoga."],
) + step(
    "Inventory ▸ Metal ▸ Receipt → + New", [
        ("Account (worker)", "CHAND KUMAR HAZRA"),
        ("Line", "Location <b>RAJESH JI</b> · Metal <b>14KT 590</b> · Weight <b>1.800</b> · Wastage % <b>2.5</b>")],
    ["Save → Wastage Wt khud <b>0.045</b>.",
     "CHAND ke paas ab is voucher se bacha: 2.000 − 1.800 − 0.045 = <b>0.155 g</b> (step 40 me check)."],
) + part("C. Order → Job → Route → Stones") + step(
    "Production Planning ▸ Order → + New", [
        ("Ord Type / Customer", "Customer / <b>KK JEWELS</b>"), ("Ref", "<b>TEST-1</b>"),
        ("Terms", "<b>15 days</b>"), ("Priority", "<b>High</b>"), ("Delivery Date", "aaj + 10 din"),
        ("SKU Lines row 1", "SKU <b>NS-1430</b> · Metal <b>14KT 590</b> · Colour <b>Y</b> · Size <b>7</b> · C-Ref <b>TEST-C</b> · Pcs <b>1</b>")],
    ["Save → Ord No khud; <b>1 job allot</b> hua — Job No likh lein (fresh demo me 28857).",
     "Order list me <b>Terms 15 days</b>, Priority High, Remark dikhne chahiye.",
     "Customer khali karke Save → refuse. Pcs 0 → refuse."],
) + step(
    "Production Planning ▸ Job Mapping", [
        ("Pending Jobs", "apna job select"), ("Process Group", "<b>Default</b> → <b>Apply Group</b> → <b>Save Route</b>")],
    ["11 steps: CAD CAM CS HM COL PP ST FP fs Meena Puwai.",
     "Job ab Pending Jobs se hat jata hai; Job History me route yahi dikhega."],
) + step(
    "Production Planning ▸ Stone Issue on Job-Card → + New", [
        ("Job No", "apna job"),
        ("Stones row 1", "Location <b>Primary</b> · SSKU <b>POLKI 12-14</b> · Pcs <b>10</b> · Weight <b>0.800</b> · S Type <b>Polki</b>"),
        ("Stones row 2", "Location <b>Primary</b> · SSKU <b>EMERALD PEAR 3*4</b> · Pcs <b>5</b> · Weight <b>0.500</b> · S Type <b>CS</b>")],
    ["Save. Same issue Pcs <b>999</b> ke saath → refuse ('Primary holds only …').",
     "<b>Show Pending</b> button bhi try karein — jin jobs ko abhi stone chahiye wo dikhenge."],
) + step(
    "Production Planning ▸ Job Card Bag", [
        ("Job No", "apna job"),
        ("POLKI 12-14 line", "select → <b>Setting Type</b> → <b>Polki</b>")],
    ["POLKI 12-14: Rcvd <b>10 / 0.800</b>, Bal 10; Setting column <b>Polki</b>. EMERALD PEAR: Rcvd <b>5 / 0.500</b>.",
     "Columns poori width me — right side khaali patti nahi.",
     "Return to Stock <b>50</b> pcs → refuse."],
) + part("D. Manufacturing — har process ka Issue aur Received") + """
<p>Har process do screens pe: <b>Manufacturing ▸ Issue</b> (title 'Issue To &lt;Process&gt;') aur
<b>Manufacturing ▸ Received</b> ('Received From &lt;Process&gt;'). Dono pe Process aur Account chuno,
<b>Show Pending</b> dabao — sirf wahi jobs aate hain jinka agla step yahi process hai. Green cells me type karo.
Issue line pe <b>Mt Price 8,680.67</b>, Size 7, L Price On NetWt, OrderNo, Client khud aate hain.</p>
""" + mfg("CAD", "Office", "koi weight nahi (CAD design step — weight cells band)", "koi weight nahi", "",
          "Save ke baad Show Pending dobara → CAD pe apna job nahi. <b>Print Voucher</b> → voucher khulta hai.") + mfg(
    "CAMMING", "Office", "koi weight nahi", "koi weight nahi", "",
    "Job History me CAD aur CAMMING rows, bina weight.") + mfg(
    "CASTING", "CHAND KUMAR HAZRA", "GrossWt <b>13.500</b> · NetWt <b>13.500</b>",
    "GrossWt <b>13.200</b> · NetWt <b>13.200</b>", "0",
    "Mt Amt = NetWt × 8,680.67 khud. Received pe Account CHAND chunte hi <b>Mt Bal</b> dikhta hai. "
    "Job History CASTING row: Loss <b>0.300</b> · <b>2.22%</b>.") + mfg(
    "HandMade", "RAHUL JI", "GrossWt <b>13.200</b> · NetWt <b>13.200</b>",
    "GrossWt <b>13.100</b> · NetWt <b>13.100</b> (jaan-boojh ke galat — agla step ise Edit se theek karega)", "3.5",
    "Save hota hai. Iss Finding <b>0.050</b>, Iss Mould <b>0.100</b>. Received pe <b>Attach Doc</b> → koi bhi "
    "file add → Save ke baad voucher ke saath judi rehti hai.",
    extra_iss="line select → <b>F4</b> Finding <b>0.050</b> → Enter · <b>F7</b> Mould <b>0.100</b> → Enter") + step(
    "Galti sudharna — saved voucher Edit", [
        ("Manufacturing ▸ Received", "Process <b>HandMade</b> → <b>Edit</b> → list me RAHUL JI wala voucher → OK"),
        ("Line", "GrossWt <b>13.000</b> · NetWt <b>13.000</b> → <b>Save</b> → Yes")],
    ["Job History HandMade: Loss <b>0.200</b> · <b>1.52%</b>, allowed 3.5% of the <b>issued</b> 13.200 = <b>0.462</b> (5 Oct rule).",
     "Edit me sirf weights / price / date / RefNo badalte hain; job ya stones badalne ho to <b>Delete</b> karke dobara banao."],
) + mfg(
    "COLOUR", "FACTORY", "GrossWt <b>13.000</b> · NetWt <b>13.000</b>",
    "GrossWt <b>13.000</b> · NetWt <b>13.000</b>", "0",
    "Loss <b>0.000</b>.") + mfg(
    "PrePolish", "BUDDHA POL", "GrossWt <b>13.000</b> · NetWt <b>13.000</b>",
    "GrossWt <b>12.900</b> · NetWt <b>12.900</b>", "0.35",
    "Loss <b>0.100</b> · <b>0.77%</b>.") + mfg(
    "Setting", "rakesh sarkar", "GrossWt <b>12.900</b> · NetWt <b>12.900</b>",
    "GrossWt <b>13.080</b> · NetWt <b>12.850</b>", "3",
    "Setting labour <b>₹240</b> = 8 Polki set × ₹30 (Emerald ka setting type nahi → ₹0). "
    "Job Card Bag: POLKI Iss 10, Back <b>2 / 0.160</b>, Bal <b>2 / 0.160</b>; EMERALD Iss 5, Bal 0.",
    extra_iss="line select → <b>F3 Stone</b> → POLKI 12-14 <b>10</b>, EMERALD PEAR <b>5</b> → OK "
              "(pop-up me Setting Type Polki, rate 30 dikhega)",
    extra_rcv="line select → <b>F3</b> → POLKI 12-14 <b>2</b> wapas → OK") + mfg(
    "Final Polish", "BUDDHA POL", "GrossWt <b>13.080</b> · NetWt <b>12.850</b>",
    "GrossWt <b>12.990</b> · NetWt <b>12.760</b>", "0.35",
    "Loss <b>0.090</b> · <b>0.70%</b>.") + mfg(
    "final setting", "akshay j", "GrossWt <b>12.990</b> · NetWt <b>12.760</b>",
    "GrossWt <b>12.970</b> · NetWt <b>12.740</b>", "0",
    "Loss <b>0.020</b>.") + mfg(
    "Meena", "JAGDISH PRA", "GrossWt <b>12.970</b> · NetWt <b>12.740</b>",
    "GrossWt <b>12.950</b> · NetWt <b>12.720</b>", "",
    "Loss <b>0.020</b>.") + mfg(
    "Puwai", "JAGDISH PRA", "GrossWt <b>12.950</b> · NetWt <b>12.720</b>",
    "GrossWt <b>12.930</b> · NetWt <b>12.700</b>", "",
    "Loss <b>0.020</b>. Ye last step tha — job ab <b>Pending for MFG Transfer</b>.") + step(
    "Manufacturing ▸ Issue / Received — baaki buttons", [],
    ["<b>Day Book</b> → Issue Day Book / Received Day Book me aaj ke saare vouchers, process-wise group.",
     "<b>Statement</b> → Worker Metal Ledger khulta hai.",
     "<b>Remove Line</b> → selected job voucher se hat jata hai (save se pehle).",
     "Received pe Account <b>(any karigar)</b> → Show Pending me sab karigaron ke jobs.",
     "<b>Delete</b> → apne job ka <b>CASTING</b> wala Received voucher chuno → refuse: <i>\"delete the later voucher "
     "first\"</i> (job aage badh chuka hai, isliye purana voucher nahi hatega). Kuch delete nahi hua.",
     "<b>Add</b> → khaali naya voucher."],
) + part("E. Job History — ek job ki poori kahani") + step(
    "Production Planning ▸ Job History (F11)", [("Job No", "apna job")],
    ["Header: SKU NS-1430, C-Ref TEST-C, Client KK JEWELS, Ord No, Route CAD CAM CS HM COL PP ST FP fs Meena Puwai.",
     "11 rows; issue half <b>pink</b>, receive half <b>green</b>. Loss column Worker ke saath: "
     "0.300 · 0.200 · 0.000 · 0.100 · 0.050 · 0.090 · 0.020 · 0.020 · 0.020 → total <b>0.800 g</b>.",
     "Setting row ka Labour <b>240.00</b>. <b>Setting Labour</b> button → yahi statement.",
     "Kisi pink cell pe double-click → us issue ka voucher; green cell → receipt voucher.",
     "Neeche stones grid me POLKI aur EMERALD lines — page scroll karke sab dikhna chahiye.",
     "<b>MFG Price</b> button → step 33 wale hi figures.",
     "<b>Show Pending</b> → abhi koi step pending nahi (job complete)."],
) + part("F. MFG Transfer → Stock → Tag → Item Search") + step(
    "Manufacturing ▸ Pending for MFG Transfer", [],
    ["Apna job list me (BANG-577 aur demo jobs ke saath). Row pe <b>F10</b> → uska Job Bag khulta hai."],
) + step(
    "Manufacturing ▸ MFG Transfer", [
        ("Show Pending", "apna job tick → OK (Fill Prices khud chalta hai)")],
    ["Location Primary · C-Ref TEST-C · Title 590 · Loss% <b>6.30</b> · N-Wt <b>12.700</b> · FineWt <b>7.493</b> · Size 7.",
     "Metal Rate <b>8,680.67</b> · Metal Amount <b>1,10,244.51</b>.",
     "Stone Amount <b>6,184.00</b> (Polki 8 pcs / 0.640 ct × 8,100 = 5,184 + Emerald 0.500 ct × 2,000 = 1,000).",
     "Labour Price 1,200 × Labour Wt 12.700 = <b>15,240.00</b>.",
     "Total <b>1,31,668.51</b> · Margin 50% = <b>65,834.26</b> · Price Per Pcs <b>1,97,502.77</b> · Tag <b>197</b>.",
     "Grey cell pe double-click → <b>Cost Break-up</b>: har component alag row me.",
     "<b>Repair (tag 0)</b> tick → Tag 0; untick → wapas 197. Margin % 40 type → Price badlega; wapas 50.",
     "Upar <b>Location</b> = Primary (pieces kahan jayenge) · <b>Split Jobs</b> = kai pieces wale job ke har piece ka "
     "alag Stock No (ye job 1 pc ka hai, isliye fark nahi).",
     "<b>Print</b> → PDF · <b>Excel Format</b> → .xlsx file."],
) + step(
    "MFG Transfer → Save", [("Save", "Yes")],
    ["Stock No milta hai (Primary me) aur <b>Tag List</b> khulta hai.",
     "Tag List me try: Print Tag Price on/off · C-Ref Barcode (TEST-C) · <b>Detail</b> (POLKI / COLOR STONE carats) · "
     "Pcs Wise · Print Selected (pehle tick) · Print All · <b>Select Printer</b> · <b>Create Txt</b>.",
     "<b>TXT Import (Stock ID)</b>: ek .txt file me Stock No likho → import → list me aa jata hai."],
) + step(
    "Sale ▸ Reports ▸ Ready Stock", [],
    ["Apna piece: Primary · cost <b>1,31,668.51</b> · price <b>1,97,502.77</b> · tag <b>197</b> · Tag Printed Y (agar print kiya)."],
) + step(
    "Item Search (top right)", [("Search", "apna Stock No, ya Job No, ya NS-1430 → Enter")],
    ["Piece card: client, order, G-Wt 12.930, N-Wt 12.700, cost / price / tag; stones grid; value summary by stone kind.",
     "Upar wali grid = <b>barcode ki history</b>: abhi MF (bana). Sale / approval ke baad wo bhi yahan judenge.",
     "<b>Job History</b> button → wapas us job pe."],
) + step(
    "Item Search → Delete History &amp; Purchase (correction path)", [("Reason", "test correction")],
    ["Piece stock se hat jata hai; job wapas <b>Pending for MFG Transfer</b> me.",
     "Ab MFG Transfer se dobara Show Pending → Save → Stock No (fresh demo me phir se <b>1</b>). "
     "Aage ke steps me isi ko <b>aapka piece</b> kahenge. (Delete ka audit record banta hai.)"],
) + part("G. Stones ka hisaab") + step(
    "Job Card Bag — bache hue 2 Polki wapas stock me", [
        ("Job No", "apna job"), ("POLKI 12-14 line", "select → <b>Return to Stock</b> → 2 pcs → Location Primary")],
    ["POLKI Bal <b>0</b>. <b>Stones in Job Cards</b> / <b>Bag Balance Report</b> → report khulte hain, Export CSV.",
     "(Ya yahi kaam Production Planning ▸ Inv Return – Stone → Show Pending se.)"],
) + part("H. Reports — sab link hai ki nahi") + step(
    "Inventory ▸ Metal ▸ Reports ▸ Metal Analysis (FY)", [],
    ["RAJESH JI · 14KT 590: Inward <b>252.800</b> (demo 201 + purchase 50 + receipt 1.800), "
     "Outward <b>3.625</b> (demo 1.625 + issue 2.000), Closing <b>249.175</b>.",
     "Primary · 24KT Gold: <b>800.000</b>. Row pe double-click → us location ka ledger."],
) + step(
    "Reports ▸ Inventory ▸ Worker Balance (Metal)", [],
    ["CHAND KUMAR HAZRA · 14KT 590: <b>0.745 g</b> (demo 0.590 + aapka 0.155) — ye sirf Inventory vouchers se."],
) + step(
    "Manufacturing ▸ Reports ▸ Karigar ▸ Worker Metal Ledger", [],
    ["CHAND KUMAR HAZRA rows: MI 1.625 · MR 1.000 · MI <b>2.000</b> · MR <b>1.800</b> (Alw 2.5% = 0.045) · "
     "ISS 15.000 · ISS 13.500 · <b>ISS 13.500</b> · RTN 14.800 · RTN 13.200 · <b>RTN 13.200 (loss 0.300)</b>.",
     "Closing <b>1.545 g</b>. Manufacturing ▸ Issue pe Account CHAND chuno → <b>Mt Bal 1.545 g</b> — dono same.",
     "RAHUL JI: ISS 13.200 · RTN 13.000 · Loss 0.200 · Alw 3.5% × 13.200 = 0.462 · Balance <b>−0.262</b> "
     "(allowance asli loss se zyada tha, isliye karigar ka balance minus — legacy ledger bhi aise hi dikhata hai)."],
) + step(
    "Manufacturing ▸ Reports ▸ Karigar ▸ Worker Stone Ledger / Worker Balance (Stone)", [],
    ["rakesh sarkar, aapke job pe: ISS POLKI 12-14 <b>10</b> · ISS EMERALD PEAR <b>5</b> · BACK POLKI <b>2</b> · "
     "SET POLKI <b>8</b> · SET EMERALD <b>5</b> (Setting receive hote hi jo wapas nahi aaye wo 'set' maane jaate hain)."],
) + step(
    "Manufacturing ▸ Reports ▸ Karigar ▸ Setting Labour Statement (is mahine)", [],
    ["rakesh sarkar: aapke job ki lines — POLKI 12-14 · Polki · issued 10 · back 2 · set 8 · 30 → <b>240.00</b>; "
     "EMERALD · — · set 5 · 0.00."],
) + step(
    "Baaki reports — har ek kholo", [],
    ["Issue Day Book · Received Day Book · Pending for MFG Transfer · MFG Transfer Day Book · Ready Stock · "
     "Metal / Stone Day Book · Job Analysis · Process Analysis · Job Card Analysis – Stone.",
     "Har report pe: Search · Group · Auto Filter · Adv. Filter · Set Column · <b>Export</b> · <b>Print</b>. "
     "Date default = financial year."],
) + part("I. Job Costing") + step(
    "Manufacturing ▸ Job Costing", [("Run", "dates waise hi (financial year) → Run")],
    ["Aapka job (28857) row: G-Wt <b>12.930</b> · N-Wt <b>12.700</b> · MT AMT <b>1,10,244.51</b> · ST AMT <b>6,184.00</b> · "
     "LABOUR <b>15,480.00</b> (setting 240 + STD 15,240) · TOTAL <b>1,31,908.51</b> · MARGIN <b>65,954.26</b> · "
     "PRICE UNIT <b>1,97,862.77</b> · TAG <b>197</b> · STOCK = aapka Stock No · RATES = frozen.",
     "<b>Ctrl+F1</b> (Stone Group Wise) → Diamond / Polki / Colour Stone aur Setting / STD alag columns; dobara Ctrl+F1 → band.",
     "<b>Ctrl+P</b> → Excel Job Costing (.xlsx) save. <b>WIP costing</b> tick → Run → demo job <b>28855</b>: N-Wt 14.800, "
     "total <b>1,46,233.92</b>, price <b>2,19,350.88</b>. <b>Ctrl+W</b> → Excel WIP Costing. Tick hata do."],
) + step(
    "Job Costing Sheet", [("Row", "apne job pe double-click")],
    ["Metal 12.700 × 8,680.67 = <b>1,10,244.51</b> · Stones POLKI 8 / 0.640 @ 8,100 = 5,184 · EMERALD 5 / 0.500 @ 2,000 = 1,000 · "
     "Stone total <b>13 pcs / 1.140 ct · 6,184.00</b> · Setting + STD <b>240 + 15,240</b> · Total <b>1,31,908.51</b> · "
     "Margin 50% <b>65,954.26</b> · Grand Total <b>1,97,862.77</b> · Tag / per gm <b>197 · 15.24</b>.",
     "Upar likha: <i>Rates frozen on MFG Transfer Vr 1</i> — stock me gaye job ka rate baad me nahi badalta.",
     "<b>Export To Excel</b> → file kholo: amounts formulas hain (cell pe click → formula). <b>Print</b> → PDF. "
     "<b>WIP Costing</b> → aaj ke rate pe wahi sheet."],
) + part("J. MFG Transfer — Edit, Format-2, Tag Print") + step(
    "Manufacturing ▸ MFG Transfer → Edit", [
        ("Edit", "Vr 1 (aapka job) → OK"), ("Margin % (green)", "<b>40</b> → Enter → <b>Save</b> → Yes")],
    ["Item Search me aapka piece: price <b>1,84,335.91</b>, tag <b>184</b> — Stock No wahi.",
     "Dobara <b>Edit</b> → Margin % <b>50</b> → Save → price wapas <b>1,97,502.77</b>, tag <b>197</b>."],
) + step(
    "MFG Transfer — prints", [],
    ["<b>Format-2</b> → PDF: har piece ka cost break-up (metal, har stone, labour, margin, price).",
     "<b>Tag Print</b> → transfer ke saare tags ka PDF. <b>Excel Format</b> → .xlsx."],
) + part("K. Sale — Approval, Sale (From Order), Excel Invoice, Return") + step(
    "Sale ▸ Ready Stock ▸ Approval", [
        ("Account", "<b>KK JEWELS</b>"), ("Read Barcode / SKU here", "aapka Stock No (<b>1</b>) → Enter"),
        ("Save", "Yes")],
    ["Line: Metal Rate <b>8,680.67</b> · Metal Amount <b>1,10,244.51</b> · FineWt 7.493 · Fine With Loss <b>7.965</b> · "
     "Stone Amount <b>6,184.00</b> · Labour Rate 1,200 · Labour <b>15,240.00</b> · Total <b>1,31,668.51</b>.",
     "Line select → <b>Stone Breakup</b> → POLKI aur EMERALD, price ke saath. Barcode me <b>99999</b> → "
     "<i>\"Item not found\"</i>.",
     "Sale ▸ Reports ▸ <b>Ready Stock Approval Balance</b> → KK JEWELS · aapka piece · 1,31,668.51 · days 0."],
) + step(
    "Approval wala piece kisi aur ko bechna (galat kaam — refuse hona chahiye)", [
        ("Sale ▸ Ready Stock ▸ Sale", "Account <b>FACTORY</b> · barcode <b>1</b> → Enter")],
    ["Message: <i>\"Stock No 1 is out on approval with KK JEWELS - it can only be returned or sold to that party\"</i>. "
     "<b>Add</b> dabao (khaali karo)."],
) + step(
    "Sale ▸ Ready Stock ▸ Approval Return", [
        ("Account", "<b>KK JEWELS</b> → <b>Show App</b> → aapka piece tick → OK"), ("Save", "Yes")],
    ["Piece wapas stock me. Approval Balance report ab khaali."],
) + step(
    "Sale ▸ Ready Stock ▸ Sale — From Order", [
        ("Account", "<b>KK JEWELS</b> (Cl Bal dikhega)"), ("Credit Days", "<b>30</b> → due date khud (aaj + 30)"),
        ("From Order", "Pending Orders me apne order ki row (RefNo <b>TEST-1</b> · C Ref <b>TEST-C</b> · Ord Pcs 1 · "
                       "Bal Pcs 1 · Stock Pcs 1) → uske green <b>Take</b> cell me <b>1</b> → OK. "
                       "(Fill Balance Pcs / Fill Stock Qty saari rows bhar dete hain — demo orders ki bhi; "
                       "yahan sirf apni row.)"),
        ("Save", "Yes")],
    ["Line me aapka piece (apne job ka piece pehle chuna jata hai). Total <b>1,31,668.51</b>.",
     "Neeche: <i>Account Information: Dr KK JEWELS 1,31,668.51 · Cr Sales A/c 1,31,668.51</i>. Save ke baad "
     "<b>Cl Bal 1,31,668.51 Dr</b>.",
     "Dobara From Order → aapka order list me nahi (ship ho gaya). Demo orders dikhte rahenge."],
) + step(
    "Excel Invoice aur Print", [("Excel Invoice", "save karo → Excel me kholo")],
    ["Ek row aapke piece ki: GrossWt 12.930 · NetWt 12.700 · FineWt 7.493 · Mt Price 8,680.67 · Mt Amount "
     "<b>1,10,244.51</b> · POLKI 12-14 8 / 0.64 @ 8,100 = <b>5,184</b> · Colour stone EMERALD 5 / 0.5 @ 2,000 = "
     "<b>1,000</b> · Labour 1,200 → <b>15,240</b> · TOTAL <b>1,31,668.51</b>. Neeche note: <i>Metal Rate Will Be "
     "Charged as on Date of Payment</i>.",
     "Kisi amount cell pe click → formula (jaise =ROUND(F4*H4,2)). <b>Print</b> → invoice PDF. <b>Catalog</b> → photo wala PDF. "
     "<b>TXT Export</b> → barcodes ki .txt."],
) + step(
    "Sale ▸ Ready Stock ▸ Sale Return", [
        ("Account", "<b>KK JEWELS</b> → <b>Sold Pieces</b> → aapka piece → OK"), ("Save", "Yes")],
    ["Piece wapas stock me. KK ka <b>Cl Bal 0.00</b>. Aapka order phir se From Order me Bal 1.",
     "Item Search → aapka piece → history: <b>MF · RA · RAR · RS · RSR</b>, party KK JEWELS ke saath."],
) + part("L. Repair") + step(
    "Production Planning ▸ Order → + New (repair order)", [
        ("Ord Type / Customer", "Customer / <b>KK JEWELS</b>"), ("Repair", "<b>tick</b>"),
        ("SKU Lines", "khaali chhodo"), ("Save", "Yes")],
    ["Repair tick ke saath bina line ke save hota hai (bina tick ke refuse hota hai)."],
) + step(
    "Order list → Repair List", [("Order", "naya repair order select → <b>Repair List</b> → aapka piece tick → OK")],
    ["Order me line: NS-1430 · Tot GWt <b>12.930</b> · Mt Amt <b>1,10,244.51</b> · remark 'Repair of Stock No 1'. "
     "Ek naya job bhi bana (fresh demo me <b>28858</b>) — uske Job Card Bag me stones <b>nahi</b> aate "
     "(purane piece ki stone detail aage nahi jaati — client se confirm karna hai)."],
) + step(
    "Sale ▸ Ready Stock ▸ Ready Repair Issue", [
        ("Account", "<b>KK JEWELS</b>"), ("Barcode", "<b>1</b> → Enter"), ("Save", "Yes")],
    ["Sale ▸ Reports ▸ <b>Repair Register</b> → KK JEWELS · piece 1 · <b>Out for repair</b> · days 0.",
     "Wapas Ready Repair Issue → <b>Delete</b> → wahi voucher → Yes → piece phir se stock me (aage ke steps ke liye)."],
) + part("M. Purchase — Ready Items, Return, Opening Stock") + step(
    "Purchase ▸ Ready Items", [
        ("Supplier", "<b>TEST SUPPLIER</b>"), ("Bill Number", "<b>B-56</b> (Bill Date aaj)"),
        ("SKU Search", "NS-1430 → OK → Add Piece form khulta hai"),
        ("Add Piece", "Location Primary · Metal <b>14KT 590</b> (Metal Rate khud 8,680.67) · Gross <b>10.000</b> · "
                      "Net <b>8.000</b> · Labour Rate <b>1200</b> · <b>Stones…</b> → POLKI 12-14 · POLKI · Pcs 2 · "
                      "Cts 0.160 · ct · Price 8100 → OK → OK"),
        ("Save", "Yes")],
    ["Line: Metal <b>69,445.36</b> · Stones <b>1,296.00</b> · Labour <b>9,600.00</b> · Total <b>80,341.36</b>; "
     "Account Information <b>Dr Purchase A/c / Cr TEST SUPPLIER 80,341.36</b>.",
     "Save → <i>New Stock No 2</i> (naya barcode). <b>BreakUp Sheet · Packing List · Picture Invoice</b> → PDFs; "
     "<b>St. Summ.</b> → POLKI 2 / 0.160 / 1,296; <b>Tag Print</b> → tag list.",
     "Reports ▸ Inventory ▸ <b>Account Ledger</b> → TEST SUPPLIER balance <b>5,29,334.86 Cr</b>."],
) + step(
    "Purchase ▸ Ready Item Return", [
        ("Supplier", "<b>TEST SUPPLIER</b> → <b>Show Stock</b> → Stock No <b>2</b> tick → OK"), ("Save", "Yes")],
    ["Piece 2 supplier ko wapas. TEST SUPPLIER balance wapas <b>4,48,993.50 Cr</b>.",
     "Item Search (top right) → <b>2</b> → Enter → status <i>returned</i>; history <b>RP · RPR</b>. "
     "Bahar se aaye piece pe <b>Delete History &amp; Purchase</b> refuse hota hai."],
) + step(
    "Purchase ▸ Opening Stock", [
        ("Ready Items", "Add Piece: NS-1430 · Primary · 14KT 590 · Gross <b>5</b> · Net <b>4</b> → Save"),
        ("Metal", "+ New → Line: Primary · <b>24KT Gold</b> · Weight <b>5</b> → Save (Account nahi maangta)"),
        ("Stone", "Opening Stone Balances screen khulti hai — dekh ke band")],
    ["Opening piece ko Stock No <b>3</b>; koi accounting entry nahi."],
) + part("N. Metal Sale, Stone Sale / Approval") + step(
    "Sale ▸ Metal → + New", [
        ("Account (customer)", "<b>KK JEWELS</b>"),
        ("Line", "Location Primary · Metal <b>24KT Gold</b> · Colour Y · Weight <b>10</b> · Price <b>15050</b>"), ("Save", "Yes")],
    ["Amount <b>1,50,500.00</b>. Row select → <b>Account Information</b> → Dr KK JEWELS / Cr Sales A/c 1,50,500.",
     "Inventory ▸ Metal ▸ Reports ▸ Metal Analysis → Primary 24KT Gold closing <b>795.000</b> (800 + 5 opening − 10)."],
) + step(
    "Sale ▸ Stone ▸ Sale / Approval / Approval Return", [
        ("Sale", "KK JEWELS · Primary · POLKI 12-14 · Pcs 2 · Weight 0.160 → Save (Price khud 8,100 → 1,296)"),
        ("Approval", "KK JEWELS · Primary · EMERALD PEAR 3*4 · Pcs 4 · Weight 0.400 → Save"),
        ("Approval Return", "KK JEWELS · Primary · EMERALD PEAR 3*4 · Pcs 1 · Weight 0.100 → Save")],
    ["Sale ▸ Reports ▸ <b>Stone Approval Analysis</b> → EMERALD: out 4 · ret 1 · bal <b>3 / 0.300 · 600.00</b>.",
     "<b>Stone Sale Register</b> aur <b>Metal Sale Register</b> me ye lines. Sale ▸ Ready Stock ▸ Sale → KK ka "
     "Cl Bal <b>1,51,796.00 Dr</b>."],
) + part("O. Inventory — Stock Transfer, Melting, Stone Issue by Lot") + step(
    "Inventory ▸ Stock Transfer → Stock Location Transfer", [
        ("Metal / Stone", "<b>Stone</b> · Item <b>POLKI 12-14</b>"), ("From → To", "<b>Primary</b> → <b>RAJESH JI</b>"),
        ("Sent", "Pcs <b>5</b> · Weight <b>0.400</b>"), ("Loss", "Pcs <b>1</b> · Weight <b>0.080</b> · Price 8100"),
        ("Save", "Yes")],
    ["Stone tab me do lines: Primary se Out 5 / 0.400 (loss 1 / 0.080), RAJESH JI me In <b>4 / 0.320</b>.",
     "Inventory ▸ Reports ▸ Registers ▸ <b>Stone Loss Register</b> → TR row: 1 pc · 0.080 · <b>648.00</b>."],
) + step(
    "Stock Transfer → Stock Melting", [
        ("Add", "naya voucher"), ("Stock Melting", "Stock No <b>1</b> → OK"), ("Save", "Yes")],
    ["Ready Stock Outward: aapka piece. Metal: 14KT 590 In <b>12.700</b> @ 8,680.67 = 1,10,244.51. Stone: POLKI 0.640 "
     "(5,184) · EMERALD 0.500 (1,000).",
     "Piece ab <b>melted</b>; Primary me POLKI 8 pcs wapas. <b>Melting List</b> → piece dikhta hai.",
     "<b>Delete</b> → ye voucher → Yes → piece wapas stock me, metal / stones wapas (undo test)."],
) + step(
    "Inventory ▸ Stone ▸ Issue Outside / Worker → Read Cert/Lot", [
        ("Read Cert/Lot", "<b>LOT-7</b> → OK (naya voucher khulta hai, line bhari hui: POLKI 12-14 · 20 · 1.600 · 8,100)"),
        ("Form", "Account <b>CHAND KUMAR HAZRA</b> · line Pcs <b>2</b> · Weight <b>0.160</b> → Save")],
    ["Row select → <b>DC Print</b> (challan, bina rate) · <b>Tag</b> (packet tag) · <b>Register</b> (Stone Day Book).",
     "Inventory ▸ Stone ▸ Receipt → <b>Show O/S</b> → CHAND: POLKI 12-14 <b>2 / 0.160</b> baaki. "
     "Inventory ▸ Metal ▸ Issue → <b>Check Bal</b> → CHAND ka Mt Bal aur location stock."],
) + part("P. Registers aur baaki reports") + step(
    "Inventory ▸ Reports ▸ Registers", [],
    ["<b>Metal Loss Register</b>: aapke job ki 9 rows — CASTING 0.300 (allow 0 → excess <b>red</b>) · HandMade 0.200 "
     "(allowed 0.462) · PrePolish 0.100 · Setting 0.050 · Final Polish 0.090 · final setting / Meena / Puwai 0.020.",
     "<b>WIP Register</b> (As on aaj): demo jobs — 28855 <b>WIP</b> PRASENJIT HandMade, 28854 <b>PND</b> CAD. "
     "<b>Process Summary</b>: har process ki row (RECTIFICATION, KHUDAI … bhi), CAD / HandMade / Setting me pcs.",
     "<b>WIP Stone</b>, <b>Dust Register</b> — khul ke chalte hain. Har report: <b>Export</b> → Excel (.xlsx), <b>F1</b> → Show All."],
) + step(
    "Dashboard, F12, Daily Metal Rate", [],
    ["Dashboard ▸ BARCODE READ: <b>1</b> → Item Search; <b>28857</b> (Job box) → Job History.",
     "<b>F12</b> → More Reports → 'worker metal' type → Enter → Worker Metal Ledger.",
     "Master ▸ Daily Metal Rate → <b>Rate As On Date</b> → har metal ka rate aur kis din set hua. Naya rate save karo → "
     "Entered By / Entered At khud bharta hai."],
) + part("Q. Settings aur menu") + step(
    "Tools ▸ Option", [],
    ["<b>Settings</b> tab ▸ Others ▸ <b>Ask \"Save? Yes / No\" before every save</b> = False → Save → ab kisi save pe "
     "popup nahi; wapas True.",
     "Settings ▸ Inventory ▸ <b>When a location would go below zero</b> → <b>Block the save</b> → step 12 wala 500 g issue ab seedha refuse; "
     "wapas <b>Warn, then allow</b>.",
     "Settings ▸ Costing ▸ <b>Tag price on the tag</b> badlo → MFG Transfer ka Tag column naye format me.",
     "<b>Menu</b> tab: Production Planning ke items untick → Save → menu se gayab; wapas tick."],
) + step(
    "UI checks", [],
    ["Sidebar nahi — sab module top menu me; Inventory ▸ Metal / Stone submenu.",
     "<b>Reports</b> menu me sections submenu ban ke (Day Books ▸, Inventory ▸, Karigar ▸ …); har report apne "
     "tab me full width khulta hai — left me report list nahi. Production Planning / Manufacturing / "
     "Inventory ▸ Reports bhi aise hi.",
     "Har tab ke × pe hover → dark background pe safed × (Close Tab).",
     "<b>Go to screen…</b> (Ctrl/Cmd+F) me 'job his' type → Job History khulta hai.",
     "Menu me <b>Waxing</b>, Purchase ke Approval / Debit Note / Parts / Settings, Inventory ke Parts / Physical Stock / "
     "Ready Item Receipt, Manufacturing ke Repair Issue / Extra Issue / Stamping <b>nahi</b> dikhte — client ne "
     "use nahi bataya / abhi samjhana baaki. Tools ▸ Option ke 'Other menu items' me tick → wapas aate hain.",
     "Inventory ▸ Metal / Stone ke 'soon' items (Bhav Cut, Conversion …) ek note kholte hain — client ke jawab ka wait."],
) + part("R. Accounts (5 Oct) — ledger, outstanding, receipt, metal receive") + step(
    "Account Groups aur Trial Balance", [
        ("Account ▸ Groups", "tree dekho (Capital, Current Assets ▸ Sundry Debtors …) → <b>Reindex</b>"),
        ("Account ▸ Trial Balance", "From 01-04 · To aaj → Show; phir <b>Ctrl+F1</b> (Detailed)")],
    ["Groups seeded hain; Reindex ke baad Index 1, 2, 3 … tree order me.",
     "Trial Balance ka Dr total = Cr total; Sales A/c, Cash, Purchase, Metal Stock ledger dikhte hain."],
) + step(
    "Receivables — bill-wise, aur Cash receipt FIFO", [
        ("Account ▸ Outstandings ▸ Receivables", "As on aaj"),
        ("Account ▸ Voucher Entry ▸ Receipt", "Account <b>KK JEWELS</b> · Mode <b>Cash</b> · Amount <b>50000</b> → "
         "<b>Auto FIFO</b> → Save")],
    ["Pehle KK JEWELS: MS 1 (metal sale) <b>1,50,500.00</b> aur SS 1 (stone sale) <b>1,296.00</b> pending; "
     "Cl Bal <b>1,51,796.00 Dr</b>.",
     "Receipt ke baad sabse purana bill pehle: MS 1 pending <b>1,00,500.00</b>, SS 1 waise hi; KK closing "
     "<b>1,01,796.00 Dr</b>. Overdue bills red me.",
     "Cash / Bank A/c me <b>Cash in Hand</b> khud aata hai. Save ke baad receipt screen ke neeche "
     "<b>Saved Receipts</b> list me sabse upar dikhta hai; select → Print."],
) + step(
    "Metal receive (fine gold se settle)", [
        ("Account ▸ Voucher Entry ▸ Receipt", "KK JEWELS · Mode <b>Metal</b> · Metal <b>24KT Gold</b> · Location "
         "<b>Primary</b> · Weight <b>2</b> → Save")],
    ["Rate aaj ka 24K <b>14,713</b> → Amount <b>29,426.00</b>; KK closing <b>72,370.00 Dr</b>.",
     "Inventory ▸ Metal Analysis: Primary 24KT Gold 2 g badha. Account ▸ More ▸ <b>Cash Flow</b> me cash "
     "receipt 50,000 KK ke naam."],
) + step(
    "Ledger, Day Book, Client Metal O/S", [
        ("Account ▸ Ledger", "Account KK JEWELS → Show; month row pe double-click; <b>Ctrl+G</b> graph"),
        ("Account ▸ Day Book", "aaj"),
        ("Account ▸ Outstandings ▸ Client Metal O/S", "As on aaj")],
    ["Ledger month-wise, double-click se vouchers; Mode filter (Cash / Bill / Metal).",
     "Client Metal O/S KK JEWELS: FINE O/S <b>8.000</b> (10 g sold − 2 g received), AMT O/S <b>72,370.00</b>; "
     "double-click → KK ka metal ledger."],
) + part("S. Karigar aur client ka metal / stone balance") + step(
    "Worker Metal Ledger aur Worker Balance (Metal)", [
        ("Reports ▸ Karigar ▸ Worker Metal Ledger", "FY"),
        ("Reports ▸ Inventory ▸ Worker Balance (Metal)", "As on aaj")],
    ["GROUP column (Worker / Client). RAHUL JI RTN row: ALW L WT <b>0.462</b> (3.5% × issued 13.200), "
     "ALW L FINE <b>0.273</b>.",
     "Worker Balance: RAHUL JI 14KT 590 in 13.200 · out 13.000 · balance <b>−0.262</b>; KK JEWELS (Client) "
     "24KT Gold in 10.000 · out 2.000 · balance <b>8.000</b>. WIP WT / PROCESS: jo karigar ke paas abhi hai.",
     "Tools ▸ Option ▸ Settings ▸ Manufacturing ▸ 'Loss allowance worked on' = Weight received back karke "
     "Save → allowed 3.5% × 13.000 = 0.455 ho jaata hai. Wapas 'Weight issued' karo."],
) + step(
    "Stone balances aur summaries", [
        ("Reports ▸ Stone ▸ Location Wise Stone Balance", "Location <b>Primary</b>, FY"),
        ("Reports ▸ Stone ▸ Stone Summary", "As on aaj; phir Options ▸ Groups only"),
        ("Reports ▸ Stone ▸ Worker Balance (Stone)", "As on aaj"),
        ("Reports ▸ Inventory ▸ Metal Summary", "As on aaj")],
    ["Primary POL: Opening <b>225.000 / 900</b>, Purchase 9.600 / 120, Closing <b>231.640 / 983</b>; CS Closing "
     "<b>229.200 / 942</b>. Closing = Opening + Inward − Outward. Neeche Job Card / WIP.",
     "Stone Summary: WHERE = RDY / INV / JC / WIP / LOS.",
     "Worker Balance (Stone): KK JEWELS (Client) EMERALD PEAR 3*4 closing <b>3</b> pcs (approval par).",
     "Metal Summary: RAJESH JI 14KT 590 INV <b>249.175</b> (= Metal Analysis closing); jobs WIP_@W / WIP_PND."],
) + part("T. Client price chart (MANNU BHAI)") + step(
    "Chart banao aur sale par lagao", [
        ("Tools ▸ Client Wise Labour Price", "MANNU BHAI chuno (Per Grm Price 1,175)"),
        ("Masters ▸ Account ▸ KK JEWELS", "Price Chart = <b>MANNU BHAI</b> → Save"),
        ("Tools ▸ Option ▸ Settings ▸ Order & Quotation", "Client wise price chart applicable = <b>True</b> → Save"),
        ("Sale ▸ Ready Stock ▸ Sale", "Account KK JEWELS → barcode <b>1</b> scan")],
    ["'Prices From Client Chart (MANNU BHAI)' khud tick; Labour Rate <b>1,175</b>, Labour <b>14,922.50</b> "
     "(1,175 × 12.700); Stone Amount <b>10,466.00</b> (MANNU BHAI ki sheet: POLKI 12-14 0.640 × 14,400 + EMERALD "
     "PEAR 0.500 × 2,500); Total <b>1,35,633.01</b>. Untick → wapas 1,200 / 15,240 / 6,184 / 1,31,668.51. "
     "Sale save mat karo.",
     "Tools ▸ Client Wise Stone Price ▸ MANNU BHAI me <b>282</b> rows (POLKI 12-14 <b>14,400</b>).",
     "Labour Price me Add Row: Family <b>Diamond Jewellery</b>, From G-Wt 10, To 20, SalePrice 900 → Save → "
     "dubara scan: Labour <b>11,430.00</b> (900 × 12.700, rule jeet-ta hai), Total <b>1,32,140.51</b>. "
     "<b>Make A Copy</b> → naam 'MANNU 2' → saare rules copy."],
) + part("U. Stock tools") + step(
    "Stock Reconciliation", [
        ("Tools ▸ Stock Reconciliation", "New Count → Barcode Id me <b>1</b> scan (Enter), phir <b>999999</b>")],
    ["In Stock Show (1): Stock 1. Add Stock But Not Show In Stock (1): Stock <b>3</b> (scan nahi hua). "
     "Data Unfound (1): 999999 'Not found'. Dubara 1 scan → '(1 already scanned)'. Export To Excel → 3 sheets."],
) + step(
    "Stock View, SKU Status, Closing Stock, Barcode Catalog", [
        ("Tools ▸ Stock View", "All Stock → Filter; Stone Info ▸ SSKU <b>POLKI</b> → Filter"),
        ("Sale ▸ Reports ▸ SKU Status", "SKU <b>NS-1430</b>"),
        ("Sale ▸ Reports ▸ Ready Closing Stock", "As on aaj → row select → Ctrl+S (Catalog), Ctrl+T (Tag Print)"),
        ("Tools ▸ Barcode Catalog", "By SKU → NS-1430 Enter → Catalog 4x8")],
    ["Stock View: All = 3 pieces; POLKI filter = Stock 1.",
     "SKU Status NS-1430: Stock 1 (RSR, In-Stock), Stock 2 (RPR, Returned), Stock 3 (OPR, In-Stock) + MFG jobs.",
     "Closing Stock: MT-RATE = aaj ka 14KT 590 rate; Catalog / Tag Print PDF banta hai."],
) + part("V. Sales registers aur dashboards") + step(
    "Registers", [
        ("Sale ▸ Reports ▸ Sales Register / Sales Return Register / Sales Profit Analysis / Purchase - Sales "
         "Analysis / Today's Daybook", "FY (Daybook: aaj)")],
    ["Sales Register: KK JEWELS 1,31,668.51, RETURN <b>Y</b>. Return Register: SR row. Ctrl+F1 DIA / POL / CS.",
     "Today's Daybook: har voucher, piece ke neeche stone lines."],
) + step(
    "Sales Dashboard aur Business Dashboard", [
        ("Reports ▸ Sales Dashboard", "By Client · Show Value → Show; buttons Month-wise, Top 20 …"),
        ("Reports ▸ Business Dashboard", "4 tabs")],
    ["Client KK JEWELS net <b>0.00</b> (sale − return). Bar chart + table; Custom Excel.",
     "Department Pending tiles per process; Daily Output (Ghat in / out-house, casting by karat, setting pcs); "
     "Daily Sale & Return; Bills Due (KK ke bills)."],
) + part("W. Tools — settings, corrections, backup, complaint, gate pass") + step(
    "Option, Advance Options, Audit Log", [
        ("Tools ▸ Option ▸ Settings", "Others ▸ DIGICAT id = 1203 → Save"),
        ("Tools ▸ Advance Options ▸ Job Card Corrections", "Job <b>28854</b> → C Ref 'TEST' → Update C Ref (Reason "
         "khaali) → phir Reason 'test' likh ke dubara"),
        ("Tools ▸ Advance Options ▸ Declarations", "Sale Ready Stock line 1 'Subject to Jaipur jurisdiction' → Save"),
        ("Tools ▸ Audit Log", "aaj")],
    ["Settings me 'Changed by / at' me aapka naam aur time.",
     "Bina reason correction <b>mana</b>; reason ke saath save. Audit Log me job_c_ref, before → after, reason.",
     "Sale print (Ready Stock ▸ Sale ▸ Print) ke neeche Declaration line aati hai."],
) + step(
    "Backup, Complaint, Gate Pass", [
        ("Tools ▸ Backup", "Backup Now"),
        ("Tools ▸ Register a Complaint", "+ New: From Customer, JOB# 28854, complaint 'stone loose' → Save → "
         "Lookup History"),
        ("Tools ▸ Gatepass", "+ New: Destination 'Mumbai office', Box Pcs 3 → Save → Print → Register")],
    ["Backup list me dated file.", "Lookup History: job ki process history.",
     "Gate pass PDF; Register me CONFIRMED khaali = red."],
) + part("X. Job History split aur Item Search") + step(
    "Ek step do karigaron me (0.4 + 0.6)", [
        ("Job History", "Job <b>28350</b> (agla step Setting, abhi issue nahi) → + Issue → Split share <b>0.4</b>, karigar A, "
         "Net 10 → Save; + Issue → share khaali (bacha hua 0.6), karigar B, Net 5 → Save")],
    ["Worker column 'A (0.4 pc)', 'B (0.6 pc)'. Teesra issue mana: 'already out in full'.",
     "B ka Receive → step abhi bhi wahi; footer WIP <b>0.4</b>. A ka Receive → step poora, agla issue dono ka weight."],
) + step(
    "Item Search", [
        ("Kisi bhi screen pe", "<b>Ctrl+I</b> → Stock No <b>1</b>")],
    ["Status In-Stock / Primary; 'This SKU Stock: made <b>3</b>, left <b>2</b>'; photo; Print, Cert Excel, "
     "Costing Sheet; Delete pe 'Delete SKU Also' checkbox."],
) + part("Y. 6–7 Oct — crash fix, laptop screen, report grid, stone price chart A") + step(
    "App band nahi hona chahiye (crash fix)", [
        ("Reports ▸ Karigar ▸ Worker Metal Ledger", "khulte hi (jab 'Running…' dikhe) tab ka <b>×</b> dabao"),
        ("Account ▸ Outstandings ▸ Client Metal O/S", "KK JEWELS row double-click → ledger popup turant band karo; "
         "ye 5 baar jaldi-jaldi")],
    ["App <b>band nahi</b> hota (pehle yahi karne par poora app close ho jaata tha)."],
) + step(
    "Laptop screen (1366 × 768) pe sab dikhe", [
        ("Sale ▸ Ready Stock ▸ Sale", "screen kholo"),
        ("Tools ▸ Stock View", "screen kholo"),
        ("Tools ▸ Option", "Menu tab")],
    ["Sale: neeche ke buttons (Show Stock … Exit) do line me aate hain, kuch kata nahi, left-right slide nahi karna padta.",
     "Stock View: <b>Filter</b> button upar; left ke filters scroll hote hain; window screen se bahar nahi jaati.",
     "Option ▸ Menu tab, Printing Options, Business Dashboard — lambi list scroll hoti hai, neeche ka hissa kata nahi."],
) + step(
    "Report grid — 2 level group, Ctrl+E, Set Column", [
        ("Reports ▸ Karigar ▸ Worker Metal Ledger", "Group = <b>GROUP</b> · then = <b>WORKER</b>"),
        ("Same report", "<b>Ctrl+E</b>; phir Set Column se ek column chhupao"),
        ("App band karke dobara kholo", "same report")],
    ["Pehle 'GROUP : Client' / 'GROUP : Worker', uske andar har WORKER, dono level pe Total row.",
     "Ctrl+E → Excel save hota hai.",
     "Chhupaya column chhupa hi rehta hai (Set Column har user ke liye alag save hota hai)."],
) + step(
    "Sales Register aur Ready Closing Stock ke shortcuts", [
        ("Sale ▸ Reports ▸ Sales Register", "<b>F9</b>, phir row select → <b>Ctrl+C</b>"),
        ("Sale ▸ Reports ▸ Ready Closing Stock", "<b>Ctrl+F1</b>")],
    ["F9 → A/C ID column aata hai (KK); dobara F9 → chhup jaata hai. Ctrl+C → Catalog PDF.",
     "Closing Stock: DIA / POL / CS columns; Stock 1 me DIA khaali, POL <b>5,184.00</b>, CS <b>1,000.00</b>. Ctrl+F1 se "
     "chhupte / dikhte hain."],
) + step(
    "Client ki stone price sheet = price type A", [
        ("Tools ▸ Client Wise Stone Price", "left me <b>A</b> chuno"),
        ("Masters ▸ Account ▸ KK JEWELS", "Price Chart = <b>A</b> → Save"),
        ("Sale ▸ Ready Stock ▸ Sale", "Account KK JEWELS → barcode <b>1</b> scan (save mat karo)"),
        ("Client Wise Stone Price ▸ A", "<b>Export Excel</b>, phir <b>Import Excel</b> wahi file")],
    ["A me <b>299</b> rows: AMETHYST CABS 250 … POLKI 6-8 <b>10,750</b> … POLKI 12-14 <b>15,000</b> (Excel ki date wali sizes "
     "theek padhi hui).",
     "Sale: Prices From Client Chart (A) tick; Stone Amount <b>10,850.00</b> (POLKI 0.640 × 15,000 + EMERALD PEAR 0.500 × 2,500); "
     "Labour wahi <b>1,200 / 15,240.00</b> (chart A me labour nahi); Total <b>1,36,334.51</b>.",
     "Import Excel: '299 stone price(s) imported' — rows wahi rehte hain."],
) + step(
    "Client ki master sheet aur locations", [
        ("Master ▸ Account", "<b>A B JEWELS</b> search karo, phir <b>SWARNVILLA</b>"),
        ("Master ▸ Metal", "<b>22KT GOLD 92.25</b> aur <b>9KT GOLD</b> dhoondo"),
        ("Master ▸ Location", "list dekho"),
        ("Tools ▸ Advance Options ▸ Masters Excel", "<b>Masters Excel</b> → save; phir <b>Import Masters Excel</b> "
         "wahi file")],
    ["A B JEWELS client (Sundry Debtors); SWARNVILLA vendor (Accounts Payable).",
     "22KT GOLD 92.25 ki purity 92.25; 9KT GOLD 37.5.",
     "Locations me <b>vishal ji</b> aur <b>VISHAL JIDISMENTAL</b>.",
     "Import me har count 0 — kuch dobara nahi judta.",
     "Karigar (All Department Worker sheet): Master ▸ Account → <b>ABHIJEET DAS</b> Worker, Department "
     "<b>Setting</b>, In-house tick; <b>AJAY BABU</b> HandMade, In-house <b>tick nahi</b> (outside); "
     "Manufacturing ▸ Issue ke Account list me saare karigar."],
) + ("<p class='muted'>Jo bhi galat mile — step number, kya kiya, kya aana tha, kya aaya, aur screenshot bhejo. "
     "Testing dobara shuru se: <b>Reset DEMO and open.bat</b>.</p>")

def render(html: str, out: Path) -> Path:
    """A4 PDF with a fixed 9pt body font, whatever the platform default is."""
    from PySide6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
    from PySide6.QtCore import QMarginsF
    from PySide6.QtPrintSupport import QPrinter

    out.parent.mkdir(parents=True, exist_ok=True)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                      QPageLayout.Orientation.Portrait,
                                      QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter))
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
    out = (Path(sys.argv[1]) if len(sys.argv) > 1
           else Path.home() / "Downloads" / "DiaGold-Full-Test-Guide.pdf")
    print(render(HTML, out))
