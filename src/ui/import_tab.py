import csv
from datetime import datetime
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTableWidget, QTableWidgetItem, QFileDialog,
    QGroupBox, QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from src.core.parser_gpg import parse_gpg_file, parse_gpg_csv, _read_rows
from src.core.parser_wallstreet import parse_wallstreet_paste, get_detected_ws_headers

# ── Column auto-detection: maps standard field → list of known aliases ─────────
_GPG_ALIASES = {
    "payment_id": [
        "source system payment id",    # Convera XLS — same as confirmation_number
        "payment id", "pay id", "payid", "payment_id",
        "transaction id", "txn id",
    ],
    "confirmation_number": [
        "source system payment id",    # Convera XLS primary key (matches WS Ext Deal #)
        "transaction reference",       # GPG Convera CSV format
        "confirmation number", "confirm number", "conf number", "conf#",
        "payment reference", "payment ref",
        "external ref", "ext ref",
    ],
    "buy_currency": [
        "currency_code",               # Convera XLS
        "currency", "ccy", "buy currency", "buy ccy",
        "pay currency", "payment currency", "currency code",
    ],
    "buy_amount": [
        "amount",                      # Convera XLS
        "pay amount", "payment amount", "value", "buy amount",
    ],
    "value_date": [
        "value_date_in_utc",           # Convera XLS
        "value date", "settlement date", "vdate", "value_date",
        "settle date", "book date",
    ],
    "status_code": [
        "payment_status",              # Convera XLS (ACCEPTED / REJECTED / etc.)
        "error_code",                  # Convera XLS DT06 code
        "status information/error", "status information", "status",
        "error", "status code", "rejection",
    ],
}

_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                 "%d %b %Y", "%d-%b-%Y", "%Y/%m/%d"]

_BANK_CODE_ALIASES = [
    "inventory_code",          # Convera XLS (e.g. ALLCUKBOA, MGACUKBOA)
    "bank code", "bank", "counterparty code", "cp code",
    "entity", "institution code", "code",
    "counterparty account", "counterparty name",
]


def _normalise(s: str) -> str:
    return s.strip().lower()


def _auto_map_columns(headers: list[str]) -> dict:
    """Try to map CSV headers → standard field names using known aliases."""
    norm_headers = {_normalise(h): h for h in headers}
    mapping = {}
    for field, aliases in _GPG_ALIASES.items():
        for alias in aliases:
            if alias in norm_headers:
                mapping[field] = norm_headers[alias]
                break
    return mapping


def _detect_bank_code_column(headers: list[str]) -> Optional[str]:
    """Return the CSV column name that most likely holds the bank/entity code."""
    norm = {_normalise(h): h for h in headers}
    for alias in _BANK_CODE_ALIASES:
        if alias in norm:
            return norm[alias]
    return None


def _detect_date_format(sample_value: str) -> str:
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(sample_value.strip(), fmt)
            return fmt
        except ValueError:
            continue
    return "%Y-%m-%d"


def _sniff_file(path: str) -> tuple[list[str], list[dict], str]:
    """Read headers and first few rows from CSV, XLS, or XLSX.

    Returns (headers, sample_rows, delimiter).
    delimiter is ',' for Excel files (unused by the Excel reader).
    """
    from pathlib import Path
    ext = Path(path).suffix.lower()

    if ext in (".xls", ".xlsx", ".xlsm"):
        rows, headers = _read_rows(path)
        return headers, rows[:5], ","

    # CSV: auto-detect delimiter
    with open(path, "r", encoding="utf-8-sig") as f:
        sample = f.read(2048)
    first_line = sample.splitlines()[0] if sample else ""
    counts = {"\t": first_line.count("\t"), ";": first_line.count(";"), ",": first_line.count(",")}
    delimiter = max(counts, key=counts.get)
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        headers = list(reader.fieldnames or [])
        rows = [row for _, row in zip(range(5), reader)]
    return headers, rows, delimiter


