"""Manufacturing: MFG Ready Stock Transfer and the ready stock it creates
(28 Sept R10-R12, T-07 / T-08).

A finished job (last route step received) is Pending for MFG Transfer. The
transfer prices it - every figure of the Fill Prices chain is stored on the
line, so a later rate change never re-prices history - and each line creates
one ready-stock item with its own Stock No / bar code, In Stock at Primary.
Deleting that item (Item Search) sends the job back to Pending for MFG
Transfer, with an audit row holding everything that was deleted.

Numbers are explicit integers, never autoincrement, so the legacy Vr 1081 and
Stock No 44733 can migrate as they are.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class MfgTransfer(Base, PKMixin, TimestampMixin):
    """One MFG Ready Stock Transfer voucher - many jobs, one per line."""

    __tablename__ = "mfg_transfers"

    vr_no: Mapped[int] = mapped_column(unique=True, index=True)
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    ref_no: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # "Split Jobs" (2 Oct §4.4): a job of several pieces becomes one stock
    # piece (Stock No) per piece instead of one for the lot.
    split_jobs: Mapped[bool] = mapped_column(Boolean, default=False)

    lines: Mapped[list["MfgTransferLine"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan",
        order_by="MfgTransferLine.sno", lazy="selectin",
    )


class MfgTransferLine(Base, PKMixin):
    """One job on a transfer, priced. Column names follow the legacy grid."""

    __tablename__ = "mfg_transfer_lines"

    transfer_id: Mapped[int] = mapped_column(
        ForeignKey("mfg_transfers.id", ondelete="CASCADE"))
    sno: Mapped[int] = mapped_column(default=1)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    pcs: Mapped[int] = mapped_column(default=1)
    gross_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    net_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    title: Mapped[float] = mapped_column(Numeric(9, 3), default=0)
    fine_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    loss_pct: Mapped[float] = mapped_column(Numeric(9, 2), default=0)
    rej_pcs: Mapped[int] = mapped_column(default=0)
    rej_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    fine_rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    metal_rate: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    metal_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    stone_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    setting_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    ex_metal_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    finding_labour: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    labour_rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    labour_weight: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    labour: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    manual_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    margin_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    margin_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    price_per_pcs: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    tag_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    tag_text: Mapped[str] = mapped_column(String(24), default="")
    is_repair: Mapped[bool] = mapped_column(Boolean, default=False)
    stamp: Mapped[str] = mapped_column(String(32), default="")
    # The stone lines of the cost break-up as priced, JSON.
    stones_json: Mapped[str] = mapped_column(Text, default="[]")

    transfer: Mapped[MfgTransfer] = relationship(back_populates="lines")


class StockItem(Base, PKMixin, TimestampMixin):
    """A finished piece in ready stock, found by Item Search (28 Sept R11)."""

    __tablename__ = "stock_items"

    stock_no: Mapped[int] = mapped_column(unique=True, index=True)   # also the bar code
    # Empty for a piece bought in ready or loaded as opening stock (2 Oct T-07).
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    line_id: Mapped[int | None] = mapped_column(
        ForeignKey("mfg_transfer_lines.id", ondelete="SET NULL"), nullable=True)
    product_sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_skus.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="in_stock")
    pcs: Mapped[int] = mapped_column(default=1)
    gross_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    net_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    tag_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    tag_text: Mapped[str] = mapped_column(String(24), default="")
    cert_no: Mapped[str] = mapped_column(String(40), default="")
    huid: Mapped[str] = mapped_column(String(16), default="")
    tag_printed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Where the piece came from: "mfg" (MFG transfer), "purchase" (Ready Items),
    # "opening" (opening stock); the ready voucher line that brought it in.
    source: Mapped[str] = mapped_column(String(12), default="mfg")
    in_line_id: Mapped[int | None] = mapped_column(nullable=True)
    # Self-describing for a piece with no job (bought in).
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    colour: Mapped[str] = mapped_column(String(16), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    c_ref: Mapped[str] = mapped_column(String(64), default="")
    # The party holding it while it is out on approval or for repair.
    holder_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"),
                                                          nullable=True)

    # in_stock · sold · on_approval (with a party) · in_repair (issued to
    # repair for a party) · returned (sent back to the supplier).
    STATUSES = ("in_stock", "sold", "on_approval", "in_repair", "returned")


class DeletionLog(Base, PKMixin):
    """Who deleted what, when, and the full record as it was (28 Sept TR9)."""

    __tablename__ = "deletion_log"

    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    ref: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(200), default="")
    before_json: Mapped[str] = mapped_column(Text, default="{}")


class VoucherAttachment(Base, PKMixin):
    """A document attached to a voucher - "Attach Doc" on the legacy receipt
    and purchase screens (28 Sept §4.4, §4.12): a karigar's slip, a supplier
    bill. The file is copied into the data folder, so it stays with the data."""

    __tablename__ = "voucher_attachments"

    ref_kind: Mapped[str] = mapped_column(String(24), index=True)   # job_voucher / metal_purchase …
    ref_no: Mapped[int] = mapped_column(index=True)                 # the voucher number
    file_name: Mapped[str] = mapped_column(String(200))             # as it was chosen
    stored_path: Mapped[str] = mapped_column(String(400))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
