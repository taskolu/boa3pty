import pytest
from decimal import Decimal
from datetime import date
from src.core.models import GPGPayment, WSEntry, MatchStatus
from src.core.matcher import reconcile


def make_gpg(conf, amount, ccy="ARS", status_code=None, status_message=None):
    return GPGPayment(
        payment_id=f"P_{conf}",
        confirmation_number=conf,
        buy_currency=ccy,
        buy_amount=Decimal(str(amount)),
        value_date=date(2026, 3, 18),
        status_code=status_code,
        status_message=status_message,
        counterparty="BANKA",
        raw_row={},
    )


def make_ws(ext_ref, rec_amount, rec_ccy="ARS"):
    """Create a WSEntry matching the real WallStreet format (pay=USD, rec=exotic)."""
    return WSEntry(
        value_date=date(2026, 3, 18),
        counterparty="BANK OF AMERICA, N.A. EXOTICS, WASHINGTON",
        pay_ccy="USD",
        pay_amount=Decimal("100.00"),
        rec_ccy=rec_ccy,
        rec_amount=Decimal(str(rec_amount)),
        rate=Decimal("1.0"),
        trader="WSS",
        wallstreet_ref=f"W_{ext_ref}",
        external_ref=ext_ref,
        deal_type="FX",
    )


def test_all_matched():
    gpg = [make_gpg("C1", 50000), make_gpg("C2", 25000)]
    ws = [make_ws("C1", 50000), make_ws("C2", 25000)]
    results = reconcile(gpg, ws)
    assert all(r.status == MatchStatus.MATCHED for r in results)
    assert len(results) == 2


def test_unmatched_gpg():
    gpg = [make_gpg("C1", 50000), make_gpg("C2", 25000)]
    ws = [make_ws("C1", 50000)]
    results = reconcile(gpg, ws)
    matched = [r for r in results if r.status == MatchStatus.MATCHED]
    unmatched = [r for r in results if r.status == MatchStatus.UNMATCHED_GPG]
    assert len(matched) == 1
    assert len(unmatched) == 1
    assert unmatched[0].gpg_record.confirmation_number == "C2"


def test_unmatched_ws():
    gpg = [make_gpg("C1", 50000)]
    ws = [make_ws("C1", 50000), make_ws("C3", 10000)]
    results = reconcile(gpg, ws)
    extra_ws = [r for r in results if r.status == MatchStatus.UNMATCHED_WS]
    assert len(extra_ws) == 1
    assert extra_ws[0].ws_record.external_ref == "C3"


def test_amount_mismatch():
    gpg = [make_gpg("C1", 50000)]
    ws = [make_ws("C1", 49999)]
    results = reconcile(gpg, ws)
    assert results[0].status == MatchStatus.AMOUNT_MISMATCH
    assert "amount" in results[0].discrepancies[0]


def test_currency_mismatch():
    gpg = [make_gpg("C1", 50000, ccy="EUR")]
    ws = [make_ws("C1", 50000, rec_ccy="GBP")]
    results = reconcile(gpg, ws)
    assert results[0].status == MatchStatus.CURRENCY_MISMATCH


def test_dt06_flagged():
    gpg = [make_gpg("C1", 50000, status_code="DT06", status_message="DATE CHANGED")]
    ws = []
    results = reconcile(gpg, ws)
    assert results[0].status == MatchStatus.FLAGGED_DT06


def test_dt06_not_flagged_if_matched():
    """DT06 code in GPG but WS entry exists — should be MATCHED."""
    gpg = [make_gpg("C1", 50000, status_code="DT06", status_message="DATE CHANGED")]
    ws = [make_ws("C1", 50000)]
    results = reconcile(gpg, ws)
    assert results[0].status == MatchStatus.MATCHED


def test_sort_order():
    """Unmatched and flagged appear before matched."""
    gpg = [
        make_gpg("C1", 50000),
        make_gpg("C2", 25000, status_code="DT06"),
        make_gpg("C3", 10000),
    ]
    ws = [make_ws("C1", 50000)]
    results = reconcile(gpg, ws)
    statuses = [r.status for r in results]
    assert statuses.index(MatchStatus.UNMATCHED_GPG) < statuses.index(MatchStatus.MATCHED)
    assert statuses.index(MatchStatus.FLAGGED_DT06) < statuses.index(MatchStatus.MATCHED)