# keep old name for any callers
def _sniff_csv(path: str) -> tuple[list[str], list[dict], str]:
    return _sniff_file(path)


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
        pass

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        panels = QHBoxLayout()

        # ── Left: GPG CSV ───────────────────────────────────────────
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

    # ── GPG CSV loading ────────────────────────────────────────────

    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GPG File", "",
            "GPG Reports (*.csv *.xls *.xlsx);;CSV Files (*.csv);;Excel Files (*.xls *.xlsx);;All Files (*)"
        )
        if not path:
            return

        # 1. Try existing configured counterparties first
        for cp_name in self.config.counterparty_names:
            cp = self.config.get_counterparty(cp_name)
            try:
                bank_col = _detect_bank_code_column(
                    _sniff_file(path)[0]
                ) or "inventory_code"
                records, bank_code = parse_gpg_file(
                    path, cp["csv_column_mapping"], cp["date_format"],
                    bank_code_column=bank_col,
                )
                if bank_code and self.config.find_by_bank_code(bank_code):
                    self._load_gpg_success(records, cp_name, bank_code, path)
                    return
            except Exception:
                continue

        # 2. Auto-detect from CSV headers and create counterparty automatically
        self._auto_detect_and_load(path)

    def _auto_detect_and_load(self, path: str):
        """Read CSV headers, auto-map columns, auto-create counterparty config."""
        try:
            headers, sample_rows, delimiter = _sniff_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Read Error", f"Could not read CSV:\n{e}")
            return

        if not headers:
            QMessageBox.warning(self, "Empty CSV", "The CSV file appears to be empty.")
            return

        col_mapping = _auto_map_columns(headers)
        bank_code_col = _detect_bank_code_column(headers)

        # Must have at minimum: confirmation_number, buy_currency, buy_amount, value_date
        required = ["confirmation_number", "buy_currency", "buy_amount", "value_date"]
        missing = [f for f in required if f not in col_mapping]
        if missing:
            # Show which headers we found so user can go fix Settings
            QMessageBox.warning(
                self, "Could Not Auto-Detect Columns",
                f"Could not automatically map these fields: {', '.join(missing)}\n\n"
                f"CSV headers found: {', '.join(headers)}\n\n"
                "Go to Settings → Add Counterparty and map the columns manually."
            )
            return

        # Detect date format from first sample row
        date_format = "%Y-%m-%d"
        if sample_rows and col_mapping.get("value_date"):
            vd_col = col_mapping["value_date"]
            sample_vd = sample_rows[0].get(vd_col, "").strip()
            if sample_vd:
                date_format = _detect_date_format(sample_vd)

        # Detect bank code value
        bank_code_value = "AUTO_DETECTED"
        if bank_code_col and sample_rows:
            bank_code_value = sample_rows[0].get(bank_code_col, "AUTO_DETECTED").strip()
        if not bank_code_value:
            bank_code_value = "AUTO_DETECTED"

        # payment_id fallback: use confirmation_number column if not found
        if "payment_id" not in col_mapping:
            col_mapping["payment_id"] = col_mapping["confirmation_number"]

        # Try to parse with auto-detected mapping
        try:
            records, detected_code = parse_gpg_file(
                path, col_mapping, date_format,
                bank_code_column=bank_code_col or "inventory_code",
                delimiter=delimiter,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Parse Error",
                f"Auto-detection found columns but parsing failed:\n{e}\n\n"
                "Go to Settings → Add Counterparty to configure manually."
            )
            return

        if not records:
            QMessageBox.warning(self, "No Records", "CSV parsed but contains no rows.")
            return

        # Use detected bank code if available
        if detected_code:
            bank_code_value = detected_code

        # Check if this bank code already exists under a different name
        existing_cp = self.config.find_by_bank_code(bank_code_value)
        if existing_cp:
            self._load_gpg_success(records, existing_cp, bank_code_value, path)
            return

        # Auto-create a new counterparty config and save it
        cp_name = bank_code_value  # use bank code as name for now
        new_config = {
            "csv_bank_code": bank_code_value,
            "wallstreet_counterparty_name": "",  # filled later from WS paste
            "csv_column_mapping": col_mapping,
            "date_format": date_format,
            "dt06_code": "DT06",
            "lookback_days": 5,
            "auto_resolve_dt06": False,
            "rules": ["dt06_date_change"],
            "wallstreet_column_mapping": {},
        }
        self.config.add_counterparty(cp_name, new_config)
        self.config.save()

        self._load_gpg_success(records, cp_name, bank_code_value, path,
                                auto_created=True)

    def _load_gpg_success(self, records, cp_name, bank_code, path,
                           auto_created=False):
        self.gpg_records = records
        self.detected_counterparty = cp_name
        display = self.config.get_display_name(cp_name)
        note = " (auto-detected)" if auto_created else ""
        self.lbl_gpg_info.setText(
            f"File: {path}\n"
            f"Records: {len(records)}\n"
            f"Counterparty: {display} (code: {bank_code}){note}"
        )
        self._populate_gpg_preview()
        self._check_ready()

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

        col_override = {}
        if self.detected_counterparty:
            cp = self.config.get_counterparty(self.detected_counterparty)
            col_override = cp.get("wallstreet_column_mapping", {})

        try:
            entries, ws_cp = parse_wallstreet_paste(text, col_override)
            self.ws_entries = entries

            # If counterparty was auto-created with blank ws_name, fill it in now
            if ws_cp and self.detected_counterparty:
                cp = self.config.get_counterparty(self.detected_counterparty)
                if not cp.get("wallstreet_counterparty_name"):
                    cp["wallstreet_counterparty_name"] = ws_cp
                    self.config.update_counterparty(self.detected_counterparty, cp)
                    self.config.save()

            # Count actual data lines: non-empty lines after the header
            all_nonempty = [l for l in text.splitlines() if l.strip()]
            data_line_count = max(0, len(all_nonempty) - 1)  # subtract header row
            dup_count = max(0, data_line_count - len(entries))
            info = (
                f"Parsed: {len(entries)} unique entries\n"
                f"Counterparty: {ws_cp or 'unknown'}"
            )
            if dup_count > 0 and len(entries) > 0:
                info += f"\n({dup_count} duplicate rows removed)"
            if len(entries) == 0:
                detected_hdrs = get_detected_ws_headers(text)
                if detected_hdrs:
                    info += f"\n\nDetected headers: {', '.join(detected_hdrs)}"
                    info += "\n(Check that 'Ext Deal #' column is present)"
                else:
                    info += "\n\nNo header row detected in paste."
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
