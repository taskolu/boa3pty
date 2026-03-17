import pytest
from decimal import Decimal
from datetime import date
from src.core.models import GPGPayment, WSEntry, MatchResult, MatchStatus


def test_gpg_payment_creation():
    p = GPGPayment(
        payment_id="PAY001",
        confirmation_number="CONF001",
        buy_currency="EUR",
        buy_amount=Decimal("50000.00"),
        value_date=date(2026, 3, 1),
        status_code=None,
        status_message=None,
        counterparty="BANKA",
        raw_row={"Payment ID": "PAY001"}
    )
    assert p.confirmation_number == "CONF001"
    assert p.buy_amount == Decimal("50000.00")
    assert p.has_dt06_flag is False


def test_gpg_payment_dt06_flag():
    p = GPGPayment(
        payment_id="PAY002",
        confirmation_number="CONF002",
        buy_currency="GBP",
        buy_amount=Decimal("25000.00"),
        value_date=date(2026, 3, 1),
        status_code="DT06",
        status_message="REQUESTED EXECUTION DATE CHANGED BY BULKFX",
        counterparty="BANKA",
        raw_row={}
    )
    assert p.has_dt06_flag is True


def test_ws_entry_creation():
    """WSEntry uses pay/rec terminology to match actual WallStreet columns."""
    e = WSEntry(
        value_date=date(2026, 3, 18),
        counterparty="BANK OF AMERICA, N.A. EXOTICS, WASHINGTON",
        pay_ccy="USD",
        pay_amount=Decimal("238.48"),
        rec_ccy="ARS",
        rec_amount=Decimal("317395.00"),
        rate=Decimal("1330.8945"),
        trader="WSS",
        wallstreet_ref="W260316040455",
        external_ref="OTR6533553/1",
        deal_type="FX",
    )
    assert e.external_ref == "OTR6533553/1"
    assert e.rec_ccy == "ARS"
    assert e.rec_amount == Decimal("317395.00")


def test_match_result_matched():
    r = MatchResult(
        status=MatchStatus.MATCHED,
        gpg_record=None,
        ws_record=None,
        discrepancies=[],
        resolution_source=None
    )
    assert r.status == MatchStatus.MATCHED
    assert r.is_ok is True


def test_match_result_unmatched():
    r = MatchResult(
        status=MatchStatus.UNMATCHED_GPG,
        gpg_record=None,
        ws_record=None,
        discrepancies=[],
        resolution_source=None
    )
    assert r.is_ok is False
