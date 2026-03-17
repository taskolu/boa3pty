"""End-to-end: parse CSV + real WS paste → match → archive → lookback → resolve"""
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path
from src.core.parser_gpg import parse_gpg_csv
from src.core.parser_wallstreet import parse_wallstreet_paste
from src.core.matcher import reconcile
from src.core.models import MatchStatus
from src.archive.archive_manager import ArchiveManager
from src.archive.history_lookup import lookup_flagged_records

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# WS paste using real WallStreet column names, matching two of the three GPG entries
WS_PASTE = (
    "\tDeal Type\tValue Date\tCustomer\tPay Ccy\tPay Amount\t"
    "Rec Ccy\tRec Amount\tRate\tTrader\tDeal #\tExt Deal #\t\n"
    "1\tFX\t01 Mar 2026\tBank A International\t"
    "USD\t54000.00\tEUR\t50000.00\t1.0800\tWSS\tWS001\tCONF001\t\n"
)

GPG_MAPPING = {
    "payment_id": "Payment ID",
    "confirmation_number": "Payment Reference",
    "buy_currency": "Currency",
    "buy_amount": "Amount",
    "value_date": "Value Date",
    "status_code": "Status Information/Error",
}


def test_full_reconciliation_flow(tmp_path):
    gpg_records, _ = parse_gpg_csv(
        str(FIXTURE_DIR / "sample_gpg.csv"),
        GPG_MAPPING, "%Y-%m-%d"
    )
    assert len(gpg_records) == 3

    ws_entries, ws_cp = parse_wallstreet_paste(WS_PASTE)
    assert len(ws_entries) == 1
    assert ws_entries[0].external_ref == "CONF001"
    assert ws_entries[0].rec_ccy == "EUR"
    assert ws_entries[0].rec_amount == Decimal("50000.00")

    results = reconcile(gpg_records, ws_entries)

    matched  = [r for r in results if r.status == MatchStatus.MATCHED]
    flagged  = [r for r in results if r.status == MatchStatus.FLAGGED_DT06]
    unmatched = [r for r in results if r.status == MatchStatus.UNMATCHED_GPG]

    assert len(matched) == 1    # CONF001
    assert len(flagged) == 1    # CONF002 (DT06)
    assert len(unmatched) == 1  # CONF003

    # Save to archive
    archive_dir = str(tmp_path / "archive")
    am = ArchiveManager(archive_dir)
    am.save_daily(date(2026, 3, 1), "BankA", results)

    # Day 2: lookback resolves CONF002
    flags = lookup_flagged_records(
        archive_dir, "BankA", lookback_days=5,
        reference_date=date(2026, 3, 2)
    )
    assert len(flags) >= 1
    assert any(f["confirmation_number"] == "CONF002" for f in flags)


def test_deduplication(tmp_path):
    """Duplicate WS rows (same Ext Deal #) should be counted as one."""
    dup_paste = (
        "\tDeal Type\tValue Date\tCustomer\tPay Ccy\tPay Amount\t"
        "Rec Ccy\tRec Amount\tRate\tTrader\tDeal #\tExt Deal #\t\n"
        "1\tFX\t01 Mar 2026\tBank A\tUSD\t100.00\tEUR\t91.00\t0.91\tWSS\tW1\tCONF001\t\n"
        "2\tFX\t01 Mar 2026\tBank A\tUSD\t100.00\tEUR\t91.00\t0.91\tWSS\tW1\tCONF001\t\n"
    )
    entries, _ = parse_wallstreet_paste(dup_paste)
    assert len(entries) == 1
