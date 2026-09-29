# Next session — Inventory walkthrough (28 Sept T-12)

Rohit closed the 28 Sept call with *"which inventory columns are needed
first — we'll target those first"* (52:15), and said the job will be based on
inventory. So this session is Inventory, voucher by voucher, on his legacy
screens. Send this agenda and the question list (group message, "28 Sept"
block) to the group before the call. Record it (`recording-checklist.md`) —
the 28 Sept audio lost 09:30–14:00, 22:30–24:30, 36:30–41:00 and 45:50–48:30,
so ask him to repeat anything said while a screen was loading.

Goal at the end of the call: a **ranked list** of the Metal and Stone
vouchers and, for each, the columns that must exist in the first build (C-01).

## 1. Five-minute demo of what 28 Sept already gave us (this build)

On job **28853 / BANG-577** (seeded exactly as his Job History showed it):

1. **Job History** — Loss and Loss % beside the worker: HandMade 1.141 /
   3.50 (read as the allowance, issued unweighed), PrePolish 1.230 / 3.77,
   Setting −0.300 / −0.96, Final Polish 0.170 / 0.54, final setting 1.333 /
   4.23. Receive side now has **Alw L %** and **Labour**.
2. **Setting Labour** button — ₹2,400 on the final-setting row: Polki
   4 + 38 pcs × ₹30, Diam 72 + 308 × ₹3. Ask **Q4** (broken unpaid?) here.
3. **Job Card Bag** — every line balances to 0; the new **Setting** column.
4. **Reports ▸ Karigar ▸ Worker Metal Ledger** — inward / outward / loss /
   allowance / running balance in weight and fine. Ask **Q3** here.
5. **MFG Price** button — the Fill Prices break-up. Ask **Q1, Q2, Q5, Q11,
   Q12** with his Vr 1081 figures beside it.
6. Ask **Q13**: why the akshay final-setting row (Vr 5410) has no loss.

## 2. Inventory ▸ Metal (25 min)

For each item: open it, one real voucher, then ask *what is it for, who
enters it, how often, which columns matter, what does it post to.*

| Voucher | What we saw on 28 Sept | Ask |
|---|---|---|
| Purchase | Vr 185, SHRIKANT, 24KT 800 g = ₹1,24,64,400 | Salesperson / Place of Supply used? Always 24KT? |
| Load Metal | not opened | What is it? |
| Issue Outside / Worker | Vr 3969, RAJESH JI → CHAND KUMAR HAZRA 1.625 g | Opening / Touch-X-Ray / Create O/S flags; "Check Bal" |
| **Issue On Tree** | not opened | Casting tree — how is metal split to jobs? |
| Receipt | Vr 1083, TUHIN BHANDARI 132.902 g, Wastage % | Recovery Vr vs Recovery Adj. Vr |
| Issue On Job Card | not opened | Same as issue with a job no? |
| **Conversion** | "24KT given, 14KT / 18KT deposited" | Alloying — how are the ratios entered? |
| **Adjustment** | not opened | When, and who approves? |
| DayBook, Reports | — | Which reports are daily? |
| **Worker Recovery** | not opened | Recovering loss beyond allowance? (links to Q3) |
| **WIP Rtn** | not opened | Metal back from WIP to stock? |
| **Bhav Cut [Lena] / [Dena]** | not opened | Rate fixing with suppliers / customers? |

Also: **Metal Analysis** (negative closings — **Q6**: block, warn or allow?)
and **Worker Ledger** (CHAND KUMAR HAZRA — the one row at 6.0% allowed loss:
why different?).

## 3. Inventory ▸ Stone (20 min)

Purchase, Load Stone, Issue Outside / Worker, Receipt (Vr 113, "Read
Cert/Lot Here", Show O/S), Issue On Job Card (Vr 13277 on job 28985),
**Extra Issue On Job Card** (**Q8** — asked at 36:25, answer lost), WIP Rtn,
Day Book, Reports. Ask **Q14**: can stones go back to stock from the job bag
without first going to a karigar?

## 4. The rest of the Inventory menu (10 min)

Parts / Mould, Physical Stock, Stock Transfer, Ready Item Receipt — one line
each: used or not.

## 5. Manufacturing leftovers (10 min)

- **Q7** — "Pending For Qc To Ready Transfer": is QC a step, who does it?
- Waxing, Repair Issue, Extra Issue, Stamping / Engraving List — used?
- **Q9** — separate pages vs one page.
- **C-05** — exports: open job cards, job bags, worker metal balances,
  location balances, stock with stock numbers.

## 6. Close (5 min)

Read back the ranked voucher list. Agree the next date. Ask again for any
date or milestone — none has been agreed in four sessions.

---

### Draft inventory model to show (T-01, for discussion — not built)

Built only after this session answers C-01, so it can be corrected on the
call rather than in code:

- **Location** (master, exists) — Primary, RAJESH JI, REPAIR RECEIPT …
- **Account** (master, exists) — supplier, karigar, client.
- **Metal** (master, exists) — title / purity; base GOLD or ALLOY.
- **Movement** (one row per voucher line): date, voucher type + no,
  location from / to, account, metal or stone SKU + size, pcs, weight,
  fine weight (stored at posting, never recomputed), carats, value.
- **Balances** — location and worker, always the running sum of movements,
  with drill-down to the voucher. The stone side already works this way
  (`StockMovement`, Job Card Analysis – Stone).
- **Negative balances** — a setting: block / warn / allow (default warn
  until Q6 is answered).
