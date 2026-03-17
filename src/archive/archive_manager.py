from __future__ import annotations
import os
from datetime import date
from pathlib import Path
from typing import Optional
from openpyxl import Workbook, load_workbook
from src.core.models import MatchResult, MatchStatus


class ArchiveManager:
    def __init__(self, archive_path: str):
        self._path = Path(archive_path)
        self._path.mkdir(parents=True, exist_ok=True)

    def _filename(self, dt: date, counterparty: str) -> Path:
        return self._path / f"{dt.isoformat()}_{counterparty}.xlsx"

    def save_daily(
        self, dt: date, counterparty: str, results: list[MatchResult]
    ):
        wb = Workbook()

        # Summary sheet
        ws_summary = wb.active
        ws_summary.title = "Summary"
        counts: dict[str, int] = {}
        for r in results:
            key = r.status.value
            counts[key] = counts.get(key, 0) + 1
        ws_summary.append(["Date", dt.isoformat()])
        ws_summary.append(["Counterparty", counterparty])
        ws_summary.append(["Total Records", len(results)])
        for status, count in counts.items():
            ws_summary.append([status, count])

        # Results sheet
        ws_results = wb.create_sheet("Results")
        ws_results.append([
            "Status", "Confirmation#", "GPG_Currency", "GPG_Amount",
            "GPG_ValueDate", "WS_RecCcy", "WS_RecAmount", "WS_ValueDate",
            "WS_Ref", "Discrepancies", "Resolution_Source"
        ])
        for r in results:
            ws_results.append([
                r.status.value,
                (r.gpg_record.confirmation_number if r.gpg_record
                 else r.ws_record.external_ref if r.ws_record else ""),
                r.gpg_record.buy_currency if r.gpg_record else "",
                str(r.gpg_record.buy_amount) if r.gpg_record else "",
                r.gpg_record.value_date.isoformat() if r.gpg_record else "",
                r.ws_record.rec_ccy if r.ws_record else "",
                str(r.ws_record.rec_amount) if r.ws_record else "",
                r.ws_record.value_date.isoformat() if r.ws_record else "",
                r.ws_record.wallstreet_ref if r.ws_record else "",
                "; ".join(r.discrepancies),
                r.resolution_source or "",
            ])

        # Flagged sheet (used for DT06 lookback)
        ws_flagged = wb.create_sheet("Flagged")
        ws_flagged.append([
            "Confirmation#", "Status", "Currency", "Amount",
            "ValueDate", "StatusCode", "StatusMessage"
        ])
        for r in results:
            if r.status in (MatchStatus.FLAGGED_DT06, MatchStatus.UNMATCHED_GPG):
                gpg = r.gpg_record
                if gpg:
                    ws_flagged.append([
                        gpg.confirmation_number,
                        r.status.value,
                        gpg.buy_currency,
                        str(gpg.buy_amount),
                        gpg.value_date.isoformat(),
                        gpg.status_code or "",
                        gpg.status_message or "",
                    ])

        filepath = self._filename(dt, counterparty)
        wb.save(str(filepath))

    def load_daily(self, dt: date, counterparty: str) -> Optional[dict]:
        filepath = self._filename(dt, counterparty)
        if not filepath.exists():
            return None

        wb = load_workbook(str(filepath), read_only=True)
        ws_summary = wb["Summary"]
        summary: dict = {}
        for row in ws_summary.iter_rows(values_only=True):
            if row[0] and row[1] is not None:
                summary[row[0]] = row[1]
        wb.close()
        return {"summary": summary, "file": str(filepath)}

    def list_archives(self) -> list[dict]:
        archives = []
        for f in sorted(self._path.glob("*.xlsx"), reverse=True):
            parts = f.stem.split("_", 1)
            if len(parts) == 2:
                archives.append({
                    "date": parts[0],
                    "counterparty": parts[1],
                    "file": str(f),
                })
        return archives
