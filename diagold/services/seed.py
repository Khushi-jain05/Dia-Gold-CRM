"""First-run data seeding: admin user, roles, and starter master data."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    Colour,
    Company,
    Currency,
    FamilyCategory,
    Location,
    ManufacturingProcess,
    Metal,
    MetalRatio,
    Role,
    SettingType,
    SkuInfo,
    StoneGroup,
    Item,
    StoneInfo,
    StoneSku,
    StoneSkuRange,
    StoneKind,
    StoneQuality,
    StoneShape,
    StoneSize,
    User,
)
from diagold.services import costing
from diagold.services.rights import grant_all


def _empty(session: Session, model) -> bool:
    return session.scalar(select(func.count()).select_from(model)) == 0


def seed_initial_data(session: Session) -> None:
    _seed_roles_and_admin(session)
    _seed_company(session)
    _seed_currencies(session)
    _seed_metals(session)
    _seed_stones(session)
    _seed_processes(session)
    _seed_sku_info(session)
    _seed_accounts(session)
    _seed_locations(session)
    _seed_setting_types(session)
    _seed_families(session)
    _seed_colours(session)
    _seed_items(session)
    session.flush()
    # Every stone must carry a group before anything downstream can price
    # or report on it.
    unassigned = assign_stone_groups(session)
    session.flush()
    _seed_stone_skus(session)
    session.flush()
    if unassigned:
        print(f'[seed] {len(unassigned)} stone(s) have no group: '
              + ', '.join(sorted(unassigned)))


def _seed_roles_and_admin(session: Session) -> None:
    admin_role = session.scalar(select(Role).where(Role.name == "Administrator"))
    if admin_role is None:
        admin_role = Role(name="Administrator", description="Full access", is_system=True)
        session.add(admin_role)
        session.flush()

    if session.scalar(select(Role).where(Role.name == "Staff")) is None:
        session.add(Role(name="Staff", description="Limited access - configure in User Right"))

    if _empty(session, User):
        admin = User(
            username="admin",
            full_name="Administrator",
            is_superuser=True,
            is_active=True,
            role_id=admin_role.id,
        )
        admin.set_password("admin")
        session.add(admin)
        session.flush()

    # Superusers bypass the matrix, but grant explicitly so the User Rights
    # screen shows a complete picture rather than an empty grid. Runs for any
    # superuser that has no grants yet, including one created by an older
    # build. grant_all() skips masters already granted, so this is idempotent.
    session.flush()
    for su in session.scalars(select(User).where(User.is_superuser.is_(True))):
        grant_all(session, su.id)


def _seed_company(session: Session) -> None:
    if _empty(session, Company):
        session.add(Company(name="Dia Gold", legal_name="Dia Gold", country="India"))


def _seed_currencies(session: Session) -> None:
    if _empty(session, Currency):
        session.add_all([
            Currency(code="INR", name="Indian Rupee", symbol="₹", exchange_rate=1, is_base=True),
            Currency(code="USD", name="US Dollar", symbol="$", exchange_rate=83),
            Currency(code="AED", name="UAE Dirham", symbol="د.إ", exchange_rate=22.6),
            Currency(code="EUR", name="Euro", symbol="€", exchange_rate=90),
        ])


# Every metal head from the client's live master, in the order the legacy
# screen lists them. Multiple heads exist per karat because casting batches
# differ in fineness - these are deliberately NOT collapsed or deduplicated.
#
# purity is recorded exactly as the head declares it: a figure in the name is
# authoritative, otherwise the nominal karat purity is seeded as a starting
# point (see costing.NOMINAL_KARAT_PCT). Confirm against the legacy export
# when C-01 lands.
_METAL_HEADS: list[tuple[str, str]] = [
    ("12 KT CASTING", "50.00"),
    ("12KT GOLD", "50.00"),
    ("12KTWIRE", "50.00"),
    ("14KT 590", "590"),
    ("14KT CASTING 59.50", "59.50"),
    ("14KT CASTING 59.80", "59.80"),
    ("14KT CASTING 59.90", "59.90"),
    ("14KT CASTING 590", "590"),
    ("14KT CASTING 60.40", "60.40"),
    ("14KT CASTING 60.90", "60.90"),
    ("14KT CASTING 61", "61"),
    ("14KT CHAIN", "58.50"),
    ("14KT CHAIN-LOCK", "58.50"),
    ("14KT Gold", "58.50"),
    ("14KT GOLD 59.50", "59.50"),
    ("14KT WIRE", "58.50"),
    ("18 KT CASTING 71", "71"),
    ("18KT CASTING 75.50", "75.50"),
    ("18KT CASTING 76", "76"),
    ("18kt casting 76.25", "76.25"),
    ("18KT CASTING 76.80", "76.80"),
    ("18KT CASTING 76.90", "76.90"),
    ("18KT CASTING 77", "77"),
    ("18KT CHAIN", "75.00"),
    ("18KT Gold", "75.00"),
    ("18KT WIRE", "75.00"),
]


def metal_code(name: str, taken: set[str]) -> str:
    """Derive a short filter code from a head name, as the legacy system does.

    Placeholder codes only - T-15 replaces these with the real legacy codes,
    which staff search by daily (C-01).
    """
    base = "".join(ch for ch in name.upper() if ch.isalnum())[:16] or "METAL"
    code, n = base, 1
    while code in taken:
        n += 1
        code = f"{base[:14]}{n}"
    taken.add(code)
    return code


def _seed_metals(session: Session) -> None:
    """Pre-load every metal head. Idempotent - matches on code."""
    existing = {
        c for c in session.scalars(select(Metal.code)).all() if c
    }
    # Dedupe only within the seed list, never against codes already in the
    # database - otherwise a second run would generate fresh "…2" codes that
    # slip past the skip below and insert every head all over again.
    taken: set[str] = set()
    for name, purity in _METAL_HEADS:
        code = metal_code(name, taken)
        if code in existing:
            continue
        pct = Decimal(purity)
        metal = Metal(
            code=code,
            name=name,
            print_on_tag=purity,
            base_metal="GOLD",
            purity_fineness=pct,
            colour="Y",
            hsn_code="7113",
            is_active=True,
        )
        session.add(metal)
        session.flush()  # need the id for the ratio rows

        # Mining Metal Ratio: base metal + alloy, totalling exactly 100.000.
        gold_pct = costing.purity_percent(metal).quantize(Decimal("0.001"))
        session.add_all([
            MetalRatio(metal_id=metal.id, base_metal="GOLD", ratio_pct=gold_pct),
            MetalRatio(metal_id=metal.id, base_metal="ALLOY",
                       ratio_pct=Decimal("100.000") - gold_pct),
        ])


def _lookup(session: Session, model, code: str, name: str, **extra):
    """Fetch-or-create one reference row. Idempotent on code."""
    row = session.scalar(select(model).where(model.code == code))
    if row is None:
        row = model(code=code, name=name, is_active=True, **extra)
        session.add(row)
        session.flush()
    return row


def _seed_stone_reference(session: Session) -> None:
    """The granular stone masters the client works in.

    Stone groups are a client decision, not a proposal: Diamond, Polki and
    Colour Stone. Shapes, types, qualities and sizes are starting points -
    users extend every one of these lists themselves.
    """
    for code, name in (("DIA", "Diamond"), ("POLKI", "Polki"), ("CS", "Colour Stone")):
        _lookup(session, StoneGroup, code, name)
    for code, name in (("RND", "Round"), ("OVL", "Oval"), ("EMR", "Emerald"),
                       ("PRN", "Princess"), ("PER", "Pear"), ("MAR", "Marquise"),
                       ("CUS", "Cushion"), ("BAG", "Baguette"), ("HRT", "Heart")):
        _lookup(session, StoneShape, code, name)
    for code, name in (("NAT", "Natural"), ("LAB", "Lab Grown"),
                       ("IMI", "Imitation"), ("SYN", "Synthetic")):
        _lookup(session, StoneKind, code, name)
    for code, name in (("VSGH", "VS-GH"), ("VSFG", "VS-FG"), ("SI", "SI"),
                       ("VVS", "VVS")):
        _lookup(session, StoneQuality, code, name)


def _seed_stones(session: Session) -> None:
    """Reference stone rows, classified against the granular masters."""
    _seed_stone_reference(session)
    existing = {c for c in session.scalars(select(StoneInfo.code)).all() if c}

    def ref(model, code):
        return session.scalar(select(model).where(model.code == code))

    rows = [
        # code,      name,             group,   kind,  shape, quality, colour, unit, hsn
        ("CZ-RND", "Cubic Zirconia", "CS",    "IMI", "RND", None,   "",      "pcs", "7104"),
        ("DIA-RND", "Diamond",       "DIA",   "NAT", "RND", "VSGH", "",      "ct",  "7102"),
        ("DIA-LAB", "Diamond",       "DIA",   "LAB", "RND", "VSFG", "",      "ct",  "7104"),
        ("EMER",    "Emerald",       "CS",    "NAT", "EMR", None,   "Green", "ct",  "7103"),
        ("RUBY",    "Ruby",          "CS",    "NAT", "OVL", None,   "Red",   "ct",  "7103"),
    ]
    for code, name, grp, kind, shape, qual, colour, unit, hsn in rows:
        if code in existing:
            continue
        session.add(StoneInfo(
            code=code, name=name,
            stone_group_id=ref(StoneGroup, grp).id,
            stone_kind_id=ref(StoneKind, kind).id,
            shape_id=ref(StoneShape, shape).id,
            quality_id=ref(StoneQuality, qual).id if qual else None,
            color=colour, weight_unit=unit, hsn_code=hsn, is_active=True,
        ))


# The client's actual process list, read off their live system, in the order
# the legacy screen shows them.
#
# The loss BASIS per process is inferred from what the step physically does -
# weight-bearing steps lose weight (NetWt), piece steps lose pieces, setting
# loses stone pieces, hand work is hourly. The client named the sequence but
# never went basis-by-basis, so CONFIRM THESE against the legacy export (C-01).
# Loss percentages are left at 0 deliberately - no figure was ever stated.
_PROCESSES: list[tuple[str, str, str]] = [
    # name, loss basis letter, module
    ("Assamble", "N", "Factory-1"),
    ("CAD", "P", "Design"),
    ("CAMMING", "P", "Design"),
    ("CASTING", "G", "Factory-1"),
    ("COLOUR", "N", "Factory-1"),
    ("DANK CHANGE", "N", "Factory-1"),
    ("Final Polish", "N", "Factory-1"),
    ("final setting", "S", "Setting"),
    ("HandMade", "H", "Factory-1"),
    ("KHUDAI", "N", "Factory-1"),
    ("Meena", "N", "Factory-1"),
    ("OFFICE", "P", "Office"),
    ("PrePolish", "N", "Factory-1"),
    ("Puwai", "S", "Setting"),
    ("RECTIFICATION", "N", "Factory-1"),
    ("Repair HM", "N", "Factory-1"),
    ("Setting", "S", "Setting"),
]


def _seed_processes(session: Session) -> None:
    """Load the client's real process list. Idempotent - matches on code."""
    existing = {c for c in session.scalars(select(ManufacturingProcess.code)).all() if c}
    taken: set[str] = set()
    for order, (name, loss, module) in enumerate(_PROCESSES, start=1):
        code = _derive_code(name, taken, maxlen=12)
        if code in existing:
            continue
        session.add(ManufacturingProcess(
            code=code, name=name, loss_type=loss, loss_percent=0,
            module=module, base_process="Job Work", labour_type="STD",
            sequence=order, order_srno=order, is_active=True,
        ))


