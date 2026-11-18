# 17 Nov testing review - task status (v0.13.0)

Source: `Dia_Gold_Meeting5_Testing_Feedback_Sales_Repair_Ledger_17Nov2026.pdf` (JewelleryERP_26).

| Task | Status | What was done |
|---|---|---|
| T-01 Wastage per karigar per process | Done (values from client: C-01) | Account > **Select Worker Process** grid (Process, Allow Metal Loss %, Allow Stone Loss %, L Price). Issue / receipt from that karigar on that process starts on his %; else the issue's, else the process master's. Legacy grid not imported yet (C-01). |
| T-02 Allowance = % x issued, also on a gain | Done | Rule in force since 16 Nov; CHANDAN MONDAL rows 5844 / 5771 / 5737 / 5745 reproduce (0.861 / 0.422 / 1.108 / 0.198). Rows with no % and any cap: Q143. |
| T-03 Receive weight carried forward | Done | Received From shows Iss G-Wt / Iss N-Wt beside the weights typed back (also on Edit). Job History + Receive starts at the issued weights, shows them, "Same as issued". Next issue already starts at the last receipt. |
| T-04 Metal Purchase | Done | Real cause: on the client's Windows PC every number / date box showed **empty** (white text on white). Fixed app-wide; clicking or tabbing into a box selects it, so a price typed in front of the hidden 0.00 can no longer read 1,33,590 (the 10x payable). Wheel never changes a box. Enter moves to the next box. New **List of ...** panel beside the voucher (narrows as you type, Enter takes the first). LPrice / L Unit / L Amount columns, labour in the payable. Vr 1 / 2 must be corrected by the client (Q149). |
| T-05 Repair issue / A B JEWELS credit | Done | Ready Repair Issue never posted. The 41,699 credit was the **Sale Return**, priced at the day's rate (no rate that day = stones only). A return now takes the values it was sold at; saved returns re-valued once on start. |
| T-06 Repair chain | Done (billing on return: Q148) | Repair line typed in (not from Repair List) is asked about on Save. Repair List shows the client's REP pieces first. C-Ref = the original job. First issue at the piece's weights. Job Mapping starts a repair route at HandMade (Tools > Option). |
| T-07 Photos | Done (folder: Q146) | `<SKU>.jpg` found in the Image folders (default `\\Server2\d\JewelleryER_25\Images`, several allowed), listed in the background. Used on every screen with a photo and the Excel invoice. A photo attached on a SKU is copied in as `<SKU>.jpg`. |
| T-08 Cash sale + receipt | Done 16 Nov | Cash sale = bill; Receipt reduces it. Cash typed on the sale: Q147. |
| T-09 Sales Profit cost | Done | Cost = metal + stone + labour (columns shown); metal at 0 on the transfer costed at the sale rate; returned sale = profit 0. |
| T-10 Ledger worker list, dept-wise | Done (formats: C-05) | Worker Metal Ledger opens on "Select Any One"; As on Today = head-wise fine balance with subtotals. Day Book DIA / POL / CS carats since v0.11.6. |
| T-11 Worker change | Done | Receipt on a karigar other than the issue's is refused with the issue named; Edit puts the pair on the header's karigar (heals Vr 54); From follows while editing. |
| T-12 Small fixes | Done, 2 asked | Delivery > 6 months warns; M.I.S. Reports once in the menu; legacy workers under Receivable moved to Payable; blank dates = T-04 fix. Issue net with stones (Q150) and fine > weight (Q151) asked, not changed. "No Ready Stock Sale saved yet" in one copy: C-06 / Q152. |
| T-13 Walk-through per flow | Team | With Rohit ji: Sale + receipt, Purchase, Repair, Karigar ledger. |
| T-14 Send list + next slot | Team | `docs/17-nov-reply.md` + questions 142-154 in `docs/group-message.md`. |
| T-15 Recording | Team | Meet's Record meeting or headphones; 30 s test. |
| T-16 WhatsApp notes | Done | Re-price (F6) on Ready Stock Sale; the rest shipped 16 Nov (v0.11.7-v0.12.0). |

Tests: e2e 220/220, ns1430 30/30, abhijeet_das all rows match, 217 screens opened with no error.
