import os
from datetime import date
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar
)
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtCore import Qt

from src.archive.archive_manager import ArchiveManager
from src.archive.history_lookup import lookup_flagged_records
from src.core.matcher import reconcile
from src.ui.import_tab import ImportTab
from src.ui.reconcile_tab import ReconcileTab
from src.ui.archive_tab import ArchiveTab
from src.ui.reports_tab import ReportsTab
from src.ui.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self._current_results = []
        self._current_counterparty = None

        self.setWindowTitle("Payment Reconciler")
        self.setMinimumSize(1280, 800)
        self._apply_dark_palette()

        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 10))
        self.setCentralWidget(self.tabs)

        # Build tabs
        self.import_tab = ImportTab(config_manager)
        self.reconcile_tab = ReconcileTab(config_manager)
        self.archive_tab = ArchiveTab(config_manager)
        self.reports_tab = ReportsTab(config_manager)
        self.settings_tab = SettingsTab(config_manager)

        self.tabs.addTab(self.import_tab, "Import")
        self.tabs.addTab(self.reconcile_tab, "Reconcile")
        self.tabs.addTab(self.archive_tab, "Archive")
        self.tabs.addTab(self.reports_tab, "Reports")
        self.tabs.addTab(self.settings_tab, "Settings")

        # Wire signals
        self.import_tab.reconciliation_requested.connect(self._run_reconciliation)
        self.reconcile_tab.save_to_archive_requested.connect(self._save_to_archive)
        self.settings_tab.settings_saved.connect(self._on_settings_saved)

        self.statusBar().showMessage("Ready")

    def _apply_dark_palette(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(45, 45, 45))
        palette.setColor(QPalette.AlternateBase, QColor(60, 60, 60))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Highlight, QColor(68, 114, 196))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)

    def _run_reconciliation(self, gpg_records, ws_entries, counterparty_name):
        self.statusBar().showMessage(
            f"Running reconciliation for {counterparty_name}..."
        )
        # Load archived flags for DT06 lookback
        archived_flags = []
        try:
            cp = self.config.get_counterparty(counterparty_name)
            lookback = cp.get("lookback_days", 5)
            archive_path = self.config.archive_path
            if not os.path.isabs(archive_path):
                archive_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", archive_path
                )
            archived_flags = lookup_flagged_records(
                archive_path, counterparty_name, lookback_days=lookback
            )
        except Exception:
            pass

        results = reconcile(gpg_records, ws_entries, archived_flags)
        self._current_results = results
        self._current_counterparty = counterparty_name

        self.reconcile_tab.load_results(results, counterparty_name)
        self.tabs.setCurrentWidget(self.reconcile_tab)

        matched = sum(1 for r in results if r.status.value == "matched")
        total = len(results)
        self.statusBar().showMessage(
            f"Reconciliation complete: {matched}/{total} matched "
            f"for {counterparty_name}"
        )

    def _save_to_archive(self, value_date: date, counterparty_display: str = ""):
        if not self._current_results:
            return
        label = counterparty_display or self._current_counterparty or "UNKNOWN"
        try:
            archive_path = self.config.archive_path
            if not os.path.isabs(archive_path):
                archive_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", archive_path
                )
            am = ArchiveManager(archive_path)
            am.save_daily(value_date, label, self._current_results)
            self.archive_tab.refresh()
            self.statusBar().showMessage(
                f"Saved: {value_date.strftime('%d %b %Y')}_{label}.xlsx"
            )
        except Exception as e:
            self.statusBar().showMessage(f"Archive save failed: {e}")

    def _on_settings_saved(self):
        self.statusBar().showMessage("Settings saved.")
        self.import_tab.reload_config()
        self.reports_tab.reload_config()
