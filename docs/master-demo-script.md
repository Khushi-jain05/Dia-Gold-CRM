# Master module — demo script

A **progress** demo, not the final sign-off demo. Nine of the eighteen master
tasks were blocked or are not code; everything buildable is built. Frame it as
a check-in so the client does not expect the whole module to be closed.

Log in as `admin` / `admin`.

---

## 1. Metal — the client's real data

**Master ▸ Metal**, search `14KT CASTING`.

Eight heads appear at different finenesses — 59.50, 59.80, 590, 60.40, 60.90, 61.

> All 26 metal heads from your system are loaded. Heads of the same karat are
> kept separate, because each casting batch has its own fineness.

Point at the **Code** column: staff filter by it, so it is shown beside the name.

## 2. Metal ratio validation — this runs live

`14KT CASTING 590` ▸ **Edit**. The **Mining Metal Ratio** grid shows
`GOLD 59.000 / ALLOY 41.000` and a running `✓ Total 100.000 / 100.00`.

Change ALLOY to **40.99** and press **Save** — the record is refused with a
message saying exactly how much to adjust by. Put it back to 41 and it saves.

> Purity recorded here drives every downstream calculation, so a ratio that
> does not total 100 cannot reach the database.

## 3. Location — corrected on the call

**Master ▸ Location** — 17 entries typed as Karigar / Department / Branch / Logical.

> These are not clients. This is where material physically sits — with a
> karigar, in a process area, at an office.

Open `GAURANG JI` and show the **Material Types Held** grid.

## 4. Manufacturing Process — loss per step

**Master ▸ Manufacturing**. The **Loss Type** column differs by row: CASTING is
`G` (GrossWt), Setting is `S` (ST PCS), HandMade is `H` (Hourly).

> Loss is computed on each step's own basis, never one global rule.

## 5. User Rights — the strongest live demo

**Master ▸ User Right**, three tabs.

1. **Users** — create `CST1`, role Staff, with a password.
2. **Rights Matrix** — select `CST1`; everything is unticked. Tick **Display**
   on **Metal** only, then **Save Rights**.
3. Log out, log in as `CST1`: Metal opens, but **+ New / Edit / Delete are
   disabled**, and no other master is reachable.

> Rights are per user, per master, per action. What is not granted is not
> available — and the check is enforced below the screen, not by hiding buttons.

Back as admin, show **Copy rights from…** and **Export**.

## 6. Daily Metal Rate

Enter today's date, a metal and a rate.

> The rate is recorded per metal per day and past days are never overwritten,
> so a valuation for an old date reproduces exactly.

---

## Do not claim

The costing, per-process loss and stock revaluation **engines** are written and
tested, but they have **no screen yet** — those arrive with Quotation,
Manufacturing and Inventory.

Say: *"purity drives costing and that calculation is in place."*
Do not offer to show a calculated price on screen — there is nowhere to show it.

## Close with

> Master is roughly three-quarters built. Stone structure and the real data
> import are waiting on you; once those land we will finish the module and
> give you the full demo.
