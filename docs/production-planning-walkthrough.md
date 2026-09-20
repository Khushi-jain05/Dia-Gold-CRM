# Production Planning — layout walkthrough for Rohit (T-08)

The commitment on the 11 September call: *"show us the layout once, we'll
design it, then ask once more, and note it down for you."* These screens are
that layout. Walk them in this order, on the sample data that reproduces what
Rohit demonstrated (order 1224 / job 28350, order 1338 / jobs 28622–28624).
Note every correction in the group afterwards, in writing.

Log in as `admin` / `admin`. Press **F11** at any time — Job History opens.

---

## 1. Order → jobs  (Production Planning ▸ Order)

Open order **1338** (KK JEWELS, 11-Sep). Three lines — NS-1430, NS-2171,
NS-1930 — and each line already has a job: 28622, 28623, 28624.

> Saving an order allots one job number per line, from one running sequence.
> Your live numbers migrate as they are — nothing is renumbered.

Press **+ New**, pick a customer, add two SKU lines (the SKU fills description,
metal and weights), **Save**. Two more jobs appear in the pending queue.

**Ask Rohit:** the field rules we could not hear on the recording — what the
Requirement Sheet is used for, when an order is "for stock", what Priority
means (Q4, Q9).

## 2. Pending queue and route  (Production Planning ▸ Job Mapping)

Top: **Pending Jobs For Definition** — a list, not a pop-up, because it is
where the day starts. Select job **28622**.

Below: the order's jobs on the left, the route on the right. Process Group
**Default** ▸ **Apply Group** — the eleven steps appear with a due date each
(CAD → CAMMING → CASTING → HandMade → COLOUR → PrePolish → Setting → Final
Polish → final setting → Meena → Puwai). **Save Route**, then **Copy To All** —
28623 and 28624 get the same route.

> The Default group is the "Set Default Process" from the Master module — the
> answer to the question left open on 3 September.

Insert a step: **Add Step**, choose *Repair HM*, drag nothing — just Save. A
repair can be added to any job's route without touching the group.

## 3. Job History  (F11)

Type **28350** in the Job No box. The header card shows client RUBY SINGH,
order 1224 dt 05-Sep, 14KT CASTING 590 Y-, 1 pc, route
`HM RHM PP ST FP fs Meena Puwai`.

The grid is the one Rohit read out: issue columns pink on the left, receive
columns green on the right. Point at the **PrePolish** row — 28.981 g out to
BUDDHA POL, 27.800 g back, **Loss 1.181**.

> Loss is never typed. It is issued net − received net − scrap − dust, per step.
> CAD carries no weight, so it shows no loss.

Press **+ Issue** on *Setting* to a worker, then **+ Receive** without a weight
— the screen refuses: *"This step carries metal — enter the gross and net
weight received back."* Try leaving Worker blank — refused too.

Below: stones on the job, and the summary line (PND, WIP, Rejection, MFG
Transfer, TOTAL PCS, Order Remark). **WIP Costing** shows what is out with
workers at today's rate — a straight view until the factory session decides
the rule.

**Ask Rohit:** *"weight should go at casting"* vs live data starting at
HandMade (Q6) — the flag is per process, not fixed. Scrap / dust / rejects (Q8).

## 4. Job Card Bag  (button from Job History, or the menu)

Same job. Five lines — daank 27 / 4.530, POLKI 14-16 6 / 0.680, 20-22 8 /
1.160, 26-28 6 / 1.190, 28-30 7 / 1.500 — Bal equals Rcvd because nothing has
been issued yet. Colour cues as on the old screen: Iss yellow, Break pink, Lost
red, Bal green.

Select POLKI 14-16 ▸ **Return to Stock** ▸ 2 pcs (weight fills itself at
0.227) ▸ Save. Bal drops to **4 / 0.453** and Primary stock goes up by the
same. Try to issue 10 — refused, the bag holds 4.

The two reports Rohit asked for: **Stones in Job Cards** (every open job) and
**Bag Balance Report** (this job with totals). Both export and print.

**Ask Rohit:** what the **Back** column means (Q7); whether Extra is entered
or derived.

## 5. Stone Issue on Job-Card and Return to Inventory