def _seed_sku_info(session: Session) -> None:
    if _empty(session, SkuInfo):
        cats = [
            ("RING", "Ring"), ("NECK", "Necklace"), ("EARR", "Earring"),
            ("BANG", "Bangle"), ("BRAC", "Bracelet"), ("PEND", "Pendant"),
            ("CHAIN", "Chain"), ("SET", "Jewellery Set"),
        ]
        session.add_all([
            SkuInfo(code=c, category=name, making_charge_type="Per Gram")
            for c, name in cats
        ])


def _seed_accounts(session: Session) -> None:
    """Seed rows the client's live system shows. Idempotent - matches on code."""
    existing = {c for c in session.scalars(select(Account.code)).all() if c}
    rows = [
        ("CASH", "Cash in Hand", "Accounts", "Cash-In-Hand"),
        ("CREDIT", "Walk-in Customer", "Client", "Sundry Debtors"),
    ]
    for code, name, kind, group in rows:
        if code not in existing:
            session.add(Account(code=code, name=name, account_type=kind,
                                group_name=group))


def _derive_code(name: str, taken: set[str], maxlen: int = 16) -> str:
    """Uppercase alphanumeric short code, unique within the list being seeded."""
    base = "".join(ch for ch in name.upper() if ch.isalnum())[:maxlen] or "ITEM"
    code, n = base, 1
    while code in taken:
        n += 1
        code = f"{base[:maxlen - 1]}{n}"
    taken.add(code)
    return code


