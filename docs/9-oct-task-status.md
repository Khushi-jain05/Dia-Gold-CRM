# 9 Oct (Session 5) - task status

Source: *Dia_Gold_Meeting5_MIS_Reports_Repair_GoLive_Data_Requirements_9Oct2026.pdf*
and the three 12 Oct walkthrough videos (`12-oct-flow-video.md`). Tests:
`tests/e2e_flow.py` (150 checks), `tests/ns1430_flow.py` (26 - the 12 Oct job
replayed), `tests/abhijeet_das.py`.

## Our tasks (§7)

| Task | Status | Where |
|---|---|---|
| T-01 Follow-up to Rohit | Ready to send | `group-message.md` (data reminder + questions 96-116) |
| T-02 Sales M.I.S. | Done | Sales Analysis, Sales Analysis[Item Wise] (Sales MIS), Sales [Voucher Wise], Day Wise Sales [MetalValue], Sales Profit[Metal], Sales Return Profit[Metal] |
| T-03 Stone M.I.S. + negatives | Done | Stone Wise Inventory, Stone Daily Touch Report, Stone in Sales Register, Stone Summery (Stone SKU Balance); negatives red + "Only negatives" |
| T-04 Production M.I.S. | Done | Stone Setting Analysis, Refining Analysis (zero guard, ratio on subtotal); Rejection / KM Register built, off until confirmed |
| T-05 Stock M.I.S. | Done | Ready Stock Inward List, Range Wise Closing / Approval Stock, Approval Out Counts, Labour in Sales Register (sold-twice flag), In-Approval Status + Goods Sold But Not Delivered (off until confirmed); TAG 0 refused |
| T-06 Repair traceability | Done (Q5 open) | Repair job keeps old Stock No, old piece out of stock, OLD / NEW stones (setting), new Stock No with old weights; WIP Repair Items, MFG TR [only Repair], MFG TR Stone [only Repair]; Item Search chain |
| T-07 Shipping + tracking | Done | Sale ▸ Dispatch / Tracking; Shiping Analysis, Shiping Pending |
| T-08 WhatsApp dispatch | Built, sandbox (Q12 / C-05) | Account WhatsApp No + consent; Tools ▸ Option ▸ Others ▸ WhatsApp; Resend; Tools ▸ WhatsApp Log |
| T-09 Checklist closing | **Blocked** - not started | Waits for the client's sheet (C-05, question 106) |
| T-10 Graphs not opening | Checked - all ours open | Question 105 asks which ones fail |
| T-11 Usage map + parallel run | Draft + tool | `usage-map-parallel-run.md`; M.I.S. Reports ▸ Parallel-run export |
| T-12 Quotation | Done (Q6, Q18 open) | Quotation ▸ Quotation (no ledger posting, Convert to Order, Status, Copy Selected Row, Client Chart, Print, Requirement Sheet, Catalog 2, Slide Show), Quotation ▸ Day Book |
| T-13 Migration checks | Done | Reports ▸ Data Quality + "Excel for the client"; `scripts/migration_checks.py` |
| T-14 Ledger Bal + M.R.P. | Ledger Bal done; M.R.P.(Stone) requirement view | Metal / mould M.R.P. and Purchase Order wait for the explanation |
| T-15 Meet transcripts | Checklist updated | `recording-checklist.md` (host action) |
| T-16 AI note | Done | `ai-features-note.md` |
| T-17 Agenda | Done | `next-session-agenda.md` |

## Complete change list (§3C)

| # | Status | Note |
|---|---|---|
| 1 | Done | Reports ▸ M.I.S. Reports lists all 34 in legacy order with status |
| 2 | Done | Default ranges: FY for sales / stock, month for refining / profit / repair, today for rejection, "as on" for daily touch / closing |
| 3, 4 | Done | Shared grid (5 Oct T-12): Auto Filter with counts, totals, row counter |
| 5, 6 | Done | Sales Analysis, Sales MIS |
| 7 | Done (Q3) | Sales Person field; "required" switch |
| 8 | Done | Data check I3 |
| 9 | Done | Stone Wise Inventory (Actual / Breakage; Loss sits in the Stone Loss Register) |
| 10 | Done | Block / warn / allow (Tools ▸ Option), now on Stone Issue on Job-Card too |
| 11 | Done (Q16) | FOT codes |
| 12 | Done | TAG 0 refused (repair-ticked line excepted) |
| 13, 14 | Done | Setting Analysis formulas, labour per issue line |
| 15 | Done | Stone Daily Touch |
| 16-20 | Done (Q5) | Repair chain |
| 21 | Done | Item Search chain |
| 22 | Built, off | Rejection Register |
| 23, 24 | Done | Refining loss %, zero guard |
| 25, 26 | Done | Sold Stone, Sold Labour |
| 27 | Done | Sold-twice flag + data check I7 |
| 28 | Built, off | KM Register (ghat / kundan columns wait) |
| 29, 30 | Done | Shipping Analysis; Tracking No on dispatch (and on Quotation) |
| 31 | Built, sandbox | WhatsApp |
| 32 | Done | Day Wise Sales sorted |
| 33 | Done | Approval Out Counts |
| 34 | Done (Q2) | Ranges from the Item master's M.I.S. bands |
| 35 | Done | Family "-" red + data check I4 |
| 36 | Built, off | Goods Sold But Not Delivered |
| 37 | Done | Sales Profit [Metal] |
| 38 | Done | Stone SKU Balance |
| 39 | Done | Data check I6 (junk / near-duplicate SSKUs) |
| 40 | Done | No report opens on an empty date |
| 41 | Done | Ledger Bal |
| 42 | Built, off | In-Approval Status |
| 43, 44, 45 | Done (Q6, Q18) | Quotation |
| 46 | Partly | M.R.P.(Stone) requirement; rest waits |
| 47 | Blocked | Checklist (C-05) |
| 48 | Checked | Our graphs open (Q10) |
| 49, 50 | Draft | Usage map, parallel-run plan + export |
| 51 | Done | Delete History & Purchase admin only, audited |
| 52 | Unchanged | Sale = 2 Oct T-04 |

## From the 12 Oct videos

| Seen | Status |
|---|---|
| Receipt F3: Return / Break / Loss pcs + cts per stone | Done |
| N-Wt = G-Wt − stones in piece × 0.2 | Done (when N-Wt is left blank) |
| Stones by weight only (pearls, sarafa) | Done |
| Issue St Wt from F3 | Done |
| Order Remark rewritten with stones used | Done (one-job orders; switch) |
| Unweighed CASTING issue / receive | Done |
| "Stock Negative ... continue?" on stone issue | Done (warn mode) |
| Order Shipping Details dialog | Done - Order list > Shipping Details: Despatch (with Tracking No), Order, Buyer's / Consignee details, Export; Fetch Dept / Fetch Last Dtls (question 117); on the order print. Tracking No also on the order form |
| Save -> "Print Order Sheet? Yes / No" | Done |
| "Do you want to merge jobs?" | Done on a multi-job issue (Show Pending): Yes keeps the jobs together, Unmerge, switch in Tools > Option - meaning to confirm (question 115) |

## Client (§8) - all open

C-01 data · C-02 negatives · C-03 WIP · C-04 formats · C-05 written requirements · C-06 rank M.I.S. · C-07 graphs.
