import pytest
from decimal import Decimal
from datetime import date
from src.core.models import GPGPayment, WSEntry, MatchResult, MatchStatus
from src.export.report_generator import generate_payment_breakdown


@pytest.fixture
def sample_results():
    results = []
    for i, (ccy, rec_amt, pay_amt) in enumerate([
        ("ARS", 317395, 238.48),
        ("BBD", 1000.00, 509.27),
        ("BAM", 1077.92, 646.12),
    ]):
        gpg = GPGPayment(
            f"P{i}", f"C{i}", ccy, Decimal(str(rec_amt)),
            date(2026, 3, 18), None, None, "BANKA", {}
        )
        ws = WSEntry(
            value_date=date(2026, 3, 18),
            counterparty="Bank A",
            pay_ccy="USD", pay_amount=Decimal(str(pay_amt)),
            rec_ccy=ccy, rec_amount=Decimal(str(rec_amt)),
            rate=Decimal("1.0"), trader="WSS",
            wallstreet_ref=f"WS{i}", external_ref=f"C{i}",
        )
        results.append(MatchResult(MatchStatus.MATCHED, gpg, ws))
    return results


def test_generate_breakdown(tmp_path, sample_results):
    output = tmp_path / "report.xlsx"
    generate_payment_breakdown(sample_results, str(output), date(2026, 3, 18))
    assert output.exists()
    assert output.stat().st_size > 0