# Locations read off the client's live system. The type column is INFERRED from
# the shapes the client described - person names are karigars, process areas are
# departments, offices are branches, and the rest are logical buckets. PUSH and
# MISCELLANEOS were never explained on the call; confirm all of these against
# the legacy export (C-01).
_LOCATIONS: list[tuple[str, str]] = [
    ("DISMENTAL", "Logical"),
    ("GAURANG JI", "Karigar"),
    ("HARISH", "Karigar"),
    ("MISCELLANEOS", "Logical"),
    ("MUMBAI OFFICE", "Branch"),
    ("Primary", "Logical"),
    ("PUSH", "Department"),
    ("puwai", "Department"),
    ("RAJAT JI", "Karigar"),
    ("RAJESH JI", "Karigar"),
    ("REPAIR RECEIPT", "Department"),
    ("SETTING PURIFICATION", "Department"),
    ("SHARAD JI", "Karigar"),
    ("SHARAD JI REPAIR", "Karigar"),
    ("SONU JI", "Karigar"),
    ("SUNIL JI", "Karigar"),
    ("Virtual", "Logical"),
]

# Setting types from the legacy screen. The client showed "Channel / CH / 0",
# so Channel keeps its real code; the rest are derived pending C-01.
_SETTING_TYPES: list[tuple[str, str]] = [
    ("Bezel", ""), ("Channel", "CH"), ("CS", ""), ("Diam", ""),
    ("Invisible Prong", ""), ("Micro Pave", ""), ("Pave", ""), ("Polki", ""),
    ("Pre Pave", ""), ("Prong", ""), ("Tapper Channel", ""),
    ("Tapper Channel Wax", ""), ("Tapper Prong", ""), ("Tapper Prong Wax", ""),
]


