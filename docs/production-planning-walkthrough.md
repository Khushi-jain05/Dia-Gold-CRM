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

---

## What is deliberately not built

- MFG Transfer counts show 0 — the Manufacturing module is a later phase.
- WIP costing has no rule yet; it multiplies net weight by today's rate.
- Barcode / lot scanning records the code but does not fill lines — the label
  format is needed.
- Findings are retired (Session 1), so the Finding Requirements print is
  empty until findings come back into scope.
