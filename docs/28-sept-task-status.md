# 28 September tasks — status

Every task from *Client Meeting Requirements & Action Items, 28 Sept 2026*
(§7, §14), with what was built, where to find it, and what is still waiting
for the client. Verified with the acceptance scripts on a fresh database and on
a copy of the working database.

## Our team

| Task | Status | What / where | Waiting on |
|---|---|---|---|
| **T-01** Inventory — metal and stone | ✅ Built | Inventory ▸ Metal ▸ … and Inventory ▸ Stone ▸ … (Purchase, Issue Outside / Worker, Receipt, Issue On Job Card, Day Book, Reports). Every line posts to the stock ledger with fine weight at posting; balances are sums of movements; Print; delete reverses with an audit row; negative stock block / warn / allow (Tools ▸ Option, default warn). 24KT / 22KT / alloy heads added from the legacy Metal Analysis. Acceptance: purchase ₹1,24,64,400 ✓, 1.625 g 14KT590 → 0.959 fine ✓, balances = Σ movements ✓. | Load Metal, Issue On Tree, Conversion, Adjustment, Worker Recovery, WIP Rtn, Bhav Cut — not explained (C-04); "Opening" and wastage meanings assumed (C-04); which columns first (C-01 / Q10) |
| **T-02** Job flow & pending | ✅ Built | Show Pending on Job History (per process, issue / receive), Job Card Bag, Stone Issue, Inv Return, MFG Transfer. Last step received → Pending for MFG Transfer; transfer → stock; delete stock → back to pending. | QC as its own step (Q7) |
| **T-03** Issue / receive voucher | ✅ Built | Manufacturing ▸ Issue ("Issue To <Process>") and Manufacturing ▸ Received ("Received From <Process>"): process, karigar with Mt Bal, RefNo, Show Pending, many jobs on one voucher number; the full legacy line - Size, Mt Price / Mt Amt at the day's rate, Manual Price / Amt, Issue St Wt / ExtraMt / Finding (F4) / MouldWt (F7), Allow Loss %, L Price On, Rej.Type / Rej Pcs / Rej Wt / Scrap / Dust on a receipt; F3 / F5 on the selected line, the line's photo, narration, print, Statement (karigar ledger); Issue / Received Day Books on the menu. Also from Job History ▸ + Issue / + Receive / Show Pending. Allow Loss % per line; F3 Stone Job Bag (setting type + price), F4 Finding, F5 Metal (from a location, booked to the karigar), F7 Mould; Mt Bal on a receipt; Narration. | Where Allow Loss % defaults from (Q3); Extra Issue (Q8) |
| **T-04** Loss engine & karigar ledger | ✅ Built | Loss / Loss % per step in Job History; Reports ▸ Worker Metal Ledger (ISS / RTN / MI / MR, weight + fine, allowance, running balance). Golden BANG-577 rows ✓ to 3 decimals. | All loss vs excess (Q3 — switch in Tools ▸ Option); why the second final-setting row shows no loss (Q13) |
| **T-05** Setting labour | ✅ Built | Stored on the receive (Job History Labour column, Setting Labour button); Reports ▸ Setting Labour Statement (month-end per karigar). BANG-577 = ₹2,400 ✓; a later rate change leaves received jobs alone ✓. | Broken pieces unpaid? (Q4) |
| **T-06** Job Card Bag | ✅ Built, one rule held back | Job 28853 seeded as the legacy bag — every line balances to 0 ✓; over-issue / over-return / over-back refused ✓; Setting Type per line. | "Return ≤ issued" not enforced until Q14 says whether extra stones can go back to stock without a karigar |
| **T-07** MFG price engine | ✅ Built | Manufacturing ▸ MFG Transfer ▸ Fill Prices; the legacy grid (Location, C-Ref, Col, Size, FineWt, Fine With Loss, Rej, Ex Metal, Finding Labour, Total Value, Stamp …); cost break-up; Print, Excel; everything stored on the line; tag-price rule a setting. Golden NSE-2495 → ₹3,05,330.12 / "305" ✓ to the paisa; no rate literal in the code ✓. | Margin vs the 20% (Q1); which net weight labour uses (Q2); tag rule (Q5); metal rate basis (Q11); setting amount on the transfer (Q12) |
| **T-08** Tagging, stock, Item Search | ✅ Built | Save → Stock No / bar code in Primary → Tag List (print all / selected / to a chosen printer, tag price on/off, C-Ref, Detail, per piece, Create Txt, TXT Import of Stock IDs, Clear). Item Search (top right). Delete History & Purchase → job back to pending, audit row ✓. Sale ▸ Ready Stock report. | Label-printer format for Create Txt; "Delete SKU also" (Q18); Diamond Tag (Q19) |
| **T-09** Job History | ✅ Built | Two-half layout with loss, allowance and labour; the page scrolls so every step and stone line is in view; double-click a pink cell → its issue voucher, green → its receipt, with Print; photo enlarges on click. | — |
| **T-10** Reports | ✅ Built | Reports: Metal Analysis (drill to the location ledger), Worker Metal Ledger, Worker Balance (Metal), Worker Stone Ledger, Worker Balance (Stone), Setting Labour Statement, Issue / Received Day Books, Metal / Stone Day Books, Pending for MFG Transfer (F10 → job bag), MFG Transfer Day Book — all on the shared report grid (search, columns, group, filters, export, FY default). Negative closings in red. | — |
| **T-11** Update the 3 Sept requirements | ✅ Written | `docs/3-sept-requirements-update.md` | Pradeep to re-issue the 3 Sept document |
| **T-12** Inventory walkthrough | ✅ Written | `docs/next-session-agenda.md`, questions in `docs/group-message.md` | The session itself (C-01) |

