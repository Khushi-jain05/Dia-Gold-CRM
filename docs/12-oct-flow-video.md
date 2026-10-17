# One job, start to finish — legacy walkthrough of 12 Oct 2026

Source: three WhatsApp screen recordings of 12 Oct 2026, 18:14–18:31 (no audio;
read frame by frame). Legacy DIAGOLD 1.1.7778, DB Diagold26, user Admin.
One stock order is taken all the way to ready stock and Item Search, so every
figure below is a real, linked example for acceptance testing.

## The piece

Order **1680**, 12-10-2026, Account **stock**, SKU **NS-1430** (bridal necklace),
14KT 590 Y, 1 pc → Job **29456** → Stock No **45127**, TAG **1218**.

## Step by step

| # | Screen | What was entered / shown |
|---|--------|--------------------------|
| 1 | Order 1680 | Account stock; line NS-1430. Metal first came as "14KT Gold 600" and was changed to **14KT 590**; Metal Rate 8,700.14 NetWt. G-Wt/N-Wt per pc then set to 0 (stock order). Header has **Repair** tick, **Tracking No**, **Prices From Client Chart**, **Slide Show File…**, **Quotation…**, Copy Selected Row, Attach Doc. A **Shipping Details** dialog (Despatch: Delivery Note No, AW No / Despatch Doc No, Ship Via / Despatch Through, Destination, EDF No; Order: Order No(s)/PO#, Sales Rep, Mode/Terms of Payment, Other Reference, Terms of Delivery; Buyer's / Consignee details; Export: Exporter's Ref, Pre-Carriage by, Vessel/Flight, Port of Loading/Discharge, Final Destination, Country of origin, Box No details, Product Description; Fetch Dept / Fetch Last Dtls). Save → "Print Order Sheet? Yes / No". Account Information on the order shows Cr Sales A/c / Dr stock. |
| 2 | Production Planning ▸ Job Card (Vr 930) | "Last Job Card No: 29455". Show Orders → order 1680 line (Ord Pcs 1, Prod Pcs 1, Job/Pcs 1, Prod Due 12-10-2026) → job **29456**. |
| 3 | Job Mapping (Vr 919) | Pending Jobs For Definition → 29456; Process Group **Default** = CAD, CAMMING, CASTING, HandMade, COLOUR, PrePolish, Setting, Final Polish, final setting, Meena, Puwai (11). CAD row deleted from the route on screen before save. Route text: "CD CAM CST HM CLR PP ST FP fs Meena Puwai". |
| 4 | Job History (F11) | Right-click lists **Issue : Factory-1** / **Rcvd : Factory-1** with every process (CAMMING, RECTIFICATION, OFFICE, HandMade, PrePolish, Setting, Final Polish, COLOUR, Meena, Puwai, Assamble, final setting, KHUDAI, Repair HM, DANK CHANGE, CAD, CASTING) — choosing one opens that voucher. |
| 5 | CAD / CAMMING / CASTING | Office, no weights: CAD issue 3288 / rcv 3284; CAMMING 3243 / 3243; CASTING 3247 / 3245. Issue asks **"Do you want to merge jobs?"** (answered No). |
| 6 | HandMade | Issue 3886 Office (Pending For Handmade list shows 0.5-pc jobs of other orders too). Receive 4171: G **50.000** N **50.000**. |
| 7 | COLOUR | FACTORY: issue 3165 50/50, receive 3135 50/50. |
| 8 | PrePolish | akshay ji office: issue 3725 50/50, receive 2579 **48.500** → loss 1.500 = **3.00 %**. |
| 9 | Setting | issue 4527 48.5, receive 4890 **49.100** → loss **−0.600 / −1.24 %** (gain). |
| 10 | Final Polish | issue 3768 49.1, receive 3762 49.1. |
| 11 | Stone ▸ Issue On Job-Card **Vr 14800** (Admin) | Lines come with Req Pcs / Req Wt from the SKU: daank − 175 / 12.400; DIA. MIX 462 / 6.300; EMERALD OCTAGON 6*4 4 / 1.920, 6*8 2 / 2.600, 7*5 8 / 7.400; POLKI 10-12 22 / 0.850, 12-14 54 / 2.860, 14-16 34 / 2.850, 16-18 13 / 1.420, 18-20 28 / 3.450, 20-22 4 / 0.690, 22-24 8 / 1.400, 24-26 6 / 1.340, 26-28 1 / 0.250, 28-30 1 / 0.240, 8-10 4 / 0.120; RED FANCY 49 / 7.230 — **875 pcs / 53.520 ct**. Save warns **"Stock Negative … Primary daank Cl Wt −9796.06, POLKI 12-14 −24.32 … RED FANCY −4044.02. Do You Want To Continue"** → Yes. |
| 12 | final setting | Issue 6115 akshay ji office, 49.100 g; **F3 Stone Job Bag** → all stones → Issue St Wt **53.520**; WIP value 26,037.44. |
| 13 | Received From Final Setting **6138** | F3 stone return grid per line: Return Pcs / Cts, Break Pcs / Cts, Loss Pcs / Cts ("Click For Return All Stone", "Fill Consignment Stones", "Fill From Worker O/S"). Returned: daank 8 / 0.580, DIA 50 / 0.750, POLKI 10-12 1 / 0.030, 12-14 4 / 0.210 + **break 1 / 0.050**, 16-18 3 / 0.320 → returned 66 / 1.890, broken 1 / 0.050. G-Wt typed **58.100** → N-Wt **47.784** = 58.100 − (53.520 − 1.890 − 0.050) ct × 0.2 = 58.100 − 10.316. Loss 1.316 = **2.68 %**; WIP value 25,760.73. |
| 14 | Stone Issue On Job-Card **Vr 14801** | Second issue, weight only (pcs 0): SOUTH SEA/JAPANESE 40.000, FRESHWATER PEARL 25.000, SARAFA 00-0 45.900, EMERALD BEADS EBDS-2 0.500 → **111.400 ct**. |
| 15 | Meena | KAILASH MEENAKAR: issue 1591 58.1 / 47.784, receive 1589 58.1 / 47.784. |
| 16 | Puwai | JAGDISH PRASAD SONI issue 3432 58.1 / 47.784 with **F3 stones 111.400** and **F5 metal: Primary, Actual, 14KT WIRE, title 590, 1.500 g** (Extra 1.500). WIP value 26,640.01. Receive 3462: G **81.880**, N **49.284** (= 47.784 + 1.500 wire); a Due Date on the receive. |
| 17 | Job History | All 11 steps listed; PND For MFG Transfer 1. Stone grid: daank 167 / 12.020 (rtn 8 / 0.580), DIA 412 / 5.550 (rtn 50 / 0.750) … total 808 / 162.980, rtn 66 / 1.890, break 1 / 0.050. **Order Remark is rewritten with the stones used**: "daank/167/12.02, DIA./412/5.55, EMERALD BEADS/0/0.5, EMERALD OCTAGON/14/11.92, FRESHWATER PEARL/0/25, POLKI/166/14.86, RED FANCY/49/7.23, SARAFA/0/45.9, SOUTH SEA/JAPANESE PEARLS/0/40". |
| 18 | MFG Ready Stock Transfer **Vr 1110** | Show Pending → job 29456 → Fill Prices: Pcs 1, G 81.880, N 49.284, Fine 29.078, Metal Rate 8,700.14, **Metal Amount 428,777.70** (= 49.284 × 8,700.14), **Stone Amount 324,619.50** (daank 0; DIA 5.550 @13,500 = 74,925; EMERALD BEADS 0.5 @250 = 125; EMERALD OCTAGON 1.920 @3,000 = 5,760, 2.600 @4,000 = 10,400, 7.400 @3,250 = 24,050; FRESHWATER 25 @100 = 2,500; POLKI 10-12 0.820 @6,700 = 5,494, 12-14 2.600 @8,100 = 21,060, 14-16 2.850 @11,600 = 33,060 …), Setting 0, **Labour STD 1,200 NetWt = 59,140.80**, **Total 812,538.00**, Price/Pcs **1,218,807** (= 1.5 × total), **Tag 1218**. Tag List: Bar Code **45127**. |
| 19 | Item Search 45127 | In Stock, Primary; Net 1,218,807, TAG 1218; history MF 1110; value summary: Net Wt 49.284 g → 428,778; DIAMOND 5.55 ct → 74,925; POLKI 14.86 ct → 198,329; COLOR STONE 142.57 ct → 51,366; Labour 59,141. "This SKU Stock 3". |

## What it tells us (for our app)

1. **Net weight on a setting receive = gross − stones set (ct × 0.2 g)** — 58.100 − 10.316 = 47.784.
2. **A step's loss % = (issued net − received net) ÷ issued net** — PrePolish 1.5 / 50 = 3.00 %, Setting −0.6 / 48.5 = −1.24 %, final setting 1.316 / 49.1 = 2.68 %.
3. **Metal issued on a step (F5, 14KT WIRE 1.5 g) adds to the received net** — 47.784 + 1.5 = 49.284.
4. **Stones issued with weight only (pearls, sarafa, pcs 0)** are allowed and priced per ct.
5. **Order Remark is refreshed with the stones actually used** (name / pcs / ct per stone).
6. **Stone issue warns "Stock Negative … Do you want to continue"** listing every location line that would go negative (our `inventory.negative_stock` = warn).
7. **MFG transfer**: Metal = N × rate; Labour = 1,200 × N; Stone = Σ ct × price; Price = Total × (1 + margin 50 %); Tag = price ÷ 1,000.
8. Order has a **Shipping Details** dialog and a **Tracking No** — the fields 9 Oct T-07 / T-08 need.
9. Issue screens ask **"Do you want to merge jobs?"** - asked on our multi-job issue too; Yes keeps the jobs together (question 115).
10. Order Shipping Details, Tracking No, Fetch Dept / Fetch Last Dtls and "Print Order Sheet?" after save - built (Order list > Shipping Details).

The full chain is reproduced on our app by `tests/ns1430_flow.py`.
