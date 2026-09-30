# Message for the shared group (T-10)

Ready to paste. It lists everything open "from server access to the last
item" across the three sessions, in the order it blocks work. The long form
with the reason behind each item is the Open Points page.

---

**Dia Gold CRM — open items (as of 29 Sept)**

Answer each with its code, one line is enough (e.g. `11 Sep C-01 — Job Mapping and Job History`).

**Answered 28 Sept on your screens — thank you, recorded**
- **M-2 (setting labour)** Both figures were right: **Diamond ₹3, Polki ₹30 per piece**, held on the Setting Type. On job 28853 (BANG-577) pieces set × rate gives exactly the ₹2,400 on your final-setting row — the new app now reproduces it.
- **Labour on net weight** — seen as "Price On: NetWt" on your transfer.
- **Tag price** — "Margin %" 50 on Mfg Ready Stock Transfer is cost × 1.5; the new price engine reproduces your Vr 1081 to the paisa (₹3,05,330.12).

**Answered 14 Sept — thank you, recorded**
- **M-5 (labour)** Labour = net weight × per-gram rate — your example 30 gm × ₹1,200 = ₹36,000. That is how the software already works; it is now confirmed, not assumed.
- **S-1** Stone cost and sale prices are typed in per stone and size by the office — there is no list to hand over. Nothing to import; the Stone SKU screen is the entry point.
- **M-5 (margin)** Tag price is just cost + 50%. The "20% less" is not part of the tag price — recorded that way; the discount field stays optional and off.

**Next sitting** — Rohit ji, you asked "when do we sit again?" and mentioned Monday. We propose **Monday 21 Sept, the usual slot**. Agenda: (1) live demo of the new app — v0.5.0, the whole Production-Planning part built "up to here" as you said, for your check; (2) the five points below; (3) the Word job-sheet format.

**Production → Manufacturing → Inventory (28 Sept) — needed next**
- **28 Sep C-01** The **Inventory session**: go through Inventory ▸ Metal and Inventory ▸ Stone voucher by voucher, and tell us which ones (and which columns) you need first. You said "job will be based on inventory" — this is what we build next.
- **28 Sep C-02 / Q1, Q5** Pricing: (a) is "Margin %" always cost + that %? (b) where does the **20%** you mentioned apply — a discount to the customer? (c) the exact rule that prints ₹3,05,330 as **"305"** on the tag; (d) repair jobs — tag price 0?
- **28 Sep C-03 / Q3** **Allowed loss %** — where does it come from: the process, the karigar or the job? And is the karigar charged for **all** loss or only what is **above** the allowance? (Your worker ledger credits the allowance, so we have set "only above" for now.)
- **28 Sep Q2** Labour on NSE-2495 was 1,200 × **12.752** g, but the piece's net weight is **12.700**. Which step's net weight does labour use?
- **28 Sep Q4** Setting labour: stones that come back **broken** — unpaid? (That is what gives ₹2,400.)
- **28 Sep Q6** **Negative stock** (Primary 24KT Gold −1,030 g in Metal Analysis) — should the new system block it, warn, or allow?
- **28 Sep Q7** "Pending For **QC** To Ready Transfer" — is QC a separate step? Who does it, what is recorded?
- **28 Sep Q8, C-04** One line each on: **Extra Issue**, Issue On Tree, Conversion, Adjustment, Worker Recovery, WIP Rtn, Bhav Cut [Lena]/[Dena], Waxing, Stamping/Engraving List.
- **28 Sep Q9** Our screens are separate pages (Job Card Bag, Job History …); yours are one page. Are separate pages fine?
- **28 Sep Q11** The metal rate 8,680.67 = 14,713 × 0.590. Is 14,713 that day's 24K rate from Daily Metal Rate, or a separate valuation rate? (Purchases on 23 Sept were at 15,570–15,598.)
- **28 Sep Q12** Does the **setting labour** paid to the karigar go into "Setting Amount" on the Mfg transfer? (It read 0.00 on Vr 1081.)
- **28 Sep Q13** Job 28853: the second final-setting row (akshay, Vr 5390 → 5410) shows **no loss** though net went 30.177 → 30.257, and the job total 3.574 leaves it out. Why is that row skipped?
- **28 Sep Q14** Can stones go **back to stock straight from the job bag** without first going to a karigar (extra stones received)? If never, we will block it.
- **28 Sep Q15** MFG Transfer **"Split Jobs"** tick: does it give each piece of a multi-piece job its own Stock No, or something else?
- **28 Sep Q16** MFG Transfer **"Old Wt"** and **"Tag%"**: what goes in these two columns? (Not built until we know.)
- **28 Sep Q17** We show **"Fine With Loss"** as FineWt × (1 + Loss%). Is that how the legacy screen works it out?
- **28 Sep Q18** Item Search **"Delete SKU also"**: does it remove the Product SKU master itself, or only this SKU's stock entry? (Not built - it deletes a master.)
- **28 Sep Q19** Tag List **"Diamond Tag"**: what is different on a diamond tag? ("Detail" is built to print the Dia / Polki / CS carats.)
- **28 Sep Q20** Issue voucher **"P.O."** button: what does it print or open?
- **28 Sep Q21** Stone Receipt **"Read Cert/Lot Here"**: what gets scanned there (certificate no., lot no.) and what should it fill in?
- **28 Sep Q22** Job History **"Other Wt"** on the receive side: which weight goes there?
- **28 Sep Q23** MFG Transfer **"Format-2"** print: please share one sample so ours matches (for now it prints each piece with its cost break-up).
- **28 Sep C-05** Exports now also of **transactions**: open job cards, job bags, worker metal balances, location balances, stock with stock numbers.

