# 2 October tasks — status

Every task from *Client Meeting Requirements & Action Items, Session 3, 2 Oct
2026* (§7, §14), with what was built, where to find it, and what is still
waiting for the client.

## Our team

| Task | Status | What / where | Waiting on |
|---|---|---|---|
| **T-01** Change file | ✅ Written | `python docs/build-change-file.py` → `~/Downloads/DiaGold-Change-File-2Oct.pdf`: what is built and where, the assumptions to confirm (B1–B8), what is waiting, screenshots. | Rohit ji's reply (C-01) |
| **T-02** Job Costing | ✅ Built | Manufacturing ▸ Job Costing (also Reports ▸ Manufacturing): register per finished job, WIP costing tick, double-click → Job Costing Sheet (photo, Export To Excel with formulas, Print, WIP Costing); Ctrl+F1 stone group wise, Ctrl+P / Ctrl+W Excel. BANG-52 reproduces 2,51,239.91 / tag 251 / 19.66 per gm. A transferred job keeps the rates frozen on its transfer. | Tag rule ÷1,000 (Q3), margin per customer? (Q2) |
| **T-03** Waxing off, Approval to Sale | ✅ Done | Waxing and Purchase Approval / Approval Return / Stone Approval / Stone App Return are off (switchable in Tools ▸ Option). Sale ▸ Ready Stock ▸ Sale, Sale Return, Approval, Approval Return, Ready Repair Issue, Settings; Sale ▸ Metal; Sale ▸ Stone ▸ …; Sale ▸ Reports. | Stone approval on purchase (C-03) |
| **T-04** Ready Stock Sale + Excel invoice | ✅ Built | Barcode / SKU read ("Item not found"), Show Stock, From Order (Pending Orders, Fill Balance Pcs / Fill Stock Qty, shipped and balance follow), Read Barcode From Approval; metal at the day's rate + stones + setting + labour; credit days / due date, salesperson, bank; Stone Breakup; Dr customer / Cr Sales A/c; Add / Edit / Save / Delete; Print; **Excel Invoice** in the client's breakup layout with formulas (Vr 1225 figures reproduce). | Print formats used (C-02 / Q1), payment-date rate (Q4), DIGICAT / RFID (Q11), As MRP / client chart |
| **T-05** MFG transfer → ready stock | ✅ Built | Location chosen per transfer, **Split Jobs** (one Stock No per piece, equal shares), Tag Print, Excel Format (.xlsx), Format-2, Edit / Delete; Ready Stock list by location, double-click opens the job; sellable by barcode. | Split rule (B6) |
| **T-06** Stock Transfer / Melting / Stone Issue | ✅ Structure built, rules UNCONFIRMED | Inventory ▸ Stock Transfer: four panes, Stock Melting, Stock Location Transfer, Barcode, Show Stock, Print 2, Melting List, Transfer Reg.; balance warning; transfer stone losses in the Stone Loss Register. Stone Issue: Read Cert/Lot, Stone Import, JobNo, DC Print, Tag, Register; Worker Adjustment / Create Outstanding Issue For Cert recorded. | C-05, Q6, Q7 |
| **T-07** Purchase | ✅ Built | Purchase ▸ Metal / Stones (inventory purchase), Ready Items (new barcodes, tunch, stones, labour, cert, HUID, bill block, Dr Purchase / Cr supplier; BreakUp Sheet, Packing List, Picture Invoice, St. Summ., Tag Print, SKU Search), Ready Item Return, Opening Stock ▸ Ready Items / Metal / Stone, Purchase ▸ Reports. | Debit Note, Parts / Moulds (C-03 / Q5); Show Ords, From Ft.Tr, Settings |
| **T-08** Loss / Dust / WIP registers | ✅ Built | Metal Loss, Stone Loss, Dust, WIP Register (WIP / PND, value), WIP process summary (every process on the master), WIP Stone — Inventory / Manufacturing ▸ Reports ▸ Registers. Every report: Excel export, F1 Show All, as-on-date mode. | C-06 data to reconcile against |
| **T-09** Approval, Metal / Stone sale, sale reports | ✅ Built | Approval / Approval Return (piece held by one party), Metal Sale, Stone Sale / Approval / Approval Return; Ready Stock Sale / Approval Register, Approval Balance, Approval Analysis; Metal Sale, Stone Sale, Stone Approval Register / Analysis. | — |
| **T-10** Repair | ✅ Built | Order ▸ Repair tick + Repair List (Repair Stock picker → lines with a job each); Ready Repair Issue; Repair Register. Repair jobs carry no stone detail (UNCONFIRMED). | Q9 |
| **T-11** Process master additions | ✅ Already there | RECTIFICATION, OFFICE, Assamble, KHUDAI, Repair HM, DANK CHANGE are seeded and outside the Default route. | — |
| **T-12** Dashboard barcode | ✅ Built | Dashboard ▸ BARCODE READ (Stock ID / SKU → Item Search, Job No → Job History); also Tools ▸ Read Barcode. | — |
| **T-13** Daily metal rate | ✅ Built | Each rate keeps entered by / at; Rate As On Date. Vouchers store the rate they used. | Booked vs payment-date rate (Q4) |
| **T-14** Next-meeting agenda | ✅ Written | `docs/next-session-agenda.md` | — |
| **T-15** Open-items list | ✅ Updated | `docs/group-message.md` — "Answered 2 Oct" and "2 Oct — needed next" blocks merged with S1 / S2 items. | Post to the group |
| **T-16** Mock-ups for review | ✅ As screenshots | The new screens are built; their screenshots are in the change file (`docs/screens-2oct/`) for Rohit ji's review. | His feedback |
| **T-17** Meet transcripts | ⏳ Our action at the next call | `docs/recording-checklist.md` — turn on Meet's Transcript, presenter on one device. | — |

