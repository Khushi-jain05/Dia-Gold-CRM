# 3 September requirements — what the 28 September session changed (T-11)

The 3 September (Master) requirements are superseded on the points below by
what the client showed on his live DIAGOLD screens on 28 September. Anyone
building from the 3 September document should read this first.

## Closed

| 3 Sept | Question | Answer (28 Sept) | Where it is built |
|---|---|---|---|
| **Q5** | Is labour charged on net weight? | **Yes.** "Price On: NetWt" on the voucher and in the cost break-up; said at 27:28 ("net weight is my metal — labour is charged on this"). *Which* net weight is a new question (28 Sept Q2). | `mfg_pricing.price_line` — labour = rate × net weight |
| **Q7** | Setting labour ₹3 or ₹30 per piece? | **Both.** Diamond ₹3, Polki ₹30 per piece, held on the Setting Type. Pieces set × rate reproduces the ₹2,400 on job 28853 exactly. | Setting Type master price; `production.setting_labour_lines`; Reports ▸ Setting Labour Statement |

## Amended

- **T-10 (margin arithmetic).** The 3 September prompt said a margin means
  `cost ÷ (1 − rate)`. The live "Margin %" on MFG Ready Stock Transfer is a
  **mark-up**: price = cost × (1 + 50%) — Vr 1081: 2,03,553.41 × 1.5 =
  3,05,330.12. The price engine follows the screen. The component-wise
  Margin / Markup modes on the Margin master stay available.

## Partly answered

| 3 Sept | Question | What 28 Sept showed | Still open |
|---|---|---|---|
| **Q4** | Is setting the same for every setting type? | No — the price differs by type (Polki vs Diam). | Are broken pieces unpaid? (28 Sept Q4) |
| **Q6** | Margin arithmetic | 50% applied as a mark-up. | Where the "20%" applies (28 Sept Q1) |
| **Q1** | Stone info — granular or flat? | Stone lines carry SSKU, size, S Type and setting type separately — supports the granular model. | Not asked directly |

## Not discussed on 28 September

Q9 Daily Labour Rates; Q2, Q3, Q8, Q10–Q13 (item size, users, daily slot, HSN,
mould, dates, default process) — still open as in the 3 September document.
