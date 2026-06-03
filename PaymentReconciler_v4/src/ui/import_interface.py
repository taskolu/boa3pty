from __future__ import annotations
import csv
import os
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QHeaderView,
    QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush

from qfluentwidgets import (
    PushButton, PrimaryPushButton, PlainTextEdit, CardWidget,
    SubtitleLabel, BodyLabel, TableWidget, ScrollArea
)

from src.core.counterparty_routing import matched_counterparty_for_bank_code
from src.core.parser_gpg import parse_gpg_file, _read_rows
from src.core.parser_wallstreet import parse_wallstreet_paste, get_detected_ws_headers

# ── Column aliases (copied from original import_tab.py) ──────────────────────
_GPG_ALIASES = {
    "payment_id": [
        "source system payment id", "payment id", "pay id", "payid",
        "payment_id", "transaction id", "txn id",
    ],
    "confirmation_number": [
        "source system payment id", "transaction reference",
        "confirmation number", "confirm number", "conf number", "conf#",
        "payment reference", "payment ref", "external ref", "ext ref",
    ],
    "buy_currency": [
        "currency_code", "currency", "ccy", "buy currency", "buy ccy",
        "pay currency", "payment currency", "currency code",
    ],
    "buy_amount": [
        "amount", "pay amount", "payment amount", "value", "buy amount",
    ],
    "value_date": [
        "value_date_in_utc", "value date", "settlement date", "vdate",
        "value_date", "settle date", "book date",
    ],
    "status_code": [
        "payment_status", "error_code", "status information/error",
        "status information", "status", "error", "status code", "rejection",
    ],
}

_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                 "%d %b %Y", "%d-%b-%Y", "%Y/%m/%d"]

_BANK_CODE_ALIASES = [
    "inventory_code", "bank code", "bank", "counterparty code", "cp code",
    "entity", "institution code", "code", "counterparty account", "counterparty name",
]


def _normalise(s: str) -> str:
    return s.strip().lower()


def _auto_map_columns(headers: list[str]) -> dict:
    norm_headers = {_normalise(h): h for h in headers}
    mapping = {}
    for field, aliases in _GPG_ALIASES.items():
        for alias in aliases:
            if alias in norm_headers:
                mapping[field] = norm_headers[alias]
                break
    return mapping


def _detect_bank_code_column(headers: list[str]) -> Optional[str]:
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
    from pathlib import Path
    ext = Path(path).suffix.lower()
    if ext in (".xls", ".xlsx", ".xlsm"):
        rows, headers = _read_rows(path)
        return headers, rows[:5], ","
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


