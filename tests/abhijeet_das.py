"""5 Oct acceptance (T-06): reproduce the legacy Worker Ledger rows of
ABHIJEET DAS - Vr 144 / 176 / 278 - with the verified rule
allowed loss = 3 % x the weight ISSUED, fine = weight x 0.590.

    python tests/abhijeet_das.py

Runs on its own throw-away database.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DIAGOLD_DATA_DIR"] = tempfile.mkdtemp(prefix="diagold-abhijeet-")

from datetime import date
from decimal import Decimal as D

from sqlalchemy import select

from diagold.db.session import SessionLocal, init_db
init_db()
from diagold.services.demo_data import load_demo
with SessionLocal() as _s:
    load_demo(_s)
    _s.commit()
from diagold.db.models import Account, Job, Metal
from diagold.services import production as P

# (issue, returned) -> legacy (loss wt / fine, allowed wt / fine, in fine, out fine)
LEGACY = [
    (D("11.240"), D("10.530"), (D("0.710"), D("0.419"), D("0.337"), D("0.199"), D("6.632"), D("6.213"))),
    (D("25.380"), D("21.730"), (D("3.650"), D("2.154"), D("0.761"), D("0.449"), D("14.974"), D("12.821"))),
    (D("33.220"), D("28.580"), (D("4.640"), D("2.738"), D("0.997"), D("0.588"), D("19.600"), D("16.862"))),
]
fails = []
with SessionLocal() as s:
    # The karigar is on the client's worker sheet (loaded at start); else add him.
    abhi = s.scalar(select(Account).where(Account.name == "ABHIJEET DAS"))
    if abhi is None:
        abhi = Account(code="ABHIJEET", name="ABHIJEET DAS", account_type="Worker",
                       group_name="Karigar")
        s.add(abhi)
        s.flush()
    metal = s.scalar(select(Metal).where(Metal.name == "14KT 590"))
    job = next(j for j in s.scalars(select(Job).where(Job.status.in_(("mapped", "in_progress"))))
               if P.current_step(s, j)[0] is not None and P.current_step(s, j)[1] is None
               and P.current_step(s, j)[0].weight_bearing)
    job.metal_id = metal.id
    on = date(2026, 4, 8)
    for issued, back, _want in LEGACY:
        step = P.current_step(s, job)[0]
        while step is not None and not step.weight_bearing:
            P.post_voucher(s, job, step, "issue", abhi.id, vr_date=on)
            P.post_voucher(s, job, step, "receive", abhi.id, vr_date=on)
            step = P.current_step(s, job)[0]
        P.post_voucher(s, job, step, "issue", abhi.id, vr_date=on, net_wt=issued,
                       gross_wt=issued, allow_loss_pct=D("3"))
        P.post_voucher(s, job, step, "receive", abhi.id, vr_date=on, net_wt=back,
                       gross_wt=back, allow_loss_pct=D("3"))
    s.flush()
    rows = [r for r in P.worker_metal_ledger(s, date(2026, 4, 1), date(2027, 3, 31),
                                             worker_id=abhi.id) if r["vrtype"] == "RTN"]
    iss = [r for r in P.worker_metal_ledger(s, date(2026, 4, 1), date(2027, 3, 31),
                                            worker_id=abhi.id) if r["vrtype"] == "ISS"]
    q = lambda v: D(str(v)).quantize(D("0.001")) if v is not None else None  # noqa: E731
    for (issued, back, want), r, i in zip(LEGACY, rows, iss):
        got = (q(r["loss_wt"]), q(r["loss_fine"]), q(r["alw_wt"]), q(r["alw_fine"]),
               q(i["in_fine"]), q(r["out_fine"]))
        ok = got == want
        print(("  PASS " if ok else "  FAIL ") + f"issue {issued} back {back}: loss / fine, "
              f"allowed / fine, in fine, out fine = {got}" + ("" if ok else f" want {want}"))
        if not ok:
            fails.append(str(issued))
    s.rollback()
print(f"\n{'ALL ROWS MATCH' if not fails else 'MISMATCH: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
