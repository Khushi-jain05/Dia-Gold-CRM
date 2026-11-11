"""Load the legacy DIAGOLD database into this app's database (go-live, 11 Nov).

The legacy database (Diagold26, or a newer backup restored on any SQL Server)
is only read. The target is whatever the app itself uses: server.ini's SQL
Server, else the local file.

    python scripts/import_legacy.py --server "SERVER2\\ERP" --user sa --password ...
    python scripts/import_legacy.py --server 127.0.0.1 --port 1433 --database Diagold26 \\
        --user sa --password ... --dry-run

--dry-run rolls everything back and only prints the report. --openings 01-04-2026
also loads the opening stock (run it on the backup taken at cut-over). Safe to run again:
what an earlier run loaded is matched, not added twice. The report is also
saved as legacy_import_<date>.txt in the app's data folder.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--server", required=True, help="host or host\\instance of the legacy SQL Server")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--database", default="Diagold26")
    ap.add_argument("--user", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    ap.add_argument("--openings", metavar="DD-MM-YYYY", default=None,
                    help="also load the opening stock (ready pieces, stones, metal) as on this "
                         "date - only on the backup taken at cut-over")
    a = ap.parse_args()

    from diagold.config import DATA_DIR, DB_LABEL
    from diagold.db.session import SessionLocal, init_db
    from diagold.services import legacy_import as LI

    print(f"Target database: {DB_LABEL}")
    init_db()
    legacy = LI.Legacy(a.server, a.database, a.user, a.password, a.port)
    try:
        with SessionLocal() as s:
            as_of = (datetime.strptime(a.openings, "%d-%m-%Y").date()
                     if a.openings else None)
            report = LI.import_all(s, legacy, as_of)
            if a.dry_run:
                s.rollback()
            else:
                s.commit()
    finally:
        legacy.close()
    text = report.text()
    print(text)
    if a.dry_run:
        print("\nDry run - nothing was saved.")
        return 0
    out = Path(DATA_DIR) / f"legacy_import_{datetime.now():%Y%m%d_%H%M%S}.txt"
    out.write_text(text, encoding="utf-8")
    print(f"\nSaved. Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
