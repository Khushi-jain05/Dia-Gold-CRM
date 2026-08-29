"""Master > User Right - manage users, roles, and the permission matrix."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from diagold.db.models import Role, RolePermission
from diagold.db.session import SessionLocal
from diagold.menu import MENU
from diagold.services.auth import CurrentUser
from diagold.ui.crud import CrudWidget
from diagold.ui.specs import SPECS


class PermissionMatrixWidget(QWidget):
    def __init__(self, user: CurrentUser, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("User Right")

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        can_edit = user.can_edit("master.user_right")
        tabs.addTab(CrudWidget(SPECS["master.user_right"], can_edit=can_edit), "Users")
        tabs.addTab(self._build_rights_tab(can_edit), "Roles && Rights")

    # -- Roles & Rights --------------------------------------------------
    def _build_rights_tab(self, can_edit: bool) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        top = QHBoxLayout()
        top.addWidget(QLabel("Role:"))
        self.role_combo = QComboBox()
        self.role_combo.currentIndexChanged.connect(self._load_tree)
        top.addWidget(self.role_combo, 1)

        self.btn_add_role = QPushButton("Add Role")
        self.btn_save = QPushButton("Save Rights")
        self.btn_add_role.clicked.connect(self._add_role)
        self.btn_save.clicked.connect(self._save)
        top.addWidget(self.btn_add_role)
        top.addWidget(self.btn_save)
        v.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Menu", "View", "Edit"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(self._on_item_changed)
        v.addWidget(self.tree)

        note = QLabel(
            "Ticking a top-level module grants every screen under it. "
            "Superusers always have full access regardless of these settings."
        )
        note.setStyleSheet("color: gray;")
        note.setWordWrap(True)
        v.addWidget(note)

        if not can_edit:
            for b in (self.btn_add_role, self.btn_save):
                b.setEnabled(False)
            self.tree.setEnabled(False)

        self._reload_roles()
        return w

    def _reload_roles(self) -> None:
        self.role_combo.blockSignals(True)
        self.role_combo.clear()
        with SessionLocal() as s:
            for role in s.scalars(select(Role).order_by(Role.name)):
                self.role_combo.addItem(role.name, role.id)
        self.role_combo.blockSignals(False)
        self._load_tree()

    def _current_role_id(self) -> int | None:
        return self.role_combo.currentData()

    def _load_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        role_id = self._current_role_id()
        granted: dict[str, tuple[bool, bool]] = {}
        if role_id is not None:
            with SessionLocal() as s:
                for p in s.scalars(
                    select(RolePermission).where(RolePermission.role_id == role_id)
                ):
                    granted[p.menu_key] = (p.can_view, p.can_edit)

        for group in MENU:
            gv, ge = granted.get(group.key, (False, False))
            parent = QTreeWidgetItem(self.tree, [group.label])
            parent.setData(0, Qt.ItemDataRole.UserRole, group.key)
            parent.setCheckState(1, _cs(gv))
            parent.setCheckState(2, _cs(ge))
            for item in group.items:
                iv, ie = granted.get(item.key, (False, False))
                child = QTreeWidgetItem(parent, [item.label])
                child.setData(0, Qt.ItemDataRole.UserRole, item.key)
                child.setCheckState(1, _cs(iv))
                child.setCheckState(2, _cs(ie))
            parent.setExpanded(True)
        self.tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column not in (1, 2):
            return
        # Editing implies viewing.
        if column == 2 and item.checkState(2) == Qt.CheckState.Checked:
            self.tree.blockSignals(True)
            item.setCheckState(1, Qt.CheckState.Checked)
            self.tree.blockSignals(False)

    def _iter_items(self):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            yield top
            for j in range(top.childCount()):
                yield top.child(j)

    def _save(self) -> None:
        role_id = self._current_role_id()
        if role_id is None:
            return
        with SessionLocal() as s:
            role = s.get(Role, role_id)
            if role and role.name == "Administrator":
                QMessageBox.information(
                    self, "Administrator",
                    "The Administrator role keeps full access and cannot be limited.",
                )
                return
            s.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
            for it in self._iter_items():
                key = it.data(0, Qt.ItemDataRole.UserRole)
                view = it.checkState(1) == Qt.CheckState.Checked
                edit = it.checkState(2) == Qt.CheckState.Checked
                if view or edit:
                    s.add(RolePermission(
                        role_id=role_id, menu_key=key,
                        can_view=view or edit, can_edit=edit,
                    ))
            s.commit()
        QMessageBox.information(self, "Saved", "Permissions updated. Users must re-login to apply.")

    def _add_role(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Role", "Role name:")
        if not ok or not name.strip():
            return
        with SessionLocal() as s:
            if s.scalar(select(Role).where(Role.name == name.strip())):
                QMessageBox.warning(self, "Add Role", "That role already exists.")
                return
            s.add(Role(name=name.strip()))
            s.commit()
        self._reload_roles()
        idx = self.role_combo.findText(name.strip())
        if idx >= 0:
            self.role_combo.setCurrentIndex(idx)


def _cs(value: bool) -> Qt.CheckState:
    return Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
