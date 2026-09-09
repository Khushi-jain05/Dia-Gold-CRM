"""Master > User Right - users, the rights matrix, and per-user options.

Rights are granted per USER, per MASTER, per ACTION (Display / Add New / Edit /
Delete / Print), mirroring the client's legacy screen. Nothing is granted by
default, so a new user sees nothing until an administrator ticks boxes here.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from diagold.db.models import User, UserPermission
from diagold.db.session import SessionLocal
from diagold.services import rights as rights_service
from diagold.services.auth import CurrentUser
from diagold.ui.crud import CrudWidget
from diagold.ui.specs import SPECS


def _cs(value: bool) -> Qt.CheckState:
    return Qt.CheckState.Checked if value else Qt.CheckState.Unchecked


class PermissionMatrixWidget(QWidget):
    def __init__(self, user: CurrentUser, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("User Right")

        can_edit = user.can_edit("master.user_right")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        heading = QLabel("User Right")
        heading.setObjectName("H1")
        layout.addWidget(heading)

        tabs = QTabWidget()
        layout.addWidget(tabs)
        tabs.addTab(
            CrudWidget(SPECS["master.user_right"], can_edit=can_edit,
                       rights=user.rights),
            "Users",
        )
        tabs.addTab(self._build_rights_tab(can_edit), "Rights Matrix")
        tabs.addTab(self._build_options_tab(can_edit), "Options")

    # -- shared ----------------------------------------------------------
    def _user_combo(self) -> QComboBox:
        combo = QComboBox()
        with SessionLocal() as s:
            for u in s.scalars(select(User).order_by(User.username)):
                label = f"{u.username} — {u.full_name}" if u.full_name else u.username
                if not u.is_active:
                    label += "  (inactive)"
                combo.addItem(label, u.id)
        return combo

    # -- Rights matrix ---------------------------------------------------
    def _build_rights_tab(self, can_edit: bool) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        top = QHBoxLayout()
        top.addWidget(QLabel("User:"))
        self.rights_user = self._user_combo()
        self.rights_user.currentIndexChanged.connect(self._load_matrix)
        top.addWidget(self.rights_user, 1)

        self.btn_copy = QPushButton("Copy rights from…")
        self.btn_export = QPushButton("Export…")
        self.btn_save_rights = QPushButton("Save Rights")
        self.btn_save_rights.setObjectName("Primary")
        self.btn_copy.clicked.connect(self._copy_rights)
        self.btn_export.clicked.connect(self._export)
        self.btn_save_rights.clicked.connect(self._save_matrix)
        for b in (self.btn_copy, self.btn_export, self.btn_save_rights):
            top.addWidget(b)
        v.addLayout(top)

        actions = [label for _, label in rights_service.ACTIONS]
        self.matrix = QTableWidget(len(rights_service.MASTER_NAMES), len(actions) + 1)
        self.matrix.setHorizontalHeaderLabels(["Master"] + actions)
        self.matrix.verticalHeader().setVisible(False)
        self.matrix.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.matrix.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for c in range(1, len(actions) + 1):
            self.matrix.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.ResizeToContents
            )
        v.addWidget(self.matrix)

        note = QLabel(
            "Nothing is granted by default — a new user has no access until "
            "boxes are ticked here. Superusers bypass the matrix entirely. "
            "Masters with no screen yet can still be configured in advance."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        v.addWidget(note)

        if not can_edit:
            for b in (self.btn_copy, self.btn_save_rights):
                b.setEnabled(False)
                b.setToolTip("You have view-only access to User Rights.")

        self._load_matrix()
        return w

    def _load_matrix(self) -> None:
        user_id = self.rights_user.currentData()
        granted: dict[str, UserPermission] = {}
        if user_id is not None:
            with SessionLocal() as s:
                for p in s.scalars(
                    select(UserPermission).where(UserPermission.user_id == user_id)
                ):
                    granted[p.master_key] = p

        for row, (name, menu_key) in enumerate(rights_service.MASTERS):
            label = QTableWidgetItem(name if menu_key else f"{name}   (screen pending)")
            label.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.matrix.setItem(row, 0, label)
            perm = granted.get(name)
            for col, (attr, _) in enumerate(rights_service.ACTIONS, start=1):
                item = QTableWidgetItem()
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(_cs(bool(perm and getattr(perm, attr))))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.matrix.setItem(row, col, item)
        self.matrix.resizeRowsToContents()

    def _save_matrix(self) -> None:
        user_id = self.rights_user.currentData()
        if user_id is None:
            return
        with SessionLocal() as s:
            for stale in s.scalars(
                select(UserPermission).where(UserPermission.user_id == user_id)
            ):
                s.delete(stale)
            s.flush()
            written = 0
            for row, name in enumerate(rights_service.MASTER_NAMES):
                flags = {
                    attr: self.matrix.item(row, col).checkState() == Qt.CheckState.Checked
                    for col, (attr, _) in enumerate(rights_service.ACTIONS, start=1)
                }
                if not any(flags.values()):
                    continue  # no row means no access
                s.add(UserPermission(user_id=user_id, master_key=name, **flags))
                written += 1
            s.commit()
        QMessageBox.information(
            self, "Saved",
            f"Rights saved for {written} master(s). "
            "The user must log in again for the change to take effect.",
        )

    def _copy_rights(self) -> None:
        target_id = self.rights_user.currentData()
        if target_id is None:
            return
        with SessionLocal() as s:
            others = [
                (u.id, u.username)
                for u in s.scalars(select(User).order_by(User.username))
                if u.id != target_id
            ]
        if not others:
            QMessageBox.information(self, "Copy rights", "There is no other user to copy from.")
            return
        names = [n for _, n in others]
        choice, ok = QInputDialog.getItem(
            self, "Copy rights from", "Copy the full matrix from:", names, 0, False
        )
        if not ok:
            return
        source_id = others[names.index(choice)][0]
        with SessionLocal() as s:
            copied = rights_service.copy_rights(s, source_id, target_id)
            s.commit()
        self._load_matrix()
        QMessageBox.information(
            self, "Copied", f"Copied {copied} master grant(s) from {choice}."
        )

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export rights matrix", "user-rights.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        with SessionLocal() as s:
            csv_text = rights_service.export_matrix(s)
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(csv_text)
        except OSError as exc:
            QMessageBox.critical(self, "Could not export", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Rights matrix written to:\n{path}")

    # -- Per-user options ------------------------------------------------
    def _build_options_tab(self, can_edit: bool) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        top = QHBoxLayout()
        top.addWidget(QLabel("User:"))
        self.opts_user = self._user_combo()
        self.opts_user.currentIndexChanged.connect(self._load_options)
        top.addWidget(self.opts_user, 1)
        self.btn_save_opts = QPushButton("Save Options")
        self.btn_save_opts.setObjectName("Primary")
        self.btn_save_opts.clicked.connect(self._save_options)
        top.addWidget(self.btn_save_opts)
        v.addLayout(top)

        flags_box = QGroupBox("Per-user switches")
        flags_form = QVBoxLayout(flags_box)
        self.flag_boxes: dict[str, QCheckBox] = {}
        for attr, label in User.PER_USER_FLAGS:
            cb = QCheckBox(label)
            self.flag_boxes[attr] = cb
            flags_form.addWidget(cb)
        v.addWidget(flags_box)

        voucher_box = QGroupBox("Back-dated vouchers")
        vform = QFormLayout(voucher_box)
        self.days_allowed = QSpinBox()
        self.days_allowed.setRange(0, 3650)
        self.apply_cutoff = QCheckBox()
        vform.addRow("Days Allowed for back Dated Voucher", self.days_allowed)
        vform.addRow("Apply Cut-off Date for back Dated Voucher", self.apply_cutoff)
        v.addWidget(voucher_box)
        v.addStretch(1)

        if not can_edit:
            self.btn_save_opts.setEnabled(False)
            for cb in self.flag_boxes.values():
                cb.setEnabled(False)
            self.days_allowed.setEnabled(False)
            self.apply_cutoff.setEnabled(False)

        self._load_options()
        return w

    def _load_options(self) -> None:
        user_id = self.opts_user.currentData()
        if user_id is None:
            return
        with SessionLocal() as s:
            u = s.get(User, user_id)
            if u is None:
                return
            for attr, cb in self.flag_boxes.items():
                cb.setChecked(bool(getattr(u, attr, False)))
            self.days_allowed.setValue(int(u.days_allowed_back_dated_voucher or 0))
            self.apply_cutoff.setChecked(bool(u.apply_cutoff_date_back_dated_voucher))

    def _save_options(self) -> None:
        user_id = self.opts_user.currentData()
        if user_id is None:
            return
        with SessionLocal() as s:
            u = s.get(User, user_id)
            if u is None:
                return
            for attr, cb in self.flag_boxes.items():
                setattr(u, attr, cb.isChecked())
            u.days_allowed_back_dated_voucher = self.days_allowed.value()
            u.apply_cutoff_date_back_dated_voucher = self.apply_cutoff.isChecked()
            s.commit()
        QMessageBox.information(self, "Saved", "Options saved for this user.")
