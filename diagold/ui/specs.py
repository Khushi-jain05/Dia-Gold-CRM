"""Declarative CRUD specs for the Master and SKU screens."""
from __future__ import annotations

from diagold.db.models import (
    Account,
    Company,
    Currency,
    Finding,
    ManufacturingProcess,
    Metal,
    OtherSetting,
    PartMould,
    ProductSku,
    Role,
    SkuInfo,
    StoneInfo,
    StonePacket,
    User,
)
from diagold.ui.crud import CrudSpec, Field

_metal_label = lambda m: f"{m.name} {m.purity_label} {m.color}".strip()
_account_label = lambda a: f"{a.code} - {a.name}"
_stone_label = lambda s: f"{s.code} - {s.name} {s.shape}".strip()
_skuinfo_label = lambda s: f"{s.code} - {s.category}"


SPECS: dict[str, CrudSpec] = {}


def _register(spec: CrudSpec) -> None:
    SPECS[spec.key] = spec


_register(CrudSpec(
    key="master.company",
    title="Companies",
    model=Company,
    order_by="name",
    fields=[
        Field("name", "Company Name", required=True),
        Field("legal_name", "Legal Name"),
        Field("address_line1", "Address Line 1", in_list=False),
        Field("address_line2", "Address Line 2", in_list=False),
        Field("city", "City"),
        Field("state", "State", in_list=False),
        Field("country", "Country", default="India", in_list=False),
        Field("pincode", "Pincode", in_list=False),
        Field("phone", "Phone"),
        Field("email", "Email"),
        Field("gstin", "GSTIN"),
        Field("pan", "PAN", in_list=False),
        Field("base_currency", "Base Currency", default="INR"),
        Field("financial_year_start", "FY Starts (MM-DD)", default="04-01", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.currency",
    title="Currencies",
    model=Currency,
    order_by="code",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("symbol", "Symbol"),
        Field("exchange_rate", "Rate to Base", type="float", decimals=6, default=1),
        Field("is_base", "Base Currency", type="bool"),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.account",
    title="Accounts",
    model=Account,
    order_by="name",
    search_hint="Search by code, name, city, GSTIN…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("account_type", "Type", type="choice",
              choices=list(Account.ACCOUNT_TYPES), default="Customer"),
        Field("group_name", "Group", default="Sundry Debtors"),
        Field("contact_person", "Contact Person", in_list=False),
        Field("phone", "Phone"),
        Field("email", "Email", in_list=False),
        Field("address", "Address", type="text", in_list=False),
        Field("city", "City"),
        Field("state", "State", in_list=False),
        Field("gstin", "GSTIN", in_list=False),
        Field("pan", "PAN", in_list=False),
        Field("currency_code", "Currency", default="INR", in_list=False),
        Field("opening_balance", "Opening Balance", type="float", in_list=False),
        Field("opening_balance_type", "Dr/Cr", type="choice", choices=["Dr", "Cr"],
              default="Dr", in_list=False),
        Field("credit_days", "Credit Days", type="int", in_list=False),
        Field("credit_limit", "Credit Limit", type="float", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.metal",
    title="Metals",
    model=Metal,
    order_by="name",
    fields=[
        Field("name", "Metal", required=True, type="choice",
              choices=["Gold", "Silver", "Platinum", "Palladium", "Other"]),
        Field("purity_label", "Purity", help_text="e.g. 22K, 18K, 925, 950"),
        Field("fineness", "Fineness", type="float", decimals=4,
              help_text="Fraction, e.g. 0.916 for 22K"),
        Field("color", "Colour", type="choice",
              choices=["", "Yellow", "White", "Rose", "Green"]),
        Field("rate_per_gram", "Rate / gram", type="float"),
        Field("hsn_code", "HSN Code"),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.findings",
    title="Findings",
    model=Finding,
    order_by="name",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("category", "Category",
              help_text="e.g. Clasp, Post, Jump ring, Bail"),
        Field("metal_id", "Metal", type="fk", fk_model=Metal, fk_label=_metal_label),
        Field("weight", "Weight", type="float", decimals=4),
        Field("unit", "Unit", type="choice", choices=["gm", "ct", "pcs"], default="gm"),
        Field("rate", "Rate", type="float"),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.parts_mould",
    title="Parts / Moulds",
    model=PartMould,
    order_by="name",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("kind", "Kind", type="choice", choices=["Part", "Mould"], default="Part"),
        Field("metal_id", "Metal", type="fk", fk_model=Metal, fk_label=_metal_label),
        Field("weight", "Weight", type="float", decimals=4),
        Field("cavity_count", "Cavities", type="int", default=1),
        Field("location", "Location"),
        Field("rate", "Rate", type="float"),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.sku_info",
    title="SKU Info",
    model=SkuInfo,
    order_by="category",
    fields=[
        Field("code", "Code", required=True),
        Field("category", "Category", required=True,
              help_text="e.g. Ring, Necklace, Earring, Bangle"),
        Field("sub_category", "Sub-Category"),
        Field("hsn_code", "HSN Code"),
        Field("gender", "Gender", type="choice",
              choices=["Unisex", "Ladies", "Gents", "Kids"], default="Unisex"),
        Field("making_charge_type", "Making Charge Type", type="choice",
              choices=["Per Gram", "Per Piece", "Percentage", "Fixed"], default="Per Gram"),
        Field("making_charge", "Making Charge", type="float"),
        Field("description", "Description", type="text", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.stone_info",
    title="Stone Info",
    model=StoneInfo,
    order_by="name",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Stone", required=True),
        Field("stone_type", "Type", type="choice",
              choices=["Natural", "Lab Grown", "Imitation", "Synthetic"], default="Natural"),
        Field("shape", "Shape", type="choice",
              choices=["Round", "Princess", "Oval", "Pear", "Marquise", "Emerald",
                       "Cushion", "Baguette", "Heart", "Other"], default="Round"),
        Field("quality", "Quality / Clarity"),
        Field("color", "Colour"),
        Field("size_mm", "Size (mm)"),
        Field("sieve", "Sieve", in_list=False),
        Field("weight_unit", "Weight Unit", type="choice", choices=["ct", "pcs"], default="ct"),
        Field("rate_per_unit", "Rate / unit", type="float"),
        Field("hsn_code", "HSN Code", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.manufacturing",
    title="Manufacturing Processes",
    model=ManufacturingProcess,
    order_by="sequence",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Process", required=True),
        Field("department", "Department"),
        Field("sequence", "Sequence", type="int", default=1),
        Field("rate_type", "Rate Type", type="choice",
              choices=["Per Gram", "Per Piece", "Per Hour", "Fixed"], default="Per Gram"),
        Field("rate", "Rate", type="float"),
        Field("is_inhouse", "In-House", type="bool", default=True),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.other",
    title="Other Settings",
    model=OtherSetting,
    order_by="group_name",
    fields=[
        Field("group_name", "Group", required=True,
              help_text="e.g. Purity Standard, Location, Complaint Type"),
        Field("name", "Name", required=True),
        Field("value", "Value"),
        Field("notes", "Notes", type="text", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- User Right (Master > User Right) -----------------------------------
_register(CrudSpec(
    key="master.user_right",
    title="Users",
    model=User,
    order_by="username",
    search_hint="Search by username, name, email…",
    fields=[
        Field("username", "Username", required=True),
        Field("full_name", "Full Name"),
        Field("email", "Email"),
        Field("role_id", "Role", type="fk", fk_model=Role, fk_label=lambda r: r.name),
        Field("password", "Password", type="password", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
        Field("is_superuser", "Superuser", type="bool", default=False,
              help_text="Superusers bypass all User-Right checks."),
    ],
))

# --- SKU module --------------------------------------------------------
_register(CrudSpec(
    key="sku.stone_packet",
    title="Stone Packets",
    model=StonePacket,
    order_by="packet_no",
    search_hint="Search by packet no, lot no, status…",
    fields=[
        Field("packet_no", "Packet No", required=True),
        Field("stone_id", "Stone", type="fk", fk_model=StoneInfo, fk_label=_stone_label),
        Field("lot_no", "Lot No"),
        Field("supplier_id", "Supplier", type="fk", fk_model=Account,
              fk_label=_account_label),
        Field("received_date", "Received Date", type="date"),
        Field("pieces", "Pieces", type="int"),
        Field("weight_ct", "Weight (ct)", type="float", decimals=4),
        Field("rate_per_ct", "Rate / ct", type="float"),
        Field("amount", "Amount", type="float"),
        Field("location", "Location", in_list=False),
        Field("status", "Status", type="choice",
              choices=["In Stock", "Partly Used", "Consumed", "Returned"], default="In Stock"),
        Field("remarks", "Remarks", type="text", in_list=False),
    ],
))

_register(CrudSpec(
    key="sku.product_sku_master",
    title="Product SKUs",
    model=ProductSku,
    order_by="sku_code",
    search_hint="Search by SKU code, name, collection…",
    fields=[
        Field("sku_code", "SKU Code", required=True),
        Field("name", "Name"),
        Field("category_id", "Category", type="fk", fk_model=SkuInfo,
              fk_label=_skuinfo_label),
        Field("metal_id", "Metal", type="fk", fk_model=Metal, fk_label=_metal_label),
        Field("collection", "Collection"),
        Field("gender", "Gender", type="choice",
              choices=["Unisex", "Ladies", "Gents", "Kids"], default="Unisex"),
        Field("size", "Size", in_list=False),
        Field("gross_weight", "Gross Wt", type="float", decimals=4),
        Field("net_weight", "Net Wt", type="float", decimals=4),
        Field("metal_weight", "Metal Wt", type="float", decimals=4, in_list=False),
        Field("stone_weight_ct", "Stone Wt (ct)", type="float", decimals=4, in_list=False),
        Field("stone_pieces", "Stone Pcs", type="int", in_list=False),
        Field("making_charge_type", "MC Type", type="choice",
              choices=["Per Gram", "Per Piece", "Percentage", "Fixed"],
              default="Per Gram", in_list=False),
        Field("making_charge", "Making Charge", type="float", in_list=False),
        Field("wastage_pct", "Wastage %", type="float", in_list=False),
        Field("hsn_code", "HSN Code", in_list=False),
        Field("image_path", "Image Path", in_list=False),
        Field("description", "Description", type="text", in_list=False),
        Field("status", "Status", type="choice",
              choices=["Active", "Inactive", "Discontinued"], default="Active"),
    ],
))
