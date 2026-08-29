"""Main application window - sidebar navigation + tabbed content area.

The navigation mirrors the client's design workbook (14 modules), but is rendered
inside the window as a sidebar so it looks and behaves identically on macOS and
Windows (Qt would otherwise push a menu bar into the native macOS menu bar).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from diagold import APP_NAME, __version__
from diagold.config import COMPANY_DISPLAY_NAME, DB_PATH
from diagold.db.session import SessionLocal
from diagold.menu import MENU, MENU_BY_KEY
from diagold.services.auth import AuthError, CurrentUser, change_password
from diagold.ui.dashboard import DashboardWidget
from diagold.ui.registry import build_widget, has_real_screen
from diagold.ui.style import APP_QSS

_ROLE_KEY = Qt.ItemDataRole.UserRole
_LABEL_KEY = Qt.ItemDataRole.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self, user: CurrentUser):
        super().__init__()
        self.user = user
        self._relogin = False
        self._tabs_by_key: dict[str, QWidget] = {}

        self.setWindowTitle(f"{APP_NAME} — {COMPANY_DISPLAY_NAME}")
        self.resize(1240, 800)
        self.setStyleSheet(APP_QSS)
        if self.menuBar() is not None:
            self.menuBar().setNativeMenuBar(False)
            self.menuBar().hide()

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(root)

        self._build_statusbar()

        QShortcut(QKeySequence.StandardKey.Find, self,
                  activated=lambda: self.nav_search.setFocus())

        self._open_dashboard()

    # -- sidebar -----------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(248)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 8, 0, 12)
        v.setSpacing(0)

        brand = QLabel("◆  Dia Gold")
        brand.setObjectName("Brand")
        sub = QLabel("JEWELLERY  ERP")
        sub.setObjectName("BrandSub")
        v.addWidget(brand)
        v.addWidget(sub)

        self.nav_search = QLineEdit()
        self.nav_search.setObjectName("NavSearch")
        self.nav_search.setPlaceholderText("Search menu…  (Ctrl/Cmd+F)")
        self.nav_search.textChanged.connect(self._filter_nav)
        v.addWidget(self.nav_search)

        self.nav = QTreeWidget()
        self.nav.setObjectName("Nav")
        self.nav.setHeaderHidden(True)
        self.nav.setIndentation(12)
        self.nav.setAnimated(True)
        self.nav.setExpandsOnDoubleClick(False)
        self.nav.setRootIsDecorated(False)
        self.nav.itemClicked.connect(self._on_nav_clicked)
        self.nav.itemExpanded.connect(lambda it: self._set_group_chevron(it, True))
        self.nav.itemCollapsed.connect(lambda it: self._set_group_chevron(it, False))
        self._populate_nav()
        v.addWidget(self.nav, 1)

        # footer - account actions
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#3A3D4A; background:#3A3D4A; max-height:1px;")
        v.addWidget(sep)
        foot = QVBoxLayout()
        foot.setContentsMargins(12, 8, 12, 0)
        foot.setSpacing(4)
        who = QLabel(f"\U0001F464  {self.user.full_name}")
        who.setStyleSheet("color:#C9CCD6; padding:4px 4px; font-weight:600;")
        foot.addWidget(who)
        btn_pw = QPushButton("Change Password")
        btn_pw.setObjectName("Ghost")
        btn_pw.clicked.connect(self._change_password)
        btn_out = QPushButton("Log Out")
        btn_out.setObjectName("Ghost")
        btn_out.clicked.connect(self._logout)
        foot.addWidget(btn_pw)
        foot.addWidget(btn_out)
        v.addLayout(foot)
        return side

    def _set_group_chevron(self, item: QTreeWidgetItem, expanded: bool) -> None:
        base = item.data(0, _LABEL_KEY)
        if base:
            item.setText(0, f"{'▾' if expanded else '▸'}  {base}")

    def _populate_nav(self) -> None:
        self.nav.clear()
        for group in MENU:
            g_item = QTreeWidgetItem(self.nav, [group.label])
            g_item.setData(0, _ROLE_KEY, group.key)
            g_item.setData(0, _LABEL_KEY, group.label)
            g_item.setFlags(g_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            f = g_item.font(0)
            f.setBold(True)
            g_item.setFont(0, f)
            self._set_group_chevron(g_item, False)
            visible_children = 0
            for item in group.items:
                if not self.user.can_view(item.key):
                    continue
                label = item.label
                if not has_real_screen(item.key):
                    label += "  ·  soon"
                c_item = QTreeWidgetItem(g_item, [label])
                c_item.setData(0, _ROLE_KEY, item.key)
                c_item.setData(0, _LABEL_KEY, item.label)
                visible_children += 1
            if visible_children == 0:
                g_item.setDisabled(True)
        self.nav.expandItem(self.nav.topLevelItem(0))  # Master open by default

    def _filter_nav(self, text: str) -> None:
        term = text.strip().lower()
        for i in range(self.nav.topLevelItemCount()):
            g = self.nav.topLevelItem(i)
            group_match = term in g.text(0).lower()
            child_shown = 0
            for j in range(g.childCount()):
                c = g.child(j)
                match = not term or group_match or term in c.text(0).lower()
                c.setHidden(not match)
                child_shown += int(match)
            g.setHidden(bool(term) and child_shown == 0 and not group_match)
            g.setExpanded(bool(term) and child_shown > 0)
        if not term:
            for i in range(self.nav.topLevelItemCount()):
                self.nav.topLevelItem(i).setExpanded(i == 0)

    # -- content ---------------------------------------------------
    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("Content")
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(52)
        h = QHBoxLayout(topbar)
        h.setContentsMargins(20, 0, 20, 0)
        self.crumb = QLabel("Dashboard")
        self.crumb.setObjectName("Crumb")
        h.addWidget(self.crumb)
        h.addStretch(1)
        chip = QLabel(f"{self.user.role_name or ('Superuser' if self.user.is_superuser else 'User')}")
        chip.setObjectName("UserChip")
        h.addWidget(chip)
        v.addWidget(topbar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("Screens")
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        v.addWidget(self.tabs, 1)
        return content

    # -- navigation actions --------------------------------------
    def _on_nav_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        key = item.data(0, _ROLE_KEY)
        if key is None:
            return
        if key in MENU_BY_KEY:  # group header - toggle expand
            item.setExpanded(not item.isExpanded())
            return
        self._open_screen(key, item.data(0, _LABEL_KEY) or item.text(0))

    def _open_dashboard(self) -> None:
        dash = DashboardWidget(self.user)
        dash.open_requested.connect(self._open_by_key)
        idx = self.tabs.addTab(dash, "  Dashboard  ")
        self.tabs.setCurrentIndex(idx)
        # dashboard tab is not closable
        self.tabs.tabBar().setTabButton(idx, self.tabs.tabBar().ButtonPosition.RightSide, None)
        self._tabs_by_key["__dashboard__"] = dash

    def _open_by_key(self, key: str) -> None:
        group = MENU_BY_KEY.get(key.split(".", 1)[0])
        label = key
        if group:
            for it in group.items:
                if it.key == key:
                    label = it.label
        self._open_screen(key, label)

    def _open_screen(self, menu_key: str, label: str) -> None:
        if not self.user.can_view(menu_key):
            QMessageBox.warning(self, "Access denied",
                                f"You do not have permission to open '{label}'.")
            return
        if menu_key in self._tabs_by_key:
            self.tabs.setCurrentWidget(self._tabs_by_key[menu_key])
            return
        try:
            widget = build_widget(menu_key, self.user)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not open '{label}':\n{exc}")
            return
        idx = self.tabs.addTab(widget, f"  {label}  ")
        self._tabs_by_key[menu_key] = widget
        self.tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        for key, w in list(self._tabs_by_key.items()):
            if w is widget and key != "__dashboard__":
                self._tabs_by_key.pop(key, None)
                self.tabs.removeTab(index)
                widget.deleteLater()
                return

    def _on_tab_changed(self, index: int) -> None:
        if index >= 0:
            self.crumb.setText(self.tabs.tabText(index).strip() or "Dashboard")

    # -- account ---------------------------------------------------
    def _build_statusbar(self) -> None:
        role = self.user.role_name or ("Superuser" if self.user.is_superuser else "No role")
        self.statusBar().showMessage(
            f"v{__version__}  ·  {self.user.username} ({role})  ·  DB: {DB_PATH}"
        )

    def _change_password(self) -> None:
        dlg = _ChangePasswordDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        with SessionLocal() as session:
            try:
                change_password(session, self.user.id, dlg.old_pw(), dlg.new_pw())
            except AuthError as exc:
                QMessageBox.critical(self, "Change Password", str(exc))
                return
        QMessageBox.information(self, "Change Password", "Password updated.")

    def _logout(self) -> None:
        if QMessageBox.question(self, "Log Out", "Log out now?") == QMessageBox.StandardButton.Yes:
            self._relogin = True
            self.close()

    def _relogin_requested(self) -> bool:
        return self._relogin


class _ChangePasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Password")
        self.setMinimumWidth(320)
        layout = QFormLayout(self)
        self._old = QLineEdit()
        self._new = QLineEdit()
        self._confirm = QLineEdit()
        for e in (self._old, self._new, self._confirm):
            e.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Current Password", self._old)
        layout.addRow("New Password", self._new)
        layout.addRow("Confirm New Password", self._confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _validate(self) -> None:
        if self._new.text() != self._confirm.text():
            QMessageBox.warning(self, "Change Password", "New passwords do not match.")
            return
        self.accept()

    def old_pw(self) -> str:
        return self._old.text()

    def new_pw(self) -> str:
        return self._new.text()
