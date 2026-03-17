from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QMessageBox, QDateEdit
)
from PyQt5.QtCore import QDate

from src.archive.archive_manager import ArchiveManager
from src.export.report_generator import generate_payment_breakdown
from src.core.models import MatchStatus
from src.core.app_dir import resolve_archive_path


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
            display = self.config.get_display_name(name)
            self.cmb_cp.addItem(display)

    def _export(self):
        cp_name = self.cmb_cp.currentText()
        if not cp_name:
            QMessageBox.warning(self, "No Counterparty", "Add a counterparty in Settings first.")
            return

        qd = self.dt_report.date()
        report_date = date(qd.year(), qd.month(), qd.day())

        archive_path = resolve_archive_path(self.config.archive_path)
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
            from datetime import date as _date
            from src.core.models import GPGPayment, WSEntry, MatchResult, MatchStatus as MS

            wb = _lw(data["file"], read_only=True)
            ws = wb["Results"]
            rows = list(ws.iter_rows(values_only=True))
            wb.close()

            def _dec(v) -> Decimal:
                try:
                    return Decimal(str(v).replace(",", "")) if v else Decimal("0")
                except Exception:
                    return Decimal("0")

            def _dt(v) -> _date:
                try:
                    return _date.fromisoformat(str(v)) if v else report_date
                except Exception:
                    return report_date

            results = []
            for row in rows[1:]:
                if not row or not row[0]:
                    continue
                # Archive columns (0-indexed):
                # 0:Status 1:Conf# 2:GPG_Ccy 3:GPG_Amt 4:GPG_VD 5:GPG_StatusCode
                # 6:WS_RecCcy 7:WS_RecAmt 8:WS_VD 9:WS_Ref 10:WS_PayCcy 11:WS_PayAmt 12:WS_Rate
                status_val = row[0]
                conf       = str(row[1] or "")
                gpg_ccy    = str(row[2] or "")
                gpg_amt    = _dec(row[3])
                gpg_vd     = _dt(row[4])

                ws_rec_ccy = str(row[6] or "") if len(row) > 6 else ""
                ws_rec_amt = _dec(row[7])       if len(row) > 7 else Decimal("0")
                ws_vd      = _dt(row[8])        if len(row) > 8 else report_date
                ws_ref     = str(row[9] or "")  if len(row) > 9 else ""
                ws_pay_ccy = str(row[10] or "") if len(row) > 10 else ""
                ws_pay_amt = _dec(row[11])       if len(row) > 11 else Decimal("0")
                ws_rate    = _dec(row[12])       if len(row) > 12 else Decimal("0")

                gpg = GPGPayment(
                    payment_id=conf, confirmation_number=conf,
                    buy_currency=gpg_ccy, buy_amount=gpg_amt,
                    value_date=gpg_vd, status_code=None,
                    status_message=None, counterparty=cp_name, raw_row={}
                )
                ws_entry = WSEntry(
                    value_date=ws_vd, counterparty=cp_name,
                    pay_ccy=ws_pay_ccy, pay_amount=ws_pay_amt,
                    rec_ccy=ws_rec_ccy, rec_amount=ws_rec_amt,
                    rate=ws_rate, trader="",
                    wallstreet_ref=ws_ref, external_ref=conf,
                ) if ws_ref or ws_rec_ccy else None

                try:
                    status = MS(status_val)
                except ValueError:
                    status = MS.MATCHED
                results.append(MatchResult(status=status, gpg_record=gpg, ws_record=ws_entry))

            generate_payment_breakdown(results, out_path, report_date)
            self.lbl_status.setText(f"Exported: {out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