## Also done

- Sale header: Cl Bal and Attach Doc; TXT Import / Export, Tag Print, Catalog on the sale-side vouchers; Fine With Loss on every ready-stock line.
- Item Search: the barcode's whole history (MF, RP / OPR, RA / RAR, RS / RSR, RRI, RPR, TR / MELT).
- Stone lines Wt/Pcs; Stock Transfer metal pane Metal / Mould, Wt/Pcs, Item Size, St Size; Account Information on every inventory voucher (TR5); Excel invoice embeds the product photo (Pillow).
- Menus: Purchase Debit Notes / Parts / Moulds / Settings, Inventory Parts / Mould / Physical Stock / Ready Item Receipt, Manufacturing Repair Issue / Extra Issue / Stamping off until confirmed (switchable).
- `python tests/e2e_flow.py` - the whole flow with data on a throw-away database (58 checks, accounts Dr = Cr, stock = sum of movements).

## Seen on the legacy screen, meaning not given - asked, not built

F10 SKU Curr, As MRP, Prices From Client Chart, Get DIGICAT Quote, Read RFID (Q11), the "App" button and "Oth FineWt" on the sale; Export Docs, Catalog 4×8, Cert Stones, PIC Folder, Avg St Price; the second Excel layout; 11 of the 13 print formats incl. Format-2 / WhatsApp (C-02); Show Ords / From Ft.Tr on purchase; Old Wt / Tag% on the MFG transfer (28 Sept Q16); metal settlement rate at payment (Q4); Job History to be checked against job 46973 when C-06 arrives.

- Window ▸ Cascade / Tile off (screens are tabs); Window ▸ Close All, Tools ▸ Change Password and Read Barcode work.
- Pieces bought in or loaded as opening stock work everywhere (Item Search, tags); Delete History & Purchase refuses a piece not made here or already on a sale / approval.
- Stock pieces carry their state: in stock · sold · on approval · in repair · returned · melted.
