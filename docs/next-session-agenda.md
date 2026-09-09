# Next session — SKU and Quotation walkthrough

Prepared for the follow-up to the 3 September 2026 Master-module review.
The client closed that call by moving the agenda on: *"SKU pe aate hain,
quotation pe aate hain."* Reports were flagged as a later topic.

---

## 1. Open items to close first (15 min)

These block work that is already written and waiting. Each one has code
sitting behind it that cannot be finished until the answer lands.

| # | Ask | Why it blocks us |
|---|---|---|
| **C-01** | Access to `SERVER2\ERP` → `Diagold26`, or CSV exports of the master tables | Metal codes and several purities are placeholders. Importers are written and tested against sample exports — they need the real files. |
| **Q7 / C-02** | The Setting Labour Chart: is the per-piece rate **₹3 or ₹30**? | A tenfold difference in karigar payouts. Nothing is assumed anywhere in the code. |
| **Q1 / C-03** | Stone reference data: confirm the nine granular masters | Built to the granular model the client demonstrated. Sign-off needed before it is treated as final. |
| **Q5** | Labour calculates on **net weight** — confirm | The basis is stored explicitly and is switchable, but the default needs confirming. |
| **Q6** | Margin: cost +50%, then 20% less to the customer | Both steps are separate editable parameters. Confirm whether the 20% is a discount off tag price. |
| **Q13** | The default process sequence | The Set Default Process screen is built and empty. |
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
