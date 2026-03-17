import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path
from src.core.parser_gpg import parse_gpg_csv

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def column_mapping():
    return {
        "payment_id": "Payment ID",
        "confirmation_number": "Payment Reference",
        "buy_currency": "Currency",
        "buy_amount": "Amount",
        "value_date": "Value Date",
        "status_code": "Status Information/Error"
    }


def test_parse_csv_returns_records(column_mapping):
    records, detected = parse_gpg_csv(
        str(FIXTURE_DIR / "sample_gpg.csv"), column_mapping, "%Y-%m-%d"
    )
    assert len(records) == 3
    assert detected == "BANKA_GPG"


def test_parse_csv_amounts(column_mapping):
    records, _ = parse_gpg_csv(
        str(FIXTURE_DIR / "sample_gpg.csv"), column_mapping, "%Y-%m-%d"
    )
    assert records[0].buy_amount == Decimal("50000.00")
    assert records[0].buy_currency == "EUR"


def test_parse_csv_dates(column_mapping):
    records, _ = parse_gpg_csv(
        str(FIXTURE_DIR / "sample_gpg.csv"), column_mapping, "%Y-%m-%d"
    )
    assert records[0].value_date == date(2026, 3, 1)


def test_parse_csv_dt06_detection(column_mapping):
    records, _ = parse_gpg_csv(
        str(FIXTURE_DIR / "sample_gpg.csv"), column_mapping, "%Y-%m-%d"
    )
    assert records[0].has_dt06_flag is False
    assert records[1].has_dt06_flag is True
    assert records[1].status_code == "DT06"


def test_parse_csv_preserves_raw_row(column_mapping):
    records, _ = parse_gpg_csv(
        str(FIXTURE_DIR / "sample_gpg.csv"), column_mapping, "%Y-%m-%d"
    )
    assert "Payment ID" in records[0].raw_row