def _seed_locations(session: Session) -> None:
    """Material-custody locations. Idempotent - matches on code."""
    existing = {c for c in session.scalars(select(Location.code)).all() if c}
    taken: set[str] = set()
    for name, kind in _LOCATIONS:
        code = _derive_code(name, taken)
        if code in existing:
            continue
        # Material types are deliberately left empty - the client never said
        # which karigar holds what, and guessing would be wrong (C-01).
        session.add(Location(code=code, name=name, location_type=kind, is_active=True))


def _seed_setting_types(session: Session) -> None:
    existing = {c for c in session.scalars(select(SettingType.code)).all() if c}
    taken = {c for _, c in _SETTING_TYPES if c}
    for name, fixed_code in _SETTING_TYPES:
        code = fixed_code or _derive_code(name, taken)
        if code in existing:
            continue
        session.add(SettingType(code=code, name=name, price=0, is_active=True))


def _seed_families(session: Session) -> None:
    existing = {c for c in session.scalars(select(FamilyCategory.code)).all() if c}
    for code, name in [("DIAJEW", "Diamond Jewellery"),
                       ("DIAPOLKI", "Diamond Polki Jewellery")]:
        if code not in existing:
            session.add(FamilyCategory(code=code, name=name, is_active=True))


def _seed_colours(session: Session) -> None:
    existing = {c for c in session.scalars(select(Colour.code)).all() if c}
    for code, name, default in [("Y", "Yellow", True), ("R", "Rose", False),
                                ("W", "White", False)]:
        if code not in existing:
            session.add(Colour(code=code, name=name, is_default=default, is_active=True))


