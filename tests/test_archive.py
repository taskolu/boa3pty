import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path
from src.core.models import GPGPayment, WSEntry, MatchResult, MatchStatus
from src.archive.archive_manager import ArchiveManager
from src.archive.history_lookup import lookup_flagged_records


@pytest.fixture
def archive_dir(tmp_path):
    return str(tmp_path / "archive")


@pytest.fixture
def sample_results():
    gpg1 = GPGPayment("P1", "C1", "ARS", Decimal("317395"), date(2026, 3, 18),
                       None, None, "BANKA", {})
    ws1 = WSEntry(
        value_date=date(2026, 3, 18),
        counterparty="Bank A",
        pay_ccy="USD", pay_amount=Decimal("238.48"),
        rec_ccy="ARS", rec_amount=Decimal("317395"),
        rate=Decimal("1330.89"), trader="WSS",
        wallstreet_ref="W001", external_ref="C1",
    )
    gpg2 = GPGPayment("P2", "C2", "GBP", Decimal("25000"), date(2026, 3, 18),
                       "DT06", "DATE CHANGED", "BANKA", {})
    return [
        MatchResult(MatchStatus.MATCHED, gpg1, ws1),
        MatchResult(MatchStatus.FLAGGED_DT06, gpg2, None),
    ]


def test_save_and_load_archive(archive_dir, sample_results):
    am = ArchiveManager(archive_dir)
    am.save_daily(date(2026, 3, 18), "BankA", sample_results)

    filepath = Path(archive_dir) / "2026-03-18_BankA.xlsx"
    assert filepath.exists()

    loaded = am.load_daily(date(2026, 3, 18), "BankA")
    assert loaded is not None
    assert loaded["summary"]["matched"] == 1
    assert loaded["summary"]["flagged_dt06"] == 1


def test_list_archives(archive_dir, sample_results):
    am = ArchiveManager(archive_dir)
    am.save_daily(date(2026, 3, 18), "BankA", sample_results)
    am.save_daily(date(2026, 3, 19), "BankA", sample_results)

    archives = am.list_archives()
    assert len(archives) == 2


def test_lookup_flagged_from_history(archive_dir, sample_results):
    am = ArchiveManager(archive_dir)
    am.save_daily(date(2026, 3, 18), "BankA", sample_results)

    flags = lookup_flagged_records(
        archive_dir, "BankA", lookback_days=5,
        reference_date=date(2026, 3, 19)
    )
    assert len(flags) == 1
    assert flags[0]["confirmation_number"] == "C2"
    assert flags[0]["status"] == "flagged_dt06"