**Stone Issue**: Vr No auto, Job, lines with Location / SSKU / Size / Pcs /
Weight. Issue EMERALD PEAR 6*4 from Primary to job 28624 — Primary stock goes
down, the job's bag shows it as Received. Issue 999 — refused: *Primary holds
only 96 pcs*. **Opening** ticked means the stones were already with the job
(no location reduced) — an assumption to confirm.

**Inv Return**: one screen, four variants (stone / metal / mould / finding).
Return 2 pieces from the bag to Primary — bag down, stock up. Posted vouchers
open as **View**, never Edit.

**Ask Rohit:** the whole narration of these two screens was lost (C-05). Ten
minutes at the start of the next call.

## 6. Printing Options

Order No / Job No, the six prints each with a template selector — Job Sheet,
Job Request, Stone Requirements, Finding Requirements, Blank Process Sheet
Back, Blank Process Sheet. **Print** writes PDFs and logs who printed what.

Open the Job Sheet for 28350: header, photo slot, route with sign columns,
stone requirements. It carries a red **PLACEHOLDER** banner on purpose.

> The layout is data, not code. Send us the Word format and one filled example
> (C-02); we reproduce it field for field by editing the template.

**Templates…** opens the template list — anyone can adjust a layout later.

## 7. Menu scope  (Tools ▸ Option)

Every Production-Planning item is a checkbox. Today the demonstrated ones are
on; WIP Job Card, Job Card, In-House, Day Book and Reports are off.

> When you tell us which two are actually used, we untick the rest here —
> no code change.

**Ask Rohit:** the two items (C-01), the three pending sub-items (C-03),
whether In-House is used (Q5).

## 8. Rtn To Inv – Stone  (18 Sept)

Job **28624**. **Show Pending** lists what the bag still holds. Enter 2 on
EMERALD PEAR 6*4 — the weight follows at the bag's average — **Save**.
Primary stock is up by 2, the bag down by 2. Change Type to **Breakage** and
return 1 more: the bag goes down, stock does not.

> Only stone comes back here — metal on the Manufacturing side, mould and
> findings never (as you said). Those classes are behind a switch, off.

**Ask Rohit:** breakage — where does it go, how is it valued (Q5).

## 9. Reports  (Production Planning ▸ Reports)

Every report has the same toolbar as the old one — Print, Search, Set
Column, Options, Group, Adv. Filter, Export, Auto Filter — plus a Total row
and a row count. None of them freeze: the query runs in the background with
a progress bar and Cancel.

- **Job Analysis** — 25006 BANG-32 at the top, 170 days overdue as of the
  From date; a column per day. Tick *Late deliveries only*: 27751 shows 21
  days late. **Ask:** does this replace the Google Sheet? (C-04)
- **Process Analysis** — grouped by the job's current step. Tick **fs** in
  the Show bar: only final setting, with its sub-total. No scrolling.
  **Ask:** the two definitions (C-01).
- **Job Card Analysis – Stone** — Primary × Polki / Colour Stone with
  OPENING · INWARD · OUTWARD · CLOSING. A negative closing is red; double-
  click a line for the vouchers behind it. **Ask:** opening balances per
  location × group (C-03) — the Opening Stone Balances screen loads them.
- **Job Stock Analysis** — 27751: ordered 18 Aug, in stock 8 Sep, 21 days;
  average and median in the footer.
- **Inv Rtn O/s Stone**, **Job O/s – Stone**, the three **day books**,
  **Inv O/S (Job O/s %)** last, and **Data Quality** — the migration checks.

---

## What is deliberately not built

- Fractional job parts (0.3 / 0.3 / 0.4 to three setters) — a schema change
  that waits for the client's rules (18 Sept C-02 / T-09).
- The data-quality checks run on this database; they run on the legacy
  server once access arrives (S1 C-01).

- MFG Transfer counts show 0 — the Manufacturing module is a later phase.
- WIP costing has no rule yet; it multiplies net weight by today's rate.
- Barcode / lot scanning records the code but does not fill lines — the label
  format is needed.
- Findings are retired (Session 1), so the Finding Requirements print is
  empty until findings come back into scope.