# ==========================================================================
# S.K.U. module seed (8 September session)
# ==========================================================================
# The client's item list, spellings preserved exactly - staff search on these
# strings, so "Bracelete" and "CHAIN PENDENT" stay as they are.
_ITEMS: list[str] = [
    "BANGLE", "Bracelete", "BRIDAL NECKLACE", "BROOCH", "CHAIN PENDENT",
    "CHANDBALI", "CHOKER", "CUFFLINKS", "DANGLERS", "EARRING", "GENTS RING",
    "JHUMKI", "LINES NECKLACE", "LONG NECKLACE", "NECK EARRING", "NECKLACE",
    "NECKLACE SET", "PENDANT", "RING", "ROUND NECKLACE", "SAMPLE", "STUDS",
    "WATCH",
]

# Stones and their groups, read off the client's system. The group is a
# classification on top of the existing stone list - stones are never renamed
# or collapsed to fit it.
_STONE_GROUPS: dict[str, tuple[str, ...]] = {
    "CS": ("MORGANITE MANI", "EMERALD PEAR", "EMERALD BEADS", "FRESHWATER",
           "SOUTH SEA", "NAVRATAN", "GREEN SYNTHETIC", "LABGROWN RUBY", "KYANITE",
           "MOP STONE", "MOON STONE", "MALACHITE", "LOLITE", "LAAKH",
           "KUNDAN MEENA", "CORAL DROP", "CITRINE",
           # Plain names carried by rows this app seeded earlier.
           "CUBIC ZIRCONIA", "EMERALD", "RUBY"),
    "POLKI": ("POLKI", "POLKI NAKLI", "POLKI REPAIR", "KILWAS (.80)",
              "KILWAS (1.20)", "KILWAS (1.50)", "LB (.70)", "LB (1.5)"),
    "DIA": ("DIA. MIX", "DIA.4", "DIA. PEAR", "DIA. MARQUISE", "DIA. NAKLI",
            "DIA.SQUARE", "DIA.ROSE CUT ROUND", "DIA.ROSE CUT FANCY",
            "DIA. BAGG TAPPER", "LABGROWN"),
}

# EMERALD PEAR and POLKI price grids, read off the Range/Size Info grid.
# (range label, price per carat, size)
_EMERALD_PEAR_RANGES = [
    ("a", "2000", "3*4"), ("b", "2300", "4*5"), ("c", "2300", "5*3"),
    ("d", "3000", "6*4"), ("e", "3250", "7*5"), ("f", "4000", "6*8"),
    ("G", "4500", "7*9"), ("H", "5000", "8*10"), ("J", "5500", "4*6"),
]
_POLKI_RANGES = [
    ("U", "7500", ""), ("V", "32000", "K1"), ("W", "36000", "K1.5"),
    ("X", "40000", "K2"), ("y", "42000", "50-55"), ("z", "48000", "55-60"),
    ("23", "8100", "12-14"), ("24", "50000", ""), ("3", "35000", ""),
]


