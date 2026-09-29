"""Open the app on a separate demo database, loaded with the walkthrough data.

    python -m diagold.demo            # load (first time) and open the app
    python -m diagold.demo --reset    # throw the demo database away, start again

The demo lives in ~/DiaGoldDemo (or DIAGOLD_DATA_DIR if set), never in the
working database, so trying the flow cannot touch real data. What to do on
each screen, and the figure it should show, is in docs/demo-walkthrough.md.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DEMO_DIR = Path.home() / "DiaGoldDemo"


def main(argv: list[str]) -> int:
    data_dir = Path(os.environ.get("DIAGOLD_DATA_DIR") or DEMO_DIR).expanduser()
    if "--reset" in argv and data_dir.exists():
        if data_dir.resolve() != DEMO_DIR.resolve():
            print(f"--reset only clears the demo folder {DEMO_DIR}, not {data_dir}.")
            return 1
        shutil.rmtree(data_dir)
    # Before anything reads diagold.config, which fixes the data folder.
    os.environ["DIAGOLD_DATA_DIR"] = str(data_dir)

    from diagold.db.session import SessionLocal, init_db
    from diagold.services.demo_data import load_demo

    init_db()
    with SessionLocal() as session:
        print(load_demo(session))
        session.commit()
    print(f"Demo database: {data_dir / 'diagold.sqlite3'}  (login admin / admin)")
    if "--load-only" in argv:
        return 0
    from main import main as run_app
    return run_app()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
