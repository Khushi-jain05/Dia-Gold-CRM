"""Every input typed by hand (16 Nov, client): no drop-down lists anywhere.

Each QComboBox in the app becomes a plain text box - no arrow, no list, no
suggestions while typing, and the wheel / arrow keys do not change it. When
the box is left, what was typed must name an entry exactly (any case): the
whole entry, or one part of it - "25007" for "25007 · NS-2740 · A B JEWELS",
"SONU JI" or "SONUJI" for "SONUJI - SONU JI". Anything else turns the box
red and says so, and :func:`check` (run by every Save) refuses to save.
Dates are typed too: no calendar pop-up.

Installed once on the QApplication (main.py); screens need no change.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QDateEdit,
                               QDialog, QMessageBox, QWidget)

MANUAL = "_manual_input"
BAD = "manualBad"           # dynamic property the style sheet colours red
_SEPARATORS = (" · ", " - ", " — ")

QSS = """
QComboBox[_manual_input="true"]::drop-down { width: 0px; border: 0px; }
QComboBox[_manual_input="true"]::down-arrow { image: none; width: 0px; height: 0px; }
QComboBox[manualBad="true"] { border: 1px solid #C0392B; background: #FDECEA; }
"""

_BLOCK_KEYS = {Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
               Qt.Key.Key_F4}


def _parts(text: str) -> list[str]:
    parts = [text]
    for sep in _SEPARATORS:
        if sep in text:
            parts += [p for p in text.split(sep) if p.strip()]
    return [p.strip().lower() for p in parts]


def match(w: QComboBox, typed: str) -> list[int]:
    """Indexes of the entries ``typed`` names exactly (whole text first)."""
    t = typed.strip().lower()
    whole = [i for i in range(w.count()) if w.itemText(i).strip().lower() == t]
    if whole:
        return whole[:1]
    return [i for i in range(w.count()) if t in _parts(w.itemText(i))[1:]]


def _is_blank(text: str) -> bool:
    t = text.strip()
    return not t or t.startswith("—") or t.lower() in ("(all)", "none")


def _blank_index(w: QComboBox) -> int:
    for i in range(w.count()):
        if _is_blank(w.itemText(i)):
            return i
    return -1


def _clear_if_blank(w: QComboBox) -> None:
    """'— none —' shows as an empty box, ready to type into."""
    if w.currentIndex() >= 0 and _is_blank(w.itemText(w.currentIndex())) \
            and w.currentText():
        w.lineEdit().blockSignals(True)
        w.setEditText("")
        w.lineEdit().blockSignals(False)


def _mark(w: QComboBox, bad: bool) -> None:
    if bool(w.property(BAD)) != bad:
        w.setProperty(BAD, bad)
        w.style().unpolish(w)
        w.style().polish(w)


def settle(w: QComboBox, warn: bool = True) -> bool:
    """Make the typed text the entry it names; False (and red) if it names none."""
    if not w.isEditable():
        return True
    typed = w.currentText().strip()
    if not typed or _is_blank(typed):
        i = _blank_index(w)
        if i >= 0 and w.currentIndex() != i:
            w.setCurrentIndex(i)
        _clear_if_blank(w)
        _mark(w, False)
        return True
    hits = match(w, typed)
    if len(hits) == 1:
        if w.currentIndex() != hits[0]:
            w.setCurrentIndex(hits[0])
        w.setEditText(w.itemText(hits[0]))
        _mark(w, False)
        return True
    _mark(w, True)
    if warn and w.isEnabled() and w.isVisible() and not w.property("_warning"):
        w.setProperty("_warning", True)
        why = (f'"{typed}" matches more than one entry - type the full name.' if hits
               else f'"{typed}" is not in the list - type the full name exactly.')
        QMessageBox.warning(w.window(), "Check the entry", why)
        w.setProperty("_warning", False)
        QTimer.singleShot(0, w.setFocus)
    return False


def check(root: QWidget | None) -> bool:
    """Run by every Save: True when each typed entry under ``root`` names one."""
    if root is None:
        return True
    win = root.window()
    for w in win.findChildren(QComboBox):
        if w.property(MANUAL) and w.isVisible() and w.isEnabled() and not settle(w, warn=False):
            QMessageBox.warning(win, "Check the entry",
                                f'"{w.currentText().strip()}" is not in the list - type the '
                                "full name exactly (the box in red).")
            w.setFocus()
            return False
    return True


def make_manual(w: QComboBox) -> None:
    if w.property(MANUAL):
        return
    w.setEditable(True)
    w.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    _orig_set_completer(w, None)
    w.setProperty(MANUAL, True)
    w.lineEdit().editingFinished.connect(lambda: settle(w))
    w.lineEdit().textEdited.connect(lambda _t: _mark(w, False))
    w.currentIndexChanged.connect(lambda _i: _clear_if_blank(w))
    # A long entry in a narrow box shows from its start, not its end (16 Nov:
    # "PRIMARY - Primary" read "MARY - Primary").
    w.currentIndexChanged.connect(lambda _i: w.lineEdit().setCursorPosition(0))
    w.lineEdit().editingFinished.connect(lambda: w.lineEdit().setCursorPosition(0))
    w.lineEdit().setCursorPosition(0)
    _clear_if_blank(w)
    w.style().unpolish(w)
    w.style().polish(w)
    _fit_box(w)
    w.model().rowsInserted.connect(lambda *_a: _fit_box(w))   # entries loaded later


def _in_grid(w: QWidget) -> bool:
    from PySide6.QtWidgets import QAbstractItemView
    p = w.parent()
    return p is not None and isinstance(p.parent(), QAbstractItemView)


def _fit_box(w: QComboBox) -> None:
    """A box on a form is wide enough for its longest entry (up to 18
    letters), so "Default" does not read "efault" (16 Nov). A box in a grid
    cell is sized by its column instead."""
    if _in_grid(w) or w.count() == 0:
        return
    longest = max(len(w.itemText(i)) for i in range(w.count()))
    w.setMinimumContentsLength(min(max(longest, 4), 18))
    w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)


_orig_set_completer = QComboBox.setCompleter


def _set_completer(self: QComboBox, completer) -> None:
    """Screens that add a completer later (the job picker) get none."""
    _orig_set_completer(self, None if self.property(MANUAL) else completer)


_orig_set_current_text = QComboBox.setCurrentText


def _set_current_text(self: QComboBox, text: str) -> None:
    """A list box picked its entry by text; a typed box only showed the text -
    so a screen's setCurrentText still selects the entry it names."""
    _orig_set_current_text(self, text)
    if self.property(MANUAL):
        hits = match(self, text) if str(text).strip() else []
        if len(hits) == 1 and self.currentIndex() != hits[0]:
            self.setCurrentIndex(hits[0])
        _mark(self, False)


_orig_accept = QDialog.accept


def _accept(self: QDialog) -> None:
    """OK / Save on any dialog: every typed entry must name one first."""
    if check(self):
        _orig_accept(self)


class _Filter(QObject):
    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 - Qt name
        et = ev.type()
        if et == QEvent.Type.Polish:
            if isinstance(obj, QComboBox):
                make_manual(obj)
            elif isinstance(obj, QDateEdit) and obj.calendarPopup():
                obj.setCalendarPopup(False)
                obj.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            return False
        combo = obj if isinstance(obj, QComboBox) else (
            obj.parent() if isinstance(obj.parent(), QComboBox) else None)
        if combo is None or not combo.property(MANUAL):
            return False
        if et == QEvent.Type.Wheel:
            ev.ignore()
            return True
        if et == QEvent.Type.KeyPress and (ev.key() in _BLOCK_KEYS or (
                ev.key() == Qt.Key.Key_Down
                and ev.modifiers() & Qt.KeyboardModifier.AltModifier)):
            return True
        if et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick) \
                and obj is combo:
            # The arrow area (zero wide now) would open the list.
            combo.lineEdit().setFocus()
            return True
        return False


_installed: _Filter | None = None


def install(app: QApplication) -> None:
    global _installed
    if _installed is not None:
        return
    QComboBox.setCompleter = _set_completer
    QComboBox.setCurrentText = _set_current_text
    QDialog.accept = _accept
    _installed = _Filter(app)
    app.installEventFilter(_installed)
