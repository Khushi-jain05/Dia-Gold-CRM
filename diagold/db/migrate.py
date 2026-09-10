"""Lightweight, non-destructive schema sync for the SQLite database.

``Base.metadata.create_all()`` creates missing *tables* but never alters an
existing one, so a model that gains or loses a column leaves older database
files broken. Until the schema settles and Alembic is introduced (see the
README), this module reconciles an existing file with the models:

1. add columns the models gained;
2. carry old values across to their replacements;
3. drop leftover ``NOT NULL`` columns the models no longer set - those reject
   every INSERT, so they cannot simply be left in place;
4. create unique indexes for columns added after the fact.

Every step is idempotent and safe to run on each start-up.
"""
from __future__ import annotations

import sqlite3

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from diagold.db.models import Base

# ALTER TABLE ... DROP COLUMN landed in SQLite 3.35 (2021).
_CAN_DROP_COLUMN = tuple(int(p) for p in sqlite3.sqlite_version.split(".")) >= (3, 35, 0)

_SQLITE_TYPE = {
    "INTEGER": "INTEGER", "BIGINT": "INTEGER", "SMALLINT": "INTEGER",
    "BOOLEAN": "BOOLEAN", "DATETIME": "DATETIME", "DATE": "DATE",
    "TEXT": "TEXT", "FLOAT": "FLOAT",
}


def _column_ddl_type(column) -> str:
    compiled = str(column.type)
    base = compiled.split("(", 1)[0].upper()
    if base.startswith("VARCHAR") or base == "STRING":
        return compiled
    if base.startswith("NUMERIC") or base.startswith("DECIMAL"):
        return compiled
    return _SQLITE_TYPE.get(base, compiled)


def _default_literal(column) -> str | None:
    # A foreign key must never be given an invented value: stamping 0 on
    # existing rows produces a dangling reference that looks populated. Leave
    # it NULL so unassigned rows are visibly unassigned.
    if column.foreign_keys:
        return None
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        # Give NOT NULL columns something to land on for existing rows.
        if not column.nullable:
            t = _column_ddl_type(column).upper()
            if t.startswith(("VARCHAR", "TEXT", "STRING")):
                return "''"
            return "0"
        return None
    value = default.arg
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def sync_schema(engine: Engine) -> list[str]:
    """Reconcile the database file with the models. Returns what changed."""
    changes: list[str] = []
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    with engine.begin() as conn:
        changes += _add_missing_columns(conn, inspector, existing)
        # Runs on every start-up, not only when columns were just added: a file
        # part-migrated by an earlier run still needs its values carried over.
        _carry_over_metal_values(conn, inspector, existing)
        _carry_over_account_types(conn, existing)
        changes += _drop_orphan_not_null_columns(conn, inspector, existing)
        _create_unique_indexes(conn, inspector, existing)
        _enforce_stone_group(conn, inspector, existing)

    return changes


def _add_missing_columns(conn, inspector, existing: set[str]) -> list[str]:
    added: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # create_all() will make it
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            ddl = (f'ALTER TABLE "{table.name}" ADD COLUMN '
                   f'"{column.name}" {_column_ddl_type(column)}')
            literal = _default_literal(column)
            if literal is not None:
                ddl += f" DEFAULT {literal}"
            conn.execute(text(ddl))
            added.append(f"+{table.name}.{column.name}")
    return added


