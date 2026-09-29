"""Main application window - top menu bar + tabbed content area.

The navigation mirrors the client's design workbook (14 modules) as a menu
bar across the top of the window, the way the legacy DIAGOLD screens are laid
out, so every screen gets the full width of the window instead of losing a
quarter of a laptop screen to a sidebar. The bar is drawn inside the window on both macOS and
Windows - Qt would otherwise push it into the native macOS menu bar.
"""
from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from diagold import APP_NAME, __version__
from diagold.config import COMPANY_DISPLAY_NAME, DB_PATH
from diagold.db.session import SessionLocal
from diagold.menu import MENU, MENU_BY_KEY
from diagold.services import settings
from diagold.services.auth import AuthError, CurrentUser, change_password
from diagold.ui.dashboard import DashboardWidget
from diagold.ui.registry import (EXTRA_SCREENS, REPORT_MENUS, SUBMENUS, build_widget,
                                 has_real_screen, report_key)
from diagold.ui.style import APP_QSS


class MainWindow(QMainWindow):
    def __init__(self, user: CurrentUser):
        super().__init__()
        self.user = user
        self._relogin = False
        self._tabs_by_key: dict[str, QWidget] = {}
        self._search_targets: dict[str, str] = {}

        self.setWindowTitle(f"{APP_NAME} — {COMPANY_DISPLAY_NAME}")
        self.resize(1240, 800)
        self.setStyleSheet(APP_QSS)

        self._build_menubar()
        self.setCentralWidget(self._build_content())
        self._build_statusbar()

        QShortcut(QKeySequence.StandardKey.Find, self,
                  activated=lambda: (self.nav_search.setFocus(), self.nav_search.selectAll()))
        # Job History is F11 in the legacy system - a habit worth keeping (UX7).
        QShortcut(QKeySequence("F11"), self,
                  activated=lambda: self._open_by_key("production_planning.job_history"))

        self._open_dashboard()

    # -- menu bar ----------------------------------------------------
    def _build_menubar(self) -> None:
        """Brand mark on the left, the module menus beside it, on one dark
        strip with a gold rule underneath."""
        strip = QWidget()
        strip.setObjectName("TopStrip")
        h = QHBoxLayout(strip)
        h.setContentsMargins(14, 0, 8, 0)
        h.setSpacing(0)
        brand = QLabel('<span style="color:#C9A227;">◆</span>&nbsp;&nbsp;Dia Gold')
        brand.setObjectName("Brand")
        brand.setTextFormat(Qt.TextFormat.RichText)
        h.addWidget(brand)
        rule = QWidget()
        rule.setObjectName("BrandRule")
        rule.setFixedSize(1, 22)
        h.addWidget(rule)
        # Parented, and non-native before anything is added: on macOS a
        # QMenuBar with no parent becomes the global menu bar at the top of
        # the screen and leaves this strip empty.
        self._menubar = QMenuBar(strip)
        self._menubar.setNativeMenuBar(False)
        self._menubar.setObjectName("TopMenu")
        h.addWidget(self._menubar, 1)
        self.setMenuWidget(strip)
        self._populate_nav()

    def _populate_nav(self) -> None:
        """(Re)build the menus - also called when Tools > Option changes which
        Production-Planning items are shown."""
        bar = self._menubar
        bar.clear()
        self._search_targets = {}
        for group in MENU:
            menu = bar.addMenu(group.label)
            menu.setObjectName("TopMenuPopup")
            shown = 0
            for item in group.items:
                if not self.user.can_view(item.key):
                    continue
                if not settings.menu_visible(item.key):
                    continue  # switched off in Tools > Option (T-07)
                if item.key in REPORT_MENUS:
                    # Reports ▸ Karigar ▸ Worker Metal Ledger … - each report
                    # opens in its own tab; the top-level Reports menu lists
                    # its sections directly.
                    target = menu if item.key == "reports.all_reports" else menu.addMenu(item.label)
                    target.setObjectName("TopMenuPopup")
                    self._add_report_menu(target, REPORT_MENUS[item.key], group.label)
                    shown += 1
                    continue
                if item.key in SUBMENUS:
                    # Inventory ▸ Metal ▸ Purchase … - hover opens the submenu.
                    sub = menu.addMenu(item.label)
                    sub.setObjectName("TopMenuPopup")
                    for key, sub_label in SUBMENUS[item.key]:
                        if key in REPORT_MENUS:
                            rep = sub.addMenu(sub_label)
                            rep.setObjectName("TopMenuPopup")
                            self._add_report_menu(rep, REPORT_MENUS[key], group.label)
                            continue
                        text = sub_label if has_real_screen(key) else f"{sub_label}  ·  soon"
                        act = sub.addAction(text)
                        act.triggered.connect(
                            lambda _c=False, k=key: self._open_by_key(k))
                        self._search_targets[
                            f"{EXTRA_SCREENS.get(key, sub_label)}  —  {group.label}"] = key
                    shown += 1
                    continue
                label = item.label
                if not has_real_screen(item.key):
                    label += "  ·  soon"
                action = menu.addAction(label)
                action.triggered.connect(
                    lambda _c=False, k=item.key, l=item.label: self._open_screen(k, l))
                self._search_targets[f"{item.label}  —  {group.label}"] = item.key
                shown += 1
            menu.setEnabled(shown > 0)
        if hasattr(self, "nav_search"):
            self._search_model.setStringList(sorted(self._search_targets, key=str.lower))

    def _add_report_menu(self, menu, sections, group_label: str) -> None:
        """One submenu per report section (or the reports straight in, for a
        section with no title); every report opens in its own tab."""
        for title, keys in sections:
            target = menu
            if title:
                target = menu.addMenu(title)
                target.setObjectName("TopMenuPopup")
            for k in keys:
                key = report_key(k)
                label = EXTRA_SCREENS.get(key, k)
                act = target.addAction(label)
                act.triggered.connect(lambda _c=False, kk=key: self._open_by_key(kk))
                self._search_targets[f"{label}  —  {group_label} report"] = key

    def _build_corner(self) -> QWidget:
        """Menu search and the account menu, at the right end of the tab row -
        space that row has anyway, so the screen loses no height for them."""
        box = QWidget()
        box.setObjectName("TabCorner")
        h = QHBoxLayout(box)
        h.setContentsMargins(8, 2, 10, 2)
        h.setSpacing(8)
        self.nav_search = QLineEdit()
        self.nav_search.setObjectName("NavSearch")
        self.nav_search.setPlaceholderText("Go to screen…  (Ctrl/Cmd+F)")
        self.nav_search.setFixedWidth(230)
        self.nav_search.setClearButtonEnabled(True)
        self._search_model = QStringListModel(sorted(self._search_targets, key=str.lower))
        completer = QCompleter(self._search_model, self.nav_search)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated.connect(self._search_go)
        self.nav_search.setCompleter(completer)
        self.nav_search.returnPressed.connect(lambda: self._search_go(self.nav_search.text()))
        h.addWidget(self.nav_search)
        # The legacy screens carry an "Item Search" link top right; so does this.
        item_search = QToolButton()
        item_search.setObjectName("UserButton")
        item_search.setText("Item Search")
        item_search.clicked.connect(lambda: self._open_by_key("manufacturing.item_search"))
        h.addWidget(item_search)

        role = self.user.role_name or ("Superuser" if self.user.is_superuser else "User")
        who = QToolButton()
        who.setObjectName("UserButton")
        who.setText(f"\U0001F464  {self.user.full_name}")
        who.setToolTip(f"{self.user.username} · {role}")
        who.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(who)
        head = menu.addAction(f"{self.user.full_name}  ·  {role}")
        head.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Change Password", self._change_password)
        menu.addAction("Log Out", self._logout)
        who.setMenu(menu)
        h.addWidget(who)
        return box

    def _search_go(self, text: str) -> None:
        text = (text or "").strip()
        key = self._search_targets.get(text)
        if key is None and text:
            # Typed part of a name and pressed Enter: open the only match.
            hits = [k for label, k in self._search_targets.items()
                    if text.lower() in label.lower()]
            key = hits[0] if len(hits) == 1 else None
        if key is None:
            return
        self._open_by_key(key)
        self.nav_search.clear()

    # -- content ---------------------------------------------------
    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("Content")
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("Screens")
        # Not document mode: on macOS that hands the tab row to the native
        # unified-toolbar look, which paints it black in dark mode.
        self.tabs.setDocumentMode(False)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.setCornerWidget(self._build_corner(), Qt.Corner.TopRightCorner)
        v.addWidget(self.tabs, 1)
        return content

    # -- navigation actions --------------------------------------
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
        label = EXTRA_SCREENS.get(key, key)
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
        # Screens that link to one another (Job History <-> Job Bag), close
        # themselves (Exit), or change the menu (Options).
        if hasattr(widget, "open_requested"):
            widget.open_requested.connect(
                lambda key, src=widget: self._open_linked(key, src))
        if hasattr(widget, "close_requested"):
            widget.close_requested.connect(
                lambda w=widget: self._close_tab(self.tabs.indexOf(w)))
        if hasattr(widget, "nav_changed"):
            widget.nav_changed.connect(self._populate_nav)

    def _open_linked(self, key: str, source: QWidget) -> None:
        """Open another job screen on the job the source screen is showing."""
        self._open_by_key(key)
        target = self._tabs_by_key.get(key)
        job_id = getattr(source, "job_id", None)
        if target is not None and job_id and hasattr(target, "show_job"):
            target.show_job(job_id)

    def _close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        for key, w in list(self._tabs_by_key.items()):
            if w is widget and key != "__dashboard__":
                self._tabs_by_key.pop(key, None)
                self.tabs.removeTab(index)
                widget.deleteLater()
                return

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
