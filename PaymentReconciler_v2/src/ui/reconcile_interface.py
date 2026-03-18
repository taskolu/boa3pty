from __future__ import annotations
from datetime import date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView,
    QAbstractItemView, QFileDialog, QMessageBox, QDateEdit,
    QInputDialog, QLineEdit, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QFont, QBrush

from qfluentwidgets import (
    PushButton, PrimaryPushButton, SubtitleLabel, BodyLabel,
    TableWidget, ComboBox, LineEdit, CardWidget, RoundMenu, Action
)

from src.core.models import MatchStatus
from src.export.report_generator import generate_payment_breakdown

# ── Column layout ───────────────────────────────────────────────────────────
_HEADERS = [
    "Status",
    "Value Date",       # WS value_date
    "Pay Currency",     # WS pay_ccy
    "Pay Amount",       # WS pay_amount
    "Rate",
    "Buy Ccy",          # WS rec_ccy
    "Buy Amount",       # WS rec_amount
    "WS Deal #",        # WS wallstreet_ref
    "Conf # / Ext Deal #",   # centre — matching key
    "GPG Status",
    "GPG Value Date",
    "GPG Amount",
    "Currency",
    "Client Account",
    "Arrival Date",
    "Notes",
]

_CONF_COL = 8
_WS_COLS  = [1, 2, 3, 4, 5, 6, 7]
_GPG_COLS = [9, 10, 11, 12, 13, 14, 15]

_WS_HEADER_BG   = QColor("#1a2a3a")
_KEY_HEADER_BG  = QColor("#3a2a00")
_GPG_HEADER_BG  = QColor("#1a3a1a")

_STATUS_BG = {
    MatchStatus.MATCHED.value:               QColor("#152815"),
    MatchStatus.UNMATCHED_GPG.value:         QColor("#301010"),
    MatchStatus.UNMATCHED_WS.value:          QColor("#2a1800"),
    MatchStatus.FLAGGED_DT06.value:          QColor("#181828"),
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: QColor("#152015"),
    MatchStatus.AMOUNT_MISMATCH.value:       QColor("#2a1200"),
    MatchStatus.CURRENCY_MISMATCH.value:     QColor("#2a1200"),
    MatchStatus.VALUE_DATE_MISMATCH.value:   QColor("#1a1a2e"),
}
_STATUS_LABEL = {
    MatchStatus.MATCHED.value:               "✓  Matched",
    MatchStatus.UNMATCHED_GPG.value:         "✗  Missing in WS",
    MatchStatus.UNMATCHED_WS.value:          "⚠  Extra in WS",
    MatchStatus.FLAGGED_DT06.value:          "⏳  DT06",
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: "↩  Resolved",
    MatchStatus.AMOUNT_MISMATCH.value:       "$  Amt Mismatch",
    MatchStatus.CURRENCY_MISMATCH.value:     "€  Ccy Mismatch",
    MatchStatus.VALUE_DATE_MISMATCH.value:   "📅  Date Mismatch",
}
_STATUS_FG = {
    MatchStatus.MATCHED.value:               QColor("#4caf50"),
    MatchStatus.UNMATCHED_GPG.value:         QColor("#ef5350"),
    MatchStatus.UNMATCHED_WS.value:          QColor("#ff9800"),
    MatchStatus.FLAGGED_DT06.value:          QColor("#9fa8da"),
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: QColor("#81c784"),
    MatchStatus.AMOUNT_MISMATCH.value:       QColor("#ff7043"),
    MatchStatus.CURRENCY_MISMATCH.value:     QColor("#ff7043"),
    MatchStatus.VALUE_DATE_MISMATCH.value:   QColor("#ce93d8"),
}

_FILTER_OPTIONS = [
    "All", "Matched", "Missing in WS", "Extra in WS",
    "DT06 Flagged", "Resolved", "Amount Mismatch", "Currency Mismatch", "Date Mismatch",
]
_FILTER_MAP = {
    "All": None,
    "Matched":           MatchStatus.MATCHED.value,
    "Missing in WS":     MatchStatus.UNMATCHED_GPG.value,
    "Extra in WS":       MatchStatus.UNMATCHED_WS.value,
    "DT06 Flagged":      MatchStatus.FLAGGED_DT06.value,
    "Resolved":          MatchStatus.RESOLVED_FROM_ARCHIVE.value,
    "Amount Mismatch":   MatchStatus.AMOUNT_MISMATCH.value,
    "Currency Mismatch": MatchStatus.CURRENCY_MISMATCH.value,
    "Date Mismatch":     MatchStatus.VALUE_DATE_MISMATCH.value,
}


