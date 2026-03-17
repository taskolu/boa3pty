from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QLineEdit, QFileDialog, QDateEdit, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QDate
from PyQt5.QtGui import QColor, QFont, QBrush

from src.core.models import MatchStatus
from src.export.report_generator import generate_payment_breakdown

# Status → (display label, row background color)
_STATUS_STYLE: dict[str, tuple[str, str]] = {
    MatchStatus.MATCHED.value:              ("✓ Matched",          "#1a3a1a"),
    MatchStatus.UNMATCHED_GPG.value:        ("✗ Missing in WS",    "#3a1a1a"),
    MatchStatus.UNMATCHED_WS.value:         ("⚠ Extra in WS",      "#3a2a00"),
    MatchStatus.FLAGGED_DT06.value:         ("⏳ DT06 Flagged",     "#2a2a3a"),
    MatchStatus.RESOLVED_FROM_ARCHIVE.value:("↩ Resolved (Archive)","#1a2a1a"),
    MatchStatus.AMOUNT_MISMATCH.value:      ("$ Amount Mismatch",  "#3a1a00"),
    MatchStatus.CURRENCY_MISMATCH.value:    ("€ Currency Mismatch","#3a1a00"),
}


class ReconcileTab(QWidget):
    save_to_archive_requested = pyqtSignal(date)

    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self._all_results = []
        self._counterparty = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── Summary bar ────────────────────────────────────────────
        self.summary_bar = QHBoxLayout()
        self._summary_labels: dict[str, QLabel] = {}
        for status_val, (label, _) in _STATUS_STYLE.items():
            lbl = QLabel("0")
            lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
            lbl.setToolTip(label)
            self._summary_labels[status_val] = lbl
            self.summary_bar.addWidget(QLabel(f"{label}:"))
            self.summary_bar.addWidget(lbl)
            self.summary_bar.addSpacing(16)
        self.summary_bar.addStretch()
        layout.addLayout(self.summary_bar)

        # ── Filter / Search ─────────────────────────────────────────
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Filter:"))
        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(
            ["All", "Matched", "Missing in WS", "Extra in WS",
             "DT06 Flagged", "Resolved", "Amount Mismatch", "Currency Mismatch"]
        )
        self.cmb_filter.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.cmb_filter)
        filter_bar.addSpacing(16)
        filter_bar.addWidget(QLabel("Search:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Conf# / currency / amount…")
        self.txt_search.textChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.txt_search, 1)
        layout.addLayout(filter_bar)

        # ── Results table ───────────────────────────────────────────
        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.verticalHeader().setVisible(False)
        layout.addWidget(self.tbl, 1)

        # ── Bottom actions ──────────────────────────────────────────
        bottom = QHBoxLayout()

        archive_group = QGroupBox("Save to Archive")
        ag_layout = QHBoxLayout(archive_group)
        ag_layout.addWidget(QLabel("Value Date:"))
        self.dt_archive = QDateEdit()
        self.dt_archive.setCalendarPopup(True)
        self.dt_archive.setDate(QDate.currentDate())
        self.dt_archive.setDisplayFormat("dd MMM yyyy")
        ag_layout.addWidget(self.dt_archive)
        self.btn_save = QPushButton("Save to Archive")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_archive)
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #2e6e2e; color: white; "
            "border-radius: 4px; padding: 4px 12px; } "
            "QPushButton:hover { background-color: #3d8f3d; } "
            "QPushButton:disabled { background-color: #444; color: #777; }"
        )
        ag_layout.addWidget(self.btn_save)
        bottom.addWidget(archive_group)

        bottom.addStretch()

        self.btn_export = QPushButton("Export Report to Excel…")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_report)
        self.btn_export.setStyleSheet(
            "QPushButton { background-color: #4472C4; color: white; "
            "border-radius: 4px; padding: 6px 16px; } "
            "QPushButton:hover { background-color: #5583d5; } "
            "QPushButton:disabled { background-color: #444; color: #777; }"
        )
        bottom.addWidget(self.btn_export)
        layout.addLayout(bottom)

    def load_results(self, results, counterparty_name: str):
        self._all_results = results
        self._counterparty = counterparty_name
        self.btn_save.setEnabled(True)
        self.btn_export.setEnabled(True)
        self._update_summary(results)
        self._populate_table(results)

    def _update_summary(self, results):
        counts: dict[str, int] = {}
        for r in results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        for sv, lbl in self._summary_labels.items():
            lbl.setText(str(counts.get(sv, 0)))

    def _apply_filter(self):
        filter_text = self.cmb_filter.currentText()
        search = self.txt_search.text().lower()

        _filter_map = {
            "All":              None,
            "Matched":          MatchStatus.MATCHED.value,
            "Missing in WS":    MatchStatus.UNMATCHED_GPG.value,
            "Extra in WS":      MatchStatus.UNMATCHED_WS.value,
            "DT06 Flagged":     MatchStatus.FLAGGED_DT06.value,
            "Resolved":         MatchStatus.RESOLVED_FROM_ARCHIVE.value,
            "Amount Mismatch":  MatchStatus.AMOUNT_MISMATCH.value,
            "Currency Mismatch":MatchStatus.CURRENCY_MISMATCH.value,
        }
        status_filter = _filter_map.get(filter_text)

        filtered = []
        for r in self._all_results:
            if status_filter and r.status.value != status_filter:
                continue
            if search:
                haystack = " ".join([
                    r.gpg_record.confirmation_number if r.gpg_record else "",
                    r.gpg_record.buy_currency if r.gpg_record else "",
                    str(r.gpg_record.buy_amount) if r.gpg_record else "",
                    r.ws_record.external_ref if r.ws_record else "",
                    r.ws_record.rec_ccy if r.ws_record else "",
                ]).lower()
                if search not in haystack:
                    continue
            filtered.append(r)
        self._populate_table(filtered)

    def _populate_table(self, results):
        headers = [
            "Status", "Conf# / Ext Deal #", "GPG Currency", "GPG Amount",
            "VD (GPG)", "WS Rec Ccy", "WS Rec Amount", "VD (WS)",
            "WS Deal #", "Discrepancies"
        ]
        self.tbl.setColumnCount(len(headers))
        self.tbl.setHorizontalHeaderLabels(headers)
        self.tbl.setRowCount(len(results))

        for row_idx, r in enumerate(results):
            status_val = r.status.value
            display_label, bg_color = _STATUS_STYLE.get(
                status_val, (status_val, "#2a2a2a")
            )
            bg = QColor(bg_color)

            conf = (r.gpg_record.confirmation_number if r.gpg_record
                    else r.ws_record.external_ref if r.ws_record else "")

            cells = [
                display_label,
                conf,
                r.gpg_record.buy_currency if r.gpg_record else "",
                str(r.gpg_record.buy_amount) if r.gpg_record else "",
                r.gpg_record.value_date.isoformat() if r.gpg_record else "",
                r.ws_record.rec_ccy if r.ws_record else "",
                str(r.ws_record.rec_amount) if r.ws_record else "",
                r.ws_record.value_date.isoformat() if r.ws_record else "",
                r.ws_record.wallstreet_ref if r.ws_record else "",
                "; ".join(r.discrepancies),
            ]
            for col_idx, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setBackground(QBrush(bg))
                self.tbl.setItem(row_idx, col_idx, item)

    def _save_archive(self):
        qd = self.dt_archive.date()
        d = date(qd.year(), qd.month(), qd.day())
        self.save_to_archive_requested.emit(d)

    def _export_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", "", "Excel Files (*.xlsx)"
        )
        if not path:
            return
        try:
            qd = self.dt_archive.date()
            d = date(qd.year(), qd.month(), qd.day())
            generate_payment_breakdown(self._all_results, path, d)
            QMessageBox.information(self, "Export", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
