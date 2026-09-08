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
        _carry_over_stone_lookups(conn, inspector, existing)
        changes += _drop_orphan_not_null_columns(conn, inspector, existing)
        _create_unique_indexes(conn, inspector, existing)

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


def _carry_over_stone_lookups(conn, inspector, existing: set[str]) -> None:
    """Move v0.1 stone text values into the granular lookup masters.

    The old shape stored shape / type / quality as free text on the stone row.
    Each distinct value becomes a lookup row and the stone points at it, so no
    classification is lost when the text columns go.
    """
    if "stone_info" not in existing:
        return
    cols = {c["name"] for c in inspector.get_columns("stone_info")}
    moves = [
        ("stone_type", "stone_kinds", "stone_kind_id"),
        ("shape", "stone_shapes", "shape_id"),
        ("quality", "stone_qualities", "quality_id"),
    ]
    for text_col, table, fk_col in moves:
        if text_col not in cols or fk_col not in cols:
            continue
        # Create any lookup row the old text refers to but that does not exist.
        conn.execute(text(
            f"INSERT INTO {table} (code, name, is_active, created_at, updated_at) "
            f"SELECT DISTINCT UPPER(REPLACE(TRIM({text_col}),' ','')), TRIM({text_col}), 1, "
            f"CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            f"FROM stone_info WHERE TRIM(COALESCE({text_col},'')) <> '' "
            f"AND UPPER(REPLACE(TRIM({text_col}),' ','')) NOT IN (SELECT code FROM {table})"
        ))
        conn.execute(text(
            f"UPDATE stone_info SET {fk_col} = ("
            f"  SELECT id FROM {table} WHERE {table}.name = TRIM(stone_info.{text_col})"
            f") WHERE {fk_col} IS NULL AND TRIM(COALESCE({text_col},'')) <> ''"
        ))


def _drop_orphan_not_null_columns(conn, inspector, existing: set[str]) -> list[str]:
    """Drop NOT NULL columns the models no longer define.

    A column the models dropped is normally harmless dead weight. But one that
    is NOT NULL with no default rejects every INSERT, because nothing supplies
    a value for it any more - so it has to go. Columns that merely sit unused
    are left alone.
    """
    dropped: list[str] = []
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
            conn.execute(text(
                f'ALTER TABLE "{table.name}" DROP COLUMN "{col["name"]}"'
            ))
            dropped.append(f'-{table.name}.{col["name"]}')
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
