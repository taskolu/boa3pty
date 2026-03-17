from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTableWidget, QTableWidgetItem, QFileDialog,
    QGroupBox, QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from src.core.parser_gpg import parse_gpg_csv
from src.core.parser_wallstreet import parse_wallstreet_paste


class ImportTab(QWidget):
    # Emits (gpg_records, ws_entries, counterparty_name)
    reconciliation_requested = pyqtSignal(list, list, str)

    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self.gpg_records = []
        self.ws_entries = []
        self.detected_counterparty = None
        self._init_ui()

    def reload_config(self):
        """Called when settings are saved — re-read config in case mappings changed."""
        pass  # config_manager is a reference, always up-to-date

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        panels = QHBoxLayout()

        # ── Left: GPG CSV ──────────────────────────────────────────
        left_group = QGroupBox("GPG CSV Import")
        left_layout = QVBoxLayout(left_group)

        self.btn_browse = QPushButton("Browse CSV File…")
        self.btn_browse.clicked.connect(self._browse_csv)
        left_layout.addWidget(self.btn_browse)

        self.lbl_gpg_info = QLabel("No file loaded")
        self.lbl_gpg_info.setWordWrap(True)
        left_layout.addWidget(self.lbl_gpg_info)

        self.tbl_gpg = QTableWidget()
        self.tbl_gpg.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_gpg.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_gpg.setAlternatingRowColors(True)
        left_layout.addWidget(self.tbl_gpg)

        panels.addWidget(left_group)

        # ── Right: WallStreet Paste ─────────────────────────────────
        right_group = QGroupBox("WallStreet Paste")
        right_layout = QVBoxLayout(right_group)

        right_layout.addWidget(QLabel(
            "Select data in WallStreet → copy → paste here (Ctrl+V):"
        ))

        self.txt_ws = QTextEdit()
        self.txt_ws.setPlaceholderText(
            "Paste tab-separated WallStreet data here…\n\n"
            "Expected columns: Deal Type | Value Date | Customer | "
            "Pay Ccy | Pay Amount | Rec Ccy | Rec Amount | Rate | "
            "Trader | Deal # | Ext Deal #\n\n"
            "(Column order does not matter — parsed by header name)"
        )
        self.txt_ws.setFont(QFont("Courier New", 9))
        self.txt_ws.textChanged.connect(self._on_paste_changed)
        right_layout.addWidget(self.txt_ws, 1)

        self.lbl_ws_info = QLabel("No data pasted")
        self.lbl_ws_info.setWordWrap(True)
        right_layout.addWidget(self.lbl_ws_info)

        self.tbl_ws = QTableWidget()
        self.tbl_ws.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_ws.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_ws.setAlternatingRowColors(True)
        right_layout.addWidget(self.tbl_ws)

        panels.addWidget(right_group)
        main_layout.addLayout(panels, 1)

        # ── Run button ──────────────────────────────────────────────
        self.btn_run = QPushButton("▶  Run Reconciliation")
        self.btn_run.setEnabled(False)
        self.btn_run.setMinimumHeight(48)
        self.btn_run.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #4472C4; color: white; "
            "border-radius: 6px; padding: 6px; } "
            "QPushButton:hover { background-color: #5583d5; } "
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self.btn_run.clicked.connect(self._run)
        main_layout.addWidget(self.btn_run)

    # ── GPG CSV ────────────────────────────────────────────────────

    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GPG CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return

        for cp_name in self.config.counterparty_names:
            cp = self.config.get_counterparty(cp_name)
            try:
                records, bank_code = parse_gpg_csv(
                    path,
                    cp["csv_column_mapping"],
                    cp["date_format"],
                )
                if bank_code and self.config.find_by_bank_code(bank_code):
                    self.gpg_records = records
                    self.detected_counterparty = cp_name
                    self.lbl_gpg_info.setText(
                        f"File: {path}\n"
                        f"Records: {len(records)}\n"
                        f"Counterparty: {cp_name} (code: {bank_code})"
                    )
                    self._populate_gpg_preview()
                    self._check_ready()
                    return
            except Exception:
                continue

        QMessageBox.warning(
            self, "Parse Error",
            "Could not parse CSV with any configured counterparty.\n"
            "Check Settings → add or update the counterparty mapping."
        )

    def _populate_gpg_preview(self):
        headers = ["Conf#", "Currency", "Amount", "Value Date", "Status"]
        self.tbl_gpg.setColumnCount(len(headers))
        self.tbl_gpg.setHorizontalHeaderLabels(headers)
        rows = self.gpg_records[:100]
        self.tbl_gpg.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.tbl_gpg.setItem(i, 0, QTableWidgetItem(r.confirmation_number))
            self.tbl_gpg.setItem(i, 1, QTableWidgetItem(r.buy_currency))
            self.tbl_gpg.setItem(i, 2, QTableWidgetItem(str(r.buy_amount)))
            self.tbl_gpg.setItem(i, 3, QTableWidgetItem(r.value_date.isoformat()))
            self.tbl_gpg.setItem(i, 4, QTableWidgetItem(r.status_code or ""))

    # ── WallStreet Paste ───────────────────────────────────────────

    def _on_paste_changed(self):
        text = self.txt_ws.toPlainText().strip()
        if not text:
            self.ws_entries = []
            self.lbl_ws_info.setText("No data pasted")
            self.tbl_ws.setRowCount(0)
            self._check_ready()
            return

        # Use counterparty's wallstreet_column_mapping override if available
        col_override = {}
        if self.detected_counterparty:
            cp = self.config.get_counterparty(self.detected_counterparty)
            col_override = cp.get("wallstreet_column_mapping", {})

        try:
            entries, ws_cp = parse_wallstreet_paste(text, col_override)
            self.ws_entries = entries
            dup_count = text.count("\n") - len(entries)
            info = (
                f"Parsed: {len(entries)} unique entries\n"
                f"Counterparty: {ws_cp or 'unknown'}"
            )
            if dup_count > 0:
                info += f"\n({dup_count} duplicate rows removed)"
            self.lbl_ws_info.setText(info)
            self._populate_ws_preview()
        except Exception as e:
            self.lbl_ws_info.setText(f"Parse error: {e}")
            self.ws_entries = []

        self._check_ready()

    def _populate_ws_preview(self):
        headers = ["Ext Deal #", "Value Date", "Pay Ccy", "Pay Amt",
                   "Rec Ccy", "Rec Amt", "Rate", "Customer"]
        self.tbl_ws.setColumnCount(len(headers))
        self.tbl_ws.setHorizontalHeaderLabels(headers)
        rows = self.ws_entries[:100]
        self.tbl_ws.setRowCount(len(rows))
        for i, e in enumerate(rows):
            self.tbl_ws.setItem(i, 0, QTableWidgetItem(e.external_ref))
            self.tbl_ws.setItem(i, 1, QTableWidgetItem(e.value_date.isoformat()))
            self.tbl_ws.setItem(i, 2, QTableWidgetItem(e.pay_ccy))
            self.tbl_ws.setItem(i, 3, QTableWidgetItem(str(e.pay_amount)))
            self.tbl_ws.setItem(i, 4, QTableWidgetItem(e.rec_ccy))
            self.tbl_ws.setItem(i, 5, QTableWidgetItem(str(e.rec_amount)))
            self.tbl_ws.setItem(i, 6, QTableWidgetItem(str(e.rate)))
            self.tbl_ws.setItem(i, 7, QTableWidgetItem(e.counterparty))

    def _check_ready(self):
        self.btn_run.setEnabled(
            len(self.gpg_records) > 0 and len(self.ws_entries) > 0
        )

    def _run(self):
        cp = self.detected_counterparty or "Unknown"
        self.reconciliation_requested.emit(self.gpg_records, self.ws_entries, cp)
