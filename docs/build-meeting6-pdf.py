"""Session 6 (19 Oct 2026) client meeting document, in the layout of the
Session 3 PDF: overview, summary, build review, requirements, action items
with AI PROMPT blocks, client actions, decisions, open questions, checklist.

    python docs/build-meeting6-pdf.py [out.pdf]

Rendered with Qt WebEngine (Chromium) so the page CSS matches the earlier
session documents. Default output: the repo root, next to the other meeting
PDFs.
"""
from __future__ import annotations

import tempfile
import html
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    ROOT / "Dia_Gold_Meeting6_Build_Feedback_Fixes_19Oct2026.pdf"
SHOTS = HERE / "screens-19oct"
FOOT = "Dia Gold — Client Meeting, 19 Oct 2026"

TAG = {"C": ("CONFIRMED", "#0E6B54"), "P": ("PROBABLE", "#7A5B00"),
       "S": ("SCREEN ONLY", "#3B5BA5"), "D": ("DONE v0.10.3", "#0E6B54"),
       "O": ("OPEN", "#B3261E")}


def tag(k: str) -> str:
    label, colour = TAG[k]
    return f"<span class='tag' style='color:{colour};border-color:{colour}'>{label}</span>"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def img(name: str, caption: str) -> str:
    return (f"<figure><img src='{(SHOTS / name).as_uri()}'/>"
            f"<figcaption>{caption}</figcaption></figure>")


def table(head: list[str], rows: list[list[str]], widths: list[int] | None = None) -> str:
    cols = "".join(f"<col style='width:{w}%'/>" for w in widths) if widths else ""
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><colgroup>{cols}</colgroup><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def prompt(text: str) -> str:
    return ("<div class='prompt'><div class='ph'>AI PROMPT — COPY FROM HERE</div>"
            f"<pre>{esc(text.strip())}</pre></div>")


def task(code: str, title: str, fields: list[tuple[str, str]], ai: str, checks: list[str]) -> str:
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in fields)
    ticks = "".join(f"<li>{c}</li>" for c in checks)
    return (f"<div class='task'><h3><span class='code'>{code}</span> {title}</h3>"
            f"<table class='kv'>{rows}</table>{prompt(ai)}<ul class='ticks'>{ticks}</ul></div>")


CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 10.2pt; color: #1d2330;
       line-height: 1.42; }
h1 { font-size: 26pt; margin: 4px 0 14px; line-height: 1.1; }
h2 { font-size: 15pt; border-bottom: 2px solid #C9A227; padding-bottom: 3px; margin: 22px 0 10px;
     page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14px 0 6px; page-break-after: avoid; }
