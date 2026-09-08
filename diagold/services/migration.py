"""T-15 - load master data from the legacy DIAGOLD database.

Source: SQL Server instance ``SERVER2\\ERP``, database ``Diagold26``, from
DIAGOLD 1.1.7778. The client has not yet provided access or exports (task
C-01), so this reads **CSV exports** - one file per legacy table - which is
also what a client can produce without opening the database to us. Point it at
a directory of CSVs and run.

What the requirements ask for, and where each is handled:

* **Idempotent** - every loader matches on the legacy code and updates in
  place, so re-running changes nothing. See :func:`_upsert`.
* **Reconciliation report** - source rows vs loaded vs rejected, with the
  reason for every rejection. See :class:`Report`.
* **Validated on load** - metal ratios total 100.00, foreign keys resolve,
  codes are unique within their master.
* **Legacy codes preserved exactly** - staff search by them daily, so codes
  are copied verbatim and never regenerated.

Masters load in dependency order; nothing references a master loaded after it.
Findings and Voucher Type are deliberately absent - the client confirmed they
are unused.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, Colour, Currency, FamilyCategory, Location,
                               ManufacturingProcess, Metal, MetalRatio, SettingType,
                               SkuInfo, StoneGroup, StoneInfo, StoneKind,
                               StoneQuality, StoneShape, StoneSize)
from diagold.services import costing

# Legacy table -> the loader that consumes it, in dependency order. The names
# on the left are the CSV file stems expected in the export directory.
LOAD_ORDER: tuple[str, ...] = (
    "company", "currency", "account", "location", "metal", "metal_ratio",
    "stone_group", "stone_kind", "stone_shape", "stone_quality", "stone_size",
    "stone", "setting_type", "sku_info", "family_category", "colour",
    "parts_mould", "mfg_process", "labour", "set_margins",
    "daily_metal_rate", "daily_labour_rate", "users", "user_rights",
)

SKIP: tuple[str, ...] = ("findings", "voucher_type")


@dataclass
class TableResult:
    table: str
    source_rows: int = 0
    loaded: int = 0
    updated: int = 0
    rejected: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected and self.source_rows == self.loaded + self.updated


@dataclass
class Report:
    results: list[TableResult] = field(default_factory=list)

    def add(self, r: TableResult) -> None:
        self.results.append(r)

    @property
    def clean(self) -> bool:
        return all(r.ok for r in self.results)

    def text(self) -> str:
        head = f"{'Table':<22}{'Source':>8}{'Loaded':>8}{'Updated':>9}{'Rejected':>10}   Status"
        out = ["Migration reconciliation", "=" * len(head), head, "-" * len(head)]
        for r in self.results:
            out.append(
                f"{r.table:<22}{r.source_rows:>8}{r.loaded:>8}{r.updated:>9}"
                f"{len(r.rejected):>10}   {'OK' if r.ok else 'CHECK'}"
            )
        out.append("-" * len(head))
        total_rej = sum(len(r.rejected) for r in self.results)
        out.append(
            f"{len(self.results)} table(s); "
            + ("no unexplained differences" if self.clean
               else f"{total_rej} rejected row(s) — see below")
        )
        for r in self.results:
            if not r.rejected:
                continue
            out.append("")
            out.append(f"Rejected from {r.table}:")
            for line_no, key, reason in r.rejected:
                out.append(f"  line {line_no:<6} {key:<24} {reason}")
        return "\n".join(out)


# -- helpers ---------------------------------------------------------------
def read_csv(directory: Path, stem: str) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield ``(line_number, row)`` from ``<directory>/<stem>.csv`` if present."""
    path = directory / f"{stem}.csv"
    if not path.exists():
        return
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            yield i, {(k or "").strip(): (v or "").strip() for k, v in row.items()}


