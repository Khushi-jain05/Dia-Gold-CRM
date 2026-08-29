"""First-run data seeding: admin user, roles, and starter master data."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    Company,
    Currency,
    ManufacturingProcess,
    Metal,
    Role,
    RolePermission,
    SkuInfo,
    StoneInfo,
    User,
)
from diagold.menu import ALL_ITEM_KEYS


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
    session.flush()


def _seed_roles_and_admin(session: Session) -> None:
    admin_role = session.scalar(select(Role).where(Role.name == "Administrator"))
    if admin_role is None:
        admin_role = Role(name="Administrator", description="Full access", is_system=True)
        session.add(admin_role)
        session.flush()
        # Explicit grants too (superuser bypasses these, but keeps data consistent).
        for key in ALL_ITEM_KEYS:
            session.add(RolePermission(role_id=admin_role.id, menu_key=key))

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


def _seed_metals(session: Session) -> None:
    if _empty(session, Metal):
        session.add_all([
            Metal(name="Gold", purity_label="24K", fineness=0.9999, color="Yellow", hsn_code="7108"),
            Metal(name="Gold", purity_label="22K", fineness=0.9160, color="Yellow", hsn_code="7113"),
            Metal(name="Gold", purity_label="18K", fineness=0.7500, color="Yellow", hsn_code="7113"),
            Metal(name="Gold", purity_label="18K", fineness=0.7500, color="White", hsn_code="7113"),
            Metal(name="Gold", purity_label="14K", fineness=0.5850, color="Rose", hsn_code="7113"),
            Metal(name="Silver", purity_label="925", fineness=0.9250, color="White", hsn_code="7113"),
            Metal(name="Platinum", purity_label="950", fineness=0.9500, color="White", hsn_code="7110"),
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


def _seed_processes(session: Session) -> None:
    if _empty(session, ManufacturingProcess):
        rows = [
            ("CAST", "Casting", "Casting", 1),
            ("FILE", "Filing", "Filing", 2),
            ("PREP", "Pre-Polish", "Polish", 3),
            ("SET", "Stone Setting", "Setting", 4),
            ("POL", "Polish", "Polish", 5),
            ("RHOD", "Rhodium", "Plating", 6),
            ("QC", "Quality Check", "QC", 7),
        ]
        session.add_all([
            ManufacturingProcess(code=c, name=n, department=d, sequence=s)
            for c, n, d, s in rows
        ])


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
    if _empty(session, Account):
        session.add_all([
            Account(code="CASH", name="Cash in Hand", account_type="Cash", group_name="Cash"),
            Account(code="C0001", name="Walk-in Customer", account_type="Customer",
                    group_name="Sundry Debtors"),
        ])
