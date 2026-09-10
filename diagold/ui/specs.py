"""Declarative CRUD specs for the Master and SKU screens."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from diagold.db.models import (
    Account,
    Item,
    ItemPriceRange,
    Colour,
    Company,
    Currency,
    DailyLabourRate,
    DailyMetalRate,
    DefaultProcessStep,
    FamilyCategory,
    Finding,
    LabourRate,
    Location,
    LocationMaterial,
    ManufacturingProcess,
    MarginComponent,
    MarginSet,
    Metal,
    MetalRatio,
    MetalVendor,
    OtherSetting,
    PartMould,
    MouldModification,
    ProcessCheckpoint,
    ProductSku,
    ProductSkuStone,
    Role,
    SettingLabourRate,
    SettingType,
    SkuInfo,
    StoneGroup,
    StoneInfo,
    StoneKind,
    StoneQuality,
    StoneShape,
    StoneSize,
    StonePacket,
    StoneSku,
    User,
)
from sqlalchemy import select

from diagold.db.session import SessionLocal
from diagold.services import costing, rates
from diagold.ui.crud import ChildSpec, CrudSpec, Field, Shortcut

_metal_label = lambda m: f"{m.code} - {m.name}".strip(" -")
_account_label = lambda a: f"{a.code} - {a.name}"
_stone_label = lambda s: f"{s.code} - {s.name}".strip(" -")
_skuinfo_label = lambda s: f"{s.code} - {s.category}"


def _stone_sku_autofill(dialog, value) -> None:
    """Mirror the Stone SKU code into the Stone field as it's typed - matches
    the client's legacy screen, where Stone defaults to the same text as
    Stone SKU but can still be edited by hand. Never overwrites something the
    user has already typed into Stone themselves.
    """
    stone_editor = dialog.editors.get("stone")
    if stone_editor is None or stone_editor.text().strip():
        return
    stone_editor.setText(value if isinstance(value, str) else "")


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
              choices=list(Account.ACCOUNT_TYPES), default="Client",
              help_text="One master for every party. Type is mainly a filter."),
        Field("group_name", "Group", type="choice",
              choices=list(Account.ACCOUNT_GROUPS), default="Accounts Receivable",
              help_text="Payable / Receivable are listed first."),
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

def _ratio_summary(rows: list[dict]) -> str:
    """Live running total under the ratio grid, so the rule is visible."""
    total = costing.ratio_total(rows)
    if not rows:
        return "No ratio rows — optional, but if present they must total 100.00"
    mark = "✓" if total == costing.RATIO_TOTAL else "✗"
    return f"{mark}  Total {total:.3f} / {costing.RATIO_TOTAL} "


def _validate_metal(values: dict, children: dict[str, list[dict]]) -> str | None:
    """Block the save unless the Mining Metal Ratio rows total exactly 100.00."""
    return costing.validate_metal_ratios(children.get("ratios", []))


_register(CrudSpec(
    key="master.metal",
    title="Metals",
    model=Metal,
    order_by="name",
    search_hint="Search by code, name, base metal, HSN…",
    validate=_validate_metal,
    fields=[
        Field("code", "Code", required=True,
              help_text="Short code staff filter by, e.g. 14KTCASTING590"),
        Field("name", "Name", required=True,
              help_text='Free text, e.g. "14KT CASTING 590".'),
        Field("print_on_tag", "Print on Tag"),
        Field("base_metal", "Base Metal", type="choice",
              choices=["GOLD", "SILVER", "PLATINUM", "PALLADIUM", "ALLOY", "OTHER"],
              default="GOLD"),
        Field("purity_fineness", "Purity / Fineness", type="float", decimals=4,
              help_text="Drives all costing. 590, 59.50 or 0.585 all understood."),
        Field("colour", "Colour", type="choice", choices=["", "Y", "W", "R", "G"]),
        Field("is_active", "Active", type="bool", default=True),

        # -- detail fields, off the list view ---------------------------
        Field("purity_for_custom", "Purity for Custom", type="float", decimals=4,
              in_list=False),
        Field("work_adjust_metal", "Work Adjust Metal", in_list=False),
        Field("specific_gravity", "Sp. Gravity", type="float", decimals=4, in_list=False),
        Field("purity_weight", "Purity Wt", type="float", decimals=4, in_list=False),
        Field("hsn_code", "HSN Code", in_list=False),
        Field("box_no", "Box #", in_list=False),
        Field("is_mrp", "MRP", type="bool", in_list=False),
        Field("is_effects_net_wt", "Is Effects Net Wt", type="bool", in_list=False),
        Field("description", "Description", type="text", in_list=False),

        # -- child grids -------------------------------------------------
        Field("ratios", "Mining Metal Ratio", type="child", in_list=False,
              help_text="Base metal plus alloy. The rows must total exactly 100.00 "
                        "or the record will not save.",
              child=ChildSpec(
                  model=MetalRatio,
                  fk_attr="metal_id",
                  order_by="id",
                  summary=_ratio_summary,
                  row_template={"base_metal": "ALLOY", "ratio_pct": 0},
                  default_rows=[
                      {"base_metal": "GOLD", "ratio_pct": 0},
                      {"base_metal": "ALLOY", "ratio_pct": 0},
                  ],
                  height=120,
                  fields=[
                      Field("base_metal", "Base Metal", type="choice",
                            choices=["GOLD", "SILVER", "PLATINUM", "PALLADIUM", "ALLOY"]),
                      Field("ratio_pct", "Ratio %", type="float", decimals=3),
                  ],
              )),
        Field("vendors", "Vendor List", type="child", in_list=False,
              help_text="Accounts that supply this metal head.",
              child=ChildSpec(
                  model=MetalVendor,
                  fk_attr="metal_id",
                  order_by="id",
                  height=90,
                  fields=[
                      Field("account_id", "Vendor", type="fk", fk_model=Account,
                            fk_label=_account_label),
                  ],
              )),
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
    search_hint="Search by username, name, email, mobile…",
    # Users are never deleted - deactivating keeps their name on historic
    # records, which is the whole point of named logins.
    deletable=False,
    fields=[
        Field("username", "Username", required=True,
              help_text="Role-shaped names such as CST1 or CAD are fine."),
        Field("full_name", "Full Name"),
        Field("email", "Email"),
        Field("mobile_number", "Mobile Number", help_text="Used for SMS."),
        Field("role_id", "Role", type="fk", fk_model=Role, fk_label=lambda r: r.name),
        Field("password", "Password", type="password", in_list=False),
        Field("password_confirm", "Confirm Password", type="password", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
        Field("is_superuser", "Superuser", type="bool", default=False,
              help_text="Superusers bypass all User-Right checks."),
    ],
))

# --- SKU module --------------------------------------------------------
# Kept but off the menu - see DROPPED_SKU_SCREENS in diagold/menu.py. The
# spec stays so the screen returns intact if the client explains Packet No.
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



# --- Location (T-04) ----------------------------------------------------
_register(CrudSpec(
    key="master.location",
    title="Locations",
    model=Location,
    order_by="name",
    search_hint="Search by code, name, type, notes…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True,
              help_text="Where material physically sits — not a client."),
        Field("location_type", "Type", type="choice",
              choices=list(Location.LOCATION_TYPES), default="Karigar"),
        Field("is_active", "Active", type="bool", default=True,
              help_text="Deactivate rather than delete."),
        Field("account_id", "Linked Account", type="fk", fk_model=Account,
              fk_label=_account_label, in_list=False),
        Field("notes", "Notes", type="text", in_list=False),
        Field("materials", "Material Types Held", type="child", in_list=False,
              help_text="Tag whatever this location holds.",
              child=ChildSpec(
                  model=LocationMaterial,
                  fk_attr="location_id",
                  order_by="id",
                  height=110,
                  row_template={"material_type": "Gold"},
                  fields=[
                      Field("material_type", "Material Type", type="choice",
                            choices=list(LocationMaterial.MATERIAL_TYPES)),
                  ],
              )),
    ],
))

# --- Setting Type (T-12) ------------------------------------------------
_register(CrudSpec(
    key="master.setting_type",
    title="Setting Types",
    model=SettingType,
    order_by="name",
    search_hint="Search by code or name…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("price", "Price", type="float"),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Family / Category (T-12) -------------------------------------------
_register(CrudSpec(
    key="master.family_category",
    title="Families / Categories",
    model=FamilyCategory,
    order_by="name",
    search_hint="Search by code or name…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True,
              help_text="The jewellery family an item belongs to. Add more "
                        "whenever a new family comes into use."),
        Field("description", "Description", type="text", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Colour (T-12) ------------------------------------------------------
_register(CrudSpec(
    key="master.colour",
    title="Colours",
    model=Colour,
    order_by="name",
    search_hint="Search by code or name…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("is_default", "Default", type="bool",
              help_text="Yellow is the client's default gold colour."),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Manufacturing Process (T-08) ---------------------------------------
_loss_choices = [f"{code} — {label}" for code, label, _ in costing.LOSS_BASES]
_process_label = lambda p: f"{p.code} - {p.name}"


def _loss_code(display: str) -> str:
    return (display or "").split("—")[0].strip()


_register(CrudSpec(
    key="master.manufacturing",
    title="Manufacturing Processes",
    model=ManufacturingProcess,
    order_by="name",
    search_hint="Search by code, name, module, base process…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Process", required=True),
        Field("loss_type", "Loss Type", type="choice",
              choices=[c for c, _, _ in costing.LOSS_BASES], default="N",
              help_text="P=PCS · G=GrossWt · N=NetWt · I=ISS_NWT · H=HOURLY · "
                        "S=ST PCS · F=Diff Wt. Loss is computed on this step's "
                        "own basis, never a global one."),
        Field("loss_percent", "Loss %", type="float", decimals=4),
        Field("base_process", "Base Process", default="Job Work"),
        Field("module", "Module"),
        Field("is_active", "Active", type="bool", default=True),

        Field("labour_type", "Labour Type", default="STD", in_list=False),
        Field("labour_accounting", "Labour Accounting", type="bool", in_list=False),
        Field("labour_gn", "Labour Gn", in_list=False),
        Field("process_type", "Type", type="choice", choices=["None", "Wax"],
              default="None", in_list=False),
        Field("is_print_vr", "Is Print Vr", type="bool", in_list=False),
        Field("order_srno", "Order Sr No", type="int", in_list=False),
        Field("department", "Department", in_list=False),
        Field("sequence", "Sequence", type="int", default=1, in_list=False),
        Field("rate_type", "Rate Type", type="choice",
              choices=["Per Gram", "Per Piece", "Per Hour", "Fixed"],
              default="Per Gram", in_list=False),
        Field("rate", "Rate", type="float", in_list=False),
        Field("is_inhouse", "In-House", type="bool", default=True, in_list=False),
        Field("check_weight_tolerance", "Check Weight Tolerance", type="bool", in_list=False),
        Field("fill_auto_stone", "Fill Auto Stone (F3)", type="bool", in_list=False),
        Field("fill_auto_mould", "Fill Auto Mould (F7)", type="bool", in_list=False),
        Field("use_diff_wt_as_metal", "Use Diff Wt As Metal", type="bool", in_list=False),

        Field("checkpoints", "QC Check Points", type="child", in_list=False,
              help_text="Checks carried out at this step.",
              child=ChildSpec(
                  model=ProcessCheckpoint,
                  fk_attr="process_id",
                  order_by="srno",
                  height=110,
                  row_template={"srno": 1, "checkpoint": ""},
                  fields=[
                      Field("srno", "Sr No", type="int"),
                      Field("checkpoint", "Check Point"),
                  ],
              )),
    ],
))

# --- Set Default Process (T-08, sequence itself pending Q13) -------------
_register(CrudSpec(
    key="master.default_process",
    title="Default Process Steps",
    model=DefaultProcessStep,
    order_by="step_no",
    search_hint="Search by remark…",
    fields=[
        Field("step_no", "Step", type="int", default=1, required=True),
        Field("process_id", "Process", type="fk", fk_model=ManufacturingProcess,
              fk_label=_process_label),
        Field("remark", "Remark"),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Daily Metal Rate (T-09) --------------------------------------------
_register(CrudSpec(
    key="master.daily_metal_rate",
    title="Daily Metal Rates",
    model=DailyMetalRate,
    order_by="rate_date",
    search_hint="Search by remark…",
    fields=[
        Field("rate_date", "Date", type="date", required=True),
        Field("metal_id", "Metal", type="fk", fk_model=Metal, fk_label=_metal_label),
        Field("rate_per_gram", "Rate / gram", type="float", decimals=4,
              help_text="One rate per metal per day. Past days are never "
                        "overwritten, so old valuations stay reproducible."),
        Field("pure_rate_per_gram", "Pure Rate / gram", type="float", decimals=4,
              help_text="Optional. Rate for 100% pure metal; valuation scales "
                        "it by each head's purity."),
        Field("remark", "Remark", in_list=False),
    ],
))

# --- Daily Labour Rates (T-09, shape pending Q9) ------------------------
_register(CrudSpec(
    key="master.daily_labour_rate",
    title="Daily Labour Rates",
    model=DailyLabourRate,
    order_by="rate_date",
    search_hint="Search by remark…",
    fields=[
        Field("rate_date", "Date", type="date", required=True),
        Field("metal_id", "Metal / Karat", type="fk", fk_model=Metal,
              fk_label=_metal_label),
        Field("rate", "Labour Rate", type="float", decimals=4),
        Field("remark", "Remark", in_list=False,
              help_text="This master was never discussed on the call — it "
                        "mirrors Daily Metal Rate pending the client's "
                        "confirmation."),
    ],
))

# --- Labour (T-11) ------------------------------------------------------
_register(CrudSpec(
    key="master.labour",
    title="Labour Rates",
    model=LabourRate,
    order_by="karat",
    search_hint="Search by karat…",
    fields=[
        Field("karat", "Karat", required=True, help_text='e.g. "18KT"'),
        Field("metal_id", "Metal Head", type="fk", fk_model=Metal, fk_label=_metal_label),
        Field("rate", "Labour Rate", type="float", decimals=4),
        Field("unit", "Unit", type="choice",
              choices=["Per Gram", "Per Piece", "Fixed"], default="Per Gram"),
        Field("weight_basis", "Weight Basis", type="choice",
              choices=list(LabourRate.WEIGHT_BASES), default="Net Weight",
              help_text="Labour is charged on NET weight, not gross. Stored "
                        "explicitly so every figure is auditable."),
        Field("effective_from", "Effective From", type="date",
              help_text="Historic jobs keep the rate that applied on their date."),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Set Margins (T-10) -------------------------------------------------
_register(CrudSpec(
    key="master.set_margins",
    title="Margin Sets",
    model=MarginSet,
    order_by="margin_key",
    search_hint="Search by margin key…",
    fields=[
        Field("margin_key", "Margin Key", required=True, help_text='e.g. "50"'),
        Field("tag_margin_percent", "Tag Margin %", type="float", decimals=4,
              help_text="Cost is raised by this to reach the tag price."),
        Field("customer_discount_percent", "Customer Discount %", type="float",
              decimals=4,
              help_text="Customer price = tag price less this. Both steps are "
                        "separate and editable — the exact rule is still being "
                        "confirmed with the client."),
        Field("overall_percent", "Overall %", type="float", decimals=4),
        Field("loss_percent", "Loss %", type="float", decimals=4),
        Field("is_active", "Active", type="bool", default=True),

        Field("is_manual", "Manual?", type="bool", in_list=False),
        Field("advance_defination", "Advance Defination?", type="bool", in_list=False),
        Field("tagprice_margin", "TagPrice Margin?", type="bool", in_list=False),
        Field("stone_group_wise", "Stone Group Wise", type="bool", in_list=False),
        Field("round_off", "Round of ?", type="float", decimals=4, in_list=False),

        Field("components", "Define Margin % On", type="child", in_list=False,
              help_text="Margin is applied component-wise, not as one number on "
                        "the total. M = Margin (cost / (1 − rate)), "
                        "U = Markup (cost × (1 + rate)).",
              child=ChildSpec(
                  model=MarginComponent,
                  fk_attr="margin_set_id",
                  order_by="id",
                  height=150,
                  row_template={"component": "Labour", "percent": 0, "mode": "U"},
                  default_rows=[{"component": c, "percent": 0, "mode": "U"}
                                for c in MarginComponent.COMPONENTS],
                  fields=[
                      Field("component", "Component", type="choice",
                            choices=list(MarginComponent.COMPONENTS)),
                      Field("percent", "%", type="float", decimals=4),
                      Field("mode", "M / U", type="choice",
                            choices=list(MarginComponent.MODES)),
                  ],
              )),
    ],
))

# --- Setting Labour Chart (T-07) ---------------------------------------
_register(CrudSpec(
    key="master.setting_labour",
    title="Setting Labour Rates",
    model=SettingLabourRate,
    order_by="stone_group",
    search_hint="Search by stone group…",
    fields=[
        Field("stone_group", "Stone Group", type="choice",
              choices=list(SettingLabourRate.STONE_GROUPS), default="Diamond",
              required=True),
        Field("rate_per_piece", "Rate / piece", type="float", decimals=4,
              help_text="Per-piece rate paid to the karigar. Comes from the "
                        "client's chart — nothing is assumed here."),
        Field("setting_type_id", "Setting Type", type="fk", fk_model=SettingType,
              fk_label=lambda s: f"{s.code} - {s.name}"),
        Field("sku_id", "SKU", type="fk", fk_model=SkuInfo, fk_label=_skuinfo_label,
              help_text="Optional. A SKU row overrides the group rate."),
        Field("effective_from", "Effective From", type="date",
              help_text="An already-settled month never changes when a rate is updated."),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Parts / Mould register (T-13) -------------------------------------
_register(CrudSpec(
    key="master.parts_mould",
    title="Parts / Moulds",
    model=PartMould,
    order_by="code",
    search_hint="Search by mould no, item, part no, CAD file…",
    fields=[
        Field("code", "Mould #", required=True,
              help_text="e.g. SLR-0139, SCR-013 — no fixed format."),
        Field("name", "Item", required=True),
        Field("kind", "Kind", type="choice", choices=["Mould", "Part"], default="Mould"),
        Field("family_id", "Family", type="fk", fk_model=FamilyCategory,
              fk_label=lambda f: f.name),
        Field("wax_weight_per_pcs", "Wt/Pcs (Wax)", type="float", decimals=4),
        Field("no_of_pcs", "No. of Pcs", type="int", default=1),
        Field("location_id", "Location", type="fk", fk_model=Location,
              fk_label=lambda l: f"{l.code} - {l.name}"),
        Field("is_active", "Active", type="bool", default=True),

        Field("description", "Description", type="text", in_list=False),
        Field("vendor_id", "Vendor", type="fk", fk_model=Account,
              fk_label=_account_label, in_list=False),
        Field("vendor_code", "Vendor Code", in_list=False),
        Field("l_price_gms", "L Price (Gms)", type="float", decimals=4, in_list=False),
        Field("cad_file_desc", "CAD File Desc", in_list=False),
        Field("part_no", "Part No", in_list=False),
        Field("metal_id", "Metal", type="fk", fk_model=Metal, fk_label=_metal_label,
              in_list=False),
        Field("weight", "Weight", type="float", decimals=4, in_list=False),
        Field("cavity_count", "Cavities", type="int", default=1, in_list=False),
        Field("rate", "Rate", type="float", in_list=False),

        Field("modifications", "Modification Update", type="child", in_list=False,
              help_text="Append-only history. Saved entries cannot be changed "
                        "or removed — add a new row instead.",
              child=ChildSpec(
                  model=MouldModification,
                  fk_attr="mould_id",
                  order_by="id",
                  append_only=True,
                  height=130,
                  row_template={"weight": 0, "remark": ""},
                  fields=[
                      Field("modified_on", "Date", type="date"),
                      Field("weight", "Weight", type="float", decimals=4),
                      Field("remark", "Remark"),
                  ],
              )),
    ],
))

# --- Stone reference masters (T-06) -------------------------------------
_simple_lookup = lambda o: o.name

for _key, _title, _model, _hint in (
    ("master.stone_group", "Stone Groups", StoneGroup, "Search by code or name…"),
    ("master.stone_shape", "Shapes", StoneShape, "Search by code or name…"),
    ("master.stone_kind", "Types", StoneKind, "Search by code or name…"),
    ("master.stone_quality", "Qualities", StoneQuality, "Search by code or name…"),
):
    _register(CrudSpec(
        key=_key, title=_title, model=_model, order_by="name", search_hint=_hint,
        fields=[
            Field("code", "Code", required=True),
            Field("name", "Name", required=True),
            Field("is_active", "Active", type="bool", default=True),
        ],
    ))

_register(CrudSpec(
    key="master.stone_size",
    title="Sizes",
    model=StoneSize,
    order_by="name",
    search_hint="Search by code or name…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Size", required=True,
              help_text="Open-ended — add new sizes as they come into use."),
        Field("size_mm", "Size (mm)", type="float", decimals=4),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

_register(CrudSpec(
    key="master.stone_info",
    title="Stone Info",
    model=StoneInfo,
    order_by="code",
    search_hint="Search by code, stone, colour…",
    fields=[
        Field("code", "Code", required=True,
              help_text="Indexed and searchable — staff filter by it."),
        Field("name", "Stone", required=True),
        Field("stone_group_id", "Stone Group", type="fk", fk_model=StoneGroup,
              fk_label=_simple_lookup),
        Field("stone_kind_id", "Type", type="fk", fk_model=StoneKind,
              fk_label=_simple_lookup),
        Field("shape_id", "Shape", type="fk", fk_model=StoneShape,
              fk_label=_simple_lookup),
        Field("quality_id", "Quality", type="fk", fk_model=StoneQuality,
              fk_label=_simple_lookup),
        Field("weight_unit", "Weight Unit", type="choice",
              choices=list(StoneInfo.WEIGHT_UNITS), default="ct",
              help_text="Travels with the stone into costing — carats for "
                        "diamond, pieces for CZ."),
        Field("is_active", "Active", type="bool", default=True),
        Field("size_id", "Size", type="fk", fk_model=StoneSize,
              fk_label=_simple_lookup, in_list=False),
        Field("color", "Colour", in_list=False),
        Field("sieve", "Sieve", in_list=False),
        Field("rate_per_unit", "Rate / unit", type="float", in_list=False),
        Field("hsn_code", "HSN Code", in_list=False),
    ],
))

# ==========================================================================
# S.K.U. module (8 September session)
# ==========================================================================
_item_label = lambda i: f"{i.code} - {i.name}"
_family_label = lambda f: f.name
_size_label = lambda s: s.name
_stonesku_label = lambda s: s.sku_code


# --- Item master (T-24) -------------------------------------------------
_register(CrudSpec(
    key="master.item",
    title="Items",
    model=Item,
    order_by="name",
    search_hint="Search by item name or code…",
    fields=[
        Field("name", "Item Name", required=True),
        Field("code", "Code", required=True,
              help_text="Used as the prefix for SKU codes."),
        Field("virtual_design_code", "Virtual Design Code",
              help_text="Prefix for design / CAD codes."),
        Field("mould_code", "Mould Code", help_text="Prefix for rubber-mould codes."),
        Field("family_id", "Family", type="fk", fk_model=FamilyCategory,
              fk_label=_family_label,
              help_text="A SKU with this item picks this family up automatically."),
        Field("unit", "Unit", type="choice", choices=["Pcs", "Gms", "Cts", "Set"],
              default="Pcs"),
        Field("pcs", "Pcs", type="int", default=1),
        Field("is_active", "Active", type="bool", default=True),
        Field("number", "Number", type="int", in_list=False),
        Field("shopify_code", "Shopify Code", in_list=False,
              help_text="Stored only — no storefront integration is built on it."),
        Field("price_ranges", "Sales Price Range (M.I.S.)", type="child", in_list=False,
              child=ChildSpec(
                  model=ItemPriceRange, fk_attr="item_id", order_by="srno", height=110,
                  row_template={"srno": 1, "price_from": 0, "price_to": 0},
                  fields=[
                      Field("srno", "S.No", type="int"),
                      Field("price_from", "Price From", type="float"),
                      Field("price_to", "Price To", type="float"),
                  ],
              )),
    ],
))


# --- Stone SKU catalogue (Harshit's flat model) --------------------------
_register(CrudSpec(
    key="sku.stone_sku",
    title="Stone SKUs",
    model=StoneSku,
    order_by="sku_code",
    search_hint="Search by Stone SKU, shape, quality, colour…",
    fields=[
        Field("sku_code", "Stone Sku", required=True,
              on_change=_stone_sku_autofill),
        Field("mrp", "MRP", in_list=False),
        Field("description", "Description", in_list=False),
        Field("stone", "Stone",
              help_text="Defaults to the Stone Sku text - type over it if the "
                         "stone name should differ."),
        Field("shape", "Shape"),
        Field("stone_type", "Type"),
        Field("quality", "Quality"),
        Field("color", "Color"),
        Field("shelf_no", "Shelf No.", in_list=False),
        Field("rfid", "RFID#", in_list=False),
        Field("range_label", "Range", in_list=False),
        Field("cost_price", "Cost Price", type="float", in_list=False),
        Field("sale_price", "Sale Price", type="float", in_list=False),
        Field("per", "Per", in_list=False),
        Field("size", "Size", in_list=False),
        Field("wt_per_pcs", "Wt/Pcs", type="float", decimals=4, in_list=False),
        Field("min_wt", "Min.Wt", type="float", decimals=4, in_list=False),
        Field("is_active", "Active", type="bool", default=True, in_list=False),
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

# --- Location (T-04) ----------------------------------------------------
_register(CrudSpec(
    key="master.location",
    title="Locations",
    model=Location,
    order_by="name",
    search_hint="Search by code, name, type, notes…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True,
              help_text="Where material physically sits — not a client."),
        Field("location_type", "Type", type="choice",
              choices=list(Location.LOCATION_TYPES), default="Karigar"),
        Field("is_active", "Active", type="bool", default=True,
              help_text="Deactivate rather than delete."),
        Field("account_id", "Linked Account", type="fk", fk_model=Account,
              fk_label=_account_label, in_list=False),
        Field("notes", "Notes", type="text", in_list=False),
        Field("materials", "Material Types Held", type="child", in_list=False,
              help_text="Tag whatever this location holds.",
              child=ChildSpec(
                  model=LocationMaterial,
                  fk_attr="location_id",
                  order_by="id",
                  height=110,
                  row_template={"material_type": "Gold"},
                  fields=[
                      Field("material_type", "Material Type", type="choice",
                            choices=list(LocationMaterial.MATERIAL_TYPES)),
                  ],
              )),
    ],
))

# --- Setting Type (T-12) ------------------------------------------------
_register(CrudSpec(
    key="master.setting_type",
    title="Setting Types",
    model=SettingType,
    order_by="name",
    search_hint="Search by code or name…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("price", "Price", type="float"),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Family / Category (T-12) -------------------------------------------
_register(CrudSpec(
    key="master.family_category",
    title="Families / Categories",
    model=FamilyCategory,
    order_by="name",
    search_hint="Search by code or name…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True,
              help_text="The jewellery family an item belongs to. Add more "
                        "whenever a new family comes into use."),
        Field("description", "Description", type="text", in_list=False),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Colour (T-12) ------------------------------------------------------
_register(CrudSpec(
    key="master.colour",
    title="Colours",
    model=Colour,
    order_by="name",
    search_hint="Search by code or name…",
    fields=[
        Field("code", "Code", required=True),
        Field("name", "Name", required=True),
        Field("is_default", "Default", type="bool",
              help_text="Yellow is the client's default gold colour."),
        Field("is_active", "Active", type="bool", default=True),
    ],
))

# --- Manufacturing Process (T-08) ---------------------------------------
_loss_choices = [f"{code} — {label}" for code, label, _ in costing.LOSS_BASES]
_process_label = lambda p: f"{p.code} - {p.name}"


# --- Product SKU Master (T-22) ------------------------------------------
def _stone_grid_summary(rows: list[dict]) -> str:
    """Pinned totals - staff read the totals, not the lines (UX11)."""
    pcs = sum(int(r.get("pieces") or 0) for r in rows)
    cts = sum(costing._dec(r.get("weight_cts")) for r in rows)
    amt = costing.stone_amount(rows)
    return f"TOTAL   {pcs} pcs   ·   {cts:.3f} cts   ·   {amt}"


def _fill_family_from_item(dialog, item_id) -> None:
    """Pick the Family up from the Item master when an Item is chosen.

    The client's rule: Family comes from the master automatically, while the
    metal karat is typed by hand every time. Only fills a blank Family, so a
    deliberate override is never stomped on.
    """
    family_editor = dialog.editors.get("family_id")
    if family_editor is None or family_editor.currentData() is not None:
        return
    if not item_id:
        return
    item = dialog.session.get(Item, item_id)
    if item is None or not item.family_id:
        return
    idx = family_editor.findData(item.family_id)
    if idx >= 0:
        family_editor.setCurrentIndex(idx)


def _show_metal_fineness(dialog, metal_id) -> None:
    """Put the chosen head's fineness beside the metal, as the legacy form does.

    Display only - costing always reads the fineness from the Metal master, so
    this copy can never drift into a calculation.
    """
    editor = dialog.editors.get("metal_fineness")
    if editor is None:
        return
    metal = dialog.session.get(Metal, metal_id) if metal_id else None
    editor.setValue(float(metal.purity_fineness) if metal is not None else 0.0)


def _fill_stone_price(grid, row: int, _value) -> None:
    """Pull a stone line's prices from the Stone SKU record.

    Each Stone SKU carries a single rate card - one range, one size, one pair
    of prices - so the line takes them straight off the chosen record. A figure
    the user typed themselves is left alone; only a blank, or one this function
    put there earlier, is replaced.
    """
    stone_sku_id = grid.cell_value(row, "stone_sku_id")
    if not stone_sku_id:
        return
    filled = getattr(grid, "_autofilled", None)
    if filled is None:
        filled = grid._autofilled = set()
    with SessionLocal() as session:
        sku = session.get(StoneSku, stone_sku_id)
    if sku is None:
        return
    for name, value in (("cost_price", sku.cost_price),
                        ("sale_price", sku.sale_price)):
        current = grid.cell_value(row, name)
        if current and (row, name) not in filled:
            continue
        grid.set_cell_value(row, name, value)
        filled.add((row, name))
    if sku.per:
        grid.set_cell_value(row, "per", sku.per)


def _price_product_sku(values: dict, children: dict, session) -> None:
    """Recompute the derived money panel from the stone grid and the metal head.

    Runs on every save so the stored figures always match the lines that
    produced them. Manual Price % is left alone - it is a separate override.
    """
    metal = session.get(Metal, values.get("metal_id")) if values.get("metal_id") else None
    rate_info = None
    if metal is not None:
        rate_info = rates.rate_for(session, metal.id, date.today())
    pure_rate = rate_info.rate if rate_info else Decimal("0")

    result = costing.cost_sku(
        stone_lines=children.get("stones", []),
        net_weight=values.get("net_weight") or 0,
        metal=metal,
        pure_rate_per_gram=pure_rate,
    )
    values["stone_amount"] = result.stone_amount
    values["metal_rate"] = result.metal_rate
    values["metal_amount"] = result.metal_amount
    values["total_rs"] = result.total_rs
    values["default_price"] = result.default_price

    # Each stone line stores its own amount, computed from the SALE price.
    for row in children.get("stones", []):
        row["amount"] = costing.stone_line_amount(
            row.get("weight_cts"), row.get("sale_price")
        )


_register(CrudSpec(
    key="sku.product_sku_master",
    title="Product SKUs",
    model=ProductSku,
    order_by="sku_code",
    search_hint="Search by SKU, description, design no, style…",
    before_save=_price_product_sku,
    # The eleven shortcuts listed down the right of the legacy screen. The
    # client uses them by reflex, so they are bound and shown. Those whose
    # panel belongs to a module that is not built yet say so rather than
    # doing nothing silently.
    shortcuts=[
        Shortcut("Ctrl+S", "Stone Info", target="stones"),
        Shortcut("Ctrl+I", "Image", action="image_attach"),
        Shortcut("Ctrl+R", "Remove Image", action="image_remove"),
        Shortcut("F5", "More Details", target="design_no"),
        Shortcut("Ctrl+F", "Finding Info",
                 note="Findings are not used by the client, so this panel is "
                      "not built. Raised as decision D2 in the 3 September session."),
        Shortcut("Ctrl+O", "Parts/Mould Info", target="master_sku",
                 note="Jumps to the reference fields. The Parts/Mould panel "
                      "arrives with the Manufacturing module."),
        Shortcut("Ctrl+L", "Labour Info",
                 note="Per-SKU labour was dropped from this screen at the client's request. Labour rates live in the Labour master, and karigar setting labour in the Setting Labour Chart."),
        Shortcut("Ctrl+P", "Mfg Process Info",
                 note="The per-SKU process routing panel arrives with the "
                      "Production Planning module."),
        Shortcut("Ctrl+G", "Client Ref(s)",
                 note="Client references arrive with the Quotation module."),
        Shortcut("Ctrl+N", "Vendor Ref(s)",
                 note="Vendor references arrive with the Purchase module."),
        Shortcut("Ctrl+T", "Extra Metal",
                 note="Extra-metal lines arrive with the Manufacturing module."),
    ],
    fields=[
        Field("sku_code", "SKU", required=True,
              help_text='e.g. "ER-1337", "625 CHOKAR", "BANG-597".'),
        Field("tag_price", "Tag Price", type="float", in_list=False,
              help_text="The figure the legacy screen prints under the SKU. Never "
                        "explained, so it is stored as entered and nothing is "
                        "derived from it."),
        Field("description", "Description"),
        Field("item_id", "Item", type="fk", fk_model=Item, fk_label=_item_label,
              on_change=_fill_family_from_item,
              help_text="Classifies the SKU. Family fills in from the master; "
                        "the metal karat is typed by hand."),
        Field("family_id", "Family", type="fk", fk_model=FamilyCategory,
              fk_label=_family_label),
        Field("metal_id", "Metal", type="fk", fk_model=Metal, fk_label=_metal_label,
              on_change=_show_metal_fineness),
        Field("metal_fineness", "Fineness", type="float", decimals=4, readonly=True,
              in_list=False,
              help_text="From the chosen metal head. Costing reads the master, "
                        "never this copy."),
        Field("gross_weight", "Gross Wt", type="float", decimals=4),
        Field("net_weight", "Net Wt", type="float", decimals=4,
              help_text="Metal is costed on net weight, not gross."),
        Field("is_active", "Active", type="bool", default=True),

        # -- money: derived, shown but never typed ----------------------
        Field("stone_amount", "Stone Amount", type="float", readonly=True, in_list=False),
        Field("metal_rate", "Mt Rate", type="float", decimals=4, readonly=True,
              in_list=False),
        Field("metal_amount", "Metal Amount", type="float", readonly=True, in_list=False),
        Field("total_rs", "TOTAL RS", type="float", readonly=True, in_list=False),
        Field("default_price", "Default Price RS", type="float", readonly=True,
              in_list=False,
              help_text="(Stone + Metal) × the margin multiplier. Recalculated on save."),
        # -- money: typed ------------------------------------------------
        # Labour Amount, Finding Labour and Setting Amount are deliberately
        # absent: the client confirmed they are not needed on this screen. The
        # verified record agrees - on ER-1337 all three were blank and TOTAL RS
        # equalled Stone Amount to the paisa. (Setting labour is still paid to
        # karigars; that lives in the Setting Labour Chart and its month-end
        # settlement, not here.)
        Field("manual_price_pct", "Manual Price %", type="float", decimals=4,
              in_list=False,
              help_text="A separate override. Stored alongside the derived price — "
                        "neither overwrites the other."),
        Field("extra_amount", "Extra Amt", type="float", in_list=False),

        # -- identity / classification ------------------------------------
        Field("remark", "Remark", in_list=False),
        Field("category", "Category", in_list=False),
        Field("category2", "Category 2", in_list=False),
        Field("pattern", "Pattern", in_list=False),
        Field("pattern2", "Pattern 2", in_list=False),
        Field("s_item", "S-Item", in_list=False),
        Field("style", "Style", in_list=False),
        Field("item_pcs", "Item Pcs", type="int", default=1, in_list=False),

        # -- physical -------------------------------------------------------
        Field("mt_plt_col", "Mt/Plt. Col", in_list=False),
        Field("enamal_col", "Enamal Col", in_list=False),
        Field("jewelry_size", "Jewelry Size", in_list=False),
        Field("chain_type", "Chain Type", in_list=False),
        Field("length", "L", in_list=False),
        Field("design_no", "Design No", in_list=False),
        Field("mt_loss_pct", "Mt Loss %", type="float", decimals=4, in_list=False),
        Field("tolerance_pct", "Tolerance %", type="float", decimals=4, in_list=False),
        Field("tolerance_g", "Tolerance G", type="bool", in_list=False),
        Field("avg_loss_pct", "Avg Loss %", type="float", decimals=4, in_list=False),
        Field("stamp", "Stamp", in_list=False),
        Field("snap", "Snap", in_list=False),
        Field("inscription", "Inscription", in_list=False),
        Field("jwl_type", "Jwl. Type", in_list=False),

        # -- flags ------------------------------------------------------------
        Field("is_rubber", "Rubber", type="bool", in_list=False),
        Field("is_master", "Master", type="bool", in_list=False),
        Field("is_cad", "CAD", type="bool", in_list=False),
        Field("is_cpx", "CPX", type="bool", in_list=False),
        Field("is_sizable", "Sizable", type="bool", in_list=False),
        Field("upc", "UPC", in_list=False),
        Field("link_cert", "Link Cert", in_list=False),
        Field("mc_pct", "MC %", type="float", decimals=4, readonly=True,
              in_list=False,
              help_text="Zero on every record seen and never explained — carried, "
                        "not computed."),
        Field("lc_pct", "LC %", type="float", decimals=4, readonly=True,
              in_list=False),

        # -- references (meaning not yet explained) -----------------------
        Field("master_sku", "MasterSKU", in_list=False),
        Field("sku_ref", "SKU Ref.", in_list=False),
        Field("hu_id", "HU Id", in_list=False),
        Field("min_pcs", "MIN.Pcs", type="int", in_list=False),
        Field("box_qty", "Box Qty", type="int", in_list=False),

        # -- images (T-25) --------------------------------------------------
        # Three images per SKU is the one thing the client asked for that the
        # legacy system does not already do. Cert Image already existed; the
        # CAD/STL file is a 3D attachment, deliberately separate from the CAD
        # image (which of the two the client meant is still open — Q20).
        Field("image_finished", "Finished", type="image", in_list=False),
        Field("image_design", "Design", type="image", in_list=False),
        Field("image_cad", "CAD", type="image", in_list=False),
        Field("image_cert", "Cert", type="image", in_list=False),
        Field("cad_stl_file", "CAD / STL File", in_list=False,
              help_text="A 3D file attachment — separate from the CAD image."),

        # -- stone bill of material ------------------------------------------
        Field("stones", "Stone Info", type="child", in_list=False,
              help_text="Amounts compute from the SALE price. Several rows per SKU "
                        "is normal.",
              child=ChildSpec(
                  model=ProductSkuStone, fk_attr="product_id", order_by="id",
                  height=200, summary=_stone_grid_summary,
                  row_template={"pieces": 0, "weight_cts": 0, "cost_price": 0,
                                "sale_price": 0, "per": "Cts"},
                  fields=[
                      Field("stone_sku_id", "SSKU", type="fk", fk_model=StoneSku,
                            fk_label=_stonesku_label, on_change=_fill_stone_price),
                      Field("description", "Description"),
                      Field("size_id", "Size", type="fk", fk_model=StoneSize,
                            fk_label=_size_label),
                      Field("wt_per_pcs", "Wt/Pcs", type="float", decimals=4),
                      Field("min_wt", "MinWt", type="float", decimals=4),
                      Field("pieces", "Pcs", type="int"),
                      Field("weight_cts", "Weight", type="float", decimals=4),
                      Field("brk_wt_pct", "Brk Wt%", type="float", decimals=4),
                      Field("cost_price", "Cost Price", type="float", decimals=4),
                      Field("sale_price", "Sale Price", type="float", decimals=4),
                      Field("per", "Per", type="choice",
                            choices=["Cts", "Pcs", "Gms"]),
                  ],
              )),
    ],
))
