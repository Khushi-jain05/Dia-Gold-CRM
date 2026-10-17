"""Run the 9 Oct migration data checks (T-13) on a data folder and write the
Excel for the client.

    python scripts/migration_checks.py [DATA_DIR] [out.xlsx]

DATA_DIR defaults to the app's own data folder; point it at the folder the
legacy export / database was loaded into.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if len(sys.argv) > 1:
    os.environ["DIAGOLD_DATA_DIR"] = sys.argv[1]

from datetime import date  # noqa: E402

from diagold.db.session import SessionLocal, init_db  # noqa: E402
from diagold.services import migration_checks as MC  # noqa: E402

init_db()
out = sys.argv[2] if len(sys.argv) > 2 else f"DiaGold-data-checks-{date.today():%Y%m%d}.xlsx"
with SessionLocal() as s:
    rows = MC.run(s)
MC.to_xlsx(rows, out)
for label, n in MC.summary(rows):
    print(f"{n:6}  {label}")
print("Saved", out)
