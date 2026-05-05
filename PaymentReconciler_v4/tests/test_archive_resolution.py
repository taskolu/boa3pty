import unittest
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.matcher import reconcile
from src.core.models import GPGPayment, MatchStatus, WSEntry


def gpg(conf, status_code=None, status_message=None):
    return GPGPayment(
        payment_id=conf,
        confirmation_number=conf,
        buy_currency="IQD",
        buy_amount=Decimal("3874000.00"),
        value_date=date(2026, 4, 24),
        status_code=status_code,
        status_message=status_message,
        counterparty="BOA3PTY",
    )


def ws(conf):
    return WSEntry(
        value_date=date(2026, 4, 27),
        counterparty="BOA Exotic",
        pay_ccy="USD",
        pay_amount=Decimal("3000.77"),
        rec_ccy="IQD",
        rec_amount=Decimal("3874000.00"),
        rate=Decimal("1291"),
        trader="",
        wallstreet_ref="W260422022748",
        external_ref=conf,
    )


class ArchiveResolutionTests(unittest.TestCase):
    def test_later_ws_row_resolves_prior_archived_dt06(self):
        results = reconcile(
            [],
            [ws("VOTR0043717/2")],
            [{
                "confirmation_number": "VOTR0043717/2",
                "status": MatchStatus.FLAGGED_DT06.value,
                "source_file": "2026-04-24_BOA Exotic.xlsx",
            }],
        )

        self.assertEqual(results[0].status, MatchStatus.RESOLVED_FROM_ARCHIVE)

    def test_later_ws_row_resolves_prior_archived_missing_without_dt06(self):
        results = reconcile(
            [],
            [ws("UNTR4797224R4/1")],
            [{
                "confirmation_number": "UNTR4797224R4/1",
                "status": MatchStatus.UNMATCHED_GPG.value,
                "source_file": "2026-04-28_BOA Exotic.xlsx",
            }],
        )

        self.assertEqual(results[0].status, MatchStatus.RESOLVED_FROM_ARCHIVE)

    def test_blank_status_missing_stays_open_until_ws_arrives_later(self):
        results = reconcile([gpg("UNTR4797224R4/1")], [], [])

        self.assertEqual(results[0].status, MatchStatus.UNMATCHED_GPG)

    def test_dt06_detection_checks_message_as_well_as_code(self):
        results = reconcile([gpg("VOTR0043717/2", status_message="Bank changed value date DT06")], [], [])

        self.assertEqual(results[0].status, MatchStatus.FLAGGED_DT06)


if __name__ == "__main__":
    unittest.main()
