"""Declarative CRUD specs for the Master and SKU screens."""
from __future__ import annotations

from diagold.db.models import (
    Account,
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
    Role,
    SettingLabourRate,
    SettingType,
    SkuInfo,
    StoneInfo,
    StonePacket,
    User,
)
from diagold.services import costing
from diagold.ui.crud import ChildSpec, CrudSpec, Field

_metal_label = lambda m: f"{m.code} - {m.name}".strip(" -")
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
