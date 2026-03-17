from __future__ import annotations
from src.core.models import GPGPayment, WSEntry, MatchResult, MatchStatus

# Priority for sorting results: lower number = shown first (problems at top)
_STATUS_PRIORITY = {
    MatchStatus.AMOUNT_MISMATCH:        0,
    MatchStatus.CURRENCY_MISMATCH:      0,
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
) -> list[MatchResult]:
    """Match GPG payments against WallStreet FX entries.

    Matching key: GPG confirmation_number == WSEntry external_ref ("Ext Deal #").
    Amount match:   GPG buy_amount    == WS rec_amount  (the exotic/received side)
    Currency match: GPG buy_currency  == WS rec_ccy

    archived_flags: optional list of dicts with 'confirmation_number' and
                    'status' keys from archive lookback (DT06 resolution).
    """
    ws_by_ref = {e.external_ref: e for e in ws_records}
    matched_ws_refs: set[str] = set()
    results: list[MatchResult] = []

    for gpg in gpg_records:
        ws = ws_by_ref.get(gpg.confirmation_number)

        if ws is not None:
            matched_ws_refs.add(gpg.confirmation_number)

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
            # Then check amount
            elif gpg.buy_amount != ws.rec_amount:
                results.append(MatchResult(
                    status=MatchStatus.AMOUNT_MISMATCH,
                    gpg_record=gpg,
                    ws_record=ws,
                    discrepancies=[
                        f"amount: GPG={gpg.buy_amount}, WS={ws.rec_amount}"
                    ],
                ))
            else:
                # Value date check:
                # WS date > GPG date = bank amended the value date forward (normal, note it)
                # WS date < GPG date = should never happen (real data error)
                # WS date == GPG date = perfect match
                discrepancies = []
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
                    ))
        else:
            # Not found in WallStreet
            if gpg.has_dt06_flag:
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
        if ws.external_ref not in matched_ws_refs:
            results.append(MatchResult(
                status=MatchStatus.UNMATCHED_WS,
                gpg_record=None,
                ws_record=ws,
            ))

    # Sort: problems first, matched last
    results.sort(key=lambda r: _STATUS_PRIORITY.get(r.status, 99))
    return results


def _check_archive(conf_number: str, flags: list[dict] | None) -> bool:
    if not flags:
        return False
    return any(
        f.get("confirmation_number") == conf_number
        and f.get("status") == MatchStatus.FLAGGED_DT06.value
        for f in flags
    )


def _get_archive_source(conf_number: str, flags: list[dict] | None) -> str | None:
    if not flags:
        return None
    for f in flags:
        if (f.get("confirmation_number") == conf_number
                and f.get("status") == MatchStatus.FLAGGED_DT06.value):
            return f.get("source_file")
    return None