## Also done on the way

- Menus across the top instead of a sidebar (Inventory ▸ Metal / Stone as submenus); Item Search link top right.
- "Save? Yes / No" before every save (switch in Tools ▸ Option).
- Lists always span their box — no blank strip after the last column.
- Orders list shows Terms, Priority and Remark (they were saved but hidden from the list).
- **30 Sept, closing the gaps found by re-reading the PDF line by line:**
  - Issue / Received vouchers: **Add, Edit, Delete** a saved voucher. Edit changes weights, prices, date, RefNo and narration. Delete undoes the whole voucher (F3 stones and F5 metal go back, the job returns to pending) when nothing later has been done on its jobs. Both are kept in the deletion log.
  - MFG Transfer: **Add, Edit, Delete** a saved transfer (Edit re-prices; the Stock Nos stay), and **Format-2**, a per-piece print with the cost break-up.
  - **Attach Doc** on Received From <Process> and on every Inventory voucher.
  - Metal Issue: **Check Bal** (the karigar's Mt Bal and metal balance, and the stock at each location).
  - Stone Receipt: **Show O/S**. Stones out with a worker; the ticked lines open a new receipt.
  - **F12**: More Reports.
  - Purchases post **Dr Purchase A/c / Cr supplier**; new **Account Ledger** report.
- **Demo data to try the whole flow:** `python -m diagold.demo` opens the app on its own database; `docs/demo-walkthrough.md` lists every step and the figure it should show.

## Client (C-01 … C-05) and open questions (Q1 … Q14)

All listed, one line each, in `docs/group-message.md` under "28 Sept". Q12–Q19
are new ones found while building:

- **Q12** Does the setting labour paid to the karigar go into "Setting Amount" on the MFG transfer?
- **Q13** Job 28853: why does the second final-setting row show no loss?
- **Q14** Can stones go back to stock straight from a job bag without first going to a karigar?
- **Q15** MFG Transfer "Split Jobs" — one Stock No per piece?
- **Q16** MFG Transfer "Old Wt" and "Tag%" — what do they hold?
- **Q17** "Fine With Loss" = FineWt × (1 + Loss%)?
- **Q18** Item Search "Delete SKU also" — delete the Product SKU master?
- **Q19** Tag List "Diamond Tag" — what changes on the tag?
- **Q20** Issue voucher "P.O." button — what does it print or open?
- **Q21** Stone Receipt "Read Cert/Lot Here" — what is scanned (a certificate no., a lot no.), and what should it fill in?
- **Q22** Job History "Other Wt" (receive side) — which weight is it?
- **Q23** MFG Transfer "Format-2" — a sample print, so ours matches it (built for now as a per-piece cost break-up).
