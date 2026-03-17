import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QFileDialog, QDialog, QDialogButtonBox,
    QFormLayout, QComboBox, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox
)
from PyQt5.QtCore import pyqtSignal


class SettingsTab(QWidget):
    settings_saved = pyqtSignal()

    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Archive path
        arch_group = QGroupBox("Archive Path (OneDrive folder)")
        arch_layout = QHBoxLayout(arch_group)
        self.txt_archive_path = QLineEdit(self.config.archive_path)
        arch_layout.addWidget(self.txt_archive_path, 1)
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_archive)
        arch_layout.addWidget(btn_browse)
        layout.addWidget(arch_group)

        # Counterparties
        cp_group = QGroupBox("Counterparties")
        cp_layout = QVBoxLayout(cp_group)

        self.lst_cp = QListWidget()
        self._refresh_cp_list()
        cp_layout.addWidget(self.lst_cp)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._add_cp)
        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._edit_cp)
        btn_remove = QPushButton("Remove")
        btn_remove.clicked.connect(self._remove_cp)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        cp_layout.addLayout(btn_row)
        layout.addWidget(cp_group)

        # Save
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setMinimumHeight(44)
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #2e6e2e; color: white; "
            "border-radius: 4px; padding: 6px 16px; } "
            "QPushButton:hover { background-color: #3d8f3d; }"
        )
        self.btn_save.clicked.connect(self._save)
        layout.addWidget(self.btn_save)
        layout.addStretch()

    def _browse_archive(self):
        path = QFileDialog.getExistingDirectory(self, "Select Archive Folder")
        if path:
            self.txt_archive_path.setText(path)

    def _refresh_cp_list(self):
        self.lst_cp.clear()
        for name in self.config.counterparty_names:
            self.lst_cp.addItem(name)

    def _add_cp(self):
        dlg = CounterpartyDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            self.config.add_counterparty(data["name"], data["config"])
            self._refresh_cp_list()

    def _edit_cp(self):
        item = self.lst_cp.currentItem()
        if not item:
            return
        name = item.text()
        cp = self.config.get_counterparty(name)
        dlg = CounterpartyDialog(self, name=name, config=cp)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            self.config.update_counterparty(data["name"], data["config"])
            self._refresh_cp_list()

    def _remove_cp(self):
        item = self.lst_cp.currentItem()
        if not item:
            return
        name = item.text()
        reply = QMessageBox.question(
            self, "Remove Counterparty",
            f"Remove '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.config.remove_counterparty(name)
            self._refresh_cp_list()

    def _save(self):
        self.config.archive_path = self.txt_archive_path.text().strip()
        self.config.save()
        self.settings_saved.emit()


class CounterpartyDialog(QDialog):
    _STANDARD_FIELDS = [
        "payment_id", "confirmation_number", "buy_currency",
        "buy_amount", "value_date", "status_code"
    ]

    def __init__(self, parent=None, name: str = "", config: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Counterparty Configuration")
        self.setMinimumWidth(600)
        self._init_ui(name, config or {})

    def _init_ui(self, name: str, config: dict):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.txt_name = QLineEdit(name)
        form.addRow("Internal Name:", self.txt_name)

        self.txt_display_name = QLineEdit(config.get("display_name", ""))
        self.txt_display_name.setPlaceholderText("e.g. BOA3PTY  (shown in UI and archive filenames)")
        form.addRow("Display Name:", self.txt_display_name)

        self.txt_bank_code = QLineEdit(config.get("csv_bank_code", ""))
        form.addRow("CSV Bank Code:", self.txt_bank_code)

        self.txt_ws_name = QLineEdit(config.get("wallstreet_counterparty_name", ""))
        form.addRow("WallStreet Customer Name:", self.txt_ws_name)

        self.cmb_date_format = QComboBox()
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d %b %Y"]
        self.cmb_date_format.addItems(formats)
        df = config.get("date_format", "%Y-%m-%d")
        if df in formats:
            self.cmb_date_format.setCurrentText(df)
        form.addRow("GPG Date Format:", self.cmb_date_format)

        self.txt_dt06 = QLineEdit(config.get("dt06_code", "DT06"))
        form.addRow("DT06 Code:", self.txt_dt06)

        self.spn_lookback = QSpinBox()
        self.spn_lookback.setRange(1, 30)
        self.spn_lookback.setValue(config.get("lookback_days", 5))
        form.addRow("Lookback Days:", self.spn_lookback)

        self.chk_auto = QCheckBox("Auto-resolve DT06")
        self.chk_auto.setChecked(config.get("auto_resolve_dt06", False))
        form.addRow("", self.chk_auto)

        layout.addLayout(form)

        # CSV column mapping
        layout.addWidget(QLabel("CSV Column Mapping (standard field → CSV header):"))
        self.tbl_mapping = QTableWidget(len(self._STANDARD_FIELDS), 2)
        self.tbl_mapping.setHorizontalHeaderLabels(["Standard Field", "CSV Column Name"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mapping.verticalHeader().setVisible(False)
        existing_map = config.get("csv_column_mapping", {})
        for i, field in enumerate(self._STANDARD_FIELDS):
            self.tbl_mapping.setItem(i, 0, QTableWidgetItem(field))
            self.tbl_mapping.item(i, 0).setFlags(
                self.tbl_mapping.item(i, 0).flags() & ~0x2  # read-only
            )
            self.tbl_mapping.setItem(i, 1, QTableWidgetItem(existing_map.get(field, "")))
        layout.addWidget(self.tbl_mapping)

        # WallStreet column mapping override
        layout.addWidget(QLabel(
            "WallStreet Column Override (leave blank to use defaults):"
        ))
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
        self.tbl_ws_mapping = QTableWidget(len(ws_fields), 3)
        self.tbl_ws_mapping.setHorizontalHeaderLabels(
            ["Field", "Default Column Name", "Override (if different)"]
        )
        self.tbl_ws_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_ws_mapping.verticalHeader().setVisible(False)
        for i, field in enumerate(ws_fields):
            self.tbl_ws_mapping.setItem(i, 0, QTableWidgetItem(field))
            self.tbl_ws_mapping.setItem(i, 1, QTableWidgetItem(ws_defaults[field]))
            self.tbl_ws_mapping.setItem(i, 2, QTableWidgetItem(existing_ws.get(field, "")))
        layout.addWidget(self.tbl_ws_mapping)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        csv_map = {}
        for i, field in enumerate(self._STANDARD_FIELDS):
            val = self.tbl_mapping.item(i, 1)
            if val and val.text().strip():
                csv_map[field] = val.text().strip()

        ws_map = {}
        for i in range(self.tbl_ws_mapping.rowCount()):
            field_item = self.tbl_ws_mapping.item(i, 0)
            override_item = self.tbl_ws_mapping.item(i, 2)
            if field_item and override_item and override_item.text().strip():
                ws_map[field_item.text()] = override_item.text().strip()

        return {
            "name": self.txt_name.text().strip(),
            "config": {
                "display_name": self.txt_display_name.text().strip(),
                "csv_bank_code": self.txt_bank_code.text().strip(),
                "wallstreet_counterparty_name": self.txt_ws_name.text().strip(),
                "csv_column_mapping": csv_map,
                "date_format": self.cmb_date_format.currentText(),
                "dt06_code": self.txt_dt06.text().strip(),
                "lookback_days": self.spn_lookback.value(),
                "auto_resolve_dt06": self.chk_auto.isChecked(),
                "rules": ["dt06_date_change"],
                "wallstreet_column_mapping": ws_map,
            }
        }
