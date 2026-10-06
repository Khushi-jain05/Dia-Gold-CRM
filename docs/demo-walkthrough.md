# Demo walkthrough — the 28 September flow, end to end

This walkthrough covers every screen built for the 28 September meeting. For each step it says what to do and the figure you should see. It runs on a **separate demo database**, so nothing here touches the working data.

## Start

```bash
python -m diagold.demo            # first time: loads the demo data and opens the app
python -m diagold.demo --reset    # start the demo again from scratch
```

- Log in with **admin / admin**.
- The demo database is kept in `~/DiaGoldDemo`.
- The status bar at the bottom of the window shows which database is open. Check it says `DiaGoldDemo` before you start.

## What the demo data contains

| What | Figures |
|---|---|
| Rates, dated 25-09-2026 | 24K fine rate **14,713 / g**, so the metal rate for 14KT 590 is **8,680.67 / g**. Labour **1,200 / g** (STD, on net weight). Tag mark-up **50%**. |
| Inventory ▸ Metal | Purchase from SHRIKANT: 24KT Gold 300 g @ 15,598, 300 g @ 15,570 and 200 g @ 15,570, into Primary, total **₹1,24,64,400**. Also 200 g of 14KT 590 into RAJESH JI. |
| | Issue: 1.625 g of 14KT 590 from RAJESH JI to CHAND KUMAR HAZRA (fine **0.959**). |
| | Receipt: 1.000 g back from him, with 3.5% wastage (**0.035**). |
| Inventory ▸ Stone | Purchase: POLKI 12-14, 100 pcs / 8.000 ct @ 8,100, and EMERALD PEAR 3*4, 50 pcs / 5.000 ct @ 2,000, into Primary. |
| Order **9001** | KK JEWELS, Terms "30 days credit", 3 lines of NS-1430 in 14KT 590. These give three jobs: |
| Job **28854** (C-Ref DEMO-A) | Mapped on the Default route. Nothing done yet, so **Issue To CAD** is pending. |
| Job **28855** (DEMO-B) | CAD, Camming and Casting are done. It is **out with PRASENJIT at HandMade**: 14.800 g issued, Allow 3.5%. |
| Job **28856** (DEMO-C) | Every step on the route has been received. **Pending for MFG Transfer.** Stones: 10 Polki and 5 Emerald went to Setting; 2 Polki came back. |
| Job **28853** (BANG-577) | The legacy example from the meeting. Its loss rows, the ₹2,400 setting labour and the bag lines are copied from the client's screen. |

The job numbers above are for a fresh demo database. If you added jobs before loading the demo, the numbers move up, but the C-Refs stay the same.

---

## 1. Order and Job Card Bag

| # | Where | Do | You should see |
|---|---|---|---|
| 1.1 | Production Planning ▸ Order | Find order 9001 | Terms **30 days credit**, Priority **Normal** and Remark are all shown in the list. |
| 1.2 | Production Planning ▸ Job Card Bag | Job No **28856** | POLKI 12-14: Rcvd 10 / 0.800, Iss 10 / 0.800, Back 2 / 0.160, **Bal 2 / 0.160**, Setting **Polki**. EMERALD PEAR 3*4: Rcvd 5, Iss 5, **Bal 0**. The columns fill the width, with no blank strip on the right. |
| 1.3 | same | Job No **28853** | Every stone line balances to **0**. |
| 1.4 | same | Select a line and **Return to Stock** more pieces than the bag holds | The save is refused with a message. |

## 2. Manufacturing ▸ Issue (Issue To <Process>)

| # | Do | You should see |
|---|---|---|
| 2.1 | Process **CAD**, Account **Office**, then **Show Pending** | Only **28854** is listed. Tick it and press OK. |
| 2.2 | Look at the line | The title reads **Issue To CAD**. Size **7**, Mt Price **8,680.67**, L Price On **NetWt**, OrderNo 9001, Client KK JEWELS. The weights are not editable, because CAD is a design step. |
| 2.3 | Type a RefNo, then **Save** | You get the "Save? Yes / No" prompt. On Yes, the voucher number is shown and the grid clears. |
| 2.4 | **Show Pending** again | Nothing is pending for CAD any more. |
| 2.5 | **Print Voucher** | The voucher opens and can be printed. |
| 2.6 | **Day Book** | The Issue Day Book shows the new voucher under CAD. |

Try the hot-keys on any weight-bearing process. Select a line first, then:

- **F3**: stones from the job's bag, with setting type and rate.
- **F4**: Issue Finding.
- **F5**: metal from a location, booked to the karigar.
- **F7**: Issue MouldWt.

