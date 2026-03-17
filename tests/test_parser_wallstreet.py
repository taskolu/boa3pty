import pytest
from decimal import Decimal
from datetime import date
from src.core.parser_wallstreet import parse_wallstreet_paste

# Real WallStreet paste format (subset of actual data)
REAL_PASTE = (
    "\tDeal Type\tValue Date\tCustomer\tPay Ccy\tPay Amount\t"
    "Rec Ccy\tRec Amount\tRate\tTrader\tDeal #\tExt Deal #\t\n"
    "1\tFX\t18 Mar 2026\tBANK OF AMERICA, N.A. EXOTICS, WASHINGTON\t"
    "USD\t238.48\tARS\t317,395.00\t1330.8945000\tWSS\tW260316040455\tOTR6533553/1\t\n"
    "2\tFX\t18 Mar 2026\tBANK OF AMERICA, N.A. EXOTICS, WASHINGTON\t"
    "USD\t24,754.52\tARS\t33,063,013.00\t1335.6356000\tWSS\tW260316040458\tOTR6531789/1\t\n"
    "3\tFX\t18 Mar 2026\tBANK OF AMERICA, N.A. EXOTICS, WASHINGTON\t"
    "USD\t646.12\tBAM\t1,077.92\t1.6683000\tWSS\tW260316040636\tCOTR1307451/2\t\n"
    # Duplicate rows (same ext ref) — should be deduplicated
    "4\tFX\t18 Mar 2026\tBANK OF AMERICA, N.A. EXOTICS, WASHINGTON\t"
    "USD\t238.48\tARS\t317,395.00\t1330.8945000\tWSS\tW260316040455\tOTR6533553/1\t\n"
    "5\tFX\t18 Mar 2026\tBANK OF AMERICA, N.A. EXOTICS, WASHINGTON\t"
    "USD\t24,754.52\tARS\t33,063,013.00\t1335.6356000\tWSS\tW260316040458\tOTR6531789/1\t\n"
)


def test_parse_real_format_returns_unique_entries():
    entries, cp = parse_wallstreet_paste(REAL_PASTE)
    assert len(entries) == 3  # duplicates removed
    assert cp == "BANK OF AMERICA, N.A. EXOTICS, WASHINGTON"


def test_parse_rec_ccy_and_amount():
    entries, _ = parse_wallstreet_paste(REAL_PASTE)
    assert entries[0].rec_ccy == "ARS"
    assert entries[0].rec_amount == Decimal("317395.00")
    assert entries[0].pay_ccy == "USD"
    assert entries[0].pay_amount == Decimal("238.48")


def test_parse_date_format():
    entries, _ = parse_wallstreet_paste(REAL_PASTE)
    assert entries[0].value_date == date(2026, 3, 18)


def test_parse_external_ref():
    entries, _ = parse_wallstreet_paste(REAL_PASTE)
    assert entries[0].external_ref == "OTR6533553/1"
    assert entries[1].external_ref == "OTR6531789/1"


def test_parse_wallstreet_ref():
    entries, _ = parse_wallstreet_paste(REAL_PASTE)
    assert entries[0].wallstreet_ref == "W260316040455"


def test_parse_trader():
    entries, _ = parse_wallstreet_paste(REAL_PASTE)
    assert entries[0].trader == "WSS"


def test_parse_empty_returns_empty():
    entries, cp = parse_wallstreet_paste("")
    assert entries == []
    assert cp is None


def test_parse_with_column_override():
    """Users with renamed columns can override via col_map_override."""
    renamed_paste = (
        "Deal Type\tSettlement Date\tBank Name\tPay Ccy\tPay Amount\t"
        "Rec Ccy\tRec Amount\tRate\tTrader\tDeal #\tExt Deal #\n"
        "FX\t18 Mar 2026\tSomeBank\tUSD\t100.00\tEUR\t91.00\t0.91\tABC\tW001\tCONF001\n"
    )
    entries, cp = parse_wallstreet_paste(
        renamed_paste,
        col_map_override={
            "value_date": "Settlement Date",
            "counterparty": "Bank Name",
        }
    )
    assert len(entries) == 1
    assert entries[0].value_date == date(2026, 3, 18)
    assert entries[0].counterparty == "SomeBank"
