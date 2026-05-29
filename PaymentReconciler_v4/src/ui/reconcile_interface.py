from __future__ import annotations
import os
import re
import tempfile
from datetime import date
from decimal import Decimal

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
from src.export.report_generator import generate_payment_breakdown, format_net_figures_html
from src.mail.outlook_draft import create_outlook_draft


def _fmt_rate(v) -> str:
    """Strip trailing zeros from a rate value."""
    try:
        from decimal import Decimal
        return format(Decimal(str(v)).normalize(), 'f')
    except Exception:
        return str(v) if v else ""


def _fmt_amt(v) -> str:
    """Format a number as 1,234,567.89"""
    try:
        return f"{float(str(v).replace(',', '')):,.2f}" if v else ""
    except Exception:
        return str(v) if v else ""

# ── Column layout ───────────────────────────────────────────────────────────
_HEADERS = [
    "Status",
    "Value Date",       # WS value_date
    "Pay Ccy",          # WS pay_ccy
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
    MatchStatus.MATCHED.value:               "Matched",
    MatchStatus.UNMATCHED_GPG.value:         "Missing in WS",
    MatchStatus.UNMATCHED_WS.value:          "Extra in WS",
    MatchStatus.FLAGGED_DT06.value:          "DT06",
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: "Resolved from Archive",
    MatchStatus.AMOUNT_MISMATCH.value:       "Amt Mismatch",
    MatchStatus.CURRENCY_MISMATCH.value:     "Ccy Mismatch",
    MatchStatus.VALUE_DATE_MISMATCH.value:   "Date Mismatch",
}
# Short labels shown in the summary bar (must all be unique)
_STATUS_SHORT = {
    MatchStatus.MATCHED.value:               "Matched",
    MatchStatus.UNMATCHED_GPG.value:         "Missing",
    MatchStatus.UNMATCHED_WS.value:          "Extra",
    MatchStatus.FLAGGED_DT06.value:          "DT06",
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: "Resolved",
    MatchStatus.AMOUNT_MISMATCH.value:       "Amt",
    MatchStatus.CURRENCY_MISMATCH.value:     "Ccy",
    MatchStatus.VALUE_DATE_MISMATCH.value:   "Date",
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

_STATUS_PRIORITY = {
    MatchStatus.AMOUNT_MISMATCH.value:       0,
    MatchStatus.CURRENCY_MISMATCH.value:     0,
    MatchStatus.VALUE_DATE_MISMATCH.value:   0,
    MatchStatus.UNMATCHED_GPG.value:         1,
    MatchStatus.UNMATCHED_WS.value:          2,
    MatchStatus.FLAGGED_DT06.value:          3,
    MatchStatus.RESOLVED_FROM_ARCHIVE.value: 4,
    MatchStatus.MATCHED.value:               5,
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
        self._declined_suggestions: set[tuple[str, str]] = set()
        self._amount_tolerances = {}
        self._email_settings = {}
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
            short = _STATUS_SHORT[sv]
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

        action_row = QHBoxLayout()
        self.lbl_suggestion_info = BodyLabel("")
        self.lbl_suggestion_info.setStyleSheet("color: #ffd54f; font-weight: bold;")
        action_row.addWidget(self.lbl_suggestion_info)
        action_row.addStretch()

        self.btn_accept = PushButton("Accept Note", self)
        self.btn_accept.setEnabled(False)
        self.btn_accept.clicked.connect(self._accept_selected)
        action_row.addWidget(self.btn_accept)

        self.btn_accept_match = PushButton("Accept Match", self)
        self.btn_accept_match.setEnabled(False)
        self.btn_accept_match.clicked.connect(self._accept_suggested_match)
        action_row.addWidget(self.btn_accept_match)

        self.btn_decline_match = PushButton("Decline Match", self)
        self.btn_decline_match.setEnabled(False)
        self.btn_decline_match.clicked.connect(self._decline_suggestion)
        action_row.addWidget(self.btn_decline_match)
        root.addLayout(action_row)

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
        self.tbl.setFont(QFont("Segoe UI", 8))
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._show_context_menu)
        self.tbl.itemSelectionChanged.connect(self._update_action_buttons)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
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
        bottom_lay.addWidget(BodyLabel("Archive name:"))
        self.txt_archive_cp = LineEdit(self)
        self.txt_archive_cp.setPlaceholderText("counterparty archive label")
        self.txt_archive_cp.setToolTip("Used in archive filenames and later lookups. Keep it consistent.")
        self.txt_archive_cp.setMaximumWidth(220)
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

        self.btn_draft_email = PushButton("Draft Email", self)
        self.btn_draft_email.setEnabled(False)
        self.btn_draft_email.clicked.connect(self._draft_email)
        bottom_lay.addWidget(self.btn_draft_email)

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

    def load_results(
        self,
        results,
        counterparty_name: str,
        amount_tolerances: dict | None = None,
        email_settings: dict | None = None,
    ):
        def _sort_key(r):
            priority = _STATUS_PRIORITY.get(r.status.value, 99)
            ccy = r.ws_record.rec_ccy if r.ws_record else ""
            amt = r.ws_record.rec_amount if r.ws_record else 0
            return (priority, ccy, amt)

        self._all_results = sorted(results, key=_sort_key)
        self._counterparty = counterparty_name
        self._amount_tolerances = self._normalize_amount_tolerances(amount_tolerances)
        self._email_settings = dict(email_settings or {})
        self._accepted_confs = set()
        self._declined_suggestions = set()
        self.btn_save.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_draft_email.setEnabled(True)
        self._refresh_match_suggestions()

        dates = [r.gpg_record.value_date for r in results if r.gpg_record]
        if dates:
            vd = max(set(dates), key=dates.count)
            self.dt_archive.setDate(QDate(vd.year, vd.month, vd.day))

        if not self.txt_archive_cp.text().strip():
            self.txt_archive_cp.setText(counterparty_name)

        self._update_summary(self._all_results)
        self._populate_table(self._all_results)
        self._update_action_buttons()

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
                    self._ws_display_key(r.ws_record) if r.ws_record else "",
                    raw.get("client_account_number", ""),
                    raw.get("client_name", ""),
                ]).lower()
                if search not in hay:
                    continue
            filtered.append(r)
        self._populate_table(filtered)
        self._update_action_buttons()

    def _populate_table(self, results):
        from PySide6.QtWidgets import QTableWidgetItem
        self.tbl.setRowCount(len(results))

        for ri, r in enumerate(results):
            sv = r.status.value
            conf_key = (r.gpg_record.confirmation_number if r.gpg_record
                        else self._ws_display_key(r.ws_record) if r.ws_record else "")
            is_accepted = conf_key in self._accepted_confs
            suggested_partner = self._suggested_partner_key(r)
            is_suggested = suggested_partner is not None

            if is_accepted:
                row_bg    = QColor("#0a2020")
                key_bg    = QColor("#0a2a1a")
                status_fg = QColor("#4dd0e1")
            elif is_suggested:
                row_bg    = QColor("#3a2d00")
                key_bg    = QColor("#5a4300")
                status_fg = QColor("#ffd54f")
            else:
                row_bg    = _STATUS_BG.get(sv, QColor("#252525"))
                key_bg    = QColor("#2a1e00") if sv == MatchStatus.MATCHED.value else QColor("#1e1a00")
                status_fg = _STATUS_FG.get(sv, QColor("white"))

            conf = (r.gpg_record.confirmation_number if r.gpg_record
                    else self._ws_display_key(r.ws_record) if r.ws_record else "")
            raw = r.gpg_record.raw_row if r.gpg_record else {}
            arrival = raw.get("Arrival_date_in_UTC", raw.get("arrival_date", ""))
            arrival = arrival.split(" ")[0] if arrival else ""
            client  = raw.get("client_account_number", "")

            ws  = r.ws_record
            gpg = r.gpg_record
            if is_accepted:
                status_display = "✓  Accepted"
            elif is_suggested:
                status_display = "Possible Match"
            else:
                status_display = _STATUS_LABEL.get(sv, sv)

            row_data = [
                (status_display,                                     row_bg, status_fg, True),
                (ws.value_date.strftime("%d %b %Y") if ws else "",  row_bg, None,      False),
                (ws.pay_ccy if ws else "",                           row_bg, None,      False),
                (_fmt_amt(ws.pay_amount) if ws else "",              row_bg, None,      False),
                (_fmt_rate(ws.rate) if ws else "",                   row_bg, None,      False),
                (ws.rec_ccy if ws else "",                           row_bg, None,      False),
                (_fmt_amt(ws.rec_amount) if ws else "",              row_bg, None,      False),
                (ws.wallstreet_ref if ws else "",                    row_bg, None,      False),
                (conf,  key_bg,
                 QColor("#4caf50") if sv == MatchStatus.MATCHED.value else QColor("#ffc107"), True),
                (gpg.status_code if gpg else "",                     row_bg, None,      False),
                (gpg.value_date.strftime("%d %b %Y") if gpg else "", row_bg, None,      False),
                (_fmt_amt(gpg.buy_amount) if gpg else "",            row_bg, None,      False),
                (gpg.buy_currency if gpg else "",                    row_bg, None,      False),
                (client,                                             row_bg, None,      False),
                (arrival,                                            row_bg, None,      False),
                ("; ".join(r.discrepancies),                         row_bg, None,      False),
            ]

            for ci, (val, bg, fg, bold) in enumerate(row_data):
                item = QTableWidgetItem(val)
                item.setBackground(QBrush(bg))
                if is_suggested and not fg:
                    fg = QColor("#fff3bf")
                if fg:
                    item.setForeground(QBrush(fg))
                if bold or is_suggested:
                    item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                if is_suggested:
                    item.setToolTip("Possible match. Select this row and use Accept Match or Decline Match.")
                self.tbl.setItem(ri, ci, item)

        self.tbl.resizeColumnsToContents()
        hh = self.tbl.horizontalHeader()
        for col in range(self.tbl.columnCount() - 1):
            if hh.sectionSize(col) > 160:
                hh.resizeSection(col, 160)

    # ── Context menu ───────────────────────────────────────────────

    _ACCEPTABLE_STATUSES = {
        MatchStatus.AMOUNT_MISMATCH.value,
        MatchStatus.CURRENCY_MISMATCH.value,
        MatchStatus.VALUE_DATE_MISMATCH.value,
        MatchStatus.UNMATCHED_GPG.value,
        MatchStatus.UNMATCHED_WS.value,
        MatchStatus.FLAGGED_DT06.value,
    }

    def _show_context_menu(self, pos):
        result, conf = self._result_for_table_row(self.tbl.rowAt(pos.y()))
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
            self._accept_result(result, conf)

    def _selected_row(self) -> int:
        ranges = self.tbl.selectedRanges()
        return ranges[0].topRow() if ranges else -1

    def _record_key(self, result) -> str:
        if result.gpg_record:
            return result.gpg_record.confirmation_number
        if result.ws_record:
            return self._ws_display_key(result.ws_record)
        return ""

    def _ws_display_key(self, ws) -> str:
        return ws.external_ref or ws.wallstreet_ref or ""

    def _result_for_table_row(self, row: int):
        if row < 0:
            return None, ""
        conf_item = self.tbl.item(row, _CONF_COL)
        if not conf_item:
            return None, ""
        conf = conf_item.text()
        for r in self._all_results:
            key = self._record_key(r)
            if key == conf:
                return r, conf
        return None, conf

    def _update_action_buttons(self):
        result, conf = self._result_for_table_row(self._selected_row())
        accept_enabled = False
        suggestion_enabled = False
        if result:
            accept_enabled = (
                result.status.value in self._ACCEPTABLE_STATUSES
                or conf in self._accepted_confs
            )
            suggestion_enabled = self._suggested_partner_key(result) is not None
        self.btn_accept.setEnabled(accept_enabled)
        self.btn_accept_match.setEnabled(suggestion_enabled)
        self.btn_decline_match.setEnabled(suggestion_enabled)

    def _accept_selected(self):
        result, conf = self._result_for_table_row(self._selected_row())
        if result:
            self._accept_result(result, conf)

    def _accept_result(self, result, conf: str):
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

    def _normalize_amount_tolerances(self, raw: dict | None) -> dict[str, Decimal]:
        tolerances = {}
        for ccy, value in (raw or {}).items():
            code = str(ccy).strip().upper()
            if not code:
                continue
            try:
                tolerances[code] = Decimal(str(value).strip())
            except Exception:
                continue
        return tolerances

    def _amount_tolerance_for(self, currency: str) -> Decimal:
        return self._amount_tolerances.get(
            (currency or "").strip().upper(),
            Decimal("0.01"),
        )

    def _amount_close(self, left, right, currency: str = "") -> bool:
        try:
            return (
                abs(Decimal(str(left)) - Decimal(str(right)))
                <= self._amount_tolerance_for(currency)
            )
        except Exception:
            return False

    def _suggestion_pair(self, gpg_result, ws_result) -> tuple[str, str]:
        return (self._record_key(gpg_result), self._record_key(ws_result))

    def _suggested_partner_key(self, result) -> str | None:
        prefix = "Suggested match: "
        for note in result.discrepancies:
            if str(note).startswith(prefix):
                return str(note)[len(prefix):].split(" ", 1)[0]
        return None

    def _clear_suggestion_notes(self):
        for result in self._all_results:
            result.discrepancies = [
                d for d in result.discrepancies
                if not str(d).startswith("Suggested match: ")
            ]

    def _update_suggestion_info(self):
        pairs = set()
        for result in self._all_results:
            partner_key = self._suggested_partner_key(result)
            if partner_key:
                pairs.add(tuple(sorted((self._record_key(result), partner_key))))
        count = len(pairs)
        if count:
            self.lbl_suggestion_info.setText(
                f"{count} possible match{'es' if count != 1 else ''} highlighted"
            )
        else:
            self.lbl_suggestion_info.setText("")

    def _refresh_match_suggestions(self):
        self._clear_suggestion_notes()
        gpg_open = [
            r for r in self._all_results
            if r.gpg_record
            and r.status in (MatchStatus.UNMATCHED_GPG, MatchStatus.FLAGGED_DT06)
        ]
        ws_open = [
            r for r in self._all_results
            if r.ws_record and r.status == MatchStatus.UNMATCHED_WS
        ]

        used_ws: set[str] = set()
        for gpg_result in gpg_open:
            gpg = gpg_result.gpg_record
            best = None
            best_score = -1
            for ws_result in ws_open:
                ws_key = self._record_key(ws_result)
                if ws_key in used_ws:
                    continue
                pair = self._suggestion_pair(gpg_result, ws_result)
                if pair in self._declined_suggestions:
                    continue
                ws = ws_result.ws_record
                if gpg.buy_currency != ws.rec_ccy:
                    continue
                if not self._amount_close(gpg.buy_amount, ws.rec_amount, gpg.buy_currency):
                    continue

                days = (ws.value_date - gpg.value_date).days
                score = 100
                if 0 <= days <= 10:
                    score += 20 - days
                elif days < 0:
                    score -= 40
                if gpg.confirmation_number and ws.external_ref:
                    if gpg.confirmation_number == ws.external_ref:
                        score += 50
                    elif (gpg.confirmation_number in ws.external_ref
                          or ws.external_ref in gpg.confirmation_number):
                        score += 15
                if score > best_score:
                    best = ws_result
                    best_score = score

            if best:
                used_ws.add(self._record_key(best))
                ws = best.ws_record
                ws_key = self._ws_display_key(ws)
                note_for_gpg = (
                    f"Suggested match: {ws_key} "
                    f"({ws.rec_ccy} {ws.rec_amount}, WS {ws.value_date.strftime('%d %b %Y')})"
                )
                note_for_ws = (
                    f"Suggested match: {gpg.confirmation_number} "
                    f"({gpg.buy_currency} {gpg.buy_amount}, GPG {gpg.value_date.strftime('%d %b %Y')})"
                )
                gpg_result.discrepancies.insert(0, note_for_gpg)
                best.discrepancies.insert(0, note_for_ws)
        self._update_suggestion_info()

    def _accept_suggested_match(self):
        result, _ = self._result_for_table_row(self._selected_row())
        if not result:
            return
        partner_key = self._suggested_partner_key(result)
        if not partner_key:
            return
        partner = next(
            (r for r in self._all_results if self._record_key(r) == partner_key),
            None
        )
        if not partner:
            return

        gpg_result = result if result.gpg_record else partner
        ws_result = result if result.ws_record else partner
        if not gpg_result.gpg_record or not ws_result.ws_record:
            return

        reply = QMessageBox.question(
            self, "Accept Suggested Match",
            "Combine the selected GPG and WallStreet rows as an accepted match?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        gpg = gpg_result.gpg_record
        ws = ws_result.ws_record
        gpg_result.status = MatchStatus.MATCHED
        gpg_result.ws_record = ws
        gpg_result.discrepancies = [
            f"✓ ACCEPTED MATCH: paired with WS {self._ws_display_key(ws)} / {ws.wallstreet_ref}",
            f"External ref differs: GPG={gpg.confirmation_number}, WS={ws.external_ref}",
        ]
        if ws.value_date != gpg.value_date:
            gpg_result.discrepancies.append(
                f"Value date: GPG={gpg.value_date.strftime('%d %b %Y')}, "
                f"WS={ws.value_date.strftime('%d %b %Y')}"
            )
        self._all_results = [r for r in self._all_results if r is not ws_result]
        self._refresh_match_suggestions()
        self._update_summary(self._all_results)
        self._apply_filter()

    def _decline_suggestion(self):
        result, _ = self._result_for_table_row(self._selected_row())
        if not result:
            return
        partner_key = self._suggested_partner_key(result)
        if not partner_key:
            return
        partner = next(
            (r for r in self._all_results if self._record_key(r) == partner_key),
            None
        )
        if partner:
            pair = (
                self._suggestion_pair(result, partner)
                if result.gpg_record else self._suggestion_pair(partner, result)
            )
            self._declined_suggestions.add(pair)
        self._refresh_match_suggestions()
        self._apply_filter()

    # ── Actions ────────────────────────────────────────────────────

    def _save_archive(self):
        qd = self.dt_archive.date()
        d = date(qd.year(), qd.month(), qd.day())
        cp = self.txt_archive_cp.text().strip() or self._counterparty or "UNKNOWN"
        self.save_to_archive_requested.emit(d, cp)

    def _export_report(self):
        qd = self.dt_archive.date()
        d = date(qd.year(), qd.month(), qd.day())
        cp = self.txt_archive_cp.text().strip() or self._counterparty or "UNKNOWN"
        default_name = f"{d.isoformat()}_{cp}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", default_name, "Excel Files (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            generate_payment_breakdown(self._all_results, path, d)
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _draft_email(self):
        qd = self.dt_archive.date()
        d = date(qd.year(), qd.month(), qd.day())
        cp = self.txt_archive_cp.text().strip() or self._counterparty or "UNKNOWN"
        try:
            report_path = self._create_temp_report_path(d, cp)
            generate_payment_breakdown(self._all_results, report_path, d)

            net_figures_html = format_net_figures_html(self._all_results)
            opening = self._email_settings.get("email_opening", "").strip()
            subject_template = (
                self._email_settings.get("email_subject")
                or "Payment Breakdown - {counterparty} - {value_date}"
            )
            subject = subject_template.format(
                counterparty=cp,
                value_date=d.strftime("%d %b %Y"),
                value_date_iso=d.isoformat(),
            )
            body_parts = []
            if opening:
                body_parts.append(f"<p>{opening}</p>")
            body_parts.append("<p><b>Net figures:</b></p>")
            body_parts.append(net_figures_html)
            body = "\n".join(body_parts)
            create_outlook_draft(
                to=self._email_settings.get("email_to", ""),
                cc=self._email_settings.get("email_cc", ""),
                subject=subject,
                body=body,
                is_html=True,
                attachment_path=report_path,
            )
            QMessageBox.information(self, "Draft Email", "Outlook draft created.")
        except Exception as e:
            QMessageBox.critical(self, "Draft Email Error", str(e))

    def _create_temp_report_path(self, value_date: date, counterparty: str) -> str:
        safe_cp = re.sub(r"[^A-Za-z0-9_. -]+", "_", counterparty).strip() or "counterparty"
        filename = f"{value_date.isoformat()}_{safe_cp}.xlsx"
        folder = os.path.join(tempfile.gettempdir(), "ExoticPaymentReconciler")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, filename)