## 3. Manufacturing ▸ Received (Received From <Process>)

| # | Do | You should see |
|---|---|---|
| 3.1 | Process **HandMade**, Account **PRASENJIT** | Mt Bal next to the account shows PRASENJIT's metal balance. |
| 3.2 | **Show Pending** | **28855** is listed, with PRASENJIT, 14.800 g. Tick it and press OK. |
| 3.3 | Enter GrossWt **14.300** and NetWt **14.300** (the green cells), then **Save** | The voucher saves. |
| 3.4 | Production Planning ▸ Job History, job **28855** | On the HandMade row: Loss **0.500**, Loss % **3.38**. The allowance is 3.5% of 14.300 = **0.500**. The next pending step is **COLOUR**. |
| 3.5 | Double-click a pink (issue) cell, then a green (receive) cell | The issue voucher opens, then the receipt. |

## 4. Job History and setting labour

| # | Where | You should see |
|---|---|---|
| 4.1 | Job History, job **28856** | 11 rows, CAD through Puwai. Casting loss **0.300** (2.22%). HandMade **0.200** (1.52%, allowed 0.462 = 3.5% of the issued 13.200). PrePolish **0.100** (0.77%). Setting **0.050**. Final Polish **0.090**. final setting, Meena and Puwai **0.020** each. Total loss **0.800 g**. |
| 4.2 | same, Setting row | Labour **₹240**: 8 Polki set × ₹30. The 5 Emerald have no setting type, so they add ₹0. |
| 4.3 | Job History, job **28853** | Loss rows: HandMade 1.141, PrePolish 1.230, Setting −0.300, Final Polish 0.170, final setting 1.333. The final-setting Labour is **₹2,400**. |
| 4.4 | Manufacturing ▸ Reports ▸ Karigar ▸ Setting Labour Statement (September) | rakesh sarkar: **₹2,400** on 28853 plus **₹240** on 28856. |

## 5. MFG Ready Stock Transfer, tags and Item Search

| # | Do | You should see |
|---|---|---|
| 5.1 | Manufacturing ▸ Pending for MFG Transfer | **28856** is listed. Press **F10** on it to open its job bag. |
| 5.2 | Manufacturing ▸ MFG Transfer, then **Show Pending**, tick 28856 | One line. Location Primary, C-Ref DEMO-C, N-Wt **12.700**, Title 590, FineWt **7.493**, Loss% **6.30**. |
| 5.3 | Read across the line | Metal Rate **8,680.67**, Metal Amount **1,10,244.51**. Stone Amount **6,184.00**: Polki 0.640 ct × 8,100 = 5,184, plus Emerald 0.500 ct × 2,000 = 1,000. Labour 1,200 × 12.700 = **15,240.00**. Total **1,31,668.51**. Margin 50% = **65,834.26**. Price **1,97,502.77**. Tag **197**. |
| 5.4 | Double-click a grey cell (**Cost Break-up**) | The same figures, one component per row. |
| 5.5 | Tick **Repair (tag 0)**, then untick it | The tag goes to 0 and comes back. |
| 5.6 | **Print** / **Excel** | A PDF / a CSV of the grid. |
| 5.7 | **Save** (confirm Yes) | A Stock No is given and the **Tag List** opens. |
| 5.8 | In the Tag List, try each option | Print Tag Price, C-Ref Barcode, **Detail** (Polki / Colour-stone carats), Pcs Wise, Print Selected / All, Select Printer, Create Txt. TXT Import reads a text file of Stock Nos. |
| 5.9 | Sale ▸ Ready Stock | The piece is shown in Primary with cost 1,31,668.51, price 1,97,502.77 and tag 197. |
| 5.10 | **Item Search** (top right), type the Stock No or 28856 | The piece, its stones and a value summary by stone kind. |
| 5.11 | **Delete History & Purchase** | The piece leaves stock. Job 28856 is back in Pending for MFG Transfer, and the deletion is written to the audit log. Transfer it again to finish. |

## 6. Inventory and karigar ledgers