class ImportInterface(QWidget):
    reconciliation_requested = Signal(list, list, str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("importInterface")
        self.config = config_manager
        self.gpg_records = []
        self.ws_entries = []
        self.detected_counterparty = None
        self._init_ui()

    def reload_config(self):
        pass

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = SubtitleLabel("Import Data")
        root.addWidget(title)

        panels = QHBoxLayout()
        panels.setSpacing(16)

        # ── GPG Card ──────────────────────────────────────────────────
        gpg_card = CardWidget(self)
        gpg_lay = QVBoxLayout(gpg_card)
        gpg_lay.setContentsMargins(16, 16, 16, 16)
        gpg_lay.setSpacing(10)

        gpg_lay.addWidget(BodyLabel("GPG CSV / Excel File"))
        self.btn_browse = PushButton("Browse File…")
        self.btn_browse.clicked.connect(self._browse_csv)
        gpg_lay.addWidget(self.btn_browse)

        self.lbl_gpg_info = BodyLabel("No file loaded")
        self.lbl_gpg_info.setWordWrap(True)
        gpg_lay.addWidget(self.lbl_gpg_info)

        self.tbl_gpg = TableWidget(self)
        self.tbl_gpg.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_gpg.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_gpg.setColumnCount(5)
        self.tbl_gpg.setHorizontalHeaderLabels(
            ["Conf #", "Currency", "Amount", "Value Date", "Status"])
        gpg_lay.addWidget(self.tbl_gpg, 1)
        panels.addWidget(gpg_card, 1)

        # ── WallStreet Card ───────────────────────────────────────────
        ws_card = CardWidget(self)
        ws_lay = QVBoxLayout(ws_card)
        ws_lay.setContentsMargins(16, 16, 16, 16)
        ws_lay.setSpacing(10)

        ws_lay.addWidget(BodyLabel("WallStreet Paste  (select rows in WS → Ctrl+C → paste here)"))

        self.txt_ws = PlainTextEdit(self)
        self.txt_ws.setPlaceholderText(
            "Paste tab-separated WallStreet data here…\n\n"
            "Expected: Deal Type | Value Date | Customer | Pay Ccy | Pay Amount | "
            "Rec Ccy | Rec Amount | Rate | Trader | Deal # | Ext Deal #\n\n"
            "(Column order doesn't matter — parsed by header name)"
        )
        self.txt_ws.setFont(QFont("Courier New", 9))
        self.txt_ws.textChanged.connect(self._on_paste_changed)
        ws_lay.addWidget(self.txt_ws, 1)

        self.lbl_ws_info = BodyLabel("No data pasted")
        self.lbl_ws_info.setWordWrap(True)
        ws_lay.addWidget(self.lbl_ws_info)

        self.tbl_ws = TableWidget(self)
        self.tbl_ws.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_ws.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_ws.setColumnCount(8)
        self.tbl_ws.setHorizontalHeaderLabels(
            ["Ext Deal #", "Value Date", "Pay Ccy", "Pay Amt",
             "Rec Ccy", "Rec Amt", "Rate", "Customer"])
        ws_lay.addWidget(self.tbl_ws, 1)
        panels.addWidget(ws_card, 1)

        root.addLayout(panels, 1)

        self.btn_run = PrimaryPushButton("▶  Run Reconciliation")
        self.btn_run.setEnabled(False)
        self.btn_run.setMinimumHeight(48)
        self.btn_run.clicked.connect(self._run)
        root.addWidget(self.btn_run)

    # ── GPG loading ───────────────────────────────────────────────────

    def _browse_csv(self):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GPG File", downloads,
            "GPG Reports (*.csv *.xls *.xlsx);;All Files (*)"
        )
        if not path:
            return

        for cp_name in self.config.counterparty_names:
            cp = self.config.get_counterparty(cp_name)
            try:
                bank_col = _detect_bank_code_column(_sniff_file(path)[0]) or "inventory_code"
                records, bank_code = parse_gpg_file(
                    path, cp["csv_column_mapping"], cp["date_format"],
                    bank_code_column=bank_col,
                )
                matched_cp = matched_counterparty_for_bank_code(self.config, bank_code or "")
                if bank_code and matched_cp:
                    self._load_gpg_success(records, matched_cp, bank_code, path)
                    return
            except Exception:
                continue

        self._auto_detect_and_load(path)

    def _auto_detect_and_load(self, path: str):
        try:
            headers, sample_rows, delimiter = _sniff_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Read Error", f"Could not read file:\n{e}")
            return
        if not headers:
            QMessageBox.warning(self, "Empty File", "The file appears to be empty.")
            return

        col_mapping = _auto_map_columns(headers)
        bank_code_col = _detect_bank_code_column(headers)
        required = ["confirmation_number", "buy_currency", "buy_amount", "value_date"]
        missing = [f for f in required if f not in col_mapping]
        if missing:
            QMessageBox.warning(
                self, "Could Not Auto-Detect Columns",
                f"Could not map: {', '.join(missing)}\n\n"
                f"Headers found: {', '.join(headers)}\n\n"
                "Go to Settings → Add Counterparty and map columns manually."
            )
            return

        date_format = "%Y-%m-%d"
        if sample_rows and col_mapping.get("value_date"):
            vd_col = col_mapping["value_date"]
            sample_vd = sample_rows[0].get(vd_col, "").strip()
            if sample_vd:
                date_format = _detect_date_format(sample_vd)

        bank_code_value = "AUTO_DETECTED"
        if bank_code_col and sample_rows:
            bank_code_value = sample_rows[0].get(bank_code_col, "AUTO_DETECTED").strip()
        if not bank_code_value:
            bank_code_value = "AUTO_DETECTED"

        if "payment_id" not in col_mapping:
            col_mapping["payment_id"] = col_mapping["confirmation_number"]

        try:
            records, detected_code = parse_gpg_file(
                path, col_mapping, date_format,
                bank_code_column=bank_code_col or "inventory_code",
                delimiter=delimiter,
            )
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", str(e))
            return

        if not records:
            QMessageBox.warning(self, "No Records", "File parsed but contains no rows.")
            return

        if detected_code:
            bank_code_value = detected_code

        existing_cp = self.config.find_by_bank_code(bank_code_value)
        if existing_cp:
            self._load_gpg_success(records, existing_cp, bank_code_value, path)
            return

        cp_name = bank_code_value
        new_config = {
            "csv_bank_code": bank_code_value,
            "wallstreet_counterparty_name": "",
            "csv_column_mapping": col_mapping,
            "date_format": date_format,
            "dt06_code": "DT06",
            "lookback_days": 10,
            "auto_resolve_dt06": False,
            "rules": ["dt06_date_change"],
            "wallstreet_column_mapping": {},
        }
        self.config.add_counterparty(cp_name, new_config)
        self.config.save()
        self._load_gpg_success(records, cp_name, bank_code_value, path, auto_created=True)

    def _load_gpg_success(self, records, cp_name, bank_code, path, auto_created=False):
        self.gpg_records = records
        self.detected_counterparty = cp_name
        display = self.config.get_display_name(cp_name)
        note = " (auto-detected)" if auto_created else ""
        self.lbl_gpg_info.setText(
            f"File: {os.path.basename(path)}\n"
            f"Records: {len(records)}   Counterparty: {display}{note}"
        )
        self.tbl_gpg.setRowCount(0)
        for i, r in enumerate(records[:200]):
            self.tbl_gpg.insertRow(i)
            self.tbl_gpg.setItem(i, 0, _item(r.confirmation_number))
            self.tbl_gpg.setItem(i, 1, _item(r.buy_currency))
            self.tbl_gpg.setItem(i, 2, _item(str(r.buy_amount)))
            self.tbl_gpg.setItem(i, 3, _item(r.value_date.isoformat()))
            self.tbl_gpg.setItem(i, 4, _item(r.status_code or ""))
        self._check_ready()

    # ── WallStreet paste ──────────────────────────────────────────────

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
            entries, ws_cp = parse_wallstreet_paste(
                text, col_override, self.config.ignored_currencies
            )
            self.ws_entries = entries

            if ws_cp and self.detected_counterparty:
                cp = self.config.get_counterparty(self.detected_counterparty)
                if not cp.get("wallstreet_counterparty_name"):
                    cp["wallstreet_counterparty_name"] = ws_cp
                    self.config.update_counterparty(self.detected_counterparty, cp)
                    self.config.save()

            all_nonempty = [l for l in text.splitlines() if l.strip()]
            dup_count = max(0, len(all_nonempty) - 1 - len(entries))
            info = f"Parsed: {len(entries)} unique entries   Counterparty: {ws_cp or 'unknown'}"
            if dup_count > 0:
                info += f"\n({dup_count} duplicate rows removed)"
            if len(entries) == 0:
                hdrs = get_detected_ws_headers(text)
                info += f"\n\nDetected headers: {', '.join(hdrs) if hdrs else 'none'}"
            self.lbl_ws_info.setText(info)

            self.tbl_ws.setRowCount(0)
            for i, e in enumerate(entries[:200]):
                self.tbl_ws.insertRow(i)
                self.tbl_ws.setItem(i, 0, _item(e.external_ref or e.wallstreet_ref))
                self.tbl_ws.setItem(i, 1, _item(e.value_date.isoformat()))
                self.tbl_ws.setItem(i, 2, _item(e.pay_ccy))
                self.tbl_ws.setItem(i, 3, _item(str(e.pay_amount)))
                self.tbl_ws.setItem(i, 4, _item(e.rec_ccy))
                self.tbl_ws.setItem(i, 5, _item(str(e.rec_amount)))
                self.tbl_ws.setItem(i, 6, _item(str(e.rate)))
                self.tbl_ws.setItem(i, 7, _item(e.counterparty))
        except Exception as e:
            self.lbl_ws_info.setText(f"Parse error: {e}")
            self.ws_entries = []

        self._check_ready()

    def _check_ready(self):
        self.btn_run.setEnabled(bool(self.gpg_records) and bool(self.ws_entries))

    def _run(self):
        cp = self.detected_counterparty or "Unknown"
        self.reconciliation_requested.emit(self.gpg_records, self.ws_entries, cp)


def _item(text: str):
    from PySide6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem(str(text))
