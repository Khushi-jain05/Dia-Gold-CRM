# 5 Nov 2026 (Production-Planning testing review) - task status

Source: `Dia_Gold_Meeting4_Production_Planning_Testing_Feedback.pdf` (5 Nov 2026 Meet, Rohit testing our app against legacy).
Build: **v0.10.8**. Tests: `tests/e2e_flow.py` 188, `tests/ns1430_flow.py` 30, `tests/abhijeet_das.py` all rows; all 210 screens open.

| Task | Status | What is in the build |
|---|---|---|
| T-01 Stone SKU - one master, sizes inside | Done | SKU > Stone SKU: one row per stone, Range / Size Info grid (range, cost, sale, per, size, Wt/Pcs, Min.Wt); existing per-size SKUs grouped by stone name on start-up, all transactions keep working; size rows saved in place, codes "NAME SIZE", a used size cannot be removed. Stone Issue on Job-Card and Stone Purchase: SSKU = stone names, Size = that stone's sizes. Full size data waits for C-01. |
| T-02 Automatic net weight | Done | Net = Gross - stones in the piece / 5, live as gross is typed (Job History + Issue / + Receive, Issue / Received grid, F3 returns taken out); can be typed over; Product SKU net follows gross less stone carats, never saved at 0. Job 29677 gives 11.949. Edge cases C-02. |
| T-03 Returned stones visible | Done | Job Card Bag Return column = stones handed back whole; Job History "Stones on this job" Rtn shows them (POLKI 12-14: Return 4, Break 1). |
| T-04 Edit / delete / change worker | Done | Edit on Stone Issue on Job-Card, Stone Purchase, Metal Issue (all inventory vouchers); Delete on the received-voucher popup; a saved issue / receipt can be moved to another karigar (pair moves together, both ledgers follow). |
| T-05 Order lines readable | Done | Order opens full screen; columns sized to content; Line P.O., Loss %, G-Wt/Pcs added; every picker type-to-narrow; editing a sold order no longer fails. |
| T-06 Job Mapping | Done | Job No box (Mapped + route / Not mapped), 8+ pending rows with count, all route steps visible, type-and-pick process cell ("camm" + Enter), List of Process panel. |
| T-07 Show Pending | Done | Job No box on Issue / Received (adds if pending at this process, else says why); "Pending For : process" with Order No / Client / Job No search, photo, Tick All. Job/Pcs 0.5: jobs still hold whole pieces (question 119). |
| T-08 Worker Metal Ledger | Done | Click a column heading = Auto Filter on it; Worker / Vr Type / Metal filters; one worker = statement without GROUP / WORKER; closing balance on the total row; latest row bright green; As on Today. |
| T-09 Ledger allowance | Done (rule) | Allowance = min(loss, ALW % x weight); a gain earns none. MANIK JI rows reproduce on the received basis. 0.000 on the demo = processes have Allow 0 - source is C-03. |
| T-10 Job History one screen | Done | One button row (More menu), two-line header, tight rows, Compact toggle, remark beside summary; fits 1366 px wide. |
| T-11 Compact Product SKU | Done | Three columns of sections; calculated fields read-only. |
| T-12 Delivery date check | Done | Asked before saving a delivery date earlier than the order date. |
| T-13 Retest round | To do | New build v0.10.8 to Rohit. |
| T-14 Reply to client | Draft | `docs/5-nov-reply.md`; questions 125-131 in `docs/group-message.md`. |
| T-15 Recording set-up | To do (us) | Meet "Record meeting" or headphones; 30-s test before the client starts. |
