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
    StoneInfo,
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
    session.flush()


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


def _seed_stones(session: Session) -> None:
    if _empty(session, StoneInfo):
        session.add_all([
            StoneInfo(code="DIA-RND", name="Diamond", stone_type="Natural", shape="Round",
                      quality="VS-GH", weight_unit="ct", hsn_code="7102"),
            StoneInfo(code="DIA-LAB", name="Diamond", stone_type="Lab Grown", shape="Round",
                      quality="VS-FG", weight_unit="ct", hsn_code="7104"),
            StoneInfo(code="CZ-RND", name="Cubic Zirconia", stone_type="Imitation", shape="Round",
                      weight_unit="pcs", hsn_code="7104"),
            StoneInfo(code="RUBY", name="Ruby", stone_type="Natural", shape="Oval",
                      color="Red", weight_unit="ct", hsn_code="7103"),
            StoneInfo(code="EMER", name="Emerald", stone_type="Natural", shape="Emerald",
                      color="Green", weight_unit="ct", hsn_code="7103"),
        ])


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
