from __future__ import annotations
from decimal import Decimal
from src.core.models import GPGPayment, WSEntry, MatchResult, MatchStatus

_AMOUNT_TOLERANCE = Decimal("0.01")

# Priority for sorting results: lower number = shown first (problems at top)
_STATUS_PRIORITY = {
    MatchStatus.AMOUNT_MISMATCH:        0,
    MatchStatus.CURRENCY_MISMATCH:      0,
    MatchStatus.VALUE_DATE_MISMATCH:    0,
    MatchStatus.UNMATCHED_GPG:          1,
    MatchStatus.UNMATCHED_WS:           2,
    MatchStatus.FLAGGED_DT06:           3,
    MatchStatus.RESOLVED_FROM_ARCHIVE:  4,
    MatchStatus.MATCHED:                5,
}


def reconcile(
    gpg_records: list[GPGPayment],
    ws_records: list[WSEntry],
    archived_flags: list[dict] | None = None,
    dt06_code: str = "DT06",
    amount_tolerances: dict | None = None,
) -> list[MatchResult]:
    """Match GPG payments against WallStreet FX entries.

    Matching key: GPG confirmation_number == WSEntry external_ref ("Ext Deal #").
    Amount match:   GPG buy_amount    == WS rec_amount  (the exotic/received side)
    Currency match: GPG buy_currency  == WS rec_ccy

    archived_flags: optional list of dicts with 'confirmation_number' and
                    'status' keys from archive lookback (DT06 resolution).
    """
    tolerances = _normalize_amount_tolerances(amount_tolerances)
    ws_by_ref = {e.external_ref: e for e in ws_records if e.external_ref}
    matched_ws_ids: set[int] = set()
    results: list[MatchResult] = []

    for gpg in gpg_records:
        ws = ws_by_ref.get(gpg.confirmation_number)

        if ws is not None:
            matched_ws_ids.add(id(ws))

            # Check currency first
            if gpg.buy_currency != ws.rec_ccy:
                results.append(MatchResult(
                    status=MatchStatus.CURRENCY_MISMATCH,
                    gpg_record=gpg,
                    ws_record=ws,
                    discrepancies=[
                        f"currency: GPG={gpg.buy_currency}, WS={ws.rec_ccy}"
                    ],
                ))
            else:
                tolerance = _amount_tolerance_for(gpg.buy_currency, tolerances)
                diff = abs(gpg.buy_amount - ws.rec_amount)
                if diff > tolerance:
                    results.append(MatchResult(
                        status=MatchStatus.AMOUNT_MISMATCH,
                        gpg_record=gpg,
                        ws_record=ws,
                        discrepancies=[
                            f"amount: GPG={gpg.buy_amount}, WS={ws.rec_amount}, "
                            f"tolerance={tolerance}"
                        ],
                    ))
                    continue

                # Value date check:
                # WS date > GPG date = bank amended the value date forward (normal, note it)
                # WS date < GPG date = should never happen (real data error)
                # WS date == GPG date = perfect match
                discrepancies = []
                if diff > Decimal("0"):
                    discrepancies.append(
                        f"Amount diff {diff} within {tolerance} tolerance"
                    )
                if ws.value_date > gpg.value_date:
                    discrepancies.append(
                        f"Bank amended value date: GPG={gpg.value_date.strftime('%d %b %Y')}"
                        f" → WS={ws.value_date.strftime('%d %b %Y')}"
                    )
                    results.append(MatchResult(
                        status=MatchStatus.MATCHED,
                        gpg_record=gpg,
                        ws_record=ws,
                        discrepancies=discrepancies,
                    ))
                elif ws.value_date < gpg.value_date:
                    results.append(MatchResult(
                        status=MatchStatus.VALUE_DATE_MISMATCH,
                        gpg_record=gpg,
                        ws_record=ws,
                        discrepancies=[
                            f"WS value date earlier than GPG: "
                            f"GPG={gpg.value_date.strftime('%d %b %Y')}, "
                            f"WS={ws.value_date.strftime('%d %b %Y')}"
                        ],
                    ))
                else:
                    results.append(MatchResult(
                        status=MatchStatus.MATCHED,
                        gpg_record=gpg,
                        ws_record=ws,
                        discrepancies=discrepancies,
                    ))
        else:
            # Not found in WallStreet
            if gpg.has_status_flag(dt06_code):
                results.append(MatchResult(
                    status=MatchStatus.FLAGGED_DT06,
                    gpg_record=gpg,
                    ws_record=None,
                ))
            elif _check_archive(gpg.confirmation_number, archived_flags):
                source = _get_archive_source(gpg.confirmation_number, archived_flags)
                results.append(MatchResult(
                    status=MatchStatus.RESOLVED_FROM_ARCHIVE,
                    gpg_record=gpg,
                    ws_record=None,
                    resolution_source=source,
                ))
            else:
                results.append(MatchResult(
                    status=MatchStatus.UNMATCHED_GPG,
                    gpg_record=gpg,
                    ws_record=None,
                ))

    # Find WS entries with no GPG match
    for ws in ws_records:
        if id(ws) not in matched_ws_ids:
            if _check_archive(ws.external_ref, archived_flags):
                source = _get_archive_source(ws.external_ref, archived_flags)
                results.append(MatchResult(
                    status=MatchStatus.RESOLVED_FROM_ARCHIVE,
                    gpg_record=None,
                    ws_record=ws,
                    discrepancies=[
                        "Resolved from prior archived missing/DT06 record"
                    ],
                    resolution_source=source,
                ))
            else:
                results.append(MatchResult(
                    status=MatchStatus.UNMATCHED_WS,
                    gpg_record=None,
                    ws_record=ws,
                ))

    # Sort: problems first, matched last
    results.sort(key=lambda r: _STATUS_PRIORITY.get(r.status, 99))
    return results


def _normalize_amount_tolerances(raw: dict | None) -> dict[str, Decimal]:
    tolerances: dict[str, Decimal] = {}
    for ccy, value in (raw or {}).items():
        code = str(ccy).strip().upper()
        if not code:
            continue
        try:
            tolerances[code] = Decimal(str(value).strip())
        except Exception:
            continue
    return tolerances


def _amount_tolerance_for(currency: str, tolerances: dict[str, Decimal]) -> Decimal:
    return tolerances.get((currency or "").strip().upper(), _AMOUNT_TOLERANCE)


def _check_archive(conf_number: str, flags: list[dict] | None) -> bool:
    if not flags:
        return False
    return any(
        f.get("confirmation_number") == conf_number
        and f.get("status") in (MatchStatus.FLAGGED_DT06.value, MatchStatus.UNMATCHED_GPG.value)
        for f in flags
    )


def _get_archive_source(conf_number: str, flags: list[dict] | None) -> str | None:
    if not flags:
        return None
    for f in flags:
        if (f.get("confirmation_number") == conf_number
                and f.get("status") in (MatchStatus.FLAGGED_DT06.value, MatchStatus.UNMATCHED_GPG.value)):
            return f.get("source_file")
    return None
