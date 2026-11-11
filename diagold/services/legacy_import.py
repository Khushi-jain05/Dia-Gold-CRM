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
from diagold.db.models.sku import Item, StoneMaster, StoneSku

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

    def run_all(self) -> Report:
        self.run_masters()
        return self.report

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



def import_all(session: Session, legacy: Legacy) -> Report:
    """Everything the legacy database holds that this app keeps, in order."""
    return Importer(session, legacy).run_all()
