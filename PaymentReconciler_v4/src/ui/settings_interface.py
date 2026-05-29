from __future__ import annotations
import hashlib
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QCheckBox,
    QHeaderView, QAbstractItemView, QInputDialog
)
from PySide6.QtCore import Signal, Qt

from qfluentwidgets import (
    PushButton, PrimaryPushButton, SubtitleLabel, BodyLabel, CaptionLabel,
    LineEdit, ComboBox, ListWidget, TableWidget, ScrollArea, CardWidget
)

from src.core.app_dir import resolve_archive_path

_SETTINGS_PWD_HASH = hashlib.sha256(b"Convera22!").hexdigest()


class SettingsInterface(QWidget):
    settings_saved = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("settingsInterface")
        self.config = config_manager
        self._unlocked = False
        self._init_ui()

    def _check_auth(self) -> bool:
        if self._unlocked:
            return True
        from PySide6.QtWidgets import QLineEdit as _LE
        pwd, ok = QInputDialog.getText(
            self, "Settings Locked", "Enter password to edit settings:",
            _LE.EchoMode.Password
        )
        if ok and hashlib.sha256(pwd.encode()).hexdigest() == _SETTINGS_PWD_HASH:
            self._unlocked = True
            return True
        if ok:
            QMessageBox.warning(self, "Access Denied", "Incorrect password.")
        return False

    def _init_ui(self):
        # Outer scroll area so settings page is scrollable
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(SubtitleLabel("Settings"))

        # ── Ignored currencies ────────────────────────────────────────
        ccy_card = CardWidget(container)
        ccy_lay = QVBoxLayout(ccy_card)
        ccy_lay.setContentsMargins(16, 12, 16, 12)
        ccy_lay.addWidget(BodyLabel("Ignored Currencies (WallStreet paste filter)"))
        self.txt_ignored_ccy = LineEdit(ccy_card)
        self.txt_ignored_ccy.setText(", ".join(self.config.ignored_currencies))
        self.txt_ignored_ccy.setPlaceholderText("e.g. JPY, INR, CLP  (comma-separated, case-insensitive)")
        ccy_lay.addWidget(self.txt_ignored_ccy)
        hint = CaptionLabel("Rows where Rec Ccy matches any of these will be skipped on paste.", ccy_card)
        hint.setStyleSheet("color: #888;")
        ccy_lay.addWidget(hint)
        root.addWidget(ccy_card)

        # ── Archive path ──────────────────────────────────────────────
        arch_card = CardWidget(container)
        arch_lay = QVBoxLayout(arch_card)
        arch_lay.setContentsMargins(16, 12, 16, 12)
        arch_lay.addWidget(BodyLabel("Default Archive Path (fallback)"))
        arch_row = QHBoxLayout()
        self.txt_archive_path = LineEdit(arch_card)
        self.txt_archive_path.setText(self.config.archive_path)
        self.txt_archive_path.setPlaceholderText("Used when a counterparty has no archive path")
        self.txt_archive_path.textChanged.connect(self._update_resolved_label)
        arch_row.addWidget(self.txt_archive_path, 1)
        btn_browse = PushButton("Browse…", arch_card)
        btn_browse.clicked.connect(self._browse_archive)
        arch_row.addWidget(btn_browse)
        arch_lay.addLayout(arch_row)
        self.lbl_resolved = CaptionLabel("", arch_card)
        self.lbl_resolved.setStyleSheet("color: #888;")
        self.lbl_resolved.setWordWrap(True)
        arch_lay.addWidget(self.lbl_resolved)
        self._update_resolved_label()
        root.addWidget(arch_card)

        # ── Counterparties ────────────────────────────────────────────
        cp_card = CardWidget(container)
        cp_lay = QVBoxLayout(cp_card)
        cp_lay.setContentsMargins(16, 12, 16, 12)
        cp_lay.addWidget(BodyLabel("Counterparties"))
        self.lst_cp = ListWidget(cp_card)
        self.lst_cp.setMaximumHeight(180)
        self._refresh_cp_list()
        cp_lay.addWidget(self.lst_cp)
        btn_row = QHBoxLayout()
        btn_add    = PushButton("Add",    cp_card)
        btn_edit   = PushButton("Edit",   cp_card)
        btn_remove = PushButton("Remove", cp_card)
        btn_add.clicked.connect(self._add_cp)
        btn_edit.clicked.connect(self._edit_cp)
        btn_remove.clicked.connect(self._remove_cp)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        cp_lay.addLayout(btn_row)
        root.addWidget(cp_card)

        # ── Save button ───────────────────────────────────────────────
        self.btn_save = PrimaryPushButton("Save Settings", container)
        self.btn_save.setMinimumHeight(44)
        self.btn_save.clicked.connect(self._save)
        root.addWidget(self.btn_save)
        root.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _update_resolved_label(self):
        raw = self.txt_archive_path.text().strip()
        try:
            resolved = resolve_archive_path(raw) if raw else ""
        except Exception:
            resolved = ""
        self.lbl_resolved.setText(f"Resolved path: {resolved}" if resolved else "")

    def _browse_archive(self):
        if not self._check_auth():
            return
        path = QFileDialog.getExistingDirectory(self, "Select Archive Folder")
        if path:
            self.txt_archive_path.setText(_normalize_onedrive_path(path))

    def _refresh_cp_list(self):
        self.lst_cp.clear()
        for name in self.config.counterparty_names:
            self.lst_cp.addItem(name)
        if self.lst_cp.count() > 0:
            self.lst_cp.setCurrentRow(0)

    def _add_cp(self):
        if not self._check_auth():
            return
        dlg = CounterpartyDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.config.add_counterparty(data["name"], data["config"])
            self.config.save()
            self._refresh_cp_list()

    def _current_cp_name(self) -> str | None:
        row = self.lst_cp.currentRow()
        if row < 0:
            row = 0
        item = self.lst_cp.item(row)
        return item.text() if item else None

    def _edit_cp(self):
        if not self._check_auth():
            return
        name = self._current_cp_name()
        if not name:
            return
        cp = self.config.get_counterparty(name)
        dlg = CounterpartyDialog(self, name=name, config=cp)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.config.update_counterparty(data["name"], data["config"])
            self.config.save()
            self._refresh_cp_list()

    def _remove_cp(self):
        if not self._check_auth():
            return
        name = self._current_cp_name()
        if not name:
            return
        reply = QMessageBox.question(
            self, "Remove Counterparty",
            f"Remove '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.config.remove_counterparty(name)
            self.config.save()
            self._refresh_cp_list()

    def _save(self):
        if not self._check_auth():
            return
        raw_ccy = self.txt_ignored_ccy.text()
        self.config.ignored_currencies = [c.strip() for c in raw_ccy.split(",") if c.strip()]
        self.config.archive_path = self.txt_archive_path.text().strip()
        self.config.save()
        self.settings_saved.emit()


# ── Counterparty dialog (plain QDialog — no fluent needed) ──────────────────

class CounterpartyDialog(QDialog):
    _STANDARD_FIELDS = [
        "payment_id", "confirmation_number", "buy_currency",
        "buy_amount", "value_date", "status_code"
    ]

    def __init__(self, parent=None, name: str = "", config: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Counterparty Configuration")
        self.setMinimumWidth(620)
        self._init_ui(name, config or {})

    def _init_ui(self, name: str, config: dict):
        from PySide6.QtWidgets import (
            QLabel, QLineEdit as _LE, QTableWidgetItem, QTableWidget as _TW
        )
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.txt_name = _LE(name)
        form.addRow("Internal Name:", self.txt_name)

        self.txt_display_name = _LE(config.get("display_name", ""))
        self.txt_display_name.setPlaceholderText("e.g. BOA3PTY  (shown in UI and archive filenames)")
        form.addRow("Display Name:", self.txt_display_name)

        self.txt_bank_code = _LE(config.get("csv_bank_code", ""))
        self.txt_bank_code.setPlaceholderText("e.g. ALLCUKBOA, MGACUKBOA (comma-separated)")
        form.addRow("CSV Bank Code(s):", self.txt_bank_code)

        self.txt_ws_name = _LE(config.get("wallstreet_counterparty_name", ""))
        form.addRow("WallStreet Customer Name:", self.txt_ws_name)

        archive_row = QHBoxLayout()
        self.txt_archive_path = _LE(config.get("archive_path", ""))
        self.txt_archive_path.setPlaceholderText("leave blank to use default archive path")
        archive_row.addWidget(self.txt_archive_path)
        btn_archive = PushButton("Browse...", self)
        btn_archive.clicked.connect(self._browse_archive_path)
        archive_row.addWidget(btn_archive)
        form.addRow("Archive Path:", archive_row)

        self.cmb_date_format = ComboBox(self)
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d %b %Y"]
        self.cmb_date_format.addItems(formats)
        df = config.get("date_format", "%Y-%m-%d")
        if df in formats:
            self.cmb_date_format.setCurrentText(df)
        form.addRow("GPG Date Format:", self.cmb_date_format)

        self.txt_dt06 = _LE(config.get("dt06_code", "DT06"))
        form.addRow("DT06 Code:", self.txt_dt06)

        self.spn_lookback = QSpinBox(self)
        self.spn_lookback.setRange(1, 30)
        self.spn_lookback.setValue(config.get("lookback_days", 10))
        form.addRow("Lookback Days:", self.spn_lookback)

        self.txt_amount_tolerances = _LE(
            self._format_amount_tolerances(config.get("amount_tolerances", {}))
        )
        self.txt_amount_tolerances.setPlaceholderText("e.g. IQD=1, CLP=1, JPY=1")
        form.addRow("Amount Tolerances:", self.txt_amount_tolerances)

        self.txt_email_to = _LE(config.get("email_to", "paymentsrelease@convera.com"))
        form.addRow("Email To:", self.txt_email_to)

        self.txt_email_cc = _LE(config.get(
            "email_cc",
            "treasuryconfirms@convera.com; bankreconaccounting@convera.com; jaunado@convera.com"
        ))
        form.addRow("Email CC:", self.txt_email_cc)

        self.txt_email_subject = _LE(config.get(
            "email_subject",
            "Payment Breakdown - {counterparty} - {value_date}"
        ))
        form.addRow("Email Subject:", self.txt_email_subject)

        self.txt_email_opening = _LE(config.get("email_opening", ""))
        form.addRow("Email Opening:", self.txt_email_opening)

        self.chk_auto = QCheckBox("Auto-resolve DT06", self)
        self.chk_auto.setChecked(config.get("auto_resolve_dt06", False))
        form.addRow("", self.chk_auto)

        layout.addLayout(form)

        # CSV column mapping
        layout.addWidget(QLabel("CSV Column Mapping (standard field → CSV header):"))
        self.tbl_mapping = _TW(len(self._STANDARD_FIELDS), 2, self)
        self.tbl_mapping.setHorizontalHeaderLabels(["Standard Field", "CSV Column Name"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mapping.verticalHeader().setVisible(False)
        existing_map = config.get("csv_column_mapping", {})
        for i, field in enumerate(self._STANDARD_FIELDS):
            field_item = QTableWidgetItem(field)
            field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_mapping.setItem(i, 0, field_item)
            self.tbl_mapping.setItem(i, 1, QTableWidgetItem(existing_map.get(field, "")))
        layout.addWidget(self.tbl_mapping)

        # WallStreet column override
        layout.addWidget(QLabel("WallStreet Column Override (leave blank to use defaults):"))
        ws_fields = [
            "deal_type", "value_date", "counterparty", "pay_ccy", "pay_amount",
            "rec_ccy", "rec_amount", "rate", "trader", "wallstreet_ref", "external_ref"
        ]
        ws_defaults = {
            "deal_type": "Deal Type", "value_date": "Value Date",
            "counterparty": "Customer", "pay_ccy": "Pay Ccy",
            "pay_amount": "Pay Amount", "rec_ccy": "Rec Ccy",
            "rec_amount": "Rec Amount", "rate": "Rate",
            "trader": "Trader", "wallstreet_ref": "Deal #",
            "external_ref": "Ext Deal #"
        }
        existing_ws = config.get("wallstreet_column_mapping", {})
        self.tbl_ws_mapping = _TW(len(ws_fields), 3, self)
        self.tbl_ws_mapping.setHorizontalHeaderLabels(
            ["Field", "Default Column Name", "Override (if different)"]
        )
        self.tbl_ws_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_ws_mapping.verticalHeader().setVisible(False)
        for i, field in enumerate(ws_fields):
            fi = QTableWidgetItem(field)
            fi.setFlags(fi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            di = QTableWidgetItem(ws_defaults[field])
            di.setFlags(di.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_ws_mapping.setItem(i, 0, fi)
            self.tbl_ws_mapping.setItem(i, 1, di)
            self.tbl_ws_mapping.setItem(i, 2, QTableWidgetItem(existing_ws.get(field, "")))
        layout.addWidget(self.tbl_ws_mapping)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        from PySide6.QtWidgets import QTableWidgetItem
        csv_map = {}
        for i, field in enumerate(self._STANDARD_FIELDS):
            val = self.tbl_mapping.item(i, 1)
            if val and val.text().strip():
                csv_map[field] = val.text().strip()

        ws_map = {}
        for i in range(self.tbl_ws_mapping.rowCount()):
            field_item    = self.tbl_ws_mapping.item(i, 0)
            override_item = self.tbl_ws_mapping.item(i, 2)
            if field_item and override_item and override_item.text().strip():
                ws_map[field_item.text()] = override_item.text().strip()

        return {
            "name": self.txt_name.text().strip(),
            "config": {
                "display_name":                   self.txt_display_name.text().strip(),
                "csv_bank_code":                  self.txt_bank_code.text().strip(),
                "wallstreet_counterparty_name":   self.txt_ws_name.text().strip(),
                "archive_path":                   self.txt_archive_path.text().strip(),
                "csv_column_mapping":             csv_map,
                "date_format":                    self.cmb_date_format.currentText(),
                "dt06_code":                      self.txt_dt06.text().strip(),
                "lookback_days":                  self.spn_lookback.value(),
                "amount_tolerances":              self._parse_amount_tolerances(
                    self.txt_amount_tolerances.text()
                ),
                "email_to":                       self.txt_email_to.text().strip(),
                "email_cc":                       self.txt_email_cc.text().strip(),
                "email_subject":                  self.txt_email_subject.text().strip(),
                "email_opening":                  self.txt_email_opening.text().strip(),
                "auto_resolve_dt06":              self.chk_auto.isChecked(),
                "rules":                          ["dt06_date_change"],
                "wallstreet_column_mapping":      ws_map,
            }
        }

    def _format_amount_tolerances(self, tolerances: dict) -> str:
        return ", ".join(
            f"{str(ccy).upper()}={value}" for ccy, value in sorted((tolerances or {}).items())
        )

    def _parse_amount_tolerances(self, raw: str) -> dict:
        parsed = {}
        for part in raw.split(","):
            text = part.strip()
            if not text:
                continue
            if "=" not in text:
                continue
            ccy, value = text.split("=", 1)
            ccy = ccy.strip().upper()
            value = value.strip()
            if ccy and value:
                parsed[ccy] = value
        return parsed

    def _browse_archive_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Counterparty Archive Folder")
        if path:
            self.txt_archive_path.setText(_normalize_onedrive_path(path))


def _normalize_onedrive_path(path: str) -> str:
    onedrive = os.environ.get("OneDrive", "") or os.environ.get("OneDriveCommercial", "")
    if onedrive:
        norm_od = os.path.normpath(onedrive)
        norm_path = os.path.normpath(path)
        if norm_path.startswith(norm_od):
            return "%OneDrive%" + norm_path[len(norm_od):]
    return path
