# AI features - research note (9 Oct T-16)

Heard on 9 Oct (A9, probable): "AI parts integrate karna hai ... iski aapke
yahan pe research karna padegi". Nothing is to be built before it is agreed
with Rohit ji. Candidates, what each needs, and what to study at the factory:

| # | Feature | What it does | Data it needs (from the ERP) | Study at Dia Gold | Effort |
|---|---|---|---|---|---|
| 1 | Loss anomaly flags | Flags a karigar / process whose loss % is outside its usual range (Refining / Setting Analysis), daily | Issue / receive vouchers, allowances - already in the app | Which losses the owner chases today, and what counts as "too much" | Small - statistics, no outside service |
| 2 | Negative-balance and data-entry checks | Explains *why* a stone / metal balance went negative and which voucher did it | Stock ledger (already) | The legacy negatives (RAJAT JI etc.) during migration | Small |
| 3 | Report Q&A | Ask in Hindi / English: "is mahine MANNU BHAI ko kitna polki gaya?" and get the figure with the report behind it | M.I.S. report queries (already) | Which questions he asks staff today | Medium - needs an AI service, internet, and a privacy decision |
| 4 | Stone breakup from a photo | Suggest the stone lines (type / size / count) of a design from its CAD image or photo | CAD images (5d of the data request), SKU stone grids | Image naming and how accurate it must be to help | Large - research |
| 5 | Order / delivery prediction | Expected ship date per order line from past days-to-ship (Shiping Analysis) | Order and dispatch dates (now captured, T-07) | Lead times per item and karigar | Medium |
| 6 | WhatsApp assistant | Customers ask "mera maal kab aayega?" on WhatsApp and get the dispatch / tracking reply | Dispatch + WhatsApp (T-07 / T-08) | Whether customers would use it | Medium - after T-08 is live |

**Suggested first step:** 1 and 2 (no outside service, no customer data
leaves the PC). Decide 3-6 with Rohit ji after the parallel run.
