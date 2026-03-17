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

# ── Column layout ──────────────────────────────────────────────────────────
# Left = WallStreet  |  Centre = matching key  |  Right = GPG
#
#  0  Status
#  1  WS: Pay Amt (USD)
#  2  WS: Rec Ccy
#  3  WS: Rec Amt
#  4  WS: Rate
#  5  WS: Value Date
#  6  *** Conf # / Ext Deal # ***   ← matching key
#  7  GPG: Currency
#  8  GPG: Amount
#  9  GPG: Value Date
# 10  GPG: Status
# 11  GPG: Arrival Date
# 12  GPG: Client Account
# 13  Notes / Discrepancies

_HEADERS = [
    "Status",
    "USD Amount",        # WS pay
    "Ccy",              # WS rec ccy
    "Exotic Amount",    # WS rec amt
    "Rate",
    "WS Value Date",
    "Conf # / Ext Deal #",   # centre — matching key
    "Currency",         # GPG
    "GPG Amount",       # GPG
    "GPG Value Date",   # GPG
    "GPG Status",       # GPG
    "Arrival Date",     # GPG raw
    "Client Account",   # GPG raw
    "Notes",
]

# Column index of the matching key
_CONF_COL = 6

# Header background per section
_WS_HEADER_BG   = QColor("#1a2a3a")   # dark blue
_KEY_HEADER_BG  = QColor("#3a2a00")   # dark amber
_GPG_HEADER_BG  = QColor("#1a3a1a")   # dark green

# Row backgrounds
_STATUS_BG = {
    MatchStatus.MATCHED.value:               QColor("#152815"),
    MatchStatus.UNMATCHED_GPG.value:         QColor("#301010"),
    MatchStatus.UNMATCHED_WS.value:          QColor("#2a1800"),
    MatchStatus.FLAGGED_DT06.value:          QColor("#181828"),
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: QColor("#152015"),
    MatchStatus.AMOUNT_MISMATCH.value:       QColor("#2a1200"),
    MatchStatus.CURRENCY_MISMATCH.value:     QColor("#2a1200"),
}

_STATUS_LABEL = {
    MatchStatus.MATCHED.value:               "✓  Matched",
    MatchStatus.UNMATCHED_GPG.value:         "✗  Missing in WS",
    MatchStatus.UNMATCHED_WS.value:          "⚠  Extra in WS",
    MatchStatus.FLAGGED_DT06.value:          "⏳  DT06",
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: "↩  Resolved",
    MatchStatus.AMOUNT_MISMATCH.value:       "$  Amt Mismatch",
    MatchStatus.CURRENCY_MISMATCH.value:     "€  Ccy Mismatch",
}

_STATUS_FG = {
    MatchStatus.MATCHED.value:               QColor("#4caf50"),
    MatchStatus.UNMATCHED_GPG.value:         QColor("#ef5350"),
    MatchStatus.UNMATCHED_WS.value:          QColor("#ff9800"),
    MatchStatus.FLAGGED_DT06.value:          QColor("#9fa8da"),
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: QColor("#81c784"),
    MatchStatus.AMOUNT_MISMATCH.value:       QColor("#ff7043"),
    MatchStatus.CURRENCY_MISMATCH.value:     QColor("#ff7043"),
}

# WS columns (indices), centre col, GPG columns (indices)
_WS_COLS  = [1, 2, 3, 4, 5]
_GPG_COLS = [7, 8, 9, 10, 11, 12, 13]


