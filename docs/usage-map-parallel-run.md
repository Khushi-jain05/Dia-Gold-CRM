# Usage map and parallel-run plan (9 Oct T-11)

Pradeep's proposal on 9 Oct (A7, A8): list **every place the ERP will be used**
("let's say 10 jagah") and put it in use at all of them, then **run in parallel
with the legacy DIAGOLD daily for the first 10-15 days** and catch the bugs.
This is the draft to agree with Rohit ji. Names in *italics* are what we saw on
his screens - he confirms or corrects each row.

## 1. Usage map - where the ERP is used

| # | Place / desk | Person (to confirm) | Device | Screens used daily | Vouchers per day (estimate - client to fill) |
|---|---|---|---|---|---|
| 1 | Order desk | *Rohit ji / office* | Office PC | Order, Quotation, Job Card, Job Mapping, Printing Options (job sheet) | |
| 2 | CAD / CAM | *Office* | Office PC | Job History (CAD / CAMMING issue-receive), Job Card Bag | |
| 3 | Casting | *Office / FACTORY* | Office PC | Issue / Received (CASTING), Metal ▸ Issue Outside / Worker (F5 metal) | |
| 4 | Handmade / Ghat | *HandMade karigars - 98 on the worker sheet* | Floor PC or office | Issue / Received (HandMade, Repair HM), Worker Metal Ledger | |
| 5 | Stone room | *Admin* | Office PC | Stone ▸ Issue On Job-Card, Inv Return - Stone, Job Card Bag, Stone Daily Touch | |
| 6 | Setting | *akshay ji office, setters (ABHIJEET DAS ...)* | Floor PC | Issue / Received with F3 stones (Return / Break / Loss), Stone Setting Analysis | |
| 7 | Polish / Colour / Meena / Puwai | *FACTORY, KAILASH MEENAKAR, JAGDISH PRASAD SONI* | Floor PC | Issue / Received, F5 metal (wire) | |
| 8 | Office stock / ready stock | *Office* | Office PC | MFG Transfer, Tag List / Tag Print, Item Search, Ready Stock, Stock Transfer | |
| 9 | Sales / approval | *Rohit ji, sales* | Office PC / laptop | Sale, Approval, Sale Return, Approval Return, Dispatch / Tracking (WhatsApp), Excel Invoice | |
| 10 | Accounts | *Accounts staff* | Office PC | Receipt / Payment / Journal / Contra, Ledger, Outstandings, Trial Balance, Ledger Bal | |
| 11 | Owner / MIS | *Rohit ji* | Laptop | M.I.S. Reports, Sales / Business Dashboard, Refining Analysis, Stone SKU Balance | |
| 12 | Purchase | *Office* | Office PC | Purchase ▸ Metal / Stones / Ready Items, Opening Stock | |

For each row the client confirms: the person's login (Master ▸ User Right), the
device (Windows build v0.10.x installed), and the screens that person may open.

## 2. Parallel run - 10 to 15 working days

**Before day 1**
- Masters loaded from the legacy export / database (C-01); opening balances on
  the cut-over date - fresh, or after the clean-up in "Excel for the client"
  (Reports ▸ Other ▸ Data Quality, C-02).
- Work in progress loaded (C-03: open jobs, job bags, karigar balances, ready
  stock, approvals, pending bills).
- Every user trained on their rows of the usage map (30 min each).

**Every day**
1. Each desk enters the day's vouchers in **both** systems.
2. At the end of the day, Reports ▸ M.I.S. Reports ▸ **Parallel-run export**
   for that day (one Excel: Sales Analysis, Stone Daily Touch, Metal Summary,
   Refining Analysis).
3. Put it beside the same four legacy reports for the day. Any difference goes
   on the bug log below, with a screenshot of both.
4. Next morning: we fix, the build is updated, the row is closed.

**Bug log** (shared sheet)

| # | Date | Desk | Screen | What differs / fails | Legacy value | New value | Owner | Fixed in build | Closed |
|---|---|---|---|---|---|---|---|---|---|

**Exit** - legacy is switched off when 3 days in a row show no difference on
the four reports and no open bug of severity "wrong number".

## 3. What we need from the client to start

C-01 data, C-02 decision on negatives, C-03 WIP on the cut-over date, the
usage map above filled in, and a start date (Q14 / question 108).
