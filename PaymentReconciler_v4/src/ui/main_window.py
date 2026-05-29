from __future__ import annotations
import os
import sys
from datetime import date
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon, setTheme, Theme, InfoBar, InfoBarPosition

from src.core.config import ConfigManager
from src.core.models import MatchStatus
from src.core.matcher import reconcile
from src.archive.archive_manager import ArchiveManager
from src.archive.history_lookup import lookup_flagged_records
from src.core.app_dir import resolve_archive_path


def _dominant_gpg_value_date(gpg_records):
    dates = [r.value_date for r in gpg_records if getattr(r, "value_date", None)]
    if not dates:
        return None
    return max(set(dates), key=dates.count)


class MainWindow(FluentWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config = config_manager
        self._current_results = []
        self._current_counterparty = None
        self._result_saved = True
        self._prev_page = None

        self.setWindowTitle("Exotic Payment Reconciler")
        self.setMinimumSize(1400, 860)
        base = getattr(
            sys, "_MEIPASS",
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        icon_path = os.path.join(base, "assets", "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        setTheme(Theme.DARK)

        from src.ui.import_interface import ImportInterface
        from src.ui.reconcile_interface import ReconcileInterface
        from src.ui.archive_interface import ArchiveInterface
        from src.ui.reports_interface import ReportsInterface
        from src.ui.settings_interface import SettingsInterface

        self.import_iface    = ImportInterface(config_manager, self)
        self.reconcile_iface = ReconcileInterface(config_manager, self)
        self.archive_iface   = ArchiveInterface(config_manager, self)
        self.reports_iface   = ReportsInterface(config_manager, self)
        self.settings_iface  = SettingsInterface(config_manager, self)

        self.addSubInterface(self.import_iface,    FluentIcon.DOWNLOAD,   "Import")
        self.addSubInterface(self.reconcile_iface, FluentIcon.CHECKBOX,   "Reconcile")
        self.addSubInterface(self.archive_iface,   FluentIcon.FOLDER,     "Archive")
        self.addSubInterface(self.reports_iface,   FluentIcon.DOCUMENT,   "Reports")
        self.addSubInterface(
            self.settings_iface, FluentIcon.SETTING, "Settings",
            NavigationItemPosition.BOTTOM
        )

        self.import_iface.reconciliation_requested.connect(self._run_reconciliation)
        self.reconcile_iface.save_to_archive_requested.connect(self._save_to_archive)
        self.settings_iface.settings_saved.connect(self._on_settings_saved)
        self.stackedWidget.currentChanged.connect(self._on_page_changed)

    # ── Reconciliation ─────────────────────────────────────────────

    def _run_reconciliation(self, gpg_records, ws_entries, counterparty_name):
        archived_flags = []
        display_name = self.config.get_display_name(counterparty_name)
        dt06_code = "DT06"
        amount_tolerances = {}
        try:
            cp = self.config.get_counterparty(counterparty_name)
            lookback = cp.get("lookback_days", 10)
            dt06_code = cp.get("dt06_code", "DT06")
            amount_tolerances = cp.get("amount_tolerances", {})
            archive_path = resolve_archive_path(
                self.config.get_counterparty_archive_path(counterparty_name)
            )
            reference_date = _dominant_gpg_value_date(gpg_records)
            archived_flags = lookup_flagged_records(
                archive_path, display_name, lookback_days=lookback,
                reference_date=reference_date)
        except Exception:
            pass

        results = reconcile(
            gpg_records,
            ws_entries,
            archived_flags,
            dt06_code=dt06_code,
            amount_tolerances=amount_tolerances,
        )
        self._current_results = results
        self._current_counterparty = counterparty_name
        self._result_saved = False

        self.reconcile_iface.load_results(results, display_name, amount_tolerances)

        # Switch to reconcile page
        self.stackedWidget.setCurrentWidget(self.reconcile_iface)
        self.navigationInterface.setCurrentItem(self.reconcile_iface.objectName())

        matched = sum(1 for r in results if r.status == MatchStatus.MATCHED)
        resolved = sum(1 for r in results if r.status == MatchStatus.RESOLVED_FROM_ARCHIVE)
        total = len(results)
        open_items = total - matched - resolved
        info_method = InfoBar.success if open_items == 0 else InfoBar.warning
        info_method(
            title="Reconciliation Complete" if open_items == 0 else "Review Needed",
            content=f"{matched} matched, {resolved} resolved from archive, {total} total — {display_name}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=4000,
            parent=self,
        )

    # ── Archive save ────────────────────────────────────────────────

    def _save_to_archive(self, value_date: date, counterparty_display: str = ""):
        if not self._current_results:
            return
        label = counterparty_display or self._current_counterparty or "UNKNOWN"
        try:
            archive_path = resolve_archive_path(
                self.config.get_counterparty_archive_path(self._current_counterparty)
            )
            am = ArchiveManager(archive_path)

            expected = os.path.join(archive_path, f"{value_date.isoformat()}_{label}.xlsx")
            if os.path.exists(expected):
                box = QMessageBox(self)
                box.setWindowTitle("Archive Already Exists")
                box.setText(
                    f"Archive for {value_date.strftime('%d %b %Y')} / {label} already exists.\n"
                    "Overwrite it?"
                )
                box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                if box.exec() != QMessageBox.Yes:
                    return

            am.save_daily(value_date, label, self._current_results)
            self._result_saved = True

            matched = sum(1 for r in self._current_results if r.status == MatchStatus.MATCHED)
            resolved = sum(
                1 for r in self._current_results
                if r.status == MatchStatus.RESOLVED_FROM_ARCHIVE
            )
            total = len(self._current_results)
            try:
                am.log_action(
                    "ARCHIVE_SAVED", label, value_date,
                    f"{matched} matched, {resolved} resolved, {total} total"
                )
            except Exception:
                pass

            self.archive_iface.refresh()
            InfoBar.success(
                title="Saved",
                content=f"{value_date.strftime('%d %b %Y')}_{label}.xlsx",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self,
            )
        except Exception as e:
            InfoBar.error(
                title="Save Failed",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self,
            )

    # ── Tab change guard ────────────────────────────────────────────

    def _on_page_changed(self, _idx: int):
        current = self.stackedWidget.currentWidget()
        if (self._prev_page is self.reconcile_iface
                and current is not self.reconcile_iface
                and self._current_results
                and not self._result_saved):
            box = QMessageBox(self)
            box.setWindowTitle("Save to Archive?")
            box.setText("You have unsaved reconciliation results.\nSave to archive now?")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            if box.exec() == QMessageBox.Yes:
                self.reconcile_iface._save_archive()
        self._prev_page = current

    # ── Settings saved ──────────────────────────────────────────────

    def _on_settings_saved(self):
        self.import_iface.reload_config()
        self.reports_iface.reload_config()
        InfoBar.success(
            title="Settings Saved",
            content="Configuration updated.",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self,
        )
