"""Attach Doc dialog: the documents kept with one voucher - add, open,
remove. Before a new voucher is saved the files are only listed; they are
attached under its number when it saves (see :func:`attach_pending`)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from diagold.db.session import SessionLocal
from diagold.services import attachments


class AttachDocDialog(QDialog):
    """``ref_no`` None = a voucher not saved yet: ``pending`` (a list of file
    paths) is edited in place and attached on save."""

    def __init__(self, ref_kind: str, ref_no: int | None, title: str, *, user=None,
                 pending: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.ref_kind, self.ref_no, self.user = ref_kind, ref_no, user
        self.pending = pending if pending is not None else []
        self.setWindowTitle(f"Attach Doc — {title}")
        self.setMinimumSize(560, 340)
        lay = QVBoxLayout(self)
        note = QLabel("Documents kept with this voucher (a karigar's slip, a bill, a photo). "
                      + ("They are attached when the voucher is saved." if ref_no is None
                         else "Each file is copied into the data folder."))
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _it: self._open())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        for label, slot in (("Add…", self._add), ("Open", self._open),
                            ("Remove", self._remove), ("Close", self.accept)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        self._load()

    def _load(self) -> None:
        self.list.clear()
        if self.ref_no is None:
            for path in self.pending:
                it = QListWidgetItem(f"{Path(path).name}   (attached on save)")
                it.setData(256, path)
                self.list.addItem(it)
            return
        with SessionLocal() as s:
            for a in attachments.list_for(s, self.ref_kind, self.ref_no):
                it = QListWidgetItem(f"{a.file_name}   {a.added_at:%d-%m-%Y %H:%M}")
                it.setData(256, a.id)
                it.setData(257, a.stored_path)
                self.list.addItem(it)

    def _add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach documents")
        if not paths:
            return
        if self.ref_no is None:
            self.pending.extend(p for p in paths if p not in self.pending)
        else:
            with SessionLocal() as s:
                for p in paths:
                    attachments.add(s, self.ref_kind, self.ref_no, p,
                                    user_id=getattr(self.user, "id", None))
                s.commit()
        self._load()

    def _open(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        path = it.data(256) if self.ref_no is None else it.data(257)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _remove(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        if self.ref_no is None:
            self.pending.remove(it.data(256))
        else:
            if QMessageBox.question(self, "Remove", f"Remove {it.text().split('   ')[0]}?") \
                    != QMessageBox.StandardButton.Yes:
                return
            from diagold.db.models import VoucherAttachment
            with SessionLocal() as s:
                a = s.get(VoucherAttachment, it.data(256))
                if a is not None:
                    attachments.remove(s, a)
                s.commit()
        self._load()


def attach_pending(ref_kind: str, ref_no: int, paths: list[str], user=None) -> None:
    """Attach the files picked before a new voucher was saved."""
    if not paths:
        return
    with SessionLocal() as s:
        for p in paths:
            attachments.add(s, ref_kind, ref_no, p, user_id=getattr(user, "id", None))
        s.commit()
