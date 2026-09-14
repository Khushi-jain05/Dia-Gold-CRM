# Next session — agenda (T-12)

Prepared after the 11 September Production-Planning walkthrough. Order of
business, as agreed on that call: the pending Production-Planning items, the
re-cover of the screens whose audio was lost, the Word job-sheet format, then
the Session 1 backlog.

## 0. Production Planning first (25 min)

1. **C-01 / C-03** — Rohit names the two items in use and the three pending
   sub-items. We untick the rest in Tools ▸ Option on the call.
2. **C-05 re-cover (10 min)** — Order entry rules (fields, Requirement Sheet,
   Quotation link, stock orders), Stone Issue on Job-Card, Order Day Book
   usage, whether anything in M.R.P. is used.
3. **C-02** — walk the Word job-sheet format and a filled example; agree which
   fields map to which placeholders.
4. **Layout review (T-08)** — Job Mapping, Job History, Job Card Bag, Printing
   Options as built; see `production-planning-walkthrough.md`. Corrections
   noted in writing.
5. **C-04** — fix a date for the factory session; question list in
   `factory-session-questions.md`.
6. Q5 In-House used? · Q6 first weight-bearing step · Q7 "Back" column ·
   Q8 scrap/dust/rejects · Q9 Priority · Q10 pre-production quotation ever?

Recording: speakers set to MacBook before joining (`recording-checklist.md`).

---

## 1. Open items to close first (15 min)

These block work that is already written and waiting. Each one has code
sitting behind it that cannot be finished until the answer lands.

Closed on 14 Sept, off this list: **Q5** labour on net weight × per-gram rate
(30 gm × ₹1,200 = ₹36,000); **Q6** tag price is just cost + 50%, the 20% is not
part of it; **S-1** the stone price list — the office types cost and sale per
stone and size; there is no list to import.

| # | Ask | Why it blocks us |
|---|---|---|
| **C-01** | Access to `SERVER2\ERP` → `Diagold26`, or CSV exports of the master tables | Metal codes and several purities are placeholders. Importers are written and tested against sample exports — they need the real files. |
| **Q7 / C-02** | The Setting Labour Chart: is the per-piece rate **₹3 or ₹30**? | A tenfold difference in karigar payouts. Nothing is assumed anywhere in the code. |
| **Q1 / C-03** | Stone reference data: confirm the nine granular masters | Built to the granular model the client demonstrated. Sign-off needed before it is treated as final. |
| **Q13** | The default process sequence | Answered on 11 Sept by the Job Mapping screen: the eleven-step Default group is loaded. Confirm. |
| **Q9** | Daily Labour Rates — same behaviour as Daily Metal Rate? | Built mirroring metal rates on that assumption. |
| **Q3 / C-04** | Staff list with roles, and which masters each may see | The rights screen is ready; only the data is missing. |
| **Q2** | Is Item Size in scope? | The client said they could record it but do not today. |
| **Q4** | Is setting behaviour identical across all setting types? | Affects whether the setting rate varies by type. |
| **Q10** | Making Charge values and HSN codes — needed at go-live? | Every SKU row currently shows 0.00 and a blank HSN. |
| **Q11** | Parts / Mould — the screen was moved through quickly | Field detail was read off the screen, not narrated. Worth a proper walkthrough. |
| **Q12** | Are there any delivery dates at all? | No deadline was mentioned in the entire meeting. |
| **C-06** | The fixed daily slot time | A time was proposed but is not recoverable from the recording. |

---

## 2. Master module — progress demo (10 min)

Show what is working, not a finished-module claim. See
[`master-demo-script.md`](master-demo-script.md).

---

## 3. SKU walkthrough (20 min)

Questions to put to the client, screen by screen:

**Structure**
- How is a SKU code built? Is it generated or typed?
- Does one SKU carry many metal / stone variants, or is each variant its own SKU?
- What is the relationship between a SKU, a mould, and a design?

**Weights and stones**
- Which weights are entered by hand and which are derived?
- How are stones attached — by packet, by size, or by count?
- Where does the wax weight from the mould feed in?

**Costing**
- At what point does a SKU acquire a cost — at creation, or per quotation?
- Which of metal / labour / setting / stone are fixed on the SKU and which vary per order?

**Copying**
- The legacy rights list has an "Allow SKU Copy" flag. When is a SKU copied, and what carries over?

---

## 4. Quotation walkthrough (20 min)

- What does a quotation start from — a SKU, a mould, or a blank line?
- Which rate applies: the day's metal rate, or one fixed at quotation time?
- How does the margin set attach — per customer, per quotation, or globally?
- Is there an approval step before a quotation becomes an order?
- What must the printed quotation show?
- Client-wise pricing: the Tools menu has Client Wise Stone / Labour / Setting Price. Are these in use?

---

## 5. Agree next steps (5 min)

- Confirm the daily slot time and that the shared group is live
- Agree what "done" means for SKU and Quotation before building starts