def _seed_items(session: Session) -> None:
    """The 23 product categories. Code doubles as the SKU-code prefix."""
    existing = {c for c in session.scalars(select(Item.code)).all() if c}
    # The session runs with autoflush off, so families added moments ago are
    # still pending and a query would not see them.
    session.flush()
    default_family = session.scalar(
        select(FamilyCategory).where(FamilyCategory.code == "DIAJEW")
    )
    taken: set[str] = set()
    for name in _ITEMS:
        code = _derive_code(name, taken, maxlen=16).lower()
        if code in existing:
            continue
        # Default every item to the client's main family; they reassign as
        # needed. Family flows from here onto each SKU.
        session.add(Item(name=name, code=code, unit="Pcs", pcs=1,
                         family_id=default_family.id if default_family else None,
                         is_active=True))

    # Items created before this column existed carry no family; give them the
    # default so the SKU screen has something to pick up.
    if default_family is not None:
        for item in session.scalars(select(Item).where(Item.family_id.is_(None))):
            item.family_id = default_family.id


def assign_stone_groups(session: Session) -> list[str]:
    """Give every stone its group. Returns the names that could not be assigned.

    Nothing is guessed: a stone whose name is not in the client's lists is
    reported rather than dropped into a group at random.
    """
    groups = {g.code: g for g in session.scalars(select(StoneGroup))}
    by_name: dict[str, str] = {}
    for group_code, names in _STONE_GROUPS.items():
        for n in names:
            by_name[n.upper()] = group_code

    unassigned: list[str] = []
    valid_ids = {g.id for g in groups.values()}
    for stone in session.scalars(select(StoneInfo)):
        # 0 means an older migration stamped a placeholder into the column;
        # treat anything that is not a real group as unassigned.
        if stone.stone_group_id in valid_ids:
            continue
        code = by_name.get((stone.name or "").upper())
        if code is None:
            # Fall back to the prefix conventions the client's data uses.
            upper = (stone.name or "").upper()
            if upper.startswith("DIA") or "LABGROWN DIA" in upper:
                code = "DIA"
            elif upper.startswith(("POLKI", "KILWAS", "LB ")):
                code = "POLKI"
        if code is None or code not in groups:
            unassigned.append(stone.name)
            continue
        stone.stone_group_id = groups[code].id
    return unassigned


def _seed_stone_skus(session: Session) -> None:
    """The priced stone catalogue, with the two grids read off the screen."""
    existing = {c for c in session.scalars(select(StoneSku.code)).all() if c}

    def size_row(label: str):
        if not label:
            return None
        row = session.scalar(select(StoneSize).where(StoneSize.name == label))
        if row is None:
            row = StoneSize(code=_derive_code(label, set(), maxlen=16),
                            name=label, is_active=True)
            session.add(row)
            session.flush()
        return row

    def stone_row(name: str, group_code: str):
        row = session.scalar(select(StoneInfo).where(StoneInfo.name == name))
        if row is None:
            group = session.scalar(select(StoneGroup).where(StoneGroup.code == group_code))
            row = StoneInfo(code=_derive_code(name, set(), maxlen=16), name=name,
                            stone_group_id=group.id, weight_unit="ct", is_active=True)
            session.add(row)
            session.flush()
        return row

    for sku_code, stone_name, group_code, ranges in (
        ("EMERALD PEAR", "EMERALD PEAR", "CS", _EMERALD_PEAR_RANGES),
        ("POLKI", "POLKI", "POLKI", _POLKI_RANGES),
    ):
        if sku_code in existing:
            continue
        stone = stone_row(stone_name, group_code)
        sku = StoneSku(code=sku_code, stone_id=stone.id, is_active=True)
        session.add(sku)
        session.flush()
        for label, price, size_name in ranges:
            size = size_row(size_name)
            # Cost equals sale on the Stone SKU master in every row observed.
            session.add(StoneSkuRange(
                stone_sku_id=sku.id, range_label=label,
                cost_price=Decimal(price), sale_price=Decimal(price),
                per="Cts", size_id=size.id if size else None,
            ))
