from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from enum import Enum
from typing import Optional


class MatchStatus(Enum):
    MATCHED = "matched"
    UNMATCHED_GPG = "unmatched_gpg"
    UNMATCHED_WS = "unmatched_ws"
    FLAGGED_DT06 = "flagged_dt06"
    RESOLVED_FROM_ARCHIVE = "resolved_from_archive"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    VALUE_DATE_MISMATCH = "value_date_mismatch"


@dataclass
class GPGPayment:
    payment_id: str
    confirmation_number: str
    buy_currency: str
    buy_amount: Decimal
    value_date: date
    status_code: Optional[str]
    status_message: Optional[str]
    counterparty: str
    raw_row: dict = field(default_factory=dict)

    @property
    def has_dt06_flag(self) -> bool:
        return self.has_status_flag("DT06")

    def has_status_flag(self, code: str) -> bool:
        needle = (code or "").strip().upper()
        if not needle:
            return False
        haystack = " ".join(
            part for part in (self.status_code, self.status_message) if part
        ).upper()
        return needle in haystack


@dataclass
class WSEntry:
    """WallStreet FX entry parsed from clipboard paste.

    Fields match the actual WallStreet column names:
      Pay Ccy / Pay Amount  — what the bank pays (often USD)
      Rec Ccy / Rec Amount  — what the bank receives (the exotic currency)
      external_ref          — "Ext Deal #" — PRIMARY matching key = GPG confirmation_number
      wallstreet_ref        — "Deal #"     — WallStreet internal reference
    """
    value_date: date
    counterparty: str
    pay_ccy: str
    pay_amount: Decimal
    rec_ccy: str
    rec_amount: Decimal
    rate: Decimal
    trader: str
    wallstreet_ref: str
    external_ref: str
    deal_type: str = "FX"


@dataclass
class MatchResult:
    status: MatchStatus
    gpg_record: Optional[GPGPayment]
    ws_record: Optional[WSEntry]
    discrepancies: list = field(default_factory=list)
    resolution_source: Optional[str] = None

    @property
    def is_ok(self) -> bool:
        return self.status in (MatchStatus.MATCHED, MatchStatus.RESOLVED_FROM_ARCHIVE)
