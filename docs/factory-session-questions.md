# Factory-team session — questions (T-09 / C-04)

Both sides agreed on 11 September that casting and manufacturing detail needs
the people who do it in the room; Rohit said he cannot explain it fully
himself. This is the list to take in. Everything here is currently either an
assumption in the code (marked) or not built.

## Weight entry
1. At which step does metal first get weighed — casting (Rohit: "should"), or
   HandMade (live data: job 28350)? Is it different for cast vs handmade
   pieces? *(Code: a per-process "carries weight" flag; CAD, CAMMING, OFFICE off.)*
2. On an **issue**, is the metal always weighed, or only on receive? Live rows
   Vr 3018 and Vr 3019 went out with no metal weight. *(Code: receive on a
   metal step must carry weight; issue may go out unweighed.)*
3. Gross vs net on the floor: what is deducted to get net — stones only, or
   findings too?

## Loss
4. Is loss simply issued net − received net, or do scrap and dust come off it
   first? *(Code: loss = issued − received − scrap − dust.)*
5. Is there an allowed loss % per process (the Session 1 "loss %" column)?
   Who is charged when it is exceeded — the karigar?
6. When more comes back than went out (Repair HM: 299.917 → 299.980), what is
   that — added metal, solder, a weighing difference?

## Scrap, dust, rejects
7. Where does scrap go — back to stock (which location), to refining, or to
   the karigar's account?
8. Dust: collected per karigar or per process area? Weighed daily or per job?
9. A rejected piece (Rej Pcs / Rej Wt): does the job go back a step, restart,
   or close? Does a reject create a new job?

## Stones on the job
10. Who issues stones to the setter — office from the bag, or the setter takes
    the bag? Is a stone "consumed" when set, or does the bag stay open until
    the piece is finished?
11. **Back** column: stones returned by the setter into the bag — correct?
12. Broken stones: who bears the cost? Do broken pieces go anywhere (a
    breakage packet)?
13. Extra: entered as a separate receipt, or simply received beyond requirement?
    *(Code: derived — received above requirement.)*

## Metal held by a job
14. When a job is finished or cancelled, how is leftover metal returned — by
    weight to a location, and against which karigar?
15. What should **WIP Costing** show — metal at issue-day rate or today's,
    labour to date, stones at cost?

## Route and workers
16. Can two steps be out at once (e.g. stones with the setter while the
    frame is at polish)? *(Code: allows one open issue per step.)*
17. Repair steps — always "Repair HM", or a repair of any step?
18. Is "Office" really a worker, or a holding location? (It appears as the
    worker on several vouchers.)

## The job sheet
19. Who fills the Word template today, from which screen, and what do they
    add that the system does not print?
20. Does the sheet travel with the piece? Is it signed per step?

Bring: the Word template and a filled example (C-02); one finished job's paper
trail; the karigar payout sheet for a month.