class ReconcileInterface(QWidget):
    save_to_archive_requested = Signal(date, str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("reconcileInterface")
        self.config = config_manager
        self._all_results = []
        self._counterparty = None
        self._accepted_confs: set[str] = set()
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        root.addWidget(SubtitleLabel("Reconcile"))

        # ── Summary bar ───────────────────────────────────────────────
        self._summary_labels: dict[str, BodyLabel] = {}
        summary_card = CardWidget(self)
        summary_lay = QHBoxLayout(summary_card)
        summary_lay.setContentsMargins(12, 8, 12, 8)
        summary_lay.setSpacing(0)
        for sv, label in _STATUS_LABEL.items():
            fg = _STATUS_FG.get(sv, QColor("white"))
            short = label.split()[-1]
            name_lbl = BodyLabel(short + " ")
            name_lbl.setStyleSheet(f"color: {fg.name()};")
            count_lbl = BodyLabel("0")
            count_lbl.setStyleSheet(
                f"color: {fg.name()}; font-weight: bold; "
                f"background: #252525; border-radius: 3px; padding: 1px 6px;"
            )
            self._summary_labels[sv] = count_lbl
            summary_lay.addWidget(name_lbl)
            summary_lay.addWidget(count_lbl)
            summary_lay.addSpacing(16)
        summary_lay.addStretch()
        root.addWidget(summary_card)

        # ── Filter bar ────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(BodyLabel("Filter:"))
        self.cmb_filter = ComboBox(self)
        self.cmb_filter.addItems(_FILTER_OPTIONS)
        self.cmb_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self.cmb_filter)
        filter_row.addSpacing(16)
        filter_row.addWidget(BodyLabel("Search:"))
        self.txt_search = LineEdit(self)
        self.txt_search.setPlaceholderText("Conf# / currency / client account…")
        self.txt_search.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.txt_search, 1)
        root.addLayout(filter_row)

        # ── Section labels ────────────────────────────────────────────
        section_row = QHBoxLayout()
        ws_lbl = BodyLabel("◀  WallStreet")
        ws_lbl.setStyleSheet("color: #5b9bd5; font-weight: bold; font-size: 10px;")
        section_row.addWidget(ws_lbl)
        section_row.addStretch()
        key_lbl = BodyLabel("MATCHING KEY")
        key_lbl.setStyleSheet("color: #ffc107; font-weight: bold; font-size: 10px;")
        section_row.addWidget(key_lbl)
        section_row.addStretch()
        gpg_lbl = BodyLabel("GPG  ▶")
        gpg_lbl.setStyleSheet("color: #66bb6a; font-weight: bold; font-size: 10px;")
        section_row.addWidget(gpg_lbl)
        root.addLayout(section_row)

        # ── Table ─────────────────────────────────────────────────────
        self.tbl = TableWidget(self)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._show_context_menu)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(True)
        self.tbl.setWordWrap(False)
        self.tbl.setColumnCount(len(_HEADERS))
        self.tbl.setHorizontalHeaderLabels(_HEADERS)
        self._style_header()
        root.addWidget(self.tbl, 1)

        # ── Bottom bar ────────────────────────────────────────────────
        bottom_card = CardWidget(self)
        bottom_lay = QHBoxLayout(bottom_card)
        bottom_lay.setContentsMargins(12, 8, 12, 8)

        bottom_lay.addWidget(BodyLabel("Value Date:"))
        self.dt_archive = QDateEdit(self)
        self.dt_archive.setCalendarPopup(True)
        self.dt_archive.setDate(QDate.currentDate())
        self.dt_archive.setDisplayFormat("dd MMM yyyy")
        bottom_lay.addWidget(self.dt_archive)

        bottom_lay.addSpacing(12)
        bottom_lay.addWidget(BodyLabel("As:"))
        self.txt_archive_cp = LineEdit(self)
        self.txt_archive_cp.setPlaceholderText("counterparty name")
        self.txt_archive_cp.setMaximumWidth(150)
        bottom_lay.addWidget(self.txt_archive_cp)

        self.btn_save = PushButton("Save to Archive", self)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_archive)
        bottom_lay.addWidget(self.btn_save)

        bottom_lay.addStretch()

        self.btn_export = PushButton("Export to Excel…", self)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_report)
        bottom_lay.addWidget(self.btn_export)

        root.addWidget(bottom_card)

    def _style_header(self):
        from PySide6.QtWidgets import QTableWidgetItem
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
        def _sort_key(r):
            is_matched = 0 if r.status == MatchStatus.MATCHED else 1
            ccy = r.ws_record.rec_ccy if r.ws_record else ""
            amt = r.ws_record.rec_amount if r.ws_record else 0
            return (is_matched, ccy, amt)

        self._all_results = sorted(results, key=_sort_key)
        self._counterparty = counterparty_name
        self._accepted_confs = set()
        self.btn_save.setEnabled(True)
        self.btn_export.setEnabled(True)

        dates = [r.gpg_record.value_date for r in results if r.gpg_record]
        if dates:
            vd = max(set(dates), key=dates.count)
            self.dt_archive.setDate(QDate(vd.year, vd.month, vd.day))

        if not self.txt_archive_cp.text().strip():
            self.txt_archive_cp.setText(counterparty_name)

        self._update_summary(self._all_results)
        self._populate_table(self._all_results)

    def _update_summary(self, results):
        counts: dict[str, int] = {}
        for r in results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        for sv, lbl in self._summary_labels.items():
            lbl.setText(str(counts.get(sv, 0)))

    def _apply_filter(self):
        status_filter = _FILTER_MAP.get(self.cmb_filter.currentText())
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
        from PySide6.QtWidgets import QTableWidgetItem
        self.tbl.setRowCount(len(results))

        for ri, r in enumerate(results):
            sv = r.status.value
            conf_key = (r.gpg_record.confirmation_number if r.gpg_record
                        else r.ws_record.external_ref if r.ws_record else "")
            is_accepted = conf_key in self._accepted_confs

            if is_accepted:
                row_bg    = QColor("#0a2020")
                key_bg    = QColor("#0a2a1a")
                status_fg = QColor("#4dd0e1")
            else:
                row_bg    = _STATUS_BG.get(sv, QColor("#252525"))
                key_bg    = QColor("#2a1e00") if sv == MatchStatus.MATCHED.value else QColor("#1e1a00")
                status_fg = _STATUS_FG.get(sv, QColor("white"))

            conf = (r.gpg_record.confirmation_number if r.gpg_record
                    else r.ws_record.external_ref if r.ws_record else "")
            raw = r.gpg_record.raw_row if r.gpg_record else {}
            arrival = raw.get("Arrival_date_in_UTC", raw.get("arrival_date", ""))
            arrival = arrival.split(" ")[0] if arrival else ""
            client  = raw.get("client_account_number", "")

            ws  = r.ws_record
            gpg = r.gpg_record
            status_display = "✓  Accepted" if is_accepted else _STATUS_LABEL.get(sv, sv)

            row_data = [
                (status_display,                                     row_bg, status_fg, True),
                (ws.value_date.strftime("%d %b %Y") if ws else "",  row_bg, None,      False),
                (ws.pay_ccy if ws else "",                           row_bg, None,      False),
                (str(ws.pay_amount) if ws else "",                   row_bg, None,      False),
                (str(ws.rate) if ws else "",                         row_bg, None,      False),
                (ws.rec_ccy if ws else "",                           row_bg, None,      False),
                (str(ws.rec_amount) if ws else "",                   row_bg, None,      False),
                (ws.wallstreet_ref if ws else "",                    row_bg, None,      False),
                (conf,  key_bg,
                 QColor("#4caf50") if sv == MatchStatus.MATCHED.value else QColor("#ffc107"), True),
                (gpg.status_code if gpg else "",                     row_bg, None,      False),
                (gpg.value_date.strftime("%d %b %Y") if gpg else "", row_bg, None,      False),
                (str(gpg.buy_amount) if gpg else "",                 row_bg, None,      False),
                (gpg.buy_currency if gpg else "",                    row_bg, None,      False),
                (client,                                             row_bg, None,      False),
                (arrival,                                            row_bg, None,      False),
                ("; ".join(r.discrepancies),                         row_bg, None,      False),
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

    # ── Context menu ───────────────────────────────────────────────

    _ACCEPTABLE_STATUSES = {
        MatchStatus.AMOUNT_MISMATCH.value,
        MatchStatus.CURRENCY_MISMATCH.value,
        MatchStatus.VALUE_DATE_MISMATCH.value,
        MatchStatus.UNMATCHED_GPG.value,
    }

    def _show_context_menu(self, pos):
        row = self.tbl.rowAt(pos.y())
        if row < 0:
            return
        conf_item = self.tbl.item(row, _CONF_COL)
        if not conf_item:
            return
        conf = conf_item.text()

        result = None
        for r in self._all_results:
            key = (r.gpg_record.confirmation_number if r.gpg_record
                   else r.ws_record.external_ref if r.ws_record else "")
            if key == conf:
                result = r
                break
        if not result:
            return

        already_accepted = conf in self._accepted_confs
        if result.status.value not in self._ACCEPTABLE_STATUSES and not already_accepted:
            return

        menu = RoundMenu(parent=self)
        label = "✎  Edit Note…" if already_accepted else "✓  Accept / Add Note…"
        act = Action(label)
        menu.addAction(act)

        chosen = menu.exec(self.tbl.viewport().mapToGlobal(pos))
        if chosen == act:
            existing_note = ""
            for d in result.discrepancies:
                if d.startswith("✓ ACCEPTED"):
                    existing_note = d.split(": ", 1)[-1] if ": " in d else ""
                    break
            note, ok = QInputDialog.getText(
                self, "Accept / Add Note",
                "Reason / note (leave blank if none):",
                QLineEdit.Normal, existing_note
            )
            if ok:
                result.discrepancies = [
                    d for d in result.discrepancies if not d.startswith("✓ ACCEPTED")
                ]
                prefix = f"✓ ACCEPTED: {note}" if note.strip() else "✓ ACCEPTED"
                result.discrepancies.insert(0, prefix)
                self._accepted_confs.add(conf)
                self._apply_filter()

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
