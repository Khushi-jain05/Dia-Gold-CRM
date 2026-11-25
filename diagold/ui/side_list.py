"""The legacy "List of ..." panel beside the box being typed in (17 Nov T-04).

The client's screens show, at the right, the list for the box being typed in -
List of Location, List of Metal - narrowing as letters are typed: "S" brings
the names starting with S first. Boxes stay typed-by-hand (16 Nov: no
drop-downs); the list only shows what can be typed, a click on a name puts it
in the box and Enter takes the first one.

``SideList`` sits inside a voucher form (CrudSpec.side_list); every other
pick box in the app gets ``FloatingList``, a panel beside its window (18 Nov:
"jab koi bhi new input add krna h toh uska side m ek list aaye").
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFrame,
                               QHBoxLayout, QLabel, QLayout, QToolButton,
                               QListWidget, QListWidgetItem, QTableWidget, QVBoxLayout,
                               QWidget)

_WIRED = "_side_list_wired"
_BLANKS = ("", "— none —")
_SEPARATORS = (" · ", " - ", " — ")


def _title_row(owner: QWidget, title: QLabel) -> QHBoxLayout:
    """The list's heading with a ✕ that closes it (23 Nov); typing in the
    box again brings it back."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(title, 1)
    close = QToolButton()
    close.setText("✕")
    close.setToolTip("Close the list - it opens again when you type in the box")
    close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    close.setAutoRaise(True)
    close.setCursor(Qt.CursorShape.PointingHandCursor)
    close.setStyleSheet("QToolButton { border: none; font-weight: 700; font-size: 15px; "
                        "padding: 0 6px; color: #8A6D00; }")
    close.clicked.connect(owner.hide)
    owner.close_btn = close
    row.addWidget(close)
    return row


def ranked(combo: QComboBox, typed: str) -> list[int]:
    """The entries to list for what is typed: those starting with it (the
    whole name or one part - "SHRIKANT - SHRIKANT") first, then those
    containing it; all of them when nothing is typed."""
    want = typed.replace("— none —", "").strip().casefold()
    first, then = [], []
    for i in range(combo.count()):
        text = combo.itemText(i)
        if text.strip() in _BLANKS:
            continue
        low = text.casefold()
        if not want:
            first.append(i)
            continue
        parts = [low] + [p.strip() for sep in _SEPARATORS for p in low.split(sep)]
        if any(p.startswith(want) for p in parts):
            first.append(i)
        elif want in low:
            then.append(i)
    return first + then


def field_label(combo: QComboBox, labels: dict | None = None) -> str:
    """What the box is: its form label, or its grid column's heading."""
    if labels and combo in labels:
        return labels[combo]
    from PySide6.QtWidgets import QFormLayout
    p = combo.parentWidget()
    lay = p.layout() if p is not None else None
    if isinstance(lay, QFormLayout):
        lab = lay.labelForField(combo)
        if lab is not None and hasattr(lab, "text"):
            return lab.text().replace("*", "").replace("&", "").strip()
    # A row of label + box (a voucher header): the label just before it.
    for found in (p.findChildren(QLayout) if p is not None else []):
        i = found.indexOf(combo)
        while i > 0:
            i -= 1
            w = found.itemAt(i).widget()
            if isinstance(w, QLabel) and w.text().strip():
                return w.text().replace("*", "").replace("&", "").strip()
            if w is not None:
                break
    t = combo.parent()
    while t is not None and not isinstance(t, QTableWidget):
        t = t.parent()
    if t is None:
        return ""
    idx = t.indexAt(combo.mapTo(t.viewport(), QPoint(2, 2)))
    head = t.horizontalHeaderItem(idx.column()) if idx.isValid() else None
    return head.text().replace("\n", " ") if head else ""


