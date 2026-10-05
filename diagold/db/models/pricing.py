"""Client-wise price charts (5 Oct Session 4 §4.7, T-05).

A PriceChart is a "price type" - "A", "MANNU BHAI" - with a default labour
per gram (MANNU BHAI = 1,175). Clients are put on a chart from the Account
master. Each chart carries three rule tables - labour, stone, setting -
whose match fields are text: blank matches anything. Rules are tried in
priority order (Set Priority) and the first match wins; with no match the
chart default applies, and with no chart, the standard master price.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class PriceChart(Base, PKMixin, TimestampMixin):
    __tablename__ = "price_charts"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    labour_per_gm: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    # Client Wise Stone Price header: Price Type and Stone Quality.
    price_type: Mapped[str] = mapped_column(String(40), default="")
    stone_quality: Mapped[str] = mapped_column(String(40), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")

    labour_rules: Mapped[list["PriceChartLabour"]] = relationship(
        cascade="all, delete-orphan", order_by="PriceChartLabour.priority", lazy="selectin")
    stone_rules: Mapped[list["PriceChartStone"]] = relationship(
        cascade="all, delete-orphan", order_by="PriceChartStone.priority", lazy="selectin")
    setting_rules: Mapped[list["PriceChartSetting"]] = relationship(
        cascade="all, delete-orphan", order_by="PriceChartSetting.priority", lazy="selectin")


class PriceChartLabour(Base, PKMixin):
    __tablename__ = "price_chart_labour"

    chart_id: Mapped[int] = mapped_column(ForeignKey("price_charts.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(default=0)
    family: Mapped[str] = mapped_column(String(80), default="")
    style: Mapped[str] = mapped_column(String(64), default="")
    sku: Mapped[str] = mapped_column(String(40), default="")
    item: Mapped[str] = mapped_column(String(80), default="")
    metal: Mapped[str] = mapped_column(String(64), default="")
    colour: Mapped[str] = mapped_column(String(16), default="")
    labour: Mapped[str] = mapped_column(String(40), default="")       # the labour's name
    from_gwt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    to_gwt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)  # 0 = no upper limit
    sale_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    per_unit: Mapped[str] = mapped_column(String(8), default="gm")    # gm / pc
    cost_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)


class PriceChartStone(Base, PKMixin):
    __tablename__ = "price_chart_stone"

    chart_id: Mapped[int] = mapped_column(ForeignKey("price_charts.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(default=0)
    family: Mapped[str] = mapped_column(String(80), default="")
    metal: Mapped[str] = mapped_column(String(64), default="")
    style: Mapped[str] = mapped_column(String(64), default="")
    sku: Mapped[str] = mapped_column(String(40), default="")
    stone_group: Mapped[str] = mapped_column(String(40), default="")
    ssku: Mapped[str] = mapped_column(String(64), default="")
    stone: Mapped[str] = mapped_column(String(80), default="")
    shape: Mapped[str] = mapped_column(String(32), default="")
    stone_type: Mapped[str] = mapped_column(String(32), default="")
    quality: Mapped[str] = mapped_column(String(32), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    unit: Mapped[str] = mapped_column(String(8), default="ct")        # ct / pc
    cost_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)


class PriceChartSetting(Base, PKMixin):
    __tablename__ = "price_chart_setting"

    chart_id: Mapped[int] = mapped_column(ForeignKey("price_charts.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(default=0)
    setting_type: Mapped[str] = mapped_column(String(80), default="")
    stone_group: Mapped[str] = mapped_column(String(40), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)   # per piece