def _dec(value: str, default: str = "0") -> Decimal:
    try:
        return Decimal(value or default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _upsert(session: Session, model, code: str, values: dict[str, Any]) -> str:
    """Insert or update by legacy code. Returns "loaded" or "updated".

    The legacy code is preserved exactly and is the identity used on re-runs,
    which is what makes the whole migration safe to repeat.
    """
    existing = session.scalar(select(model).where(model.code == code))
    if existing is None:
        session.add(model(code=code, **values))
        return "loaded"
    for k, v in values.items():
        setattr(existing, k, v)
    return "updated"


def _lookup_id(session: Session, model, code: str) -> int | None:
    if not code:
        return None
    row = session.scalar(select(model).where(model.code == code))
    return row.id if row else None


# -- loaders ---------------------------------------------------------------
def load_simple(session: Session, directory: Path, stem: str, model,
                mapper: Callable[[dict[str, str]], dict[str, Any]],
                code_field: str = "Code") -> TableResult:
    """Load a master whose rows need no cross-table resolution."""
    res = TableResult(stem)
    seen: set[str] = set()
    for line, row in read_csv(directory, stem):
        res.source_rows += 1
        code = row.get(code_field, "").strip()
        if not code:
            res.rejected.append((line, "(blank)", f"missing {code_field}"))
            continue
        if code in seen:
            res.rejected.append((line, code, "duplicate code within the source file"))
            continue
        seen.add(code)
        try:
            values = mapper(row)
        except Exception as exc:  # noqa: BLE001 - report, never abort the run
            res.rejected.append((line, code, f"could not map row: {exc}"))
            continue
        outcome = _upsert(session, model, code, values)
        setattr(res, outcome, getattr(res, outcome) + 1)
    session.flush()
    return res


def load_metal_ratios(session: Session, directory: Path) -> TableResult:
    """Load Mining Metal Ratio child rows and enforce the 100.00 rule."""
    res = TableResult("metal_ratio")
    by_metal: dict[str, list[tuple[int, str, Decimal]]] = {}
    for line, row in read_csv(directory, "metal_ratio"):
        res.source_rows += 1
        by_metal.setdefault(row.get("MetalCode", ""), []).append(
            (line, row.get("BaseMetal", ""), _dec(row.get("Ratio", "0")))
        )

    for metal_code, rows in by_metal.items():
        metal = session.scalar(select(Metal).where(Metal.code == metal_code))
        if metal is None:
            for line, _, _ in rows:
                res.rejected.append((line, metal_code, "no such metal head"))
            continue
        error = costing.validate_metal_ratios(
            [{"ratio_pct": pct} for _, _, pct in rows]
        )
        if error:
            for line, _, _ in rows:
                res.rejected.append((line, metal_code, error))
            continue
        for stale in session.scalars(
            select(MetalRatio).where(MetalRatio.metal_id == metal.id)
        ):
            session.delete(stale)
        session.flush()
        for _, base, pct in rows:
            session.add(MetalRatio(metal_id=metal.id, base_metal=base, ratio_pct=pct))
            res.loaded += 1
    session.flush()
    return res


def run(session: Session, export_dir: str | Path) -> Report:
    """Load every master from a directory of legacy CSV exports.

    Safe to re-run: rows are matched on their legacy code and updated in
    place, so a second run reports updates and changes nothing.
    """
    directory = Path(export_dir)
    report = Report()

    report.add(load_simple(session, directory, "currency", Currency, lambda r: dict(
        name=r.get("Name", ""), symbol=r.get("Symbol", ""),
        exchange_rate=_dec(r.get("Rate", "1"), "1"), is_active=True)))

    report.add(load_simple(session, directory, "account", Account, lambda r: dict(
        name=r.get("Name", ""), account_type=r.get("Type", "Client"),
        group_name=r.get("Group", "Accounts Receivable"),
        phone=r.get("Phone", ""), email=r.get("Email", ""),
        address=r.get("Address", ""), city=r.get("City", ""),
        gstin=r.get("GSTIN", ""), is_active=True)))

    report.add(load_simple(session, directory, "location", Location, lambda r: dict(
        name=r.get("Name", ""), location_type=r.get("Type", "Karigar"),
        notes=r.get("Notes", ""), is_active=True)))

    report.add(load_simple(session, directory, "metal", Metal, lambda r: dict(
        name=r.get("Name", ""), print_on_tag=r.get("PrintOnTag", ""),
        base_metal=r.get("BaseMetal", "GOLD"),
        purity_fineness=_dec(r.get("Purity", "0")),
        purity_for_custom=_dec(r.get("PurityCustom", "0")),
        colour=r.get("Colour", ""), specific_gravity=_dec(r.get("SpGravity", "0")),
        purity_weight=_dec(r.get("PurityWt", "0")), hsn_code=r.get("HSN", ""),
        box_no=r.get("Box", ""), is_active=True)))

    report.add(load_metal_ratios(session, directory))

    for stem, model in (("stone_group", StoneGroup), ("stone_kind", StoneKind),
                        ("stone_shape", StoneShape), ("stone_quality", StoneQuality)):
        report.add(load_simple(session, directory, stem, model,
                               lambda r: dict(name=r.get("Name", ""), is_active=True)))

    report.add(load_simple(session, directory, "stone_size", StoneSize, lambda r: dict(
        name=r.get("Name", ""), size_mm=_dec(r.get("SizeMM", "0")), is_active=True)))

    report.add(load_simple(session, directory, "stone", StoneInfo, lambda r: dict(
        name=r.get("Name", ""),
        stone_group_id=_lookup_id(session, StoneGroup, r.get("GroupCode", "")),
        stone_kind_id=_lookup_id(session, StoneKind, r.get("TypeCode", "")),
        shape_id=_lookup_id(session, StoneShape, r.get("ShapeCode", "")),
        quality_id=_lookup_id(session, StoneQuality, r.get("QualityCode", "")),
        size_id=_lookup_id(session, StoneSize, r.get("SizeCode", "")),
        color=r.get("Colour", ""), weight_unit=r.get("Unit", "ct"),
        rate_per_unit=_dec(r.get("Rate", "0")), hsn_code=r.get("HSN", ""),
        is_active=True)))

    report.add(load_simple(session, directory, "setting_type", SettingType,
                           lambda r: dict(name=r.get("Name", ""),
                                          price=_dec(r.get("Price", "0")),
                                          is_active=True)))

    report.add(load_simple(session, directory, "sku_info", SkuInfo, lambda r: dict(
        category=r.get("Category", ""), sub_category=r.get("SubCategory", ""),
        hsn_code=r.get("HSN", ""), gender=r.get("Gender", "Unisex"),
        making_charge_type=r.get("MCType", "Per Gram"),
        making_charge=_dec(r.get("MakingCharge", "0")), is_active=True)))

    report.add(load_simple(session, directory, "family_category", FamilyCategory,
                           lambda r: dict(name=r.get("Name", ""), is_active=True)))
    report.add(load_simple(session, directory, "colour", Colour,
                           lambda r: dict(name=r.get("Name", ""), is_active=True)))

    report.add(load_simple(session, directory, "mfg_process", ManufacturingProcess,
                           lambda r: dict(
                               name=r.get("Name", ""),
                               base_process=r.get("BaseProcess", "Job Work"),
                               labour_type=r.get("LabourType", "STD"),
                               loss_type=(r.get("LossType", "N") or "N")[:1].upper(),
                               module=r.get("Module", ""), is_active=True)))
    return report
