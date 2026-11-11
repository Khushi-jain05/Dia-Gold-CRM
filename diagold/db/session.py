"""SQLAlchemy engine / session setup."""
from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from diagold.config import DATABASE_URL, IS_SERVER, SQL_ECHO

if IS_SERVER:
    # Several PCs share the one SQL Server database. pre_ping drops a
    # connection the server closed overnight instead of failing the next save.
    engine: Engine = create_engine(
        DATABASE_URL, echo=SQL_ECHO, future=True, pool_pre_ping=True, pool_recycle=1800,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        echo=SQL_ECHO,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        """Enforce foreign keys - SQLite has them off by default."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def number_lock(session, key: str) -> None:
    """Hold the next-number sequence ``key`` until this transaction ends.

    Numbers are max + 1, so two PCs saving at once on the shared server would
    both read the same max. An exclusive application lock makes the second
    wait for the first to commit; the unique index stays the backstop. Not
    needed on the local SQLite file (one PC, one writer). If the lock is not
    granted within 10 s it carries on and leaves it to the unique index.
    """
    if not IS_SERVER:
        return
    session.execute(text(
        "DECLARE @r int; EXEC @r = sp_getapplock @Resource = :k, @LockMode = 'Exclusive', "
        "@LockOwner = 'Transaction', @LockTimeout = 10000"), {"k": f"diagold:{key}"})


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _fit_types_for_sql_server(metadata) -> None:
    """Text columns as SQLite has always treated them, on SQL Server.

    SQLite never enforced a VARCHAR length, so values longer than the model's
    String(n) are saved every day; SQL Server would refuse them. Text becomes
    NVARCHAR (Unicode whatever the server's collation): 450 where an index or
    key covers it (the 900-byte key limit), 4000 elsewhere.
    """
    from sqlalchemy import String, Text, Unicode, UnicodeText

    for table in metadata.sorted_tables:
        keyed = {c.name for c in table.primary_key.columns}
        keyed |= {fk.parent.name for fk in table.foreign_keys}
        for ix in table.indexes:
            keyed |= {c.name for c in ix.columns}
        for con in table.constraints:
            keyed |= {c.name for c in getattr(con, "columns", ())}
        for col in table.columns:
            if isinstance(col.type, Text):
                col.type = UnicodeText()
            elif isinstance(col.type, String) and not col.type.__class__.__name__.startswith("Enum"):
                wide = 450 if (col.name in keyed or col.unique or col.index) else 4000
                col.type = Unicode(max(wide, col.type.length or 0))


def _fit_cascades_for_sql_server(metadata) -> list[str]:
    """Turn off the ON DELETE actions SQL Server refuses.

    SQL Server rejects a foreign key whose ON DELETE CASCADE / SET NULL would
    give a table a second cascade path from the same ancestor (jobs ->
    job_vouchers directly and through job_steps), or a cycle. Walking the
    tables in dependency order, any such action is set to NO ACTION; the
    first path keeps its cascade. The app deletes through the ORM, so a row a
    dropped path would have removed is removed with its parent anyway - and
    if not, the server refuses the delete rather than leave an orphan.
    """
    down: dict[str, set[str]] = {}   # table -> tables its cascades reach

    def reach(t: str) -> set[str]:
        out, todo = set(), [t]
        while todo:
            for n in down.get(todo.pop(), ()):
                if n not in out:
                    out.add(n)
                    todo.append(n)
        return out

    demoted = []
    for table in metadata.sorted_tables:
        for fk in sorted(table.foreign_keys, key=lambda f: f.parent.name):
            if not fk.ondelete or fk.ondelete.upper() == "NO ACTION":
                continue
            parent, child = fk.column.table.name, table.name
            ups = {parent} | {a for a in down if parent in reach(a)}
            below = {child} | reach(child)
            clash = parent == child or any(
                b in reach(a) or b == a for a in ups for b in below)
            if clash:
                fk.ondelete = None
                if fk.constraint is not None:
                    fk.constraint.ondelete = None
                demoted.append(f"{child}.{fk.parent.name}")
            else:
                down.setdefault(parent, set()).add(child)
    return demoted


def init_db() -> None:
    """Create all tables and run first-run seeding."""
    from diagold.db.migrate import (  # noqa: WPS433
        rebuild_tables, repair_dangling_references, sync_schema,
    )
    from diagold.db.models import Base
    from diagold.services.seed import seed_initial_data

    if IS_SERVER:
        _fit_types_for_sql_server(Base.metadata)
        _fit_cascades_for_sql_server(Base.metadata)
    Base.metadata.create_all(engine)
    sync_schema(engine)  # add columns models gained since the file was made
    if not IS_SERVER:
        rebuild_tables(engine)  # recreate any table too changed to ALTER in place
        repair_dangling_references(engine)  # a rebuild runs with foreign keys off
    with SessionLocal() as session:
        seed_initial_data(session)
        from diagold.services.accounts import backfill_nominals, seed_groups
        seed_groups(session)          # the account-group tree (5 Oct T-01)
        from diagold.services.inventory import backfill_accounts, backfill_wt_per_pcs
        backfill_accounts(session)  # purchases saved before they posted accounts
        backfill_wt_per_pcs(session)  # stone lines saved before Wt/Pcs existed
        backfill_nominals(session)    # Sales / Purchase A/c entries get their account
        from diagold.services.production import backfill_setting_types
        backfill_setting_types(session)  # setting type from the stone; labour re-worked
        from diagold.services.master_import import seed_master_sheet
        seed_master_sheet(session)    # the client's master sheet + locations (9 Oct)
        from diagold.services.master_import import seed_workers
        seed_workers(session)         # the client's karigars by department (9 Oct)
        from diagold.services.price_charts import seed_default_charts
        seed_default_charts(session)  # price type "A" with the client's stone chart
        from diagold.services.stone_master import group_stone_skus
        group_stone_skus(session)     # one Stone SKU with its sizes inside (5 Nov T-01)
        from diagold.services.stone_master import seed_stone_list
        seed_stone_list(session)      # the client's Stone SKU List (11 Nov)
        session.commit()
