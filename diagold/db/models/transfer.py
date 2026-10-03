"""Inventory ▸ Stock Transfer (2 Oct Session 3 §4.6, R7, T-06): one voucher,
four panes - Ready Stock Outward, Metal, Stone, Ready Stock Transfer.

* Stock melting (Vr 557): a ready piece goes out of ready stock (BANG-103) and
  its metal and stones come back into a location's stock.
* Location transfer: stones out of one location (RAJAT JI) and into another
  (SONU JI); a ready piece moved to another location.

The client's narration of these screens was not captured, so what the loss
columns mean is an assumption (UNCONFIRMED, 2 Oct Q6): a location's stock
moves by In / Out only, and the loss columns are recorded beside them for the
loss registers.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class StockTransfer(Base, PKMixin, TimestampMixin):
    __tablename__ = "stock_transfers"

    vr_no: Mapped[int] = mapped_column(unique=True, index=True)
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    contact_person: Mapped[str] = mapped_column(String(64), default="")
    ref_no: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["StockTransferLine"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan",
        order_by="StockTransferLine.id", lazy="selectin")


class StockTransferLine(Base, PKMixin):
    __tablename__ = "stock_transfer_lines"

    transfer_id: Mapped[int] = mapped_column(ForeignKey("stock_transfers.id", ondelete="CASCADE"))
    # ready_out · metal · stone · ready_transfer
    pane: Mapped[str] = mapped_column(String(16))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    # ready panes: the piece, and where it was before (to undo)
    stock_item_id: Mapped[int | None] = mapped_column(ForeignKey("stock_items.id"),
                                                      nullable=True)
    prev_location_id: Mapped[int | None] = mapped_column(nullable=True)
    # metal / stone panes
    mt_type: Mapped[str] = mapped_column(String(16), default="Actual")
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    colour: Mapped[str] = mapped_column(String(16), default="")
    stone_sku_id: Mapped[int | None] = mapped_column(ForeignKey("stone_skus.id"), nullable=True)
    particulars: Mapped[str] = mapped_column(String(120), default="")
    s_type: Mapped[str] = mapped_column(String(24), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    in_pcs: Mapped[int] = mapped_column(default=0)
    in_wt: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    in_loss_pcs: Mapped[int] = mapped_column(default=0)
    in_loss_wt: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    out_pcs: Mapped[int] = mapped_column(default=0)
    out_wt: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    out_loss_pcs: Mapped[int] = mapped_column(default=0)
    out_loss_wt: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    unit: Mapped[str] = mapped_column(String(8), default="")
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    job_no: Mapped[int | None] = mapped_column(nullable=True)
    remark: Mapped[str] = mapped_column(String(200), default="")

    transfer: Mapped[StockTransfer] = relationship(back_populates="lines")