class SideList(QWidget):
    def __init__(self, dialog: QWidget, labels: dict[QWidget, str], parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.labels = labels            # header box -> its field label
        self.combo: QComboBox | None = None
        self.setFixedWidth(230)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 12, 8)
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: 600;")
        lay.addLayout(_title_row(self, self.title))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # A click on the list never takes the cursor out of the box: leaving
        # the box checks what is typed, so "pri" + a click on PRIMARY warned
        # "not in the list" before the click could put the name in (19 Nov).
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(self._pick)
        self.list.itemActivated.connect(self._pick)
        lay.addWidget(self.list, 1)
        QApplication.instance().focusChanged.connect(self._focus)
        self.setVisible(False)

    def _combo_of(self, w: QWidget | None) -> QComboBox | None:
        if w is None:
            return None
        combo = w if isinstance(w, QComboBox) else (
            w.parent() if isinstance(w.parent(), QComboBox) else None)
        if combo is None or not self.dialog.isAncestorOf(combo):
            return None
        return combo

    def _label(self, combo: QComboBox) -> str:
        return field_label(combo, self.labels)

    def _focus(self, _old, new) -> None:
        try:
            combo = self._combo_of(new)
        except RuntimeError:          # the dialog is gone
            return
        if combo is None or combo is self.combo:
            return
        self.combo = combo
        label = self._label(combo)
        self.title.setText(f"List of {label}" if label else "List")
        if not combo.property(_WIRED) and combo.lineEdit() is not None:
            combo.setProperty(_WIRED, True)
            combo.lineEdit().textEdited.connect(
                lambda text, c=combo: self._typed(text) if c is self.combo else None)
        self._fill("")
        self.setVisible(True)

    def _typed(self, text: str) -> None:
        self._fill(text)
        if not self.isVisible():
            self.setVisible(True)           # closed with ✕, typing brings it back

    def _fill(self, typed: str) -> None:
        combo = self.combo
        if combo is None:
            return
        self.list.clear()
        for i in ranked(combo, typed):
            it = QListWidgetItem(combo.itemText(i))
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(it)

    def _pick(self, item: QListWidgetItem) -> None:
        combo = self.combo
        if combo is None:
            return
        combo.setCurrentIndex(int(item.data(Qt.ItemDataRole.UserRole)))
        if combo.lineEdit() is not None:
            combo.lineEdit().setText(combo.itemText(combo.currentIndex()))
        combo.setFocus()

    def take_first(self) -> bool:
        """Enter in a box whose text names no entry exactly: the first name
        the list shows goes in (legacy). False when there is nothing to take."""
        combo = self.combo
        w = QApplication.focusWidget()
        if combo is None or self._combo_of(w) is not combo or self.list.count() == 0 \
                or not self.isVisible():
            return False
        typed = combo.currentText().strip().casefold()
        if any(combo.itemText(i).strip().casefold() == typed for i in range(combo.count())):
            return False
        self._pick(self.list.item(0))
        return True