| # | Where | You should see |
|---|---|---|
| 6.1 | Inventory ▸ Metal ▸ Purchase | The SHRIKANT voucher totals **₹1,24,64,400** (800 g). **Print** makes a PDF. |
| 6.2 | Inventory ▸ Metal ▸ Issue Outside / Worker | 1.625 g of 14KT 590 to CHAND KUMAR HAZRA, fine **0.959**. |
| 6.3 | Inventory ▸ Metal ▸ Receipt | 1.000 g back, wastage 3.5% = **0.035**. |
| 6.4 | Inventory ▸ Metal ▸ Reports ▸ Metal Analysis | Primary 24KT Gold: inward **800.000**, closing 800.000. RAJESH JI 14KT 590: inward **201.000**, outward 1.625, closing **199.375**. Double-click a row to open that location's ledger. |
| 6.5 | Reports ▸ Inventory ▸ Worker Balance (Metal) | CHAND KUMAR HAZRA **0.590 g**. That is 1.625 − 1.000 − 0.035, from the Inventory vouchers only. |
| 6.6 | Manufacturing ▸ Reports ▸ Karigar ▸ Worker Metal Ledger | CHAND KUMAR HAZRA rows: MI 1.625, MR 1.000 (Alw 3.5%, 0.035), ISS 15.000, ISS 13.500, RTN 14.800 (loss 0.200), RTN 13.200 (loss 0.300). Closing **1.090 g / fine 0.643**. |
| 6.7 | Manufacturing ▸ Issue, Account CHAND KUMAR HAZRA | Mt Bal **1.090 g / fine 0.643**, matching the ledger. |
| 6.8 | Inventory ▸ Metal ▸ Issue Outside / Worker | Try to issue 500 g from RAJESH JI. With Tools ▸ Option ▸ negative stock on **warn** (the default), you are asked before it goes through. On **block**, it is refused. |
| 6.9 | Inventory ▸ Stone ▸ Purchase | POLKI 12-14 100 / 8.000, EMERALD PEAR 3*4 50 / 5.000. |

## 7. UI checks

- There is no sidebar. Every module is in the top menu bar, and Inventory ▸ Metal / Stone open as submenus.
- The Issue, Received, Job Card Bag and MFG Transfer grids fill the width. A grid with more columns than fit scrolls sideways.
- Every save asks "Save? Yes / No". This can be switched off in Tools ▸ Option.
- **Show Pending** appears on the Issue, Received, MFG Transfer, Job History, Job Card Bag, Stone Issue and Inv Return screens.

## 8. Edit, delete and the other voucher buttons

| # | Where | Do | You should see |
|---|---|---|---|
| 8.1 | Manufacturing ▸ Received, process HandMade | Receive 28855 (14.300), Save. Then **Edit**, pick that voucher, change NetWt to 14.200, Save | Job History 28855 shows the HandMade receipt at 14.200. |
| 8.2 | same | **Delete**, pick the voucher, Yes | 28855 is back in Show Pending for HandMade, with PRASENJIT. |
| 8.3 | Manufacturing ▸ Issue | Issue a job, then Delete the voucher of the step *before* it | Refused: "delete the later voucher first". |
| 8.4 | Manufacturing ▸ Received | **Attach Doc** before Save, add a file, then Save | Edit the voucher, Attach Doc: the file is listed and opens. |
| 8.5 | Manufacturing ▸ MFG Transfer | After 5.7, **Edit**, pick the transfer, set Margin % to 40, Save | Price **1,84,335.91**, tag **184**, same Stock No. |
| 8.6 | same | **Format-2** | A PDF: one block per piece with metal, each stone, labour, margin, price. |
| 8.7 | same | **Delete**, pick the transfer | The piece leaves stock; 28856 is back in Pending for MFG Transfer. |
| 8.8 | Inventory ▸ Metal ▸ Issue Outside / Worker | **Check Bal**, pick CHAND KUMAR HAZRA | Mt Bal 1.090 g / fine 0.643; 14KT 590 balance 0.590; RAJESH JI 199.375 in stock. |
| 8.9 | Inventory ▸ Stone ▸ Issue Outside / Worker, then Receipt | Issue 10 Polki to CHAND, receive 4 back, then **Show O/S** on Receipt | 6 pcs / 0.480 ct outstanding. Tick it, OK: a new receipt opens filled in. |
| 8.10 | anywhere | **F12** | More Reports: type "worker metal", Enter opens Worker Metal Ledger. |
| 8.11 | Reports ▸ Inventory ▸ Account Ledger | FY dates | Purchase A/c Dr **1,24,64,400** (MP 1); SHRIKANT Cr **1,24,64,400**. |

## Menu items marked "to be explained"

These are placeholders because the client has not yet said what they do (C-04):

- Manufacturing: Waxing, Repair Issue, Extra Issue, Job Costing, Stamping / Engraving List.
- Inventory ▸ Metal: Load Metal, Issue On Tree, Conversion, Adjustment, Worker Recovery, WIP Rtn, Bhav Cut.
- Inventory ▸ Stone: Load Stone, Extra Issue On Job Card, WIP Rtn.

Each one opens a note saying what is waiting on the client.