def _carry_over_metal_values(conn, inspector, existing: set[str]) -> None:
    """Move v0.1 metal values into the fields that replaced them.

    The old shape was {name, purity_label, fineness, color}; the new one records
    a head name, a code, purity_fineness and colour. Rows written by the old
    build are recognised by still carrying a purity_label. Guarded so it only
    ever fills blanks - safe to re-run.
    """
    if "metals" not in existing:
        return
    cols = {c["name"] for c in inspector.get_columns("metals")}
    if "purity_label" not in cols:
        return  # already migrated

    legacy = "purity_label IS NOT NULL AND TRIM(purity_label) <> ''"

    if "purity_fineness" in cols and "fineness" in cols:
        # 0.916 style fractions are understood as-is by costing.purity_fraction.
        conn.execute(text(
            "UPDATE metals SET purity_fineness = fineness "
            f"WHERE {legacy} AND fineness > 0 "
            "AND (purity_fineness IS NULL OR purity_fineness = 0)"
        ))
    if "print_on_tag" in cols:
        conn.execute(text(
            "UPDATE metals SET print_on_tag = purity_label "
            f"WHERE {legacy} AND (print_on_tag IS NULL OR print_on_tag = '')"
        ))
    if "colour" in cols and "color" in cols:
        conn.execute(text(
            "UPDATE metals SET colour = CASE UPPER(TRIM(color)) "
            "WHEN 'YELLOW' THEN 'Y' WHEN 'WHITE' THEN 'W' "
            "WHEN 'ROSE' THEN 'R' WHEN 'GREEN' THEN 'G' ELSE '' END "
            f"WHERE {legacy} AND (colour IS NULL OR colour = '')"
        ))
    if "base_metal" in cols:
        # The ALTER stamped 'GOLD' on every row, so there is no blank to test
        # for - key off the legacy marker instead.
        conn.execute(text(
            "UPDATE metals SET base_metal = UPPER(TRIM(name)) "
            f"WHERE {legacy} AND name IS NOT NULL AND TRIM(name) <> ''"
        ))
    if "code" in cols:
        conn.execute(text(
            "UPDATE metals SET code = UPPER(REPLACE(COALESCE(name,'METAL'),' ','')) "
            "|| '-' || id WHERE code IS NULL OR TRIM(code) = ''"
        ))


def _carry_over_account_types(conn, existing: set[str]) -> None:
    """Map v0.1 account types onto the client's four party types.

    The old build offered Customer / Supplier / Karigar / Bank / Cash / Expense
    / Income / Other. The client actually works with Client / Worker / Designer
    / Accounts, so anything still holding an old value is translated. Rows
    already on a new value are untouched, so this is safe to re-run.
    """
    if "accounts" not in existing:
        return
    mapping = {
        "Customer": "Client",
        "Karigar": "Worker",
        "Supplier": "Accounts",
        "Bank": "Accounts",
        "Cash": "Accounts",
        "Expense": "Accounts",
        "Income": "Accounts",
        "Other": "Accounts",
    }
    for old, new in mapping.items():
        conn.execute(
            text("UPDATE accounts SET account_type = :new WHERE account_type = :old"),
            {"new": new, "old": old},
        )


# Tables that could not be altered in place and must be rebuilt once the
# main transaction has closed.
_pending_rebuilds: set[str] = set()


def rebuild_tables(engine: Engine) -> list[str]:
    """Recreate tables whose shape changed too much to ALTER.

    SQLite cannot drop a column that a foreign key names, so the table is
    recreated from the model and whatever columns both shapes share are copied
    across. Anything only the old shape had is gone - which is the point, since
    the model no longer has it.
    """
    if not _pending_rebuilds:
        return []
    done: list[str] = []
    names, _pending_rebuilds_local = set(_pending_rebuilds), None
    _pending_rebuilds.clear()

    for name in names:
        table = Base.metadata.tables.get(name)
        if table is None:
            continue
        with engine.connect() as conn:
            # Foreign keys must be off while the table is swapped, and that
            # cannot be toggled inside a transaction.
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.commit()  # the PRAGMA autobegan a transaction; close it first
            old_cols = {c["name"] for c in inspect(engine).get_columns(name)}
            shared = [c.name for c in table.columns if c.name in old_cols]
            trans = conn.begin()
            try:
                conn.execute(text(f'ALTER TABLE "{name}" RENAME TO "{name}__old"'))
                table.create(bind=conn)
                carried = 0
                if shared:
                    cols = ", ".join(f'"{c}"' for c in shared)
                    kept = conn.execute(text(f'SELECT COUNT(*) FROM "{name}__old"')).scalar()
                    try:
                        conn.execute(text(
                            f'INSERT INTO "{name}" ({cols}) SELECT {cols} FROM "{name}__old"'
                        ))
                        carried = kept or 0
                    except Exception as exc:  # noqa: BLE001
                        # The old rows cannot be expressed in the new shape -
                        # a required column they never had, or a uniqueness the
                        # old data breaks. Start clean rather than half-migrate,
                        # and say so instead of losing rows quietly.
                        conn.execute(text(f'DELETE FROM "{name}"'))
                        print(f"[migrate] {name}: rebuilt empty, {kept} old row(s) "
                              f"could not be carried across ({type(exc).__name__}). "
                              f"Reference data reseeds on start-up.")
                conn.execute(text(f'DROP TABLE "{name}__old"'))
                trans.commit()
                done.append(f"{name} ({carried} row(s) carried)")
            except Exception:
                trans.rollback()
                raise
            finally:
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    return done