class FloatingList(QFrame):
    """The list beside a pick box, inside the box's own window: to the right
    of the box, or to its left when there is no room. It never takes the
    focus, so typing carries on in the box; one per window, gone with it."""

    WIDTH = 250

    def __init__(self, win: QWidget) -> None:
        super().__init__(win)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("FloatingList")
        self.setStyleSheet("#FloatingList { background: #FFFFFF; border: 1px solid #C9A227;"
                           " border-radius: 6px; }")
        self.combo: QComboBox | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 6)
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: 600; border: none;")
        lay.addLayout(_title_row(self, self.title))
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(self._pick)
        lay.addWidget(self.list, 1)
        self.hide()

    def show_for(self, combo: QComboBox) -> None:
        if combo is not self.combo:
            self.combo = combo
            label = field_label(combo)
            self.title.setText(f"List of {label}" if label else "List")
            if not combo.property(_WIRED) and combo.lineEdit() is not None:
                combo.setProperty(_WIRED, True)
                combo.lineEdit().textEdited.connect(
                    lambda text, c=combo: self._typed(text) if c is self.combo else None)
        self._fill("")
        self._place(combo)
        self.show()
        self.raise_()

    def _typed(self, text: str) -> None:
        self._fill(text)
        if not self.isVisible() and self.combo is not None:
            try:
                self._place(self.combo)     # closed with ✕, typing brings it back
            except RuntimeError:
                return
            self.show()
            self.raise_()

    def _place(self, combo: QComboBox) -> None:
        win = self.parentWidget()
        h = max(min(380, win.height() - 8), 120)
        at = combo.mapTo(win, QPoint(0, 0))
        x = at.x() + combo.width() + 4
        if x + self.WIDTH > win.width():
            x = at.x() - self.WIDTH - 4               # no room on the right: the left
        if x < 0:
            x = max(win.width() - self.WIDTH - 4, 0)
        y = min(max(at.y(), 4), max(win.height() - h - 4, 0))
        self.setGeometry(x, y, self.WIDTH, h)

    def _fill(self, typed: str) -> None:
        combo = self.combo
        if combo is None:
            return
        self.list.clear()
        try:
            for i in ranked(combo, typed):
                it = QListWidgetItem(combo.itemText(i))
                it.setData(Qt.ItemDataRole.UserRole, i)
                self.list.addItem(it)
        except RuntimeError:                 # the box is gone
            self.combo = None
            self.hide()

    def _pick(self, item: QListWidgetItem) -> None:
        combo = self.combo
        if combo is None:
            return
        combo.setCurrentIndex(int(item.data(Qt.ItemDataRole.UserRole)))
        if combo.lineEdit() is not None:
            combo.lineEdit().setText(combo.itemText(combo.currentIndex()))
        combo.setFocus()

    def take_first(self, combo: QComboBox) -> bool:
        """Enter: the first name listed goes in when the text names none."""
        if combo is not self.combo or not self.isVisible() or self.list.count() == 0:
            return False
        typed = combo.currentText().strip().casefold()
        if any(combo.itemText(i).strip().casefold() == typed for i in range(combo.count())):
            return False
        self._pick(self.list.item(0))
        return True


_LIST = "_floating_list"


def _pick_box(w: QWidget | None) -> QComboBox | None:
    if w is None:
        return None
    combo = w if isinstance(w, QComboBox) else (
        w.parent() if isinstance(w.parent(), QComboBox) else None)
    from diagold.ui.manual_input import MANUAL
    if combo is None or not combo.property(MANUAL) or not combo.isEnabled():
        return None
    if w is not combo and w is not combo.lineEdit():
        # Only the box and its text field - never the box's own drop-down
        # pop-up: on the Mac it opens over the box and the list was built
        # inside it, a strip reading "List" that took the typing (25 Nov).
        return None
    if owner_side_list(combo) is not None:
        return None                         # the screen has its own panel
    return combo


def owner_side_list(w: QWidget) -> "SideList | None":
    """The 'List of ...' panel of the form or screen a box sits on, if any -
    a dialog's own, or a screen's inside a tab (Quotation, 19 Nov)."""
    p = w
    while p is not None:
        side = getattr(p, "side_list", None)
        if isinstance(side, SideList):
            return side
        p = p.parentWidget()
    return None


def floating_for(win: QWidget, make: bool = True) -> FloatingList | None:
    fl = win.findChild(FloatingList, _LIST)
    if fl is None and make:
        fl = FloatingList(win)
        fl.setObjectName(_LIST)
        fl.setStyleSheet(fl.styleSheet().replace("#FloatingList", f"#{_LIST}"))
    return fl


def _focus_changed(old: QWidget | None, new: QWidget | None) -> None:
    try:
        combo = _pick_box(new)
        if old is not None:
            prev = floating_for(old.window(), make=False)
            if prev is not None and (combo is None or prev.parentWidget() is not combo.window()):
                prev.hide()
        if combo is not None and combo.count() > 1:
            floating_for(combo.window()).show_for(combo)
        elif new is not None:
            here = floating_for(new.window(), make=False)
            if here is not None:
                here.hide()
    except RuntimeError:                    # a window closing under us
        pass


def install(app: QApplication) -> None:
    """Every pick box in the app gets the list beside it (18 Nov)."""
    app.focusChanged.connect(_focus_changed)


def take_first(combo: QComboBox) -> bool:
    fl = floating_for(combo.window(), make=False)
    return fl is not None and fl.take_first(combo)
