"""All ORM models. Importing this package registers every table on ``Base``."""
from __future__ import annotations

from diagold.db.models.base import Base
from diagold.db.models.auth import Role, RolePermission, User, hash_password, verify_password
from diagold.db.models.master import (
    Account,
    Company,
    Currency,
    Finding,
    ManufacturingProcess,
    Metal,
    OtherSetting,
    PartMould,
    SkuInfo,
    StoneInfo,
)
from diagold.db.models.sku import ProductSku, ProductSkuStone, StonePacket

__all__ = [
    "Base",
    "Role",
    "RolePermission",
    "User",
    "hash_password",
    "verify_password",
    "Account",
    "Company",
    "Currency",
    "Finding",
    "ManufacturingProcess",
    "Metal",
    "OtherSetting",
    "PartMould",
    "SkuInfo",
    "StoneInfo",
    "ProductSku",
    "ProductSkuStone",
    "StonePacket",
]
