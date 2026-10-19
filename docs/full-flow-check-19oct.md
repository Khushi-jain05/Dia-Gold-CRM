# Full flow check — 19-10-2026  (FF-19OCT)

Database `~/Library/Application Support/DiaGoldCRM/diagold.sqlite3`  
Backup before the run `~/Library/Application Support/DiaGoldCRM/diagold.sqlite3.backup-20261019-164513-pre-full-flow`  
Result: **35 passed, 0 failed**

## A. Masters

- Daily Metal Rate 19-10-2026: 24K fine 14,713 / g on 14KT 590 and 24KT Gold
- Supplier **FULL FLOW SUPPLIER** (code FFSUP)
- Stone SKU **DIA RD MIX** (diamond, 13,500 / ct)
- KK JEWELS WhatsApp 98765 43210, opted in; Tools ▸ Option WhatsApp on (sandbox)
- 14KT 590 metal rate used: **8,680.67 / g**

## B. Inventory (Inventory ▸ Metal / Stone)

- Stone Purchase Vr **3** from FULL FLOW SUPPLIER: POLKI 12-14 40 pcs 3.200 ct @8,100 = 25,920 · DIA RD MIX 500 pcs 7.000 ct @13,500 = 94,500 · EMERALD PEAR 3*4 20 pcs 2.000 ct @2,000 = 4,000
- Metal Purchase Vr **4**: 14KT 590 100 g into Primary
- Metal Issue Outside / Worker Vr **2** to CHAND KUMAR HAZRA: saved at 5 g, then **edited to 4.000 g** — Primary went back up by 1 g (19 Oct item 5)
- Metal Receipt Vr **2** from CHAND: 3.800 g, wastage 2.5 % = 0.095

## C. Order ▸ Order

- Order **9002** KK JEWELS, Ref FF-19OCT, Terms 30 days, Tracking No TRK-FF-19OCT; Shipping Details: BlueDart → Jaipur, buyer/consignee from KK JEWELS
- Line 1 NS-1430 14KT 590 Y size 7 × 1 · Line 2 BANG-32 size 2.4 × 2
- On save: **no job** — the lines wait in Job Card ▸ Show Orders

## D. Production - Planning ▸ Job Card

- Job Card Vr **1** → jobs **28860** (NS-1430), **28861** and **28862** (BANG-32, 1 pc each)
- Edit Job# with any of them shows this voucher

## E. Job Mapping + Inventory ▸ Stone ▸ Issue On Job Card

- All three jobs mapped to **Default**: CAD CAM CS HM COL PP ST FP fs Meena Puwai
- Stone Issue on Job-Card Vr **11267** for job 28860: DIA RD MIX 120 / 1.800 ct, POLKI 12-14 12 / 0.960, EMERALD PEAR 3*4 6 / 0.600 — Job Card Bag 138 pcs / 3.360 ct

## F. Job History — job 28860 (F11)

- CAD issue Vr 5442 Office (no weight)
- CAD receive Vr 5443 Office (no weight)
- CAMMING issue Vr 5444 Office (no weight)
- CAMMING receive Vr 5445 Office (no weight)
- Casting issue Vr 5446 Office G 22.000 N 22.000
- Casting receive Vr 5447 Office (no weight)
- HandMade issue Vr 5448 CHAND KUMAR HAZRA G 22.000 N 22.000
- HandMade receive Vr 5449 CHAND KUMAR HAZRA G 21.500 N 21.500
- COLOUR issue Vr 5450 FACTORY G 21.500 N 21.500
- COLOUR receive Vr 5451 FACTORY G 21.500 N 21.500
- PrePolish issue Vr 5452 BUDDHA POL G 21.500 N 21.500
- PrePolish receive Vr 5453 BUDDHA POL G 21.200 N 21.200
- Setting issue Vr 5454 rakesh sarkar G 21.200 N 21.200
- Setting receive Vr 5455 rakesh sarkar G 21.800 N 21.163
- Final Polish issue Vr 5456 BUDDHA POL G 21.850 N 21.213
- Final Polish receive Vr 5457 BUDDHA POL G 21.840 N 21.203
- final setting issue Vr 5458 akshay j G 21.840 N 21.203
- final setting receive Vr 5459 akshay j G 21.830 N 21.193
- Meena issue Vr 5460 JAGDISH PRA G 21.830 N 21.193
- Meena receive Vr 5461 JAGDISH PRA G 21.820 N 21.183
- Puwai issue Vr 5462 JAGDISH PRA G 21.820 N 21.183
- Puwai receive Vr 5463 JAGDISH PRA G 21.810 N 21.173
- **Check:** CASTING row has an issue weight 22.000 and a blank receipt (item 1); HandMade 22.000 → 21.500 (loss 0.500 = 2.27 %); COLOUR issue 21.500 (item 2); Setting receipt Vr 5455 edited to G 21.850 (item 1 'edit')

## G. Jobs 2 + 3 (BANG-32)

- Every step on ONE voucher for both jobs; merged as **M5464** on the CAD issue
- HandMade 12.000 each, 0.050 loss per step after it

## H. Job Costing + Manufacturing ▸ MFG Transfer

- Job Costing job 28860: metal 183,795.83 + stones 31,777.50 + labour 25,407.60 = total 240,980.93
- MFG Transfer Vr **1** (margin 50 %): stock **1** (NS-1430, job 28860) G 21.810 N 21.173 total 240,980.93 price 361,471.40 TAG **361**; stock **2**, **3** (BANG-32)

## I. Reports ▸ Ready Closing Stock

- Stock 1: **DIA WT 1.785 · POL WT 0.800 · CS WT 0.600** (item 2); amounts on Ctrl+F1

## J. Sale ▸ Ready Stock

- Approval Vr **1** BANG-32 stock 2 to KK → Approval Return Vr **1** (back in stock)
- Sale Vr **1** to KK JEWELS: stock 1 (against order 9002 line 1) + stock 3; total 355,596.70
- Dispatched by Courier, tracking BD-FF-19OCT; WhatsApp to KK in Tools ▸ WhatsApp Log (status sandbox)
- Receipt Vr **1** from KK: cash 1,00,000

## K. Purchase ▸ Ready Items + Inventory ▸ Stock Transfer

- Ready Items Purchase Vr **1** from FULL FLOW SUPPLIER: BANG-32 G 25.000, stones 6.5 ct → **N-Wt 23.700** (item 3); stock 4
- Stock Transfer Vr **1** — Stock Melting of 4: piece out, 23.700 g 14KT 590 and the stones back into Primary (item 4: on screen, removing the piece removes all three panes' lines)

## L. Where to compare

- Order ▸ Order List / Status ▸ Ready: order 9002 = Ready
- Reports ▸ Ready Closing Stock: stock 2 (BANG-32) is the only one of this flow still in stock
- Account ▸ Ledger KK JEWELS: sale debit, receipt 1,00,000 credit
- Reports ▸ Karigar ▸ Worker Metal Ledger: CHAND — issue 4.000 (edited), receipt 3.800
- Accounts Dr = Cr and stock = movements were checked after the flow
