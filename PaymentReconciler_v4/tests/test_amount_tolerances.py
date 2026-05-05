import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.matcher import reconcile
from src.core.models import GPGPayment, MatchStatus, WSEntry


def gpg(conf, currency="IQD", amount="3874000.49"):
    return GPGPayment(
        payment_id=conf,
        confirmation_number=conf,
        buy_currency=currency,
        buy_amount=Decimal(amount),
        value_date=date(2026, 4, 30),
        status_code=None,
        status_message=None,
        counterparty="BOA3PTY",
    )


def ws(conf, currency="IQD", amount="3874000.00"):
    return WSEntry(
        value_date=date(2026, 4, 30),
        counterparty="BOA Exotic",
        pay_ccy="USD",
        pay_amount=Decimal("3000.77"),
        rec_ccy=currency,
        rec_amount=Decimal(amount),
        rate=Decimal("1291"),
        trader="",
        wallstreet_ref="W260422022748",
        external_ref=conf,
    )


class AmountToleranceTests(unittest.TestCase):
    def test_currency_tolerance_allows_whole_unit_rounding(self):
        results = reconcile(
            [gpg("CONF1")],
            [ws("CONF1")],
            amount_tolerances={"IQD": "1"},
        )

        self.assertEqual(results[0].status, MatchStatus.MATCHED)
        self.assertIn("within 1 tolerance", results[0].discrepancies[0])

    def test_default_cent_tolerance_still_flags_amount_mismatch(self):
        results = reconcile([gpg("CONF1")], [ws("CONF1")])

        self.assertEqual(results[0].status, MatchStatus.AMOUNT_MISMATCH)

    def test_tolerance_is_currency_specific(self):
        results = reconcile(
            [gpg("CONF1", currency="AZN", amount="4439.49")],
            [ws("CONF1", currency="AZN", amount="4439.00")],
            amount_tolerances={"IQD": "1"},
        )

        self.assertEqual(results[0].status, MatchStatus.AMOUNT_MISMATCH)


if __name__ == "__main__":
    unittest.main()
