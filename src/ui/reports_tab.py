import os
from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QMessageBox, QDateEdit
)
from PyQt5.QtCore import QDate

from src.archive.archive_manager import ArchiveManager
from src.export.report_generator import generate_payment_breakdown
from src.core.models import MatchStatus


class ReportsTab(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self._init_ui()

    def reload_config(self):
        self._populate_counterparties()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Generate Excel reports from archived data."))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Report Date:"))
        self.dt_report = QDateEdit()
        self.dt_report.setCalendarPopup(True)
        self.dt_report.setDate(QDate.currentDate())
        self.dt_report.setDisplayFormat("dd MMM yyyy")
        row1.addWidget(self.dt_report)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Counterparty:"))
        self.cmb_cp = QComboBox()
        self._populate_counterparties()
        row1.addWidget(self.cmb_cp)
        row1.addStretch()
        layout.addLayout(row1)

        self.btn_export = QPushButton("Export Payment Breakdown to Excel…")
        self.btn_export.setMinimumHeight(44)
        self.btn_export.setStyleSheet(
            "QPushButton { background-color: #4472C4; color: white; "
            "border-radius: 4px; padding: 6px 16px; } "
            "QPushButton:hover { background-color: #5583d5; }"
        )
        self.btn_export.clicked.connect(self._export)
        layout.addWidget(self.btn_export)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def _populate_counterparties(self):
        self.cmb_cp.clear()
        for name in self.config.counterparty_names:
            self.cmb_cp.addItem(name)

    def _export(self):
        cp_name = self.cmb_cp.currentText()
        if not cp_name:
            QMessageBox.warning(self, "No Counterparty", "Add a counterparty in Settings first.")
            return

        qd = self.dt_report.date()
        report_date = date(qd.year(), qd.month(), qd.day())

        archive_path = self.config.archive_path
        if not os.path.isabs(archive_path):
            archive_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", archive_path
            )

        try:
            am = ArchiveManager(archive_path)
            data = am.load_daily(report_date, cp_name)
            if not data:
                QMessageBox.warning(self, "No Archive",
                    f"No archive found for {report_date.isoformat()} / {cp_name}.")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"{report_date.isoformat()}_{cp_name}_breakdown.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not out_path:
            return

        # Re-load results from archive (simplified: read Results sheet)
        try:
            from openpyxl import load_workbook as _lw
            from decimal import Decimal
            from src.core.models import GPGPayment, MatchResult, MatchStatus as MS

            wb = _lw(data["file"], read_only=True)
            ws = wb["Results"]
            rows = list(ws.iter_rows(values_only=True))
            wb.close()

            results = []
            for row in rows[1:]:
                if not row or not row[0]:
                    continue
                status_val = row[0]
                conf = row[1] or ""
                gpg_ccy = row[2] or ""
                gpg_amt = Decimal(str(row[3])) if row[3] else Decimal("0")
                gpg_vd_str = row[4] or ""
                try:
                    from datetime import date as _date
                    gpg_vd = _date.fromisoformat(gpg_vd_str) if gpg_vd_str else report_date
                except ValueError:
                    gpg_vd = report_date

                gpg = GPGPayment(
                    payment_id=conf, confirmation_number=conf,
                    buy_currency=gpg_ccy, buy_amount=gpg_amt,
                    value_date=gpg_vd, status_code=None,
                    status_message=None, counterparty=cp_name, raw_row={}
                )
                try:
                    status = MS(status_val)
                except ValueError:
                    status = MS.MATCHED
                results.append(MatchResult(status=status, gpg_record=gpg, ws_record=None))

            generate_payment_breakdown(results, out_path, report_date)
            self.lbl_status.setText(f"Exported: {out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
