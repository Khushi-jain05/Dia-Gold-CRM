# Dia Gold CRM v0.5.0 — test script

Login `admin` / `admin`. Do the steps in order: each screen feeds the next
(order → jobs → route → vouchers → bag → return → reports). Sample data
(jobs 28350, 25006, 27751) is already there.

1. Master ▸ Account ▸ + New — Code RAHUL, Name RAHUL JI, Type Worker.
2. Master ▸ Metal ▸ + New — TEST22 / 22KT TEST 916 / fineness 916; ratio GOLD 91.6 + ALLOY 8.3 is refused, 8.4 saves.
3. SKU ▸ Stone SKU ▸ + New — RUBY OVAL 5*4, cost 800, sale 1200, Per Cts; Make A Copy.
4. SKU ▸ Product SKU ▸ + New — RG-9001, item ring, metal 14KT CASTING 590, gross 5.200 / net 4.100, stone RUBY OVAL 5*4 × 4 pcs 1.000 ct; totals compute; duplicate code refused.
5. Production Planning ▸ Order ▸ + New — KK JEWELS, lines RG-9001 ×2 and NS-2968 ×1; two jobs allotted.
6. Job Mapping — Apply Group Default, Save Route, Copy To All, Add Step Repair HM.
7. Stone Issue on Job-Card — Primary, EMERALD PEAR 6*4, 4 pcs / 1.200; 999 pcs refused.
8. Job History (F11) — issue/receive on CASTING with RAHUL JI → loss 0.050; refusals; Add Comments; Print.
9. Job Card Bag — Issue to Worker 2, Return to Stock 1, over-issue refused; two reports.
10. Inv Return – Stone — Show Pending, return 1, Save.
11. Printing Options — Job Sheet + Stone Requirements → PDFs.
12. Opening Stone Balances — RAJAT JI, RUBY OVAL 5*4, 100 pcs / 25 ct → value 20,000.
13. Reports — every report; Group, Auto Filter, Export, Print.
14. Tools ▸ Option — untick Job Card Bag, Save, menu changes.

The PDF handed to the tester is generated from this list by `docs/build-test-script-pdf.py`.
