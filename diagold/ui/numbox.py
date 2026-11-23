"""Number boxes as plain text boxes, app-wide (23 Nov).

On the client's Windows PC every QSpinBox / QDoubleSpinBox showed nothing -
Weight, Pcs, Rate typed but not seen - on every tab, through two fixes of
the spin box (dark text, 17 Nov; the inner field's width, 18 Nov), while
plain text boxes always showed. So the spin boxes are not used at all: every
screen module imports ``SpinBox`` / ``DoubleSpinBox`` from here under the
names QSpinBox / QDoubleSpinBox (patching PySide6.QtWidgets itself breaks
PySide's own type lookups - every table crashed). They are QLineEdits
that speak the spin box's API (value / setValue / valueChanged / setRange /
setDecimals / setSuffix / setSpecialValueText / setGroupSeparatorShown ...),
so no screen's code changes: digits only, the value formatted on leaving
the box, Up / Down step it, the whole value selected on entering it, and the
wheel never changes it.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit

_ALLOWED = set("0123456789.,-")


class _NumBox(QLineEdit):
    ButtonSymbols = QAbstractSpinBox.ButtonSymbols
    CorrectionMode = QAbstractSpinBox.CorrectionMode
    StepType = QAbstractSpinBox.StepType

    _INT = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min, self._max = 0.0, 99.0 if self._INT else 99.99
        self._decimals = 0 if self._INT else 2
        self._value = 0.0
        self._step = 1.0
        self._prefix = self._suffix = self._special = ""
        self._groups = False
        self._entering = False
        self.textEdited.connect(self._typed)
        self.editingFinished.connect(self._show)
        self._show()

    # -- the spin box's API ------------------------------------------------
    def value(self):
        return int(round(self._value)) if self._INT else self._value

    def setValue(self, value) -> None:  # noqa: N802 - Qt name
        try:
            v = float(value if value not in (None, "") else 0)
        except (TypeError, ValueError):
            v = 0.0
        v = self._fit(v)
        changed = v != self._value
        self._value = v
        self._show()
        if changed:
            self._emit()

    def _emit(self) -> None:
        self.valueChanged.emit(self.value())

    def _fit(self, v: float) -> float:
        v = min(max(v, self._min), self._max)
        return float(int(round(v))) if self._INT else round(v, self._decimals)

    def minimum(self):
        return int(self._min) if self._INT else self._min

    def maximum(self):
        return int(self._max) if self._INT else self._max

    def setMinimum(self, lo) -> None:  # noqa: N802
        self.setRange(lo, max(float(lo), self._max))

    def setMaximum(self, hi) -> None:  # noqa: N802
        self.setRange(min(float(hi), self._min), hi)

    def setRange(self, lo, hi) -> None:  # noqa: N802
        self._min, self._max = float(lo), float(hi)
        v = self._fit(self._value)
        if v != self._value:
            self._value = v
            self._show()
            self._emit()
        else:
            self._show()

    def decimals(self) -> int:
        return self._decimals

    def setDecimals(self, n: int) -> None:  # noqa: N802
        if not self._INT:
            self._decimals = int(n)
            self._value = self._fit(self._value)
            self._show()

    def singleStep(self):  # noqa: N802
        return self._step

    def setSingleStep(self, step) -> None:  # noqa: N802
        self._step = float(step)

    def stepBy(self, n: int) -> None:  # noqa: N802
        self.setValue(self._value + n * self._step)

    def stepUp(self) -> None:  # noqa: N802
        self.stepBy(1)

    def stepDown(self) -> None:  # noqa: N802
        self.stepBy(-1)

    def prefix(self) -> str:
        return self._prefix

    def setPrefix(self, text: str) -> None:  # noqa: N802
        self._prefix = text or ""
        self._show()

    def suffix(self) -> str:
        return self._suffix

    def setSuffix(self, text: str) -> None:  # noqa: N802
        self._suffix = text or ""
        self._show()

    def specialValueText(self) -> str:  # noqa: N802
        return self._special

    def setSpecialValueText(self, text: str) -> None:  # noqa: N802
        self._special = text or ""
        self._show()

    def setGroupSeparatorShown(self, on: bool) -> None:  # noqa: N802
        self._groups = bool(on)
        self._show()

    def isGroupSeparatorShown(self) -> bool:  # noqa: N802
        return self._groups

    def cleanText(self) -> str:  # noqa: N802
        return self._number_text()

    def textFromValue(self, v) -> str:  # noqa: N802
        return self._format(float(v))

    def interpretText(self) -> None:  # noqa: N802
        self._typed(self.text())

    def lineEdit(self) -> "QLineEdit":  # noqa: N802
        return self

    # nothing to do for a text box
    def setButtonSymbols(self, *_a) -> None:  # noqa: N802
        pass

    def setKeyboardTracking(self, *_a) -> None:  # noqa: N802
        pass

    def setAccelerated(self, *_a) -> None:  # noqa: N802
        pass

    def setCorrectionMode(self, *_a) -> None:  # noqa: N802
        pass

    def setWrapping(self, *_a) -> None:  # noqa: N802
        pass

    def setStepType(self, *_a) -> None:  # noqa: N802
        pass

    # -- display / typing --------------------------------------------------
    def _format(self, v: float) -> str:
        if self._INT:
            body = f"{int(round(v)):,}" if self._groups else f"{int(round(v))}"
        else:
            body = f"{v:,.{self._decimals}f}" if self._groups else f"{v:.{self._decimals}f}"
        return body

    def _number_text(self) -> str:
        return self._format(self._value)

    def _show(self) -> None:
        if self._special and self._value == self._min:
            text = self._special
        else:
            text = f"{self._prefix}{self._number_text()}{self._suffix}"
        if self.text() != text:
            self.setText(text)

    def _typed(self, text: str) -> None:
        t = text
        if self._prefix and t.startswith(self._prefix):
            t = t[len(self._prefix):]
        if self._suffix and t.endswith(self._suffix):
            t = t[:-len(self._suffix)]
        t = t.replace(",", "").strip()
        if t in ("", "-", ".", "-."):
            v = 0.0
        else:
            try:
                v = float(t)
            except ValueError:
                return
        v = self._fit(v)
        if v != self._value:
            self._value = v
            self._emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt name
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and not self.isReadOnly():
            self.stepBy(1 if key == Qt.Key.Key_Up else -1)
            self.selectAll()
            return
        ch = event.text()
        if ch and ch.isprintable() and not (event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)) \
                and ch not in _ALLOWED:
            return                      # digits only
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().focusInEvent(event)
        if not self.isReadOnly():
            self._entering = event.reason() == Qt.FocusReason.MouseFocusReason
            QTimer.singleShot(0, self.selectAll)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().mouseReleaseEvent(event)
        if self._entering:              # a click into it: the whole value, to type over
            self._entering = False
            QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().focusOutEvent(event)
        self._show()


class SpinBox(_NumBox):
    valueChanged = Signal(int)
    _INT = True


class DoubleSpinBox(_NumBox):
    valueChanged = Signal(float)
    _INT = False