**Production Planning reports (18 Sept) — five one-line answers**
- **18 Sep C-01** Two definitions behind the analysis reports: (a) an **open job** — does it exclude cancelled ones, and does it end at the final receipt or at MFG transfer? (b) a job's **current process** — the last step issued and not received, or the next step not yet started? (c) **PROD DUE** — the order's delivery date, or a separate production date?
- **18 Sep C-02** **Fractional splitting** — job 27684 went to setting as 0.3 / 0.3 / 0.4 pieces to three karigars. When is a job split, who decides, how are part weights set, can parts merge back, and what happens when Pcs > 1?
- **18 Sep C-03** **Opening stone balances** per location × Diamond / Polki / Colour Stone (pcs, ct, value) for FY 2026-27 — or a stock-take date to establish them. This is what makes the negative closings go away; the screen to load them is ready.
- **18 Sep C-04** The **Google Sheet** you track late deliveries in — its columns tell us what Job Analysis must replace.
- **18 Sep C-05** Shop-floor PC is Windows 7 with an old Chrome — upgrade, or must we support it? Also Excel exports of the reports you showed, so we can match them exactly.
- **18 Sep Q5** **Breakage** — where do broken stones go and how are they valued? · **Q7** job 27751 Setting: 16.480 g out, 4.040 g back — entry error or partial receipt? · **Q8** Job Stock Analysis "STOCK DT" — final receipt, MFG transfer or tagging?

**Production Planning (11 Sept) — still needed**
- **11 Sep C-01** Which **two** Production-Planning items are actually used? (WIP Job Card / Job Card / Job Mapping / In-House / Job Card Bag / Job History / Printing Options / Inv Return / Day Book / Reports) — after checking downstairs.
- **11 Sep C-02** The **Word job-sheet format** + one filled example — we generate it from the system so no one re-types it.
- **11 Sep C-03** The **three pending sub-items** at the bottom of Production Planning — which three?
- **11 Sep C-04** A date for the **factory session** (casting, weights, loss, scrap, rejects) with the people who run those steps.
- **11 Sep C-05** Ten minutes at the start of the next call to **re-cover Order, Stone Issue, Order Day Book and M.R.P.** — our recording lost that part (our fault, not yours).
- **11 Sep C-06** Exports of orders **1224, 1338, 1339** and jobs **28350, 28590, 28622–28624** with vouchers — the exact records you showed, so we can prove the screens against them.
- **11 Sep Q5–Q9** Is **In-House** used? · Which step first carries **metal weight** — casting or handmade? · What does the bag's **Back** column mean? · Is **Priority** on an order used, and how?

**Master (3 Sept) — still open**
- **M-1** Access to `SERVER2\ERP → Diagold26`, or exports of Metals / Locations / Items / Stones / Accounts.
- **M-3** Sign-off on the nine stone masters.
- **M-4** Staff list + which screens each person may open.
- **M-5** Confirm the default process order — we have loaded the 11-step route from the 11 Sept screen.
- **M-6** The daily slot time.

**SKU (8 Sept) — still open**
- **S-2** Stone SKU: one record per stone with sizes beneath it, or one per size? (Decides how the office types prices in — S-1.)
- **S-3** Cost Price vs Sale Price — on ER-1337 Polki sale (7,800) is below cost (12,900).
- **S-4** MasterSKU / SKU Ref / HU Id, Tag Price 6,200, MC% / LC%, 217% Manual Price, Brk Wt%, Create Variance, the "Multi…" button — one line each on what they do.
- **S-5** Where the design and CAD images live (folder + naming).

**Dates** — none have been agreed in three sessions. Even a rough month for go-live helps us order the work.

Full list with reasons: *(paste the Open Points link)*
