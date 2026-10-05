"""Small charts drawn with QPainter - no extra library to ship (5 Oct UX3,
T-13 Sales Dashboard, T-14 dashboard)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

PALETTE = ["#C9A227", "#0E6B54", "#3B6FB6", "#B4472E", "#7A5B9A", "#2E8B8B", "#8C6D1F",
           "#5C6661", "#D17A22", "#4F7A28"]


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float, Decimal)) else 0.0


class BarChart(QWidget):
    """Vertical bars with their labels and values; negative bars go down."""

    def __init__(self, labels: list[str], values: list, title: str = "", parent=None,
                 decimals: int = 0):
        super().__init__(parent)
        self.labels, self.values, self.title = labels, [_num(v) for v in values], title
        self.decimals = decimals
        self.setMinimumSize(420, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        w, h = self.width(), self.height()
        top = 28 if self.title else 10
        left, right, bottom = 12, 12, 46
        if self.title:
            f = QFont()
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(0, 4, w, 20), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setFont(QFont())
        if not self.values:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data")
            return
        hi = max(max(self.values), 0.0)
        lo = min(min(self.values), 0.0)
        span = (hi - lo) or 1.0
        area_h = h - top - bottom
        zero_y = top + area_h * (hi / span)
        n = len(self.values)
        slot = (w - left - right) / n
        bw = max(slot * 0.65, 2)
        p.setPen(QPen(QColor("#9AA1AC")))
        p.drawLine(int(left), int(zero_y), int(w - right), int(zero_y))
        small = QFont()
        small.setPointSizeF(8)
        for i, (lab, v) in enumerate(zip(self.labels, self.values)):
            x = left + slot * i + (slot - bw) / 2
            bh = area_h * abs(v) / span
            y = zero_y - bh if v >= 0 else zero_y
            p.fillRect(QRectF(x, y, bw, bh), QColor(PALETTE[i % len(PALETTE)] if n <= 10
                                                   else PALETTE[0]))
            p.setPen(QColor("#222"))
            p.setFont(small)
            txt = f"{v:,.{self.decimals}f}"
            p.drawText(QRectF(x - 20, (y - 14) if v >= 0 else (y + bh), bw + 40, 14),
                       Qt.AlignmentFlag.AlignCenter, txt)
            p.drawText(QRectF(left + slot * i, h - bottom + 4, slot, bottom - 6),
                       Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, str(lab)[:18])


class PieChart(QWidget):
    """Share of each label in the total, with a legend."""

    def __init__(self, labels: list[str], values: list, title: str = "", parent=None):
        super().__init__(parent)
        self.labels, self.values, self.title = labels, [max(_num(v), 0.0) for v in values], title
        self.setMinimumSize(320, 240)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        total = sum(self.values)
        top = 26 if self.title else 6
        if self.title:
            f = QFont()
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(0, 4, self.width(), 20), Qt.AlignmentFlag.AlignCenter, self.title)
            p.setFont(QFont())
        if not total:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data")
            return
        d = min(self.height() - top - 10, self.width() * 0.5)
        rect = QRectF(10, top, d, d)
        start = 90 * 16
        for i, v in enumerate(self.values):
            span = int(-360 * 16 * v / total)
            p.setBrush(QColor(PALETTE[i % len(PALETTE)]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPie(rect, start, span)
            start += span
        p.setPen(QColor("#222"))
        y = top
        for i, (lab, v) in enumerate(zip(self.labels, self.values)):
            if not v:
                continue
            p.fillRect(QRectF(d + 24, y + 3, 10, 10), QColor(PALETTE[i % len(PALETTE)]))
            p.drawText(QRectF(d + 40, y, self.width() - d - 44, 16), Qt.AlignmentFlag.AlignLeft,
                       f"{lab}  {v:,.0f}  ({100 * v / total:.0f}%)")
            y += 18
