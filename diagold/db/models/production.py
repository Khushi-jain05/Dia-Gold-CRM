"""Order -> Production-Planning models (11 September session).

The production backbone the client walked through: an ORDER allots one JOB per
SKU line; a job is MAPPED to an ordered route of process steps; every material
movement on a step is a numbered VOUCHER (issue or receive) carrying the worker
and both weights, so loss per step is derived, never typed; stones issued to a
job sit in its BAG until they are issued to a setter, returned to stock, broken
or lost.

Identifiers (order no, job no, voucher no) are plain integers set explicitly,
never database autoincrement, because the client's live numbers - orders 1224
and 1338, jobs 28350 and 28622-28624, vouchers 706-3242 - must migrate with
their numbers intact (TR10).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


# --------------------------------------------------------------------------
# Order
# --------------------------------------------------------------------------
class Order(Base, PKMixin, TimestampMixin):
    """A customer (or stock) order. Saving it allots one job per line (R1).

    Field rules were narrated on the call but the recording has no audio for
    that window (§4.1, AUDIO LOST) - the header mirrors the legacy screen and
    validation stays light until the client re-covers it (C-05).
    """

    __tablename__ = "orders"

    order_no: Mapped[int] = mapped_column(unique=True, index=True)
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    ref: Mapped[str] = mapped_column(String(64), default="")
    terms: Mapped[str] = mapped_column(String(120), default="")
    currency_code: Mapped[str] = mapped_column(String(8), default="INR")
    # "Customer" or "Stock" - orders can be for a named customer or for stock.
    order_type: Mapped[str] = mapped_column(String(16), default="Customer")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Heard as a field entered at order time; values and effect unknown (Q9).
    priority: Mapped[str] = mapped_column(String(24), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")

    ORDER_TYPES = ("Customer", "Stock")

    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
        order_by="OrderLine.sno", lazy="selectin",
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"Order {self.order_no}"


class OrderLine(Base, PKMixin):
    """One SKU line of an order. Each line becomes a job."""

    __tablename__ = "order_lines"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    sno: Mapped[int] = mapped_column(default=1)
    product_sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_skus.id"), nullable=True
    )
    sku_desc: Mapped[str] = mapped_column(String(200), default="")
    c_ref: Mapped[str] = mapped_column(String(64), default="")   # customer's reference
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    colour: Mapped[str] = mapped_column(String(16), default="")
    size: Mapped[str] = mapped_column(String(32), default="")
    pcs: Mapped[int] = mapped_column(default=1)
    net_wt_per_pcs: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    tot_gross_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    metal_rate_unit: Mapped[str] = mapped_column(String(16), default="")
    metal_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(24), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")

    order: Mapped[Order] = relationship(back_populates="lines")


# --------------------------------------------------------------------------
# Job and its route
# --------------------------------------------------------------------------
class Job(Base, PKMixin, TimestampMixin):
    """One piece (or lot) being manufactured against an order line.

    Job numbers are a single global sequence (order 1338 -> 28622, 28623,
    28624), not per order (TR1). A job is linked to its order by number and
    line serial rather than a foreign key to the line row, so re-saving the
    order (which rewrites its lines) never orphans the job.
    """

    __tablename__ = "jobs"

    job_no: Mapped[int] = mapped_column(unique=True, index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    line_sno: Mapped[int] = mapped_column(default=1)
    product_sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_skus.id"), nullable=True
    )
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    c_ref: Mapped[str] = mapped_column(String(64), default="")
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    colour: Mapped[str] = mapped_column(String(16), default="")
    pcs: Mapped[int] = mapped_column(default=1)
    prod_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    prod_del_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    # pending (no route) -> mapped -> in_progress (first voucher) -> complete;
    # cancelled when its order line is removed before any movement.
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # When the route was set (Job Mapping day book) and when the last step
    # was received back (STOCK DT in Job Stock Analysis - assumed to be the
    # final receipt; MFG transfer is a later module, see 18 Sept Q8).
    mapped_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str] = mapped_column(String(200), default="")

    STATUSES = ("pending", "mapped", "in_progress", "complete", "cancelled")

    steps: Mapped[list["JobStep"]] = relationship(
        back_populates="job", cascade="all, delete-orphan",
        order_by="JobStep.seq", lazy="selectin",
    )
    # Read-only conveniences for labels ("28350 · NS-2968 · RUBY SINGH").
    product_sku = relationship("ProductSku", lazy="joined", viewonly=True)
    account = relationship("Account", lazy="joined", viewonly=True)

    @property
    def label(self) -> str:
        sku = self.product_sku.sku_code if self.product_sku else ""
        who = self.account.name if self.account else "stock"
        return " · ".join(p for p in (str(self.job_no), sku, who) if p)

    def __str__(self) -> str:  # pragma: no cover
        return self.label


class JobStep(Base, PKMixin):
    """One step of a job's route, copied from a process group at mapping time
    and editable per job afterwards - a repair step may be inserted (TR2)."""

    __tablename__ = "job_steps"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(default=1)
    process_id: Mapped[int] = mapped_column(ForeignKey("manufacturing_processes.id"))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Copied from the process when the route is set, so a later change to the
    # master never rewrites history. CAD carries no metal weight (TR5).
    weight_bearing: Mapped[bool] = mapped_column(Boolean, default=True)

    job: Mapped[Job] = relationship(back_populates="steps")


# --------------------------------------------------------------------------
# Issue / receive vouchers
# --------------------------------------------------------------------------
class JobVoucher(Base, PKMixin, TimestampMixin):
    """One material movement on a job step - an ISSUE to a worker or a RECEIVE
    back from them (TR3).

    A receive points at the issue it closes, so WIP is simply "issues with no
    receive" and loss per step is issue.net_wt - receive.net_wt - scrap - dust
    (TR4) - computed, never stored.
    """

    __tablename__ = "job_vouchers"

    vr_no: Mapped[int] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(8))          # issue / receive
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    step_id: Mapped[int] = mapped_column(ForeignKey("job_steps.id", ondelete="CASCADE"))
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_vouchers.id", ondelete="SET NULL"), nullable=True
    )
    # Workers are Accounts of type Worker; the office itself is one ("Office").
    worker_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    vr_time: Mapped[str] = mapped_column(String(5), default="")   # "16:52"
    pcs: Mapped[int] = mapped_column(default=0)
    gross_wt: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    net_wt: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    # issue side
    stone_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    extra: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    finding: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    mould: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    wip_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    # receive side
    del_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rej_pcs: Mapped[int] = mapped_column(default=0)
    rej_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    scrap: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    dust: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    KINDS = ("issue", "receive")


# --------------------------------------------------------------------------
# Stock and the stone side of a job
# --------------------------------------------------------------------------
class MaterialStock(Base, PKMixin):
    """What a location holds, by material class.

    One balance row per (location, class, reference, size). Stone rows point
    at a Stone SKU, metal rows at a Metal, mould rows at a Part/Mould; finding
    rows carry only text because the Findings master is retired (S1 D2).
    """

    __tablename__ = "material_stock"

    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    material_class: Mapped[str] = mapped_column(String(8))   # stone/metal/mould/finding
    ref_id: Mapped[int | None] = mapped_column(nullable=True)
    ref_text: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    pcs: Mapped[int] = mapped_column(default=0)
    weight: Mapped[float] = mapped_column(Numeric(14, 4), default=0)

    CLASSES = ("stone", "metal", "mould", "finding")


class StoneIssue(Base, PKMixin, TimestampMixin):
    """Stone - Issue On Job-Card: stones move from a stock location into a
    job's bag (§4.2). The client's narration of this screen was not recorded;
    field meanings are read from the legacy screen - confirm before release
    (C-05)."""

    __tablename__ = "stone_issues"

    vr_no: Mapped[int] = mapped_column(unique=True, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    ref_no: Mapped[str] = mapped_column(String(64), default="")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    barcode: Mapped[str] = mapped_column(String(64), default="")
    lot_no: Mapped[str] = mapped_column(String(32), default="")
    # ASSUMPTION: "Opening" means the stones were already with the job when the
    # system started, so no stock location is reduced. Confirm (C-05).
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["StoneIssueLine"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan",
        order_by="StoneIssueLine.sno", lazy="selectin",
    )


class StoneIssueLine(Base, PKMixin):
    __tablename__ = "stone_issue_lines"

    issue_id: Mapped[int] = mapped_column(ForeignKey("stone_issues.id", ondelete="CASCADE"))
    sno: Mapped[int] = mapped_column(default=1)
    # "For Multiple…": a line may go to a different job than the header's.
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    stone_sku_id: Mapped[int | None] = mapped_column(ForeignKey("stone_skus.id"), nullable=True)
    particulars: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    wt_per_pcs: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    req_pcs: Mapped[int] = mapped_column(default=0)
    req_wt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    pcs: Mapped[int] = mapped_column(default=0)
    weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    price_unit: Mapped[str] = mapped_column(String(8), default="Cts")
    s_type: Mapped[str] = mapped_column(String(32), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")

    issue: Mapped[StoneIssue] = relationship(back_populates="lines")


class JobBagLine(Base, PKMixin):
    """One stone type + size within a job's bag (§4.5).

    Every quantity on the ledger is derived from the movements beneath it -
    nothing on this row is a running total that could drift.
    """

    __tablename__ = "job_bag_lines"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    stone_sku_id: Mapped[int | None] = mapped_column(ForeignKey("stone_skus.id"), nullable=True)
    particulars: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    s_type: Mapped[str] = mapped_column(String(32), default="")
    # Unit travels with the stone (ct for diamond/polki/colour stones, pcs
    # for some imitation stones) - S1 T-06.
    unit: Mapped[str] = mapped_column(String(8), default="ct")
    req_pcs: Mapped[int] = mapped_column(default=0)
    req_wt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    # Where the stones came from, so a return goes back to the same shelf.
    source_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )

    movements: Mapped[list["JobBagMovement"]] = relationship(
        back_populates="line", cascade="all, delete-orphan",
        order_by="JobBagMovement.id", lazy="selectin",
    )
    job = relationship("Job", lazy="joined", viewonly=True)

    @property
    def label(self) -> str:
        job_no = self.job.job_no if self.job else "?"
        return f"{job_no} · {self.particulars} {self.size}".strip()


class JobBagMovement(Base, PKMixin, TimestampMixin):
    """One change to a bag line: received into the bag, issued to a worker,
    returned to stock, broken, lost, or back from the worker into the bag."""

    __tablename__ = "job_bag_movements"

    line_id: Mapped[int] = mapped_column(ForeignKey("job_bag_lines.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))
    pcs: Mapped[int] = mapped_column(default=0)
    weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    mv_date: Mapped[date] = mapped_column(Date, default=date.today)
    worker_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    ref_kind: Mapped[str] = mapped_column(String(16), default="")   # stone_issue / inv_return
    ref_id: Mapped[int | None] = mapped_column(nullable=True)
    remark: Mapped[str] = mapped_column(String(200), default="")

    KINDS = ("rcvd", "iss", "rtn", "break", "lost", "back")

    line: Mapped[JobBagLine] = relationship(back_populates="movements")


class InventoryReturn(Base, PKMixin, TimestampMixin):
    """Rtn to Inv - Stone / Metal / Mould / Finding: material leaves a job and
    re-enters stock at a location (TR7). Four variants with one shape."""

    __tablename__ = "inventory_returns"

    vr_no: Mapped[int] = mapped_column(unique=True, index=True)
    material_class: Mapped[str] = mapped_column(String(8), default="stone")
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["InventoryReturnLine"]] = relationship(
        back_populates="ret", cascade="all, delete-orphan",
        order_by="InventoryReturnLine.sno", lazy="selectin",
    )


class InventoryReturnLine(Base, PKMixin):
    __tablename__ = "inventory_return_lines"

    return_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_returns.id", ondelete="CASCADE")
    )
    sno: Mapped[int] = mapped_column(default=1)
    # stone: the bag line the pieces leave; metal / mould: the master row.
    bag_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_bag_lines.id"), nullable=True
    )
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    mould_id: Mapped[int | None] = mapped_column(ForeignKey("parts_moulds.id"), nullable=True)
    particulars: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    pcs: Mapped[int] = mapped_column(default=0)
    weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    # Returned goes back to saleable stock at the location; Breakage is
    # recorded separately and credits nothing (valuation open - 18 Sept Q5).
    rtn_type: Mapped[str] = mapped_column(String(12), default="Returned")
    # Credited location per line - the shelf the stones were picked from.
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    price_unit: Mapped[str] = mapped_column(String(8), default="Cts")
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    remark: Mapped[str] = mapped_column(String(200), default="")

    RTN_TYPES = ("Returned", "Breakage")

    ret: Mapped[InventoryReturn] = relationship(back_populates="lines")


class StockMovement(Base, PKMixin):
    """The stock ledger behind :class:`MaterialStock` (18 Sept, TR3).

    Every change to a location's holding is one row here, so the location x
    stone-group report can show OPENING / INWARD / OUTWARD / CLOSING for any
    period and drill from a cell to the vouchers behind it. Balance rows in
    MaterialStock are the fast total; this is the truth they summarise.
    """

    __tablename__ = "stock_movements"

    mv_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    material_class: Mapped[str] = mapped_column(String(8), default="stone")
    ref_id: Mapped[int | None] = mapped_column(nullable=True)
    ref_text: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    # DIAMOND / POLKI / COLOR STONE - the client's three heads (S1 D4, S3 D9).
    stone_group: Mapped[str] = mapped_column(String(24), default="", index=True)
    # opening / inward / outward / return / breakage / adjust
    kind: Mapped[str] = mapped_column(String(10), index=True)
    pcs: Mapped[int] = mapped_column(default=0)              # signed
    weight: Mapped[float] = mapped_column(Numeric(14, 4), default=0)   # signed
    value: Mapped[float] = mapped_column(Numeric(18, 2), default=0)    # signed
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    ref_kind: Mapped[str] = mapped_column(String(16), default="")   # stone_issue / inv_return / bag
    ref_no: Mapped[int | None] = mapped_column(nullable=True)      # the voucher number
    remark: Mapped[str] = mapped_column(String(200), default="")

    KINDS = ("opening", "inward", "outward", "return", "breakage", "adjust")


class JobComment(Base, PKMixin):
    """Timestamped, user-attributed notes on a job (Job History > Add
    Comments, 18 Sept R14)."""

    __tablename__ = "job_comments"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    text: Mapped[str] = mapped_column(Text, default="")


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------
class PrintTemplate(Base, PKMixin, TimestampMixin):
    """A print layout held as data, not code (TR8).

    The body is HTML with {{placeholders}} and {{#steps}}...{{/steps}} /
    {{#stones}}...{{/stones}} repeating blocks, so the client's Word job-sheet
    format can be reproduced - and adjusted later - without a developer.
    Until that Word file arrives (C-02) every seeded template is a clearly
    marked placeholder.
    """

    __tablename__ = "print_templates"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(24))
    body: Mapped[str] = mapped_column(Text, default="")
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    KINDS: tuple[tuple[str, str], ...] = (
        ("job_sheet", "Job Sheet"),
        ("job_request", "Job Request"),
        ("stone_req", "Stone Requirements"),
        ("finding_req", "Finding Requirements"),
        ("blank_back", "Blank Process Sheet Back"),
        ("blank_front", "Blank Process Sheet"),
    )


class PrintLog(Base, PKMixin):
    """What was printed, when, by whom - T-04 engine requirement 4."""

    __tablename__ = "print_log"

    printed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("print_templates.id"), nullable=True
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    file_path: Mapped[str] = mapped_column(String(255), default="")


class AppSetting(Base, PKMixin):
    """Key/value configuration - e.g. which Production-Planning menu items are
    shown, so the menu is scoped by configuration and never by a code change
    (T-07)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), unique=True)
    value: Mapped[str] = mapped_column(String(255), default="")
