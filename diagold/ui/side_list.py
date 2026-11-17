"""The legacy "List of ..." panel beside a voucher (17 Nov T-04).

The client's Metal Purchase shows, at the right, the list for the box being
typed in - List of Location, List of Metal - narrowing as letters are typed.
Boxes stay typed-by-hand (16 Nov: no drop-downs); the list only shows what
can be typed, and a click on a name puts it in the box.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QLabel,
                               QListWidget, QListWidgetItem, QTableWidget, QVBoxLayout,
                               QWidget)

_WIRED = "_side_list_wired"
_BLANKS = ("", "— none —")


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
        lay.addWidget(self.title)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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
        if combo in self.labels:
            return self.labels[combo]
        p = combo.parent()
        while p is not None and not isinstance(p, QTableWidget):
            p = p.parent()
        if p is None:
            return ""
        idx = p.indexAt(combo.mapTo(p.viewport(), QPoint(2, 2)))
        head = p.horizontalHeaderItem(idx.column()) if idx.isValid() else None
        return head.text() if head else ""

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
                lambda text, c=combo: self._fill(text) if c is self.combo else None)
        self._fill("")
        self.setVisible(True)

    def _fill(self, typed: str) -> None:
        combo = self.combo
        if combo is None:
            return
        want = typed.replace("— none —", "").strip().casefold()
        self.list.clear()
        for i in range(combo.count()):
            text = combo.itemText(i)
            if text.strip() in _BLANKS or (want and want not in text.casefold()):
                continue
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(it)

    def _pick(self, item: QListWidgetItem) -> None:
        combo = self.combo
        if combo is None:
            return
        combo.setCurrentIndex(int(item.data(Qt.ItemDataRole.UserRole)))
        combo.setFocus()

    def take_first(self) -> bool:
        """Enter in a box whose text names no entry exactly: the first name
        the list shows goes in (legacy). False when there is nothing to take."""
        combo = self.combo
        w = QApplication.focusWidget()
        if combo is None or self._combo_of(w) is not combo or self.list.count() == 0:
            return False
        typed = combo.currentText().strip().casefold()
        if any(combo.itemText(i).strip().casefold() == typed for i in range(combo.count())):
            return False
        self._pick(self.list.item(0))
        return True
