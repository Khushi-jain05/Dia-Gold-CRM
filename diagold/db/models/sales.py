"""Ready-stock vouchers: one shape for every voucher that moves finished,
barcoded pieces (2 Oct Session 3 §4.5, §4.9-4.11):

    rs_sale              Sale ▸ Ready Stock ▸ Sale             out, Dr customer / Cr Sales A/c
    rs_sale_return       Sale ▸ Ready Stock ▸ Sale Return      back in, reverses the sale
    rs_approval          Sale ▸ Ready Stock ▸ Approval         out on approval with a party
    rs_approval_return   Sale ▸ Ready Stock ▸ Approval Return  back from approval
    rs_repair_issue      Sale ▸ Ready Stock ▸ Ready Repair Issue  out to repair for a party
    rp_purchase          Purchase ▸ Ready Items                in, new barcodes, Dr Purchase / Cr supplier
    rp_return            Purchase ▸ Ready Item Return          out, back to the supplier
    rp_opening           Purchase ▸ Opening Stock ▸ Ready Items  in, new barcodes, no accounts

A line is one piece (Stock No) with its weights and the amounts it was
valued at - metal at the voucher's rate, stones, setting, labour - stored
whole, so a printed invoice reproduces exactly.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class ReadyVoucher(Base, PKMixin, TimestampMixin):
    __tablename__ = "ready_vouchers"
    __table_args__ = (UniqueConstraint("vr_type", "vr_no", name="uq_ready_voucher_no"),)

    vr_type: Mapped[str] = mapped_column(String(24), index=True)
    vr_no: Mapped[int] = mapped_column(index=True)
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    vr_time: Mapped[str] = mapped_column(String(8), default="")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    ref_no: Mapped[str] = mapped_column(String(64), default="")
    currency_code: Mapped[str] = mapped_column(String(8), default="INR")
    credit_days: Mapped[int] = mapped_column(default=0)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    salesperson: Mapped[str] = mapped_column(String(64), default="")
    bank_name: Mapped[str] = mapped_column(String(64), default="")
    margin_type: Mapped[str] = mapped_column(String(32), default="")      # approval
    # Purchase bill block (Ready Items, Vr 56): bill date / number / account / amount.
    bill_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bill_no: Mapped[str] = mapped_column(String(40), default="")
    bill_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"),
                                                        nullable=True)
    bill_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Cash or Bill on a sale and its return (5 Oct D2: "sale me aur return me
    # dono me chahiye - cash aur bill").
    mode: Mapped[str] = mapped_column(String(8), default="Bill")
    # Prices From Client Chart was applied (5 Oct T-05).
    client_chart: Mapped[bool] = mapped_column(Boolean, default=False)

    lines: Mapped[list["ReadyVoucherLine"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan",
        order_by="ReadyVoucherLine.sno", lazy="selectin")


class ReadyVoucherLine(Base, PKMixin):
    __tablename__ = "ready_voucher_lines"

    voucher_id: Mapped[int] = mapped_column(ForeignKey("ready_vouchers.id", ondelete="CASCADE"))
    sno: Mapped[int] = mapped_column(default=1)
    stock_item_id: Mapped[int | None] = mapped_column(ForeignKey("stock_items.id"),
                                                      nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    product_sku_id: Mapped[int | None] = mapped_column(ForeignKey("product_skus.id"),
                                                       nullable=True)
    c_ref: Mapped[str] = mapped_column(String(64), default="")
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    title: Mapped[float] = mapped_column(Numeric(9, 3), default=0)        # Fine / Tunch %
    loss_pct: Mapped[float] = mapped_column(Numeric(9, 2), default=0)
    colour: Mapped[str] = mapped_column(String(16), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    pcs: Mapped[int] = mapped_column(default=1)
    old_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    gross_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    net_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    fine_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    metal_rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    metal_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    st_wt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)       # carats
    stone_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    setting_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    labour_rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    labour: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    other_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    # Stone breakup as valued: [{label, s_type, size, pcs, weight, unit, price}].
    stones_json: Mapped[str] = mapped_column(Text, default="[]")
    # Sold against an order line (From Order): updates its Shipped / Bal.
    order_line_id: Mapped[int | None] = mapped_column(ForeignKey("order_lines.id"),
                                                      nullable=True)
    # The approval / repair line this one closes (Approval Return, From Approval).
    source_line_id: Mapped[int | None] = mapped_column(nullable=True)
    remark: Mapped[str] = mapped_column(String(200), default="")

    voucher: Mapped[ReadyVoucher] = relationship(back_populates="lines")