class ReconcileTab(QWidget):
    save_to_archive_requested = pyqtSignal(date, str)

    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self._all_results = []
        self._counterparty = None
        self._init_ui()

    # ── UI construction ────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Summary bar
        summary_row = QHBoxLayout()
        self._summary_labels: dict[str, QLabel] = {}
        for sv, label in _STATUS_LABEL.items():
            count_lbl = QLabel("0")
            count_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
            count_lbl.setAlignment(Qt.AlignCenter)
            count_lbl.setMinimumWidth(26)
            fg = _STATUS_FG.get(sv, QColor("white"))
            count_lbl.setStyleSheet(
                f"QLabel {{ color: {fg.name()}; font-weight: bold; "
                "background: #252525; border-radius: 3px; padding: 1px 6px; }}"
            )
            self._summary_labels[sv] = count_lbl
            lbl = QLabel(label.split()[-1])   # short name
            lbl.setStyleSheet(f"color: {fg.name()};")
            summary_row.addWidget(lbl)
            summary_row.addWidget(count_lbl)
            summary_row.addSpacing(14)
        summary_row.addStretch()
        layout.addLayout(summary_row)

        # Filter / search
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Filter:"))
        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems([
            "All", "Matched", "Missing in WS", "Extra in WS",
            "DT06 Flagged", "Resolved", "Amount Mismatch", "Currency Mismatch",
        ])
        self.cmb_filter.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.cmb_filter)
        filter_bar.addSpacing(16)
        filter_bar.addWidget(QLabel("Search:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Conf# / currency / client account…")
        self.txt_search.textChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.txt_search, 1)
        layout.addLayout(filter_bar)

        # Section labels above table
        section_row = QHBoxLayout()
        section_row.addSpacing(4)
        ws_lbl = QLabel("◀  WallStreet")
        ws_lbl.setStyleSheet("color: #5b9bd5; font-weight: bold; font-size: 10px;")
        section_row.addWidget(ws_lbl)
        section_row.addStretch()
        key_lbl = QLabel("MATCHING KEY")
        key_lbl.setStyleSheet("color: #ffc107; font-weight: bold; font-size: 10px;")
        section_row.addWidget(key_lbl)
        section_row.addStretch()
        gpg_lbl = QLabel("GPG  ▶")
        gpg_lbl.setStyleSheet("color: #66bb6a; font-weight: bold; font-size: 10px;")
        section_row.addWidget(gpg_lbl)
        section_row.addSpacing(4)
        layout.addLayout(section_row)

        # Table
        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(True)
        self.tbl.setWordWrap(False)
        self.tbl.setColumnCount(len(_HEADERS))
        self.tbl.setHorizontalHeaderLabels(_HEADERS)
        self._style_header()
        layout.addWidget(self.tbl, 1)

        # Bottom bar
        bottom = QHBoxLayout()
        archive_group = QGroupBox("Save to Archive")
        ag = QHBoxLayout(archive_group)
        ag.addWidget(QLabel("Value Date:"))
        self.dt_archive = QDateEdit()
        self.dt_archive.setCalendarPopup(True)
        self.dt_archive.setDate(QDate.currentDate())
        self.dt_archive.setDisplayFormat("dd MMM yyyy")
        ag.addWidget(self.dt_archive)
        ag.addWidget(QLabel("As:"))
        self.txt_archive_cp = QLineEdit()
        self.txt_archive_cp.setPlaceholderText("BOA3PTY")
        self.txt_archive_cp.setMaximumWidth(110)
        ag.addWidget(self.txt_archive_cp)
        self.btn_save = QPushButton("Save")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_archive)
        self.btn_save.setStyleSheet(
            "QPushButton{background:#2e6e2e;color:white;border-radius:4px;padding:4px 10px}"
            "QPushButton:hover{background:#3d8f3d}"
            "QPushButton:disabled{background:#444;color:#777}"
        )
        ag.addWidget(self.btn_save)
        bottom.addWidget(archive_group)
        bottom.addStretch()
        self.btn_export = QPushButton("Export to Excel…")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_report)
        self.btn_export.setStyleSheet(
            "QPushButton{background:#4472C4;color:white;border-radius:4px;padding:6px 14px}"
            "QPushButton:hover{background:#5583d5}"
            "QPushButton:disabled{background:#444;color:#777}"
        )
        bottom.addWidget(self.btn_export)
        layout.addLayout(bottom)

    def _style_header(self):
        """Colour the header: WS=blue, Key=amber, GPG=green."""
        hh = self.tbl.horizontalHeader()
        for col in range(len(_HEADERS)):
            item = QTableWidgetItem(_HEADERS[col])
            item.setTextAlignment(Qt.AlignCenter)
            item.setFont(QFont("Segoe UI", 8, QFont.Bold))
            if col in _WS_COLS:
                item.setBackground(QBrush(_WS_HEADER_BG))
                item.setForeground(QBrush(QColor("#5b9bd5")))
            elif col == _CONF_COL:
                item.setBackground(QBrush(_KEY_HEADER_BG))
                item.setForeground(QBrush(QColor("#ffc107")))
            elif col in _GPG_COLS:
                item.setBackground(QBrush(_GPG_HEADER_BG))
                item.setForeground(QBrush(QColor("#66bb6a")))
            self.tbl.setHorizontalHeaderItem(col, item)

    # ── Data loading ───────────────────────────────────────────────

    def load_results(self, results, counterparty_name: str):
        self._all_results = results
        self._counterparty = counterparty_name
        self.btn_save.setEnabled(True)
        self.btn_export.setEnabled(True)

        # Auto-set archive date from most common GPG value date
        dates = [r.gpg_record.value_date for r in results if r.gpg_record]
        if dates:
            vd = max(set(dates), key=dates.count)
            self.dt_archive.setDate(QDate(vd.year, vd.month, vd.day))

        if not self.txt_archive_cp.text().strip():
            self.txt_archive_cp.setText(counterparty_name)

        self._update_summary(results)
        self._populate_table(results)

    def _update_summary(self, results):
        counts: dict[str, int] = {}
        for r in results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        for sv, lbl in self._summary_labels.items():
            lbl.setText(str(counts.get(sv, 0)))

    def _apply_filter(self):
        _filter_map = {
            "All": None,
            "Matched":           MatchStatus.MATCHED.value,
            "Missing in WS":     MatchStatus.UNMATCHED_GPG.value,
            "Extra in WS":       MatchStatus.UNMATCHED_WS.value,
            "DT06 Flagged":      MatchStatus.FLAGGED_DT06.value,
            "Resolved":          MatchStatus.RESOLVED_FROM_ARCHIVE.value,
            "Amount Mismatch":   MatchStatus.AMOUNT_MISMATCH.value,
            "Currency Mismatch": MatchStatus.CURRENCY_MISMATCH.value,
        }
        status_filter = _filter_map.get(self.cmb_filter.currentText())
        search = self.txt_search.text().lower()

        filtered = []
        for r in self._all_results:
            if status_filter and r.status.value != status_filter:
                continue
            if search:
                raw = r.gpg_record.raw_row if r.gpg_record else {}
                hay = " ".join([
                    r.gpg_record.confirmation_number if r.gpg_record else "",
                    r.gpg_record.buy_currency if r.gpg_record else "",
                    str(r.gpg_record.buy_amount) if r.gpg_record else "",
                    r.ws_record.external_ref if r.ws_record else "",
                    raw.get("client_account_number", ""),
                    raw.get("client_name", ""),
                ]).lower()
                if search not in hay:
                    continue
            filtered.append(r)
        self._populate_table(filtered)

    def _populate_table(self, results):
        self.tbl.setRowCount(len(results))

        for ri, r in enumerate(results):
            sv = r.status.value
            row_bg  = _STATUS_BG.get(sv, QColor("#252525"))
            key_bg  = QColor("#2a1e00") if sv == MatchStatus.MATCHED.value else QColor("#1e1a00")
            status_fg = _STATUS_FG.get(sv, QColor("white"))

            conf = (r.gpg_record.confirmation_number if r.gpg_record
                    else r.ws_record.external_ref if r.ws_record else "")

            raw = r.gpg_record.raw_row if r.gpg_record else {}
            arrival = raw.get("Arrival_date_in_UTC", raw.get("arrival_date", ""))
            arrival = arrival.split(" ")[0] if arrival else ""
            client  = raw.get("client_account_number", "")

            ws = r.ws_record
            gpg = r.gpg_record

            row_data = [
                # 0  Status
                (_STATUS_LABEL.get(sv, sv), row_bg, status_fg, True),
                # 1  WS USD Amount
                (str(ws.pay_amount) if ws else "",      row_bg, None, False),
                # 2  WS Rec Ccy
                (ws.rec_ccy if ws else "",              row_bg, None, False),
                # 3  WS Rec Amount
                (str(ws.rec_amount) if ws else "",      row_bg, None, False),
                # 4  Rate
                (str(ws.rate) if ws else "",            row_bg, None, False),
                # 5  WS Value Date
                (ws.value_date.strftime("%d %b %Y") if ws else "", row_bg, None, False),
                # 6  CONF # (centre key)
                (conf,                                  key_bg, QColor("#ffc107"), True),
                # 7  GPG Currency
                (gpg.buy_currency if gpg else "",       row_bg, None, False),
                # 8  GPG Amount
                (str(gpg.buy_amount) if gpg else "",    row_bg, None, False),
                # 9  GPG Value Date
                (gpg.value_date.strftime("%d %b %Y") if gpg else "", row_bg, None, False),
                # 10 GPG Status
                (gpg.status_code or ("OK" if gpg else ""), row_bg, None, False),
                # 11 Arrival Date
                (arrival,                               row_bg, None, False),
                # 12 Client Account
                (client,                                row_bg, None, False),
                # 13 Notes
                ("; ".join(r.discrepancies),            row_bg, None, False),
            ]

            for ci, (val, bg, fg, bold) in enumerate(row_data):
                item = QTableWidgetItem(val)
                item.setBackground(QBrush(bg))
                if fg:
                    item.setForeground(QBrush(fg))
                if bold:
                    item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.tbl.setItem(ri, ci, item)

        self.tbl.resizeColumnsToContents()

    # ── Actions ────────────────────────────────────────────────────

    def _save_archive(self):
        qd = self.dt_archive.date()
        d = date(qd.year(), qd.month(), qd.day())
        cp = self.txt_archive_cp.text().strip() or self._counterparty or "UNKNOWN"
        self.save_to_archive_requested.emit(d, cp)

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
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
