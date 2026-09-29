"""Render the full-flow test script to a PDF.

    python docs/build-full-flow-pdf.py [out.pdf]

One new job taken from order to ready stock through every screen built so
far (Masters, Inventory, Production Planning, Manufacturing, Reports), with
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
""" + H1.format("Dia Gold CRM — Full Flow Test Script") + """
<p class='muted'>Order se Ready Stock tak ek naya job — har screen jo ab tak bani hai (Master, Inventory,
Production Planning, Manufacturing, Reports), aur har step pe kya type karna hai aur screen pe kya aana chahiye.
Login <b>admin</b> / <b>admin</b>.</p>
""" + BOX.format("""<b>Shuru kaise karein:</b> Terminal me project folder se <b>python -m diagold.demo --reset</b>.
Ye ek alag demo database kholta hai (~/DiaGoldDemo) — asli data ko kuch nahi hota. Isme aaj ke rates
(24K fine 14,713/g → 14KT 590 = 8,680.67/g), labour 1,200/g, margin 50%, karigar CHAND KUMAR HAZRA, aur
demo jobs 28854–28856 pehle se hain. Neeche window ke status bar me <b>DiaGoldDemo</b> dikhna chahiye.""") + """
""" + BOX.format("""<b>Aapka job:</b> step 10 me order save hote hi ek naya Job No milega (fresh demo me
<b>28857</b>). Wahi number likh lein — step 11 se aakhir tak har jagah wahi job chunna hai. Demo jobs
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
    ["Save → Manufacturing ▸ Issue ke Account dropdown me RAHUL JI dikhega (step 17 — HandMade — me use hoga)."],
) + part("B. Inventory — stock andar lao, karigar ko do") + step(
    "Inventory ▸ Stone ▸ Purchase → + New", [
        ("Supplier", "SHRIKANT"), ("Ref No", "TEST-ST"),
        ("Line 1", "Location <b>Primary</b> · SSKU <b>POLKI 12-14</b> · Pcs <b>20</b> · Weight <b>1.600</b> · Price <b>8100</b> · Per Cts"),
        ("Line 2", "Location <b>Primary</b> · SSKU <b>EMERALD PEAR 3*4</b> · Pcs <b>10</b> · Weight <b>1.000</b> · Price <b>2000</b> · Per Cts")],
    ["Amount khud: line 1 <b>12,960.00</b>, line 2 <b>2,000.00</b>; neeche summary 2 lines · 30 pcs · 2.600 ct · amount <b>14,960.00</b>.",
     "Save → Vr No khud. Row select → <b>Print</b> → PDF."],
) + step(
    "Inventory ▸ Metal ▸ Purchase → + New", [
        ("Supplier", "SHRIKANT"), ("Ref No", "TEST-MT"),
        ("Line", "Location <b>RAJESH JI</b> · Metal <b>14KT 590</b> · Colour Y · Weight <b>50.000</b> · Price <b>8680.67</b>")],
    ["Amount <b>4,34,033.50</b>; Save ke baad Fine <b>29.500</b> (50 × 0.590)."],
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
     "CHAND ke paas ab is voucher se bacha: 2.000 − 1.800 − 0.045 = <b>0.155 g</b> (step 35 me check)."],
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
    "GrossWt <b>13.000</b> · NetWt <b>13.000</b>", "3.5",
    "Job History HandMade: Loss <b>0.200</b> · <b>1.52%</b>, allowed 3.5% of 13.000 = <b>0.455</b>. "
    "Iss Finding <b>0.050</b>, Iss Mould <b>0.100</b>.",
    extra_iss="line select → <b>F4</b> Finding <b>0.050</b> → Enter · <b>F7</b> Mould <b>0.100</b> → Enter") + mfg(
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
     "Received pe Account <b>(any karigar)</b> → Show Pending me sab karigaron ke jobs."],
) + part("E. Job History — ek job ki poori kahani") + step(
    "Production Planning ▸ Job History (F11)", [("Job No", "apna job")],
    ["Header: SKU NS-1430, C-Ref TEST-C, Client KK JEWELS, Ord No, Route CAD CAM CS HM COL PP ST FP fs Meena Puwai.",
     "11 rows; issue half <b>pink</b>, receive half <b>green</b>. Loss column Worker ke saath: "
     "0.300 · 0.200 · 0.000 · 0.100 · 0.050 · 0.090 · 0.020 · 0.020 · 0.020 → total <b>0.800 g</b>.",
     "Setting row ka Labour <b>240.00</b>. <b>Setting Labour</b> button → yahi statement.",
     "Kisi pink cell pe double-click → us issue ka voucher; green cell → receipt voucher.",
     "Neeche stones grid me POLKI aur EMERALD lines — page scroll karke sab dikhna chahiye.",
     "<b>MFG Price</b> button → step 28 wale hi figures.",
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
     "<b>Print</b> → PDF · <b>Excel</b> → CSV."],
) + step(
    "MFG Transfer → Save", [("Save", "Yes")],
    ["Stock No milta hai (Primary me) aur <b>Tag List</b> khulta hai.",
     "Tag List me try: Print Tag Price on/off · C-Ref Barcode (TEST-C) · <b>Detail</b> (POLKI / COLOR STONE carats) · "
     "Pcs Wise · Print Selected (pehle tick) · Print All · <b>Select Printer</b> · <b>Create Txt</b>.",
     "<b>TXT Import (Stock ID)</b>: ek .txt file me Stock No likho → import → list me aa jata hai."],
) + step(
    "Sale ▸ Ready Stock", [],
    ["Apna piece: Primary · cost <b>1,31,668.51</b> · price <b>1,97,502.77</b> · tag <b>197</b> · Tag Printed Y (agar print kiya)."],
) + step(
    "Item Search (top right)", [("Search", "apna Stock No, ya Job No, ya NS-1430 → Enter")],
    ["Piece card: client, order, G-Wt 12.930, N-Wt 12.700, cost / price / tag; stones grid; value summary by stone kind.",
     "<b>Job History</b> button → wapas us job pe."],
) + step(
    "Item Search → Delete History &amp; Purchase (correction path)", [("Reason", "test correction")],
    ["Piece stock se hat jata hai; job wapas <b>Pending for MFG Transfer</b> me.",
     "Ab MFG Transfer se dobara Show Pending → Save → naya Stock No. (Delete ka audit record banta hai.)"],
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
     "RAHUL JI: ISS 13.200 · RTN 13.000 · Loss 0.200 · Alw 3.5% = 0.455 · Balance <b>−0.255</b> "
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
) + part("I. Settings aur UI") + step(
    "Tools ▸ Option", [],
    ["Behaviour: <b>Ask \"Save? Yes / No\" before every save</b> untick → Save → ab kisi save pe popup nahi; wapas tick.",
     "<b>Inventory: when a location would go below zero</b> → <b>Block the save</b> → step 8 wala 500 g issue ab seedha refuse; "
     "wapas <b>Warn, then allow (default)</b>.",
     "<b>Tag price on the tag</b> dropdown badlo → MFG Transfer ka Tag column naye format me.",
     "Production Planning ke items untick → Save → menu se gayab; wapas tick."],
) + step(
    "UI checks", [],
    ["Sidebar nahi — sab module top menu me; Inventory ▸ Metal / Stone submenu.",
     "<b>Reports</b> menu me sections submenu ban ke (Day Books ▸, Inventory ▸, Karigar ▸ …); har report apne "
     "tab me full width khulta hai — left me report list nahi. Production Planning / Manufacturing / "
     "Inventory ▸ Reports bhi aise hi.",
     "Har tab ke × pe hover → dark background pe safed × (Close Tab).",
     "<b>Go to screen…</b> (Ctrl/Cmd+F) me 'job his' type → Job History khulta hai.",
     "Manufacturing / Inventory ke 'to be explained' items (Waxing, Extra Issue, Bhav Cut …) ek note kholte hain — "
     "ye client ke jawab ka wait kar rahe hain."],
) + ("<p class='muted'>Jo bhi galat mile — step number aur screenshot ke saath bhej do. "
     "Dobara shuru karna ho to: python -m diagold.demo --reset.</p>")

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
           else Path.home() / "Downloads" / "DiaGold-Full-Flow-Test.pdf")
    print(render(HTML, out))
