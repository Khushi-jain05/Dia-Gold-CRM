"""Go-live import from the legacy DIAGOLD database (11 Nov 2026).

The client sent ``dg_new.bak`` - a SQL Server backup of ``Diagold26`` (the
2026-27 year, opened 1 Apr 2026). Restored on any SQL Server (the office
SERVER2\\ERP, or a test container), this reads it directly and loads it into
our database, whichever that is.

Rules, the same as every import in this app:

* **Only adds and fills.** A legacy record already here (matched by its
  legacy ID from an earlier run, else by name / code ignoring case and extra
  spaces) is never changed - only its blank fields are filled. Where both
  have a value and they differ, the report lists it for a person to decide.
  Settings agreed with the client in our sessions are not overwritten.
* **Re-runnable.** Every legacy row is linked (``LegacyLink``) to the row it
  became, so importing a newer backup at cut-over updates the same rows.
* **Nothing guessed silently.** A row that cannot be placed is skipped with
  its reason in the report.

Legacy tables are named by number; what each holds was read off the data:
999999911 accounts, 999999991 Product SKUs, 999999992 SKU stones,
999999995 SKU labour, 888888811/12/13/15 opening ready stock (voucher /
piece / stones / labour).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, AccountGroup, Colour, Company, Currency,
                               FamilyCategory, LegacyLink, Location, ManufacturingProcess,
                               Metal, MetalRatio, PartMould, SettingType, StoneGroup,
                               StoneInfo, StoneKind, StoneQuality, StoneShape, StoneSize,
                               User)
from diagold.db.models.sku import Item, ProductSku, ProductSkuStone, StoneMaster, StoneSku

ZERO = Decimal("0")


# --------------------------------------------------------------------------
# Reading the legacy database
# --------------------------------------------------------------------------
class Legacy:
    """A read-only view of the restored legacy database."""

    def __init__(self, server: str, database: str = "Diagold26", user: str = "",
                 password: str = "", port: int | None = None) -> None:
        import pymssql
        kw: dict[str, Any] = {"server": server, "database": database, "charset": "utf8",
                              "login_timeout": 15}
        if user:
            kw.update(user=user, password=password)
        if port:
            kw["port"] = port
        self.conn = pymssql.connect(**kw)
        self.database = database

    def rows(self, sql: str) -> list[dict[str, Any]]:
        cur = self.conn.cursor(as_dict=True)
        cur.execute(sql)
        out = cur.fetchall()
        cur.close()
        return out

    def table(self, name: str, where: str = "", order: str = "") -> list[dict[str, Any]]:
        sql = f"SELECT * FROM [{name}]"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        return self.rows(sql)

    def close(self) -> None:
        self.conn.close()


def text(v: Any) -> str:
    """A legacy text cell: trimmed, single-spaced, "-" (the legacy blank) as ""."""
    if v is None:
        return ""
    s = " ".join(str(v).split())
    return "" if s in ("-", "—") else s


def num(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return ZERO


def whole(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def yes(v: Any) -> bool:
    return str(v).strip().lower() in ("yes", "y", "1", "true")


def key(s: str) -> str:
    """How two names are compared: case and spacing ignored."""
    return " ".join((s or "").split()).upper()


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------
@dataclass
class Result:
    table: str
    source: int = 0
    added: int = 0
    matched: int = 0
    filled: int = 0
    skipped: list[str] = field(default_factory=list)
    differs: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def text(self) -> str:
        head = f"{'Legacy table':<34}{'Rows':>7}{'Added':>7}{'Already':>9}{'Filled':>8}{'Skipped':>9}"
        out = ["Legacy import", "=" * len(head), head, "-" * len(head)]
        for r in self.results:
            out.append(f"{r.table:<34}{r.source:>7}{r.added:>7}{r.matched:>9}{r.filled:>8}"
                       f"{len(r.skipped):>9}")
        for r in self.results:
            if r.skipped:
                out += ["", f"{r.table} - skipped:"] + [f"  {s}" for s in r.skipped]
            if r.partial:
                out += ["", f"{r.table} - loaded, but:"] + [f"  {p}" for p in r.partial]
            if r.changed:
                out += ["", f"{r.table} - changed to the legacy value:"] + [f"  {c}" for c in r.changed]
            if r.differs:
                out += ["", f"{r.table} - kept ours, legacy differs:"] + [f"  {d}" for d in r.differs]
        if self.notes:
            out += ["", "Notes:"] + [f"  {n}" for n in self.notes]
        return "\n".join(out)


# --------------------------------------------------------------------------
# Matching and filling
# --------------------------------------------------------------------------
def _blank(v: Any) -> bool:
    if v is None or isinstance(v, bool):
        return v is None
    if isinstance(v, (int, float, Decimal)):
        return v == 0
    return str(v).strip() == ""


class Importer:
    def __init__(self, session: Session, legacy: Legacy) -> None:
        self.s = session
        self.L = legacy
        self.report = Report()
        self._links: dict[tuple[str, str], int] = {
            (k, lid): t for k, lid, t in session.execute(
                select(LegacyLink.kind, LegacyLink.legacy_id, LegacyLink.target_id))}
        self.ids: dict[str, dict[Any, Any]] = {}   # kind -> legacy id -> our row
        self._indexes: dict[tuple[Any, str], dict[str, Any]] = {}

    # -- links ---------------------------------------------------------------
    def link(self, kind: str, lid: Any, row) -> None:
        k = (kind, str(lid))
        if self._links.get(k) == row.id:
            return
        if k in self._links:
            ln = self.s.scalar(select(LegacyLink).where(LegacyLink.kind == kind,
                                                        LegacyLink.legacy_id == str(lid)))
            ln.target_id = row.id
        else:
            self.s.add(LegacyLink(kind=kind, legacy_id=str(lid), target_id=row.id))
        self._links[k] = row.id

    def linked(self, model, kind: str, lid: Any):
        t = self._links.get((kind, str(lid)))
        return self.s.get(model, t) if t else None

    def _index(self, model, attr: str) -> dict[str, Any]:
        """Every row of ``model`` by key(attr) - read once per run."""
        ix = self._indexes.get((model, attr))
        if ix is None:
            ix = {}
            for row in self.s.scalars(select(model).order_by(model.id)):
                ix.setdefault(key(getattr(row, attr) or ""), row)
            self._indexes[(model, attr)] = ix
        return ix

    def _remember(self, row) -> None:
        for (model, attr), ix in self._indexes.items():
            if isinstance(row, model):
                ix.setdefault(key(getattr(row, attr) or ""), row)

    def free_code(self, model, wanted: str, size: int, attr: str = "code") -> str:
        """``wanted`` if no other row has it, else wanted-2, wanted-3 ..."""
        base = (wanted or "X").strip()[:size] or "X"
        taken = self._index(model, attr)
        code, n = base, 1
        while key(code) in taken:
            n += 1
            tail = f"-{n}"
            code = base[: size - len(tail)] + tail
        return code

    def by_name(self, model, name: str, attr: str = "name"):
        return self._index(model, attr).get(key(name)) if name else None

    def put(self, res: Result, kind: str, lid: Any, model, values: dict[str, Any],
            find: Callable[[], Any], label: str, compare: Iterable[str] = (),
            code_attr: str | None = "code", code_size: int = 24,
            prefer: Iterable[str] = (), same: Callable[[str, Any, Any], bool] | None = None):
        """Add the legacy row, or fill the blanks of the one already here.

        ``compare``: fields where a difference is reported and ours kept.
        ``prefer``: fields where the legacy value replaces ours (reported) -
        ours was a stand-in until the legacy data arrived.
        """
        row = self.linked(model, kind, lid) or find()
        if row is None:
            if code_attr and code_attr in values:
                values[code_attr] = self.free_code(model, values[code_attr] or label,
                                                   code_size, code_attr)
            row = model(**values)
            self.s.add(row)
            self.s.flush()
            self._remember(row)
            res.added += 1
        else:
            res.matched += 1
            filled = False
            for k, v in values.items():
                if k == code_attr:
                    continue
                have = getattr(row, k)
                if _blank(have) and not _blank(v):
                    setattr(row, k, v)
                    filled = True
                elif _blank(v) or (same or (lambda _k, a, b: _same(a, b)))(k, have, v):
                    continue
                elif k in prefer:
                    res.changed.append(f"{label}: {k} {have!s} -> {v!s}")
                    setattr(row, k, v)
                elif k in compare:
                    res.differs.append(f"{label}: {k} ours {have!s} / legacy {v!s}")
            if filled:
                res.filled += 1
        self.link(kind, lid, row)
        self.ids.setdefault(kind, {})[lid] = row
        return row

    # -- the masters, in dependency order -------------------------------------
    def run_masters(self) -> Report:
        for step in (self.company, self.currencies, self.colours, self.metals,
                     self.locations, self.stone_groups, self.stone_shapes,
                     self.stone_qualities, self.stone_kinds, self.stone_sizes,
                     self.stones, self.setting_types, self.stone_skus, self.processes,
                     self.families, self.items, self.moulds, self.account_groups,
                     self.accounts, self.users):
            step()
            self.s.flush()
        return self.report

    def run_all(self, openings_as_of=None) -> Report:
        self.run_masters()
        self.product_skus()
        self.s.flush()
        if openings_as_of is not None:
            _OpeningStep.run(self, openings_as_of)
            self.s.flush()
        return self.report

    def product_skus(self) -> None:
        _SkuStep.run(self)

    def _res(self, table: str, rows: list) -> Result:
        r = Result(table, source=len(rows))
        self.report.results.append(r)
        return r

    def company(self) -> None:
        rows = self.L.table("CompanyMaster")
        res = self._res("CompanyMaster", rows)
        for c in rows[:1]:
            co = self.s.scalar(select(Company).order_by(Company.id))
            vals = {"legal_name": text(c.get("CompanyName")),
                    "address_line1": text(c.get("Address1")),
                    "address_line2": text(c.get("Address2")),
                    "city": text(c.get("City")), "state": text(c.get("State")),
                    "country": text(c.get("Country")).title(),
                    "pincode": text(c.get("PIN")).strip("*"),
                    "phone": text(c.get("Phone")), "email": text(c.get("Email")).lower()}
            self.put(res, "company", c["CompanyID"], Company,
                     {"name": "Dia Gold", **vals}, lambda co=co: co, "Company",
                     code_attr=None)

    def currencies(self) -> None:
        rows = [r for r in self.L.table("CurrencyMaster") if text(r["CurrencyName"])]
        res = self._res("CurrencyMaster", rows)
        for r in rows:
            name, code = text(r["CurrencyName"]), text(r["CurrencyCode"]).upper()
            if key(name) in ("RS", "INR", "RUPEES") or code in ("RS", "INR"):
                code, name = "INR", "Indian Rupee"
            elif code == "$" or "DOLLAR" in key(name):
                code = "USD"
            elif key(name) == "EURO":
                code = "EUR"
            self.put(res, "currency", r["CurrencyID"], Currency,
                     {"code": code, "name": name.title(), "symbol": text(r["CurrencyCode"])},
                     lambda c=code: self.by_name(Currency, c, "code"),
                     name, code_size=8)

    def colours(self) -> None:
        rows = [r for r in self.L.table("ColorMaster") if text(r["ColorName"])]
        res = self._res("ColorMaster", rows)
        for r in rows:
            name, code = text(r["ColorName"]), text(r["ColorCode"]).upper()
            self.put(res, "colour", r["ColorID"], Colour,
                     {"code": code, "name": name.title(), "is_active": yes(r["IsActive"])},
                     lambda n=name, c=code: self.by_name(Colour, n)
                     or self.by_name(Colour, c, "code"),
                     name)

    def metals(self) -> None:
        bases = {r["BaseMetalID"]: text(r["BaseMetalName"]).upper()
                 for r in self.L.table("BaseMetalMaster")}
        colour = {r["ColorID"]: text(r["ColorCode"]).upper() for r in self.L.table("ColorMaster")}
        ratios: dict[int, list[tuple[str, Decimal]]] = {}
        for r in self.L.table("MetalRatio", order="MetalID, Srlno"):
            ratios.setdefault(r["MetalID"], []).append(
                (bases.get(r["BaseMetalID"], ""), num(r["Ratio"])))
        rows = [r for r in self.L.table("MetalMaster", order="MetalID") if r["MetalID"] > 0]
        res = self._res("MetalMaster", rows)
        for r in rows:
            name = text(r["MetalName"])
            row = self.put(res, "metal", r["MetalID"], Metal, {
                "name": name, "code": text(r["MetalCode"]).upper().replace(" ", ""),
                "purity_fineness": num(r["Fineness"]),
                "base_metal": bases.get(r["BaseMetalID"], "") or "GOLD",
                "print_on_tag": text(r["CodeOnTag"]), "description": text(r["Description"]),
                "specific_gravity": num(r["SPGravity"]), "hsn_code": text(r["M_HSN"]),
                "box_no": text(r["boxno"]), "colour": colour.get(r["ColorID"], ""),
                "is_effects_net_wt": yes(r["IsNetWt"]),
                "is_active": r["IsActive"] is None or yes(r["IsActive"]),
            }, lambda n=name: self.by_name(Metal, n), name,
                # Ours was read off the name (master sheet, Q94); the legacy
                # figure is what the client's system weighs fine metal by.
                prefer=("purity_fineness",), compare=("base_metal",), same=_same_purity)
            if not row.ratios and ratios.get(r["MetalID"]):
                for base, pct in ratios[r["MetalID"]]:
                    row.ratios.append(MetalRatio(base_metal=base or "GOLD", ratio_pct=pct))

    def locations(self) -> None:
        rows = [r for r in self.L.table("LocationMaster", order="LocationID")
                if text(r["LocationName"])]
        res = self._res("LocationMaster", rows)
        for r in rows:
            name = text(r["LocationName"])
            self.put(res, "location", r["LocationID"], Location, {
                "code": key(text(r["LocationCode"]) or name).replace(" ", ""), "name": name,
                "location_type": "Logical" if key(name) == "PRIMARY" else "Karigar",
                "is_active": yes(r["isActive"]),
            }, lambda n=name: self.by_name(Location, n), name)

    # The legacy groups by our names.
    GROUP_ALIAS = {"DIAMOND": "Diamond", "POLKI": "Polki", "COLOR STONE": "Colour Stone",
                   "COLOUR STONE": "Colour Stone"}

    def stone_groups(self) -> None:
        rows = [r for r in self.L.table("StoneGroupMaster") if text(r["StoneGroupName"])]
        res = self._res("StoneGroupMaster", rows)
        for r in rows:
            name = self.GROUP_ALIAS.get(key(text(r["StoneGroupName"])),
                                        text(r["StoneGroupName"]).title())
            self.put(res, "stone_group", r["StoneGroupID"], StoneGroup, {
                "code": text(r["StoneGroupCode"]).upper(), "name": name,
                "is_active": yes(r["isActive"])}, lambda n=name: self.by_name(StoneGroup, n), name)

    def _simple(self, table: str, kind: str, model, id_col: str, name_col: str,
                code_col: str | None, active_col: str | None = "IsActive") -> None:
        rows = [r for r in self.L.table(table, order=id_col) if text(r[name_col])]
        res = self._res(table, rows)
        for r in rows:
            name = text(r[name_col])
            code = text(r[code_col]).upper() if code_col else key(name)
            vals = {"code": code or key(name), "name": name}
            if active_col:
                vals["is_active"] = yes(r[active_col])
            self.put(res, kind, r[id_col], model, vals,
                     lambda n=name: self.by_name(model, n), name)

    def stone_shapes(self) -> None:
        self._simple("ShapeMaster", "stone_shape", StoneShape, "ShapeID", "ShapeName",
                     "ShapeCode")

    def stone_qualities(self) -> None:
        self._simple("QualityMaster", "stone_quality", StoneQuality, "QualityID",
                     "QualityName", "QualityCode")

    def stone_kinds(self) -> None:
        self._simple("TypeMaster", "stone_kind", StoneKind, "TypeID", "TypeName", "TypeCode",
                     "isActive")

    def stone_sizes(self) -> None:
        self._simple("SizeMaster", "stone_size", StoneSize, "SizeID", "SizeName", None)

    def stones(self) -> None:
        rows = [r for r in self.L.table("StoneMaster", order="StoneID") if text(r["StoneName"])]
        res = self._res("StoneMaster", rows)
        groups = self.ids.get("stone_group", {})
        colour_stone = self.by_name(StoneGroup, "Colour Stone")
        for r in rows:
            name = text(r["StoneName"])
            g = groups.get(r["StoneGroupID"]) or colour_stone
            if g is None:
                res.skipped.append(f"{name}: no stone group")
                continue
            self.put(res, "stone", r["StoneID"], StoneInfo, {
                "code": text(r["StoneCode"]).upper(), "name": name, "stone_group_id": g.id,
                "is_active": yes(r["isActive"])}, lambda n=name: self.by_name(StoneInfo, n), name)

    def setting_types(self) -> None:
        rows = [r for r in self.L.table("SettingTypeMaster", order="SettingTypeID")
                if text(r["SettingTypeName"])]
        res = self._res("SettingTypeMaster", rows)
        for r in rows:
            name = text(r["SettingTypeName"])
            self.put(res, "setting_type", r["SettingTypeID"], SettingType, {
                "code": text(r["SettingTypeCode"]).upper(), "name": name,
                "price": num(r["Price"]), "is_active": yes(r["IsActive"])},
                lambda n=name: self.by_name(SettingType, n), name, compare=("price",))

    def stone_skus(self) -> None:
        """StoneSkuMaster -> Stone SKU (our StoneMaster); StoneSkuSizeDetail -> its sizes."""
        from diagold.services.stone_master import sync_sizes
        names = {kind: {r[c]: text(r[n]) for r in self.L.table(t)}
                 for kind, t, c, n in (("stone", "StoneMaster", "StoneID", "StoneName"),
                                       ("shape", "ShapeMaster", "ShapeID", "ShapeName"),
                                       ("type", "TypeMaster", "TypeID", "TypeName"),
                                       ("quality", "QualityMaster", "QualityID", "QualityName"),
                                       ("color", "StoneColorMaster", "StoneColorID",
                                        "StoneColorName"),
                                       ("size", "SizeMaster", "SizeID", "SizeName"),
                                       ("unit", "UnitMaster", "UnitID", "UnitName"))}
        rows = [r for r in self.L.table("StoneSkuMaster", order="StoneskuID")
                if text(r["StoneSkuName"])]
        res = self._res("StoneSkuMaster (Stone SKU)", rows)
        for r in rows:
            name = text(r["StoneSkuName"])
            self.put(res, "stone_sku", r["StoneskuID"], StoneMaster, {
                "name": name, "stone": names["stone"].get(r["StoneID"], ""),
                "shape": names["shape"].get(r["ShapeID"], ""),
                "stone_type": names["type"].get(r["TypeID"], ""),
                "quality": names["quality"].get(r["QualityID"], ""),
                "color": names["color"].get(r["StoneColorID"], ""),
                "shelf_no": text(r["ShelfNo"]), "description": text(r["Description"]),
                "add_in_netwt": yes(r["isAddInNet"]), "is_active": yes(r["isActive"]),
            }, lambda n=name: self.by_name(StoneMaster, n), name, code_attr=None)

        rows = self.L.table("StoneSkuSizeDetail", order="StoneSkuID, Sno")
        res = self._res("StoneSkuSizeDetail (sizes)", rows)
        masters = self.ids.get("stone_sku", {})
        touched: dict[int, StoneMaster] = {}
        for r in rows:
            m = masters.get(r["StoneSkuID"])
            size = names["size"].get(r["SizeID"], "")
            label = f"{m.name if m else r['StoneSkuID']} {size or r['Range']}"
            if m is None:
                res.skipped.append(f"{label}: Stone SKU {r['StoneSkuID']} not in StoneSkuMaster")
                continue
            rng = text(r["Range"])

            def find(m=m, size=size, rng=rng):
                same = [s for s in m.sizes if key(s.size) == key(size)]
                return next((s for s in same if key(s.range_label) == key(rng)),
                            same[0] if same else None)
            row = self.put(res, "stone_size_row", f"{r['StoneSkuID']}:{r['SizeID']}:{rng}",
                           StoneSku, {
                               "master_id": m.id, "stone": m.name, "size": size,
                               "range_label": rng, "cost_price": num(r["BasePrice"]),
                               "sale_price": num(r["Price"]),
                               "per": names["unit"].get(r["SizeUnitID"], "") or "Cts",
                               "wt_per_pcs": num(r["WtPerPcs"]),
                               "is_active": r["isActive"] is None or yes(r["isActive"]),
                           }, find, label, compare=("cost_price",), code_attr=None)
            if row not in m.sizes:
                m.sizes.append(row)
            touched[m.id] = m
        self.s.flush()
        for m in touched.values():
            sync_sizes(self.s, m)

    LOSS = {"ISS WT": "I", "DIFF WT": "F", "RCVD WT": "N"}

    def processes(self) -> None:
        bases = {r["MasterProcessID"]: text(r["MasterProcessName"])
                 for r in self.L.table("XXXXXXXXX")}
        rows = [r for r in self.L.table("ProcessMaster", order="ProcessID")
                if r["ProcessID"] > 0 and text(r["ProcessName"])]
        res = self._res("ProcessMaster", rows)
        for r in rows:
            name = text(r["ProcessName"])
            self.put(res, "process", r["ProcessID"], ManufacturingProcess, {
                "code": key(name).replace(" ", "")[:12], "name": name,
                "base_process": bases.get(r["MasterProcessID"], "") or "Job Work",
                "loss_type": self.LOSS.get(key(text(r["LossType"])), ""),
                "labour_accounting": bool(r["isLabAc"]), "order_srno": whole(r["orderByCol"]),
                "short_code": text(r["ProcessCode"])[:8],
                "fill_auto_stone": bool(r["FillStone"]), "fill_auto_mould": bool(r["FillMould"]),
                "check_weight_tolerance": bool(r["isCheckWt"]),
                "is_print_vr": bool(r["isPrintVr"]), "is_active": yes(r["isActive"]),
            }, lambda n=name: self.by_name(ManufacturingProcess, n), name,
                # The route string ("HM RHM PP ST FP fs") is written in the
                # legacy codes. The loss basis stays as agreed in our sessions.
                prefer=("short_code",), code_size=24)

    def families(self) -> None:
        self._simple("FamilyMaster", "family", FamilyCategory, "FamilyID", "FamilyName",
                     "FamilyCode", "isActive")

    def items(self) -> None:
        rows = [r for r in self.L.table("ItemMaster", order="ItemID") if text(r["ItemName"])]
        res = self._res("ItemMaster", rows)
        for r in rows:
            name = text(r["ItemName"])
            self.put(res, "item", r["ItemID"], Item, {
                "code": text(r["ItemCode"]).upper(), "name": name,
                "unit": text(r["PcsPair"]) or "Pcs", "pcs": whole(r["ipcs"]) or 1,
                "virtual_design_code": text(r["DesignCode"]), "mould_code": text(r["mCode"]),
                "shopify_code": text(r["shopifycode"]), "is_active": yes(r["isActive"]),
            }, lambda n=name: self.by_name(Item, n), name, code_size=32)

    def moulds(self) -> None:
        rows = [r for r in self.L.table("MouldMaster", order="MouldID") if text(r["MouldName"])]
        res = self._res("MouldMaster", rows)
        items, metals = self.ids.get("item", {}), self.ids.get("metal", {})
        families = self.ids.get("family", {})
        for r in rows:
            name = text(r["MouldName"])
            item = items.get(r["ItemID"])
            metal, fam = metals.get(r["MetalID"]), families.get(r["FamilyID"])
            self.put(res, "mould", r["MouldID"], PartMould, {
                "code": name.upper(), "name": item.name if item else name,
                "description": text(r["Description"]),
                "wax_weight_per_pcs": num(r["WtPerPcsWax"]), "weight": num(r["WtPerPcsMetal"]),
                "metal_id": metal.id if metal else None, "family_id": fam.id if fam else None,
                "l_price_gms": num(r["LPrice"]), "cad_file_desc": text(r["CADDesc"]),
                "part_no": text(r["PartNo"]), "vendor_code": text(r["vrndorcode"]),
                "is_active": yes(r["isActive"]),
            }, lambda n=name: self.by_name(PartMould, n, "code"), name)

    NATURE = {1001: "Assets", 1002: "Liabilities", 1003: "Income", 1004: "Expenses"}

    def account_groups(self) -> None:
        rows = [r for r in self.L.table("GroupMaster", order="AccGroupId")
                if r["AccGroupId"] > 0 and text(r["AccGroupName"])]
        res = self._res("GroupMaster (account groups)", rows)
        for r in rows:
            name = text(r["AccGroupName"])
            self.put(res, "account_group", r["AccGroupId"], AccountGroup, {
                "name": name, "code": text(r["AccGroupCode"]).upper(),
                "nature": self.NATURE.get(r["PrmGroupID"], ""), "index_no": whole(r["MyIndex"]),
                "sub_ledger_required": bool(r["isSubLadger"]),
            }, lambda n=name: self.by_name(AccountGroup, n), name, code_attr=None)
        groups = self.ids.get("account_group", {})
        for r in rows:          # parents once every group exists
            g, parent = groups.get(r["AccGroupId"]), groups.get(r["ParentAccGroupId"])
            if g is not None and parent is not None and g.parent_id is None and parent is not g:
                g.parent_id = parent.id

    # Legacy "inventory group" -> our account type.
    ACCOUNT_TYPE = {1001: "Worker", 1002: "Client", 1003: "Client", 1007: "Designer"}

    def accounts(self) -> None:
        groups = self.ids.get("account_group", {})
        currencies = self.ids.get("currency", {})
        rows = self.L.table("999999911", order="AccountID")
        res = self._res("999999911 (accounts)", rows)
        for r in rows:
            name = text(r["AccountName"])
            if r["AccountID"] <= 0:
                res.skipped.append(f"{name}: legacy system ledger (ours has its own)")
                continue
            if not name:
                res.skipped.append(f"account {r['AccountID']}: no name")
                continue
            g = groups.get(r["AccountGroupID"])
            cur = currencies.get(r["CurrencyID"])
            address = ", ".join(a for a in (text(r["Address1"]), text(r["Address2"]),
                                            text(r["Address3"])) if a)
            self.put(res, "account", r["AccountID"], Account, {
                "code": text(r["AccountCode"]).upper() or key(name).replace(" ", "")[:24],
                "name": name,
                "account_type": self.ACCOUNT_TYPE.get(r["InventoryGroupID"], "Accounts"),
                "group_name": g.name if g else "",
                "address": address, "city": text(r["City"]), "state": text(r["State"]),
                "phone": text(r["Phone"]), "email": text(r["Email"]),
                "gstin": text(r["GST"]), "pan": text(r["PANNo"]),
                "currency_code": cur.code if cur else "INR",
                "credit_days": whole(r["CreditDays"]), "credit_limit": num(r["CreditAmt"]),
                "opening_balance": num(r["OPAmt"]),
                "opening_balance_type": text(r["OPDrCr"]) or "Dr",
                "is_active": yes(r["isActive"]),
            }, lambda n=name: self.by_name(Account, n), name,
                compare=("account_type",))

    def users(self) -> None:
        rows = self.L.table("U00000001", order="UserID")
        res = self._res("U00000001 (users)", rows)
        for r in rows:
            name = text(r["UserName"])
            if not name or key(name) == "ADMIN":
                res.skipped.append(f"{name or r['UserID']}: our admin login stays")
                continue
            existing = self.linked(User, "user", r["UserID"]) or self.by_name(User, name,
                                                                                "username")
            if existing is not None:
                res.matched += 1
                self.link("user", r["UserID"], existing)
                continue
            u = User(username=name, full_name=name, password_hash="",
                     mobile_number=text(r["MobileNo"]),
                     is_active=r["isActive"] is None or yes(r["isActive"]))
            u.set_password(str(r["PS"] or ""))
            self.s.add(u)
            self.s.flush()
            self._remember(u)
            self.link("user", r["UserID"], u)
            res.added += 1
        if res.added:
            self.report.notes.append(
                f"{res.added} legacy login(s) added with their legacy password and NO rights - "
                "give each its rights in Master > User Right (the legacy form numbers do not "
                "map to our screens).")


class _SkuStep:
    """Product SKUs with their stones (999999991 + 999999992)."""

    @staticmethod
    def run(imp: "Importer") -> None:
        from diagold.services.stone_master import sync_sizes
        L, s = imp.L, imp.s
        names = {t: {r[c]: text(r[n]) for r in L.table(t)} for t, c, n in (
            ("SubItemMaster", "SubItemID", "SubItemName"),
            ("SKUCategoryMaster", "SKUCategoryID", "SKUCategoryName"),
            ("StyleMaster", "StyleID", "StyleName"),
            ("ItemSizeMaster", "ItemSizeID", "ItemSizeName"),
            ("ChainTypeMaster", "ChainTypeID", "ChainTypeName"),
            ("InscriptionMaster", "InscriptionID", "InscriptionName"),
            ("ColorMaster", "ColorID", "ColorCode"),
            ("SizeMaster", "SizeID", "SizeName"),
            ("UnitMaster", "UnitID", "UnitName"))}
        items, families = imp.ids.get("item", {}), imp.ids.get("family", {})
        metals, masters = imp.ids.get("metal", {}), imp.ids.get("stone_sku", {})
        sizes, settings = imp.ids.get("stone_size", {}), imp.ids.get("setting_type", {})

        rows = L.table("999999991", order="SKUID")
        res = imp._res("999999991 (Product SKUs)", rows)
        stones_by_sku: dict[Any, list[dict]] = {}
        for r in L.table("999999992", order="SkuID, SrlNo"):
            stones_by_sku.setdefault(r["SkuID"], []).append(r)
        sres = imp._res("999999992 (SKU stones)", [x for v in stones_by_sku.values() for x in v])
        nres = imp._res("SKU stone sizes not in StoneSkuSizeDetail", [])

        # A size row by (legacy Stone SKU, legacy size): the ones linked when the
        # sizes loaded, then any of the master's rows of that size.
        by_size: dict[tuple[Any, Any], StoneSku] = {}
        for lid, row in imp.ids.get("stone_size_row", {}).items():
            ssku, size_id, _rng = lid.split(":", 2)
            by_size.setdefault((ssku, size_id), row)
        touched: dict[int, StoneMaster] = {}

        def size_row(r) -> StoneSku | None:
            m = masters.get(r["SSKUID"])
            if m is None:
                return None
            k = (str(int(r["SSKUID"])), str(int(r["SizeID"])))
            row = by_size.get(k)
            if row is None:
                label = names["SizeMaster"].get(int(r["SizeID"]), "")
                row = next((x for x in m.sizes if key(x.size) == key(label)), None)
                if row is None:      # the SKU uses a size the stone's list lacks
                    row = StoneSku(master_id=m.id, stone=m.name, size=label,
                                   cost_price=num(r["BasePrice"]), sale_price=num(r["Price"]),
                                   per=names["UnitMaster"].get(r["UnitID"], "") or "Cts")
                    m.sizes.append(row)
                    s.flush()
                    nres.added += 1
                    nres.source += 1
                    touched[m.id] = m
                by_size[k] = row
            return row

        # SKU codes differing only in inner spaces are separate legacy SKUs, so
        # these match on the exact code (case aside), not on key().
        def ck(c: str) -> str:
            return (c or "").strip().upper()
        have_codes = {ck(c): i for i, c in s.execute(select(ProductSku.id, ProductSku.sku_code))}
        for n, r in enumerate(rows, start=1):
            code = (r["SkuName"] or "").strip()
            if not code:
                res.skipped.append(f"SKU {r['SKUID']}: no name")
                continue
            metal = metals.get(r["MetalID"])
            item, fam = items.get(r["ItemID"]), families.get(r["FamilyID"])
            vals = {
                "sku_code": code, "description": text(r["Description"]),
                "remark": text(r["ProdDesc"]),
                # What the legacy screen prints under the SKU is its ID (6200 on
                # ER-1337) - C-14 answered by the data.
                "tag_price": num(r["SKUID"]),
                "item_id": item.id if item else None,
                "family_id": fam.id if fam else (item.family_id if item else None),
                "metal_id": metal.id if metal else None,
                "metal_fineness": num(metal.purity_fineness) if metal else ZERO,
                "s_item": names["SubItemMaster"].get(r["SubItemID"], ""),
                "category": names["SKUCategoryMaster"].get(r["SKUCategoryID"], ""),
                "style": names["StyleMaster"].get(r["Style2ID"], ""),
                "jewelry_size": names["ItemSizeMaster"].get(r["ItemSizeID"], ""),
                "chain_type": names["ChainTypeMaster"].get(r["ChainTypeID"], ""),
                "inscription": names["InscriptionMaster"].get(r["InscriptionID"], ""),
                "mt_plt_col": names["ColorMaster"].get(r["ColorID"], ""),
                "enamal_col": names["ColorMaster"].get(r["EColorID"], ""),
                "item_pcs": whole(r["TotItemPcs"]) or 1, "design_no": text(r["DesignNo"]),
                "length": text(r["ItemLength"]),
                "mt_loss_pct": num(r["MetalLossP"]), "avg_loss_pct": num(r["AvgLoss"]),
                "gross_weight": num(r["GrossWt"]), "net_weight": num(r["NetWt"]),
                "stamp": text(r["Stamp"]), "snap": text(r["Snap"]),
                "is_rubber": bool(r["ISrubber"]), "is_master": bool(r["ISMaster"]),
                "is_cad": bool(r["ISCAD"]), "is_sizable": bool(r["isResizable"]),
                "upc": text(r["UPC"]), "link_cert": text(r["CERTLink"]),
                "master_sku": text(r["MasterSKU"]), "sku_ref": text(r["RefCode"]),
                "hu_id": text(r["HMID"]), "min_pcs": whole(r["minPcs"]),
                "image_finished": text(r["PictureName"]),
                "cad_stl_file": text(r["CADFileName"]),
                "labour_amount": num(r["LabourTotal"]),
                "finding_labour": num(r["FindingTotal"]),
                "setting_amount": num(r["SettingTotal"]), "extra_amount": num(r["ExtraTotal"]),
                "stone_amount": num(r["StoneTotal"]), "total_rs": num(r["TOTAL"]),
                "is_active": yes(r["IsActive"]),
            }
            sku = imp.linked(ProductSku, "sku", r["SKUID"])
            if sku is None and ck(code) in have_codes:
                sku = s.get(ProductSku, have_codes[ck(code)])
            if sku is None:
                sku = ProductSku(**vals)
                s.add(sku)
                s.flush()
                have_codes[ck(code)] = sku.id
                res.added += 1
            else:
                res.matched += 1
                filled = False
                for k, v in vals.items():
                    if k != "sku_code" and _blank(getattr(sku, k)) and not _blank(v):
                        setattr(sku, k, v)
                        filled = True
                res.filled += filled
            imp.link("sku", r["SKUID"], sku)

            lines = stones_by_sku.get(r["SKUID"], [])
            if lines and sku.stones:
                sres.matched += len(lines)      # its stones are already here
                continue
            for st in lines:
                row = size_row(st)
                if row is None:
                    sres.partial.append(f"{code} line {st['SrlNo']}: no stone link - Stone SKU "
                                        f"{st['SSKUID']} is not in the legacy Stone SKU master")
                size = sizes.get(int(st["SizeID"]))
                stype = settings.get(st["STypeID"])
                sku.stones.append(ProductSkuStone(
                    stone_sku_id=row.id if row else None,
                    description=(f"{row.stone} {row.size}".strip() if row
                                 else f"legacy Stone SKU {st['SSKUID']}"),
                    size_id=size.id if size else None,
                    wt_per_pcs=num(st["WtPerPcs"]), min_wt=num(st["MinWt"]),
                    pieces=whole(st["Pcs"]), weight_cts=num(st["Weight"]),
                    brk_wt_pct=num(st["BreakP"]), cost_price=num(st["BasePrice"]),
                    sale_price=num(st["Price"]),
                    per=names["UnitMaster"].get(st["UnitID"], "") or "Cts",
                    amount=num(st["Amount"]),
                    setting_type_id=stype.id if stype else None))
                sres.added += 1
            if n % 500 == 0:
                s.flush()
        s.flush()
        for m in touched.values():
            sync_sizes(s, m)
        process = L.rows("SELECT COUNT(DISTINCT SkuID) n FROM [999999996] "
                         "WHERE LossP <> 0 OR Labour <> 0")[0]["n"]
        imp.report.notes.append(
            f"{process} SKUs carry a loss % / labour per process (legacy table 999999996). "
            "There is no per-SKU process table here yet - asked the client whether it is "
            "still used; nothing from it is loaded.")
        imp.report.notes.append(
            "Legacy ManualPrice (106 on ER-1337, up to 1,97,237 elsewhere) is not our Manual "
            "Price % (217 on ER-1337's screen) - not loaded, asked the client what it holds.")


class _OpeningStep:
    """Opening stock on the cut-over date - only when asked for (--openings).

    What the legacy database holds is its state when the backup was taken
    (dg_new.bak: 31 Mar 2026), so this is run on the backup taken AT
    cut-over. Ready pieces keep their legacy Stock ID (JewelleryID) as their
    Stock No, so tags already printed still scan.
    """

    @staticmethod
    def run(imp: "Importer", as_of) -> None:
        from diagold.services import settings
        # A legacy piece priced 0 is real stock: the "TAG 0" guard is for new
        # entries, so it is off while the opening loads and put back after.
        guard = settings.opt("stock.refuse_tag_zero", imp.s)
        settings.set_setting(imp.s, "stock.refuse_tag_zero", "0")
        try:
            _OpeningStep.ready_stock(imp, as_of)
        finally:
            settings.set_setting(imp.s, "stock.refuse_tag_zero", guard)
        _OpeningStep.stones(imp, as_of)
        _OpeningStep.metals(imp, as_of)
        _OpeningStep.parties(imp)

    @staticmethod
    def ready_stock(imp: "Importer", as_of) -> None:
        from diagold.db.models import StockItem
        from diagold.services import sales
        from diagold.services.production import ProductionError
        L, s = imp.L, imp.s
        names = {t: {r[c]: text(r[n]) for r in L.table(t)} for t, c, n in (
            ("ColorMaster", "ColorID", "ColorCode"), ("ItemSizeMaster", "ItemSizeID", "ItemSizeName"),
            ("SizeMaster", "SizeID", "SizeName"), ("UnitMaster", "UnitID", "UnitName"),
            ("StoneSkuMaster", "StoneskuID", "StoneSkuName"))}
        in_stock = {r["JID"] for r in L.table("ReadyIds")}
        pieces: dict[Any, list[dict]] = {}
        for r in L.table("888888812", order="MasterID, RowID"):
            if r["JewelleryID"] in in_stock:
                pieces.setdefault(r["MasterID"], []).append(r)
        stones: dict[Any, list[dict]] = {}
        for r in L.table("888888813", order="JewelleryID, SrlNo"):
            stones.setdefault(r["JewelleryID"], []).append(r)
        vouchers = [v for v in L.table("888888811", "FOT = 'RO'", order="MasterID")
                    if v["MasterID"] in pieces]
        res = imp._res("888888811/12/13 (opening ready stock)",
                       [p for v in vouchers for p in pieces[v["MasterID"]]])
        locs, metals = imp.ids.get("location", {}), imp.ids.get("metal", {})
        skus = {int(lid): t for (k, lid), t in imp._links.items() if k == "sku"}
        taken = {n for (n,) in s.execute(select(StockItem.stock_no))}
        for v in vouchers:
            if imp._links.get(("ready_opening", str(v["MasterID"]))):
                res.matched += len(pieces[v["MasterID"]])
                continue
            lines = []
            for r in pieces[v["MasterID"]]:
                loc, metal = locs.get(r["LocationID"]), metals.get(r["MetalID"])
                lines.append({
                    "location_id": loc.id if loc else None,
                    "product_sku_id": skus.get(int(r["SkuID"])),
                    "metal_id": metal.id if metal else None,
                    "colour": names["ColorMaster"].get(r["ColorID"], ""),
                    "size": names["ItemSizeMaster"].get(r["ItemSizeID"], ""),
                    "c_ref": text(r["Cref"]), "pcs": whole(r["Pcs"]) or 1,
                    "gross_wt": num(r["GrossWt"]), "net_wt": num(r["NetWt"]),
                    "fine_wt": num(r["FineWt"]), "metal_rate": num(r["MetalRate"]),
                    "metal_amount": num(r["MetalAmount"]), "stone_amount": num(r["StoneAmount"]),
                    "setting_amount": num(r["SettingAmount"]), "labour": num(r["Labour"]),
                    "total": num(r["TotalValue"]), "price": num(r["TotalValue"]),
                    "huid": text(r["HMID"]), "cert_no": text(r["ItemCertNo"]),
                    "remark": f"Legacy Stock ID {r['JewelleryID']}"
                              + (f", job {r['Jobno']}" if r["Jobno"] else ""),
                    "stones": [{"label": " ".join(x for x in (
                                    names["StoneSkuMaster"].get(st["StoneSkuID"], ""),
                                    names["SizeMaster"].get(st["SizeID"], "")) if x),
                                "size": names["SizeMaster"].get(st["SizeID"], ""),
                                "pcs": whole(st["Pcs"]), "weight": num(st["Weight"]),
                                "unit": names["UnitMaster"].get(st["UnitID"], "") or "Cts",
                                "price": num(st["Price"])}
                               for st in stones.get(r["JewelleryID"], [])],
                    "_jid": int(r["JewelleryID"]),
                })
            try:
                with s.begin_nested():
                    vr = sales.post_ready(s, "rp_opening", {
                        "vr_date": as_of, "ref_no": f"Legacy RO {v['VrNo']}",
                        "remark": text(v["Remark"]) or "Opening from the legacy system"},
                        [{k: x for k, x in ln.items() if k != "_jid"} for ln in lines])
            except ProductionError as exc:
                res.skipped.append(f"RO {v['VrNo']}: {exc}")
                continue
            items = [s.get(StockItem, line.stock_item_id) for line in vr.lines]
            for item in items:          # off the numbers post_ready gave, first
                item.stock_no = -item.id
            s.flush()
            for item, ln in zip(items, lines):
                no = ln["_jid"]
                if no in taken:
                    no = max(taken) + 1
                    res.partial.append(f"Stock ID {ln['_jid']}: number in use, "
                                       f"given Stock No {no}")
                item.stock_no = no
                taken.add(no)
                imp.link("stock_item", ln["_jid"], item)
            imp.link("ready_opening", v["MasterID"], vr)
            res.added += len(lines)
            s.flush()

    @staticmethod
    def stones(imp: "Importer", as_of) -> None:
        from diagold.services.production import post_opening_stock
        L, s = imp.L, imp.s
        rows = L.table("StoneBalanceClosing", order="LocationID, SskuID, SizeID")
        res = imp._res("StoneBalanceClosing (opening stones)", rows)
        size_name = {r["SizeID"]: text(r["SizeName"]) for r in L.table("SizeMaster")}
        masters, locs = imp.ids.get("stone_sku", {}), imp.ids.get("location", {})
        rows_by_size = {}
        for lid, row in imp.ids.get("stone_size_row", {}).items():
            ssku, size_id, _ = lid.split(":", 2)
            rows_by_size.setdefault((ssku, size_id), row)
        skipped_wt: dict[str, Decimal] = {}
        for r in rows:
            kind = text(r["Type"]) or "(blank)"
            wt, pcs = num(r["ClWeight"]), whole(r["ClPcs"])
            if kind != "Actual" or wt < 0 or pcs < 0 or (not wt and not pcs):
                why = kind if kind != "Actual" else ("negative" if wt < 0 or pcs < 0 else "zero")
                skipped_wt[why] = skipped_wt.get(why, ZERO) + wt
                if why != "zero":
                    res.skipped.append(f"{why}: Stone SKU {r['SskuID']} size "
                                       f"{size_name.get(r['SizeID'], r['SizeID'])} at location "
                                       f"{r['LocationID']} {wt} ct / {pcs} pcs")
                continue
            lid = f"{r['SskuID']}:{r['SizeID']}:{r['LocationID']}:{text(r['LotNo'])}"
            if imp._links.get(("stone_opening", lid)):
                res.matched += 1
                continue
            m, loc = masters.get(r["SskuID"]), locs.get(r["LocationID"])
            row = rows_by_size.get((str(int(r["SskuID"])), str(int(r["SizeID"]))))
            if row is None and m is not None:
                row = next((x for x in m.sizes
                            if key(x.size) == key(size_name.get(r["SizeID"], ""))), None)
            if loc is None:
                res.skipped.append(f"location {r['LocationID']} not loaded")
                continue
            mv = post_opening_stock(
                s, loc.id, row.id if row else None, pcs, wt, as_of=as_of,
                group="" if row else "Other", value=num(r["clvalue"]) or None,
                remark=f"Legacy closing, Stone SKU {r['SskuID']}" + (
                    "" if row else " (not in the Stone SKU master)"))
            imp.link("stone_opening", lid, mv)
            res.added += 1
        if skipped_wt:
            imp.report.notes.append(
                "Opening stones not loaded: " + ", ".join(
                    f"{k} {v} ct" for k, v in sorted(skipped_wt.items()) if k != "zero")
                + " - a negative or Breakage / Loss closing is not stock; the legacy figures "
                  "need clearing first (Q69).")

    @staticmethod
    def metals(imp: "Importer", as_of) -> None:
        from diagold.db.models import InvVoucher, InvVoucherLine
        from diagold.services import inventory as INV
        L, s = imp.L, imp.s
        rows = L.table("MetalBalanceClosing", order="LocationID, MetalID")
        res = imp._res("MetalBalanceClosing (opening metal)", rows)
        metals, locs = imp.ids.get("metal", {}), imp.ids.get("location", {})
        colour = {r["ColorID"]: text(r["ColorCode"]) for r in L.table("ColorMaster")}
        per_loc: dict[Any, list[dict]] = {}
        for r in rows:
            kind, wt = text(r["MtType"]) or "(blank)", num(r["ClWeight"])
            if kind != "Actual" or wt <= 0:
                if wt:
                    res.skipped.append(f"{kind if kind != 'Actual' else 'negative'}: metal "
                                       f"{r['MetalID']} at location {r['LocationID']} {wt} g")
                continue
            per_loc.setdefault(r["LocationID"], []).append(r)
        for loc_id, lines in per_loc.items():
            if imp._links.get(("metal_opening", str(loc_id))):
                res.matched += len(lines)
                continue
            loc = locs.get(loc_id)
            if loc is None:
                res.skipped.append(f"location {loc_id} not loaded")
                continue
            v = InvVoucher(vr_type="metal_opening", vr_no=INV.next_vr_no(s, "metal_opening"),
                           vr_date=as_of, is_opening=True, ref_no="Legacy closing",
                           remark="Opening from the legacy system")
            s.add(v)
            s.flush()
            for n, r in enumerate(lines, start=1):
                metal = metals.get(r["MetalID"])
                if metal is None:
                    res.skipped.append(f"metal {r['MetalID']} not loaded")
                    continue
                ln = {"location_id": loc.id, "metal_id": metal.id, "weight": num(r["ClWeight"]),
                      "colour": colour.get(r["ColorID"], ""), "amount": num(r["clvalue"])}
                INV.fill_line(s, "metal_opening", ln)
                s.add(InvVoucherLine(voucher_id=v.id, sno=n, **ln))
                res.added += 1
            s.flush()
            s.refresh(v)
            INV.post_voucher(s, v)
            imp.link("metal_opening", loc_id, v)

    @staticmethod
    def parties(imp: "Importer") -> None:
        """Party balances are money: shown for checking, never posted here (Q69)."""
        rows = imp.L.rows(
            "SELECT LedgerID, SUM(ISNULL(InGold,0) - ISNULL(OutGold,0)) gold, "
            "SUM(ISNULL(inAmount,0) - ISNULL(OutAmount,0)) amt, COUNT(*) n, "
            "MIN(VrDate) d0, MAX(VrDate) d1 FROM ClientBalance GROUP BY LedgerID "
            "HAVING SUM(ISNULL(InGold,0) - ISNULL(OutGold,0)) <> 0 "
            "OR SUM(ISNULL(inAmount,0) - ISNULL(OutAmount,0)) <> 0 ORDER BY LedgerID")
        names = {r["AccountID"]: text(r["AccountName"])
                 for r in imp.L.table("999999911")}
        res = imp._res("ClientBalance (party balances - NOT posted)", rows)
        for r in rows:
            res.partial.append(f"{names.get(r['LedgerID'], r['LedgerID'])}: fine gold "
                               f"{num(r['gold']):.3f} g, amount {num(r['amt']):.2f} "
                               f"({r['n']} entries {r['d0']}..{r['d1']})")
        imp.report.notes.append(
            "Party opening balances are listed under ClientBalance for checking against the "
            "legacy Trial Balance - post them once the client confirms the cut-over figures "
            "(Q69).")


def _same_purity(k: str, a: Any, b: Any) -> bool:
    """Purity 76, 760 and 0.76 are the same figure in three notations."""
    if k != "purity_fineness":
        return _same(a, b)
    from types import SimpleNamespace

    from diagold.services.costing import purity_fraction
    return (purity_fraction(SimpleNamespace(purity_fineness=a))
            == purity_fraction(SimpleNamespace(purity_fineness=b)))


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float, Decimal)) or isinstance(b, (int, float, Decimal)):
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except Exception:  # noqa: BLE001
            return False
    return key(str(a)) == key(str(b))


def import_masters(session: Session, legacy: Legacy) -> Report:
    return Importer(session, legacy).run_masters()



def import_all(session: Session, legacy: Legacy, openings_as_of=None) -> Report:
    """Everything the legacy database holds that this app keeps, in order.
    With a date, the opening stock too (run on the cut-over backup)."""
    return Importer(session, legacy).run_all(openings_as_of)