def _drop_orphan_not_null_columns(conn, inspector, existing: set[str]) -> list[str]:
    """Drop NOT NULL columns the models no longer define.

    A column the models dropped is normally harmless dead weight. But one that
    is NOT NULL with no default rejects every INSERT, because nothing supplies
    a value for it any more - so it has to go. Columns that merely sit unused
    are left alone.
    """
    dropped: list[str] = []
    rebuild: set[str] = set()
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        model_cols = {c.name for c in table.columns}
        for col in inspector.get_columns(table.name):
            if col["name"] in model_cols or col.get("primary_key"):
                continue
            if col.get("nullable", True) or col.get("default") is not None:
                continue  # unused but not in the way
            if not _CAN_DROP_COLUMN:
                raise RuntimeError(
                    f'The column "{table.name}.{col["name"]}" is NOT NULL but is no '
                    f"longer written by the application, so records cannot be saved. "
                    f"SQLite {sqlite3.sqlite_version} cannot drop it (3.35+ required). "
                    f"Upgrade Python/SQLite, or delete the database file to start fresh."
                )
            # An index over the column survives the drop and then breaks every
            # later statement against the table, so it goes first.
            for ix in inspector.get_indexes(table.name):
                if col["name"] in (ix.get("column_names") or []):
                    conn.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
            try:
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" DROP COLUMN "{col["name"]}"'
                ))
            except Exception:  # noqa: BLE001
                # SQLite refuses to drop a column named in a foreign key, so
                # the table has to be rebuilt to the model's shape instead.
                rebuild.add(table.name)
                break
            dropped.append(f'-{table.name}.{col["name"]}')
    for name in rebuild:
        dropped.append(f'~{name} (rebuilt)')
    _pending_rebuilds.update(rebuild)
    return dropped


def _create_unique_indexes(conn, inspector, existing: set[str]) -> None:
    """Add unique indexes for unique columns that were added after the fact."""
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        have = {ix["name"] for ix in inspector.get_indexes(table.name)}
        for column in table.columns:
            if not column.unique or column.primary_key:
                continue
            name = f"uq_{table.name}_{column.name}"
            if name in have:
                continue
            try:
                conn.execute(text(
                    f'CREATE UNIQUE INDEX "{name}" ON "{table.name}" ("{column.name}")'
                ))
            except Exception:  # noqa: BLE001 - duplicates already in the file
                pass


def _enforce_stone_group(conn, inspector, existing: set[str]) -> None:
    """Refuse a stone with no group, at the database level.

    The model already declares the column NOT NULL, which covers databases
    created from scratch. SQLite cannot tighten an existing nullable column
    without rebuilding the table, so a trigger enforces the same rule on files
    that predate it - and it holds against a direct write, not only the form.
    """
    if "stone_info" not in existing:
        return
    cols = {c["name"] for c in inspector.get_columns("stone_info")}
    if "stone_group_id" not in cols:
        return
    for event in ("INSERT", "UPDATE"):
        name = f"trg_stone_group_required_{event.lower()}"
        conn.execute(text(f'DROP TRIGGER IF EXISTS "{name}"'))
        conn.execute(text(
            f'CREATE TRIGGER "{name}" BEFORE {event} ON stone_info '
            f"FOR EACH ROW WHEN NEW.stone_group_id IS NULL OR NOT EXISTS "
            f"(SELECT 1 FROM stone_groups WHERE id = NEW.stone_group_id) "
            f"BEGIN SELECT RAISE(ABORT, "
            f"'A stone must belong to a stone group (Diamond, Polki or Colour Stone).'); "
            f"END"
        ))