.kicker { letter-spacing: 3px; font-size: 9pt; color: #7A5B00; font-weight: 700; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 12px; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #d9dde5; padding: 5px 7px; vertical-align: top; text-align: left; }
thead th { background: #f3efe2; font-size: 9pt; text-transform: uppercase; letter-spacing: .4px; }
table.kv th { width: 22%; background: #faf8f1; font-weight: 600; }
.cover th { width: 24%; background: none; border: none; border-bottom: 1px solid #eee;
            letter-spacing: 2px; font-size: 8.5pt; color: #6b7280; }
.cover td { border: none; border-bottom: 1px solid #eee; }
.box { border: 1.5px solid #C9A227; background: #fffbea; padding: 10px 12px; margin: 12px 0;
       border-radius: 4px; page-break-inside: avoid; }
.box.red { border-color: #B3261E; background: #fff4f2; }
.box b.h { display: block; letter-spacing: 2px; font-size: 9pt; margin-bottom: 4px; }
.tag { font-size: 7.5pt; font-weight: 700; border: 1px solid; border-radius: 3px; padding: 0 4px;
       white-space: nowrap; }
.prompt { border: 1px dashed #8a8f9c; background: #f7f8fa; margin: 8px 0; padding: 8px 10px;
          page-break-inside: auto; }
.prompt .ph { font-size: 8pt; letter-spacing: 2px; color: #555; font-weight: 700; margin-bottom: 4px; }
.prompt pre { white-space: pre-wrap; font-family: Menlo, Consolas, monospace; font-size: 8.4pt;
              margin: 0; }
.task { margin-bottom: 18px; }
.task h3 .code { background: #1d2330; color: #fff; padding: 1px 6px; border-radius: 3px;
                 margin-right: 6px; }
ul.ticks { list-style: none; padding-left: 4px; }
ul.ticks li:before { content: '☐  '; }
ul.done li:before { content: '☑  '; color: #0E6B54; }
figure { margin: 8px 0 14px; page-break-inside: avoid; }
figure img { width: 100%; border: 1px solid #ccd; }
figcaption { font-size: 8.6pt; color: #555; margin-top: 3px; }
.muted { color: #6b7280; }
.foot { font-size: 8pt; color: #888; margin-top: 30px; }
.pb { page-break-before: always; }
q { font-style: italic; }
"""

COVER = f"""
<div class='kicker'>DIA GOLD — JEWELLERY ERP · SESSION 6</div>
<h1>Client Meeting<br>Build Feedback &amp; Fixes</h1>
<table class='cover'>
<tr><th>MEETING</th><td>Client feedback on our build after his own testing (demo data) — five issues
sent on WhatsApp, walked through on the call; data for live testing; WhatsApp on dispatch</td></tr>
<tr><th>DATE</th><td>Monday, 19 October 2026 · 2:37 – 2:51 PM IST (~14 min)</td></tr>
<tr><th>PLATFORM</th><td>Google Meet <b>qwa-ikjz-unk</b></td></tr>
<tr><th>CLIENT</th><td>Rohit Singh — Dia Gold (jewellery manufacturing); presented from his Windows
PC, joined from two devices</td></tr>
<tr><th>OUR TEAM</th><td>Pradeep Sharma · Khushi Jain</td></tr>
<tr><th>FOLLOWS</th><td>S1 Masters 3 Sep · S2 Order &amp; Production-Planning 11 Sep · S3 Manufacturing,
Purchase, Sale 2 Oct · S4 5 Oct · S5 M.I.S., Repair, Go-live 9 Oct · legacy walkthrough videos 12 Oct</td></tr>
<tr><th>SOURCE</th><td>One screen recording, 14m01s. Audio transcribed twice (Whisper large-v3-turbo,
Hindi and English); 84 frames read at 10-second intervals; the client's five WhatsApp screenshots
with their captions (sent 14:36).</td></tr>
<tr><th>PREPARED</th><td>19 October 2026 — fixes released the same day as <b>v0.10.3</b></td></tr>
</table>
<p>Every task in Section 7 carries a ready-to-paste <b>AI PROMPT</b> block — self-contained enough to
hand straight to a coding agent without re-reading this document.</p>
<h3>How to use this document</h3>
{table(["If you want to…", "Go to"], [
    ["Understand the session in 60 seconds", "§2 Executive Summary"],
    ["See each issue the client raised, with his screenshot", "§3 Client Requirements"],
    ["Know exactly what was wrong and what the rule is now", "§4 Detailed Functional Requirements"],
    ["Hand a task to an AI coding agent", "§7 Action Items — copy the AI PROMPT box verbatim"],
    ["Chase the client for something", "§8 Action Items — Client"],
    ["Know what was agreed / what is still unsafe to build", "§11 Decisions · §12 Open Questions"],
    ["Track progress", "§14 Complete Task Checklist"]], [70, 30])}
<div class='box red'><b class='h'>READ THIS FIRST — THE CLIENT'S VOICE IS AGAIN BADLY DEGRADED</b>
As in Session 3, the client spoke from a separate device and most of his speech transcribes as noise
(both the Hindi and the English pass). Our own team is clear. <b>What this means:</b> the five issues
are documented from the client's <b>own written captions</b> on WhatsApp (his words, quoted exactly)
and from his screenshots — that part is reliable. Spoken detail is used only where a phrase was
intelligible, with its time stamp. Meet's built-in transcript was not switched on again (S3 T-17) —
please turn it on for the next call.</div>
<div class='box'><b class='h'>CONFIDENCE TAGS</b>
{tag("C")} the client's written words or clearly heard · {tag("P")} heard, partly degraded ·
{tag("S")} read from the screen only · {tag("D")} fixed and tested in v0.10.3 · {tag("O")} needs the
client. Hindi is quoted as written / heard so a Hindi speaker can verify.</div>
"""

OVERVIEW = f"""
<h2>1. Meeting Overview</h2>
{table(["Field", "Detail"], [
    ["Date &amp; time", "Monday 19 October 2026, 2:37 – 2:51 PM IST. One recording, 14m01s."],
    ["Platform", "Google Meet <b>qwa-ikjz-unk</b>. Rohit Singh screen-shared most of the call: WhatsApp Web "
                 "(the five screenshots and captions he had sent at 14:36), then our build on his PC. "
                 "Khushi Jain shared our build for ~1 minute (Dashboard, menus, Sales Dashboard, WIP Register "
                 "— Process Summary, Business Dashboard)."],
    ["Participants", "<b>Rohit Singh</b> — client, Dia Gold. <b>Pradeep Sharma</b> — our team, lead. "
                     "<b>Khushi Jain</b> — our team; took the feedback, asked for data access."],
    ["Purpose", "(1) The client's feedback after testing our build himself on demo data — five issues. "
                "(2) Moving from demo data to the client's real data. (3) WhatsApp message to the customer "
                "on dispatch."],
    ["Build the client used", "An earlier build: his menu bar still reads <i>Master · SKU · Quotation · MRP · "
                              "Production Planning …</i> — i.e. before v0.10.2 (Order menu, Job Card). He "
                              "needs the new build to see this document's fixes (T-07)."],
    ["Screens covered", "Job History (job 28857, BANG-32, client DKJ, order 9002) · Ready Closing Stock · "
                        "Ready Items Purchase (BANG-32 from A B JEWELS) · Stock Transfer (Stock Melting) · "
                        "Metal Issue Outside / Worker · Business Dashboard."],
    ["Not covered", "New requirements; reports; masters. Nothing was rejected — every point is a defect or "
                    "a gap in what was already built."]], [22, 78])}
<h2>2. Executive Summary</h2>
<p>The client has started testing our build on his own PC with demo data. He sent five issues on
WhatsApp with screenshots, then walked through them on the call. <b>All five are defects or small gaps
in screens we had already built — no new module was asked for.</b> All five are fixed and tested in
<b>v0.10.3</b>, released the same day.</p>
<ol>
<li><b>Job History.</b> CASTING should not need a metal weight on receipt; after a receipt with a loss
(<i>ghat</i>) the next process did not pick the new gross / net by itself; and a saved entry could not be
opened and changed. <i>All three fixed.</i></li>
<li><b>Ready Closing Stock</b> showed the stone <i>amounts</i> under DIA / POL / CS; the client wants the
<b>diamond and polki weight</b>. <i>Carat columns added.</i></li>
<li><b>Ready Items Purchase</b> kept N-Wt equal to G-Wt (25.000 / 25.000) although the piece carries
6.500 ct of stones. <i>N-Wt now follows G-Wt less the stones at 0.2 g a carat (→ 23.700).</i></li>
<li><b>Stock Transfer ▸ Stock Melting.</b> Removing the melted piece left its metal and stone lines on
the voucher. <i>They now go together.</i></li>
<li><b>Metal Issue Outside / Worker</b> had no Edit. <i>Every inventory voucher can now be edited;
stock and accounts re-post.</i></li>
</ol>
<p>Two process points: Khushi asked for the <b>database credentials</b> so testing can move from demo to
live data; the client said in-progress jobs are being completed in the old software first and the data
will follow {tag("P")}. The WhatsApp message to a customer when goods are dispatched (Meta Cloud API, customer
opt-in) came up again {tag("P")} — it is built (9 Oct T-08) and waits for the client's Meta business number.</p>
<div class='box'><b class='h'>BOTTOM LINE FOR THE BUILD TEAM</b>
Nothing to start — the five fixes are in <b>v0.10.3</b> (e2e 168 checks, the 12 Oct replay 29, a UI smoke
of all five 21/21). <b>Do next:</b> T-07 send the client the new Windows build with this file;
T-08 get the database credentials / legacy data; ask Q120–Q124 before changing any of these rules
further.</div>
"""

ISSUES = [
    ("1-job-history.png",
     "Job History, job 28857 (BANG-32): CASTING received 1.000 / 1.000; HandMade received 20.000; the "
     "COLOUR issue (Vr 5448) went out with no gross / net.",
     "B1", "Job History — CASTING receipt",
     "“casting me metal recieve don't mandatory”",
     "CASTING went out unweighed (Office) and came back 1.000 / 1.000 — a weight typed only to get the "
     "receipt saved."),
    (None, None, "B2", "Job History — next process after a loss",
     "“ghat recieve ke baad next process me gross wt. &amp; net wt. do not pick auto”",
     "HandMade received 20.000 / 20.000; the COLOUR issue straight after it shows no G-Wt / N-Wt — "
     "the single-job + Issue did not carry the last weight forward (only Show Pending did)."),
    (None, None, "B3", "Job History — edit one entry",
     "“dont edit particular entry for save entry” · audio 06:28: <q>isme bhi mujhe edit chahiye tha</q>",
     "Double-clicking a cell opened the voucher read-only (Print only); the only way to change it was "
     "Manufacturing ▸ Issue / Received ▸ Edit and finding the Vr again."),
    ("2-ready-closing-stock.png",
     "Ready Closing Stock: NECKLACE 14KT 590 — POL 5,184.00 and CS 1,000.00 are amounts, not weights.",
     "B4", "Ready Closing Stock — stone weights",
     "“Isme Dia. , polki ka wt. chaiye”",
     "DIA / POL / CS carried the stone value per group (Ctrl+F1); there was no carat column."),
    ("3-ready-items-purchase.png",
     "Ready Items Purchase Vr 1, BANG-32 from A B JEWELS: G-Wt 25.000, N-Wt 25.000, St Wt 6.500.",
     "B5", "Ready Items Purchase — net weight",
     "“net wt update problem” · audio 05:21–05:33: <q>…net weight, ye same aa raha hai…</q> — Khushi: "
     "<q>theek hai, main formula correct kar deti hoon</q> — <q>jaise meri Excel sheet me aa raha tha, wo "
     "formula</q>",
     "Adding stones to a new piece changed St Wt but N-Wt stayed equal to G-Wt."),
    ("4-stock-transfer-melting.png",
     "Stock Transfer Vr 1: Metal (1) and Stone (2: polki 3.500 ct @15,000, daank 3.000 ct) still on the "
     "voucher after the melted piece was removed from Ready Stock Outward.",
     "B6", "Stock Transfer — Stock Melting, Remove Line",
     "“stock melting line remove karne par metal or stone do not remove”",
     "Stock Melting adds three kinds of line (the piece out, its metal in, its stones in) with no link "
     "between them, so Remove Line took out only the one row."),
    ("5-metal-issue-list.png",
     "Metal Issue Outside / Worker list: + New, View, Delete, Refresh — no Edit.",
     "B7", "Metal Issue Outside / Worker — Edit",
     "“edit ka option”",
     "Every Inventory voucher was view-only once saved (delete and re-enter was the only way)."),
]


def section3() -> str:
    rows = []
    figs = []
    for shot, cap, code, screen, words, seen in ISSUES:
        rows.append([f"<b>{code}</b>", screen, words, seen, tag("C")])
    rows += [
        ["<b>B8</b>", "Our build shown by Khushi", "—",
         "Dashboard, the menus, Sales Dashboard, WIP Register — Process Summary, Business Dashboard "
         "(Department Pending, pending by date, share by process). No objection heard.", tag("S")],
        ["<b>B9</b>", "Live data for testing",
         "Khushi (07:20): <q>database ka credential chahiye tha so that hum testing live kar sakein, abhi "
         "to ye demo data pe chal raha hai</q>. Client (12:20): <q>jo in-progress hoga … purane software me "
         "complete kara raha hoon … uske baad</q>",
         "In-progress jobs are being finished in the legacy software; the data comes after. Date not given.",
         tag("P")],
        ["<b>B10</b>", "WhatsApp on dispatch",
         "08:27: <q>customer ke liye maal dispatch hoga to uske paas WhatsApp message chala jaye … Meta API "
         "… requirement</q>; 09:57: <q>… option badhana padega …</q>",
         "Matches 9 Oct T-08 (built: sandbox / Meta Cloud API, opt-in per account, log, resend). Needs the "
         "client's Meta business number and approved template.", tag("P")],
        ["<b>B11</b>", "Unclear — Job Bag vs Job History",
         "02:11: <q>Job History me … Job Bag me to daala tha maine, isme miss ho gaya … jis entry ko …</q>",
         "Something entered in the Job Bag did not show in Job History — which entry is not clear (Q122).",
         tag("O")],
    ]
    for shot, cap, *_ in ISSUES:
        if shot:
            figs.append(img(shot, cap))
    return (f"<h2>3. Client Requirements</h2><h3>3A. The client's issues — his words, what we "
            "found</h3>" + table(["#", "Screen", "Client's words", "What we found", "Confidence"], rows,
                                 [5, 15, 32, 38, 10])
            + "<h3>3B. The client's screenshots</h3>" + "".join(figs))


REQS = [
    ("R1", "CASTING receipt needs no weight", "B1",
     "A receipt on a process listed in Tools ▸ Option ▸ Production Planning <b>“Processes received without "
     "a weight”</b> (default <b>CASTING</b>) saves with no gross / net — even when the issue was weighed. "
     "No loss is worked for it. The next process then goes out at the last weight on the job (the casting "
     "issue's weight, or the last receipt). Other metal steps still need the weight back unless nothing "
     "weighed went out (12 Oct rule kept). The same rule applies when the receipt is edited.",
     "services/production.py: receive_weight_optional(), post_voucher(), update_voucher()",
     "Weighed CASTING 22.000 out → received blank → next issue 22.000 / 22.000."),
    ("R2", "Next process picks the last gross / net", "B2",
     "Job History ▸ <b>+ Issue</b> fills Gross / Net with the job's last weights (what came back on the "
     "last receipt — 20.000 after HandMade; 19.360 after PrePolish), as Show Pending already did. They "
     "can be typed over. <b>+ Issue</b> also opens on the job's <b>next step in route order</b> (CAD, "
     "CAMMING first — they just take no weight) instead of jumping to the first weighed step.",
     "ui/production.py: VoucherDialog._step_changed(), __init__",
     "HandMade 20 → 19.5 received → COLOUR issue opens with 19.5 / 19.5 and saves."),
    ("R3", "Edit an entry from Job History", "B3",
     "Double-click a pink (issue) or green (receipt) cell → the voucher → <b>Edit</b>. It opens on its "
     "process screen with its figures (gross, net, stone, scrap, dust, allow %, rejection, prices); change "
     "and Save. Loss and setting labour are worked again; the change is logged; a job already in ready "
     "stock is refused (delete its stock item first). Job History refreshes after.",
     "ui/production.py: voucher_view(); ui/manufacturing.py: ProcessVoucherWidget.edit_vr()",
     "COLOUR Vr 5448 edited 19.5 → 19.4 and saved."),
    ("R4", "Ready Closing Stock — DIA / POL / CS weight", "B4",
     "Three carat columns always shown after FINE: <b>DIA WT, POL WT, CS WT</b> — the carats of diamond, "
     "polki and colour stone in the piece (from its stone lines; pearls / sarafa count as colour stone, "
     "as the stone groups do). Totals per group and grand total. The amounts stay, as DIA AMT / POL AMT / "
     "CS AMT on Ctrl+F1.",
     "services/stock_tools.py: piece_row(); ui/stock_tools.py: ready_closing_stock",
     "DIA + POL + CS WT = the piece's total carats."),
    ("R5", "Ready Items — N-Wt from G-Wt and stones", "B5",
     "On a new piece (Ready Items Purchase, Opening Stock): <b>N-Wt = G-Wt − stone carats × 0.2 g</b>, "
     "worked again when G-Wt or the stones change (Add Piece and Stone Breakup); FineWt follows (N-Wt × "
     "title ÷ 1000). N-Wt can still be typed over. 25.000 with 6.500 ct → <b>23.700</b>. The 0.2 g / ct is "
     "the legacy setting-receipt rule (12 Oct video); the client mentioned his Excel formula — Q120.",
     "services/sales.py: net_from_gross(); ui/ready_vouchers.py",
     "25.000 g with 3.5 + 3.0 ct → 23.700."),
    ("R6", "Stock Melting lines go together", "B6",
     "Stock Melting puts the piece (Ready Stock Outward), its metal (Metal) and its stones (Stone) on the "
     "voucher as one group. Remove Line on any of them asks once and removes the whole group. The same "
     "piece cannot be melted twice on one voucher.",
     "ui/stock_transfer.py: stock_melting(), remove_line()",
     "Melt → 3 lines; remove the piece → 0; remove a stone line → 0."),
    ("R7", "Edit on inventory vouchers", "B7",
     "Metal Issue Outside / Worker — and every Inventory voucher (purchase, issue, receipt, opening, "
     "sale …) — has <b>Edit</b>. Save takes the voucher's old stock movements and account entries out and "
     "posts it again from the new lines; it is logged. Refused when receipts / payments are knocked off "
     "against the bill, or (in block mode) when what it brought in has already gone out.",
     "services/inventory.py: repost_voucher(), _reverse_postings(); ui/inventory.py",
     "Issue 2.000 → 1.500: location balance up 0.500, one set of movements."),
]


def section4() -> str:
    out = ["<h2 class='pb'>4. Detailed Functional Requirements</h2><p>One block per fix: the rule as it now "
           "stands in the build, where it lives, and the check that proves it.</p>"]
    for code, title, src, rule, where, test in REQS:
        out.append(f"<h3>{code}. {title} {tag('D')}</h3>" + table(["", ""], [
            ["From", src], ["Rule now", rule], ["Code", f"<span class='muted'>{where}</span>"],
            ["Proved by", test]], [16, 84]).replace("<thead><tr><th></th><th></th></tr></thead>", ""))
    return "".join(out)


TECH = f"""
<h2>5. Technical Requirements</h2>
{table(["#", "Requirement", "Detail"], [
    ["TR1", "Re-posting an inventory voucher is atomic", "Old movements and entries out, new ones in, in one "
     "transaction; any refusal rolls the whole edit back. Stock = Σ movements still holds (e2e invariant)."],
    ["TR2", "Receipt-weight rule is configuration", "The list of processes is a Tools ▸ Option text "
     "setting, not code — the client can add or remove processes."],
    ["TR3", "Melting group is a client-side link", "The group key is the melted piece's id; it is not stored — "
     "what is saved is the same three panes as before."],
    ["TR4", "Tests", "tests/e2e_flow.py §N12 (6 new checks, 168 in all), tests/ns1430_flow.py 29, "
     "tests/abhijeet_das.py all rows; an offscreen UI smoke of all five screens 21/21."]], [6, 30, 64])}
<h2>6. UI/UX Requirements</h2>
{table(["#", "Requirement"], [
    ["UX1", "Job History voucher view: <b>Edit</b> beside Print Voucher."],
    ["UX2", "+ Issue: Gross / Net already filled; the step box on the next step of the route."],
    ["UX3", "Ready Closing Stock: DIA WT / POL WT / CS WT always visible; amounts renamed DIA AMT / POL AMT / "
            "CS AMT (Ctrl+F1)."],
    ["UX4", "Stock Transfer: one question before a melted group is removed."],
    ["UX5", "Inventory voucher lists: Edit button (the same form as + New, with the saved lines)."]], [6, 94])}
"""

TASKS = [
    ("T-01", "CASTING receipt without weight (R1)", "DONE", "B1 — the client's caption", """
In a jewellery manufacturing ERP (Python, SQLAlchemy, PySide6), a JOB moves through a route of
PROCESSES (CAD, CAMMING, CASTING, HandMade, COLOUR, PrePolish, Setting ...). Each step is ISSUED to a
karigar with gross / net weight and RECEIVED back with gross / net; loss = issued net - received net.

Change: a receipt on a process named in a configurable list (setting "pp.receive_weight_optional",
comma-separated, default "CASTING") may be saved with NO gross / net even when the issue was weighed.
- No loss is computed for that pair (receive net is None).
- The next issue defaults to the job's last weighed figure (the casting issue weight).
- Apply the same rule in the voucher EDIT path, not only on first save.
- Every other weighed process keeps the rule: a receipt needs a net weight unless the issue went
  out unweighed.
Acceptance: CASTING issued 22.000 / 22.000, received blank -> saved; next issue proposes 22.000 / 22.000.
""", ["Setting in Tools ▸ Option, default CASTING", "Post and edit paths both", "e2e check"]),
    ("T-02", "+ Issue carries the last weight and opens on the next step (R2)", "DONE", "B2", """
Job History has "+ Issue": a dialog with Step, Worker, Pcs, Gross Wt, Net Wt, Allow Loss %, F3 stones,
F5 metal. Today it opens on the first weight-bearing step and leaves Gross / Net blank.

Change:
1. Open on the job's CURRENT step in route order (production.current_step(job)) when that step has
   nothing out; fall back to the first weighed step otherwise.
2. When the chosen step carries weight and this is an ISSUE, fill Gross / Net with
   production.last_weights(job) (the last receipt; split shares summed). The user may type over.
Acceptance (client's job 28857): HandMade received 20.000 -> COLOUR issue opens with 20.000 / 20.000.
""", ["Prefill on step change", "Route order", "UI smoke"]),
    ("T-03", "Edit a Job History entry (R3)", "DONE", "B3", """
Job History: double-clicking an issue (pink) or receipt (green) cell opens voucher_view(voucher_id),
which today only prints. Add an "Edit" button: open ProcessVoucherWidget(kind) in a dialog, call
edit_vr(vr_no) to load the saved voucher's lines, let the user change the editable cells and Save
(production.update_voucher re-works loss and setting labour, writes an audit row, refuses a job already
transferred to ready stock). Refresh Job History when the dialog closes.
Acceptance: COLOUR Vr 5448 19.5 -> 19.4 saved and shown.
""", ["Edit button", "Refresh after", "Audit row"]),
    ("T-04", "Ready Closing Stock carats (R4)", "DONE", "B4", """
Ready Closing Stock lists every piece in stock with DIA / POL / CS = stone VALUE per group
(sales.stone_block(stone) -> DIAMOND / POLKI / COLOR STONE). Add carats per group:
dia_wt, polki_wt, cs_wt = sum of the stone lines' weight per group (3 decimals, totals).
Columns after FINE: DIA WT, POL WT, CS WT (always shown); rename the amounts DIA AMT / POL AMT /
CS AMT and keep them on the Ctrl+F1 toggle.
Acceptance: DIA WT + POL WT + CS WT = the piece's total stone carats.
""", ["Three columns with totals", "Amounts renamed"]),
    ("T-05", "Ready Items N-Wt from stones (R5)", "DONE", "B5", """
Ready Items Purchase / Opening Stock: a new piece has G-Wt, N-Wt, stones (each with weight in carats).
Rule: N-Wt = G-Wt - total stone carats x 0.2 g (min 0, 3 decimals); FineWt = N-Wt x title / 1000.
Re-work N-Wt whenever G-Wt changes (Add Piece dialog) or the stones change (Add Piece "Stones..." and the
grid's Stone Breakup on an unsaved new piece). Keep N-Wt editable afterwards.
Acceptance: 25.000 g with 3.500 + 3.000 ct -> N-Wt 23.700.
UNCONFIRMED: the client referred to "the formula in my Excel sheet" - confirm before changing (Q120).
""", ["Add Piece", "Stone Breakup", "FineWt follows"]),
    ("T-06", "Stock Melting group + inventory voucher Edit (R6, R7)", "DONE", "B6, B7", """
A) Stock Transfer ▸ Stock Melting adds: the piece (pane ready_out), its metal (pane metal), its stones
(pane stone). Tag all of them with the melted item's id ("_melt"). Remove Line on any tagged row:
confirm once, then remove every row with that tag. Refuse melting the same piece twice on one voucher.
B) Inventory vouchers (Metal / Stone purchase, issue, receipt, opening, sale ...) are CrudSpec screens
saved with after_save=post_voucher and editable=False. Make them editable. On save: if the voucher
already has StockMovements / AccountEntries (ref_kind=vr_type, ref_no=vr_no), reverse them (same code
as delete: adjust MaterialStock, delete movements and entries, refuse if bill allocations exist or -
in block mode - if what it brought in has gone out), log the edit, then post_voucher again.
Acceptance: metal issue 2.000 -> 1.500 raises the location by 0.500 with one set of movements.
""", ["Melt group remove", "No double melt", "Edit + repost", "Audit"]),
    ("T-07", "Send the client the new build with this document", "TODO", "B-all; client is on a pre-v0.10.2 build", """
Build the Windows installer from v0.10.3 (PyInstaller spec lists every file under diagold/), send it with
this PDF. Ask the client to re-test the five points on the same records (job 28857, Ready Closing Stock,
BANG-32 purchase, a stock melting, a metal issue) and reply on WhatsApp per point.
""", ["Windows build v0.10.3", "Sent with this file", "Client re-test reply"]),
    ("T-08", "Move testing to the client's data", "TODO", "B9", """
Get read access to the legacy database (SERVER2\\ERP -> Diagold26) or the exports listed in the data
request. Run scripts/migration_checks.py on it and share the Excel of findings; load masters first, then
open stock, then the jobs the client has NOT finished in the legacy software.
""", ["Credentials / exports received", "Migration checks run", "Masters loaded"]),
]


def section7() -> str:
    out = ["<h2 class='pb'>7. Action Items — Our Team</h2><p>Each task is self-contained. Copy the AI "
           "PROMPT block verbatim into a coding agent. Status: DONE = in v0.10.3 and tested.</p>"]
    for code, title, status, why, ai, checks in TASKS:
        done = status == "DONE"
        t = task(code, title + (" " + tag("D") if done else ""), [
            ("Why", why), ("Owner", "Dev team" if code not in ("T-07", "T-08") else "Khushi Jain; Pradeep to review"),
            ("Priority", "HIGH" + (" — done" if done else " — today")),
            ("Status", "Done in v0.10.3" if done else "To do")], ai, checks)
        if done:
            t = t.replace("<ul class='ticks'>", "<ul class='ticks done'>")
        out.append(t)
    return "".join(out)


CLIENT = f"""
<h2>8. Action Items — Client</h2>
{table(["#", "Action", "Detail", "Unblocks"], [
    ["C-01", "Database access or exports", "Credentials for SERVER2\\ERP / Diagold26 (read only), or the "
     "Excel exports in the data request. After the in-progress jobs are finished in the old software.", "T-08"],
    ["C-02", "Net-weight formula", "The Excel sheet / formula you use for N-Wt on a bought piece (Q120).", "T-05"],
    ["C-03", "Install v0.10.3 and re-test", "The five points on the same records; reply per point.", "T-07"],
    ["C-04", "Meta WhatsApp", "Business number, display name and an approved dispatch template (Meta Cloud "
     "API) — the sandbox is ready.", "9 Oct T-08"],
    ["C-05", "Meet transcript", "Switch on Activities ▸ Transcripts next time — your voice does not survive "
     "the recording.", "all"]], [7, 22, 56, 15])}
<h2>10. Dependencies</h2>
{table(["Item", "Depends on"], [
    ["Client re-test (C-03)", "T-07 new build"],
    ["Live-data testing (T-08)", "C-01; client finishing in-progress jobs in the legacy software"],
    ["Any further change to the net formula", "C-02 / Q120"],
    ["Real WhatsApp messages", "C-04"]], [40, 60])}
"""

DECISIONS = f"""
<h2>11. Decisions Made</h2>
{table(["#", "Decision", "Detail", "Confidence"], [
    ["D1", "CASTING receipt is weight-optional", "Client's caption. Kept as a configurable list.", tag("C")],
    ["D2", "Next issue takes the last weight", "Client's caption; typed over when needed.", tag("C")],
    ["D3", "Saved entries are editable", "Job History entries and inventory vouchers; every edit logged.", tag("C")],
    ["D4", "Closing stock shows DIA / POLKI weight", "Client's caption. Amounts kept on Ctrl+F1.", tag("C")],
    ["D5", "N-Wt follows the stones", "Formula to be matched to the client's Excel (Q120).", tag("P")],
    ["D6", "Testing moves to live data", "After the in-progress jobs are closed in the old software.", tag("P")]],
    [6, 32, 50, 12])}
<h2>12. Open Questions / Clarifications</h2>
<p>Nothing here has an answer yet. Do not let anyone — human or AI — guess at these. Numbered after the
questions already with the client (Q1–Q119).</p>
{table(["#", "Question", "Why it matters", "Blocks"], [
    ["Q120", "Net weight of a bought piece: is it G-Wt − stone carats × 0.2 g? You mentioned the formula in "
             "your Excel sheet — please send it (pearls / sarafa by weight too?).", "Every purchased piece's "
             "N-Wt, metal amount and fine.", "T-05"],
    ["Q121", "CASTING received without weight: only CASTING, or other processes too? Does the casting "
             "karigar keep the metal against his name until the next weight?", "Karigar metal balance, "
             "loss registers.", "T-01"],
    ["Q122", "“Job Bag me daala tha, Job History me miss ho gaya” (02:11) — which entry was missing?",
     "Possible display gap between Job Card Bag and Job History.", "—"],
    ["Q123", "Ready Closing Stock: carats only, or also pieces (pcs) per DIA / POLKI / CS?", "Column set.", "T-04"],
    ["Q124", "Edit on every inventory voucher, or only some? Should editing need a User Right (like "
             "Delete History)?", "Rights matrix.", "T-06"]], [7, 50, 30, 13])}
<h2>13. Final Deliverables / Expected Outcomes</h2>
{table(["#", "Deliverable", "Definition of done"], [
    ["1", "Five fixes", "In v0.10.3, tested (§5 TR4) — done."],
    ["2", "Client re-test", "Client confirms each of B1–B7 on his PC."],
    ["3", "Live data", "Masters and open stock from the legacy database loaded; migration checks shared."]],
    [6, 30, 64])}
"""

CHECKLIST = """
<h2 class='pb'>14. Complete Task Checklist</h2>
<p>Tick as completed. T- = our team · C- = client · Q = answer before changing the linked rule.</p>
<h3>Done — v0.10.3</h3>
<ul class='ticks done'>
<li>T-01 CASTING receipt without weight (setting, default CASTING)</li>
<li>T-02 + Issue: last gross / net, next step in route order</li>
<li>T-03 Edit from Job History</li>
<li>T-04 Ready Closing Stock DIA / POL / CS WT</li>
<li>T-05 Ready Items N-Wt = G-Wt − ct × 0.2</li>
<li>T-06 Stock Melting group remove · inventory voucher Edit</li>
</ul>
<h3>Today</h3>
<ul class='ticks'>
<li>T-07 Windows build v0.10.3 + this file to Rohit</li>
<li>Questions Q120–Q124 to the group</li>
</ul>
<h3>Client</h3>
<ul class='ticks'>
<li>C-01 Database access / exports</li>
<li>C-02 Net-weight formula (Excel)</li>
<li>C-03 Re-test the five points</li>
<li>C-04 Meta WhatsApp number + template</li>
<li>C-05 Meet transcript on</li>
</ul>
<h3>Next</h3>
<ul class='ticks'><li>T-08 Live-data testing after C-01</li></ul>
"""


def build_html() -> str:
    body = (COVER + OVERVIEW + section3() + section4() + TECH + section7() + CLIENT + DECISIONS
            + CHECKLIST + f"<p class='foot'>{FOOT}</p>")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Dia Gold Session 6</title>" \
           f"<style>{CSS}</style></head><body>{body}</body></html>"


def main() -> None:
    from PySide6.QtCore import QMarginsF, QUrl
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    page = QWebEnginePage()
    done: dict[str, bool] = {}

    def loaded(ok: bool) -> None:
        layout = QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                             QMarginsF(14, 16, 14, 18), QPageLayout.Unit.Millimeter)
        page.printToPdf(str(OUT), layout)

    def printed(path: str, ok: bool) -> None:
        done["ok"] = ok
        app.quit()
    page.loadFinished.connect(loaded)
    page.pdfPrintingFinished.connect(printed)
    # setHtml() stops at 2 MB; a file has no such limit.
    tmp = Path(tempfile.mkdtemp()) / "meeting6.html"
    tmp.write_text(build_html(), encoding="utf-8")
    page.load(QUrl.fromLocalFile(str(tmp)))
    app.exec()
    print(("Wrote " if done.get("ok") else "FAILED ") + str(OUT))


if __name__ == "__main__":
    main()
