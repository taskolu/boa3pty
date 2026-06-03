from __future__ import annotations

from src.core.config import ConfigManager


def matched_counterparty_for_bank_code(
    config: ConfigManager,
    bank_code: str,
    fallback_counterparty: str = "",
) -> str | None:
    matched = config.find_by_bank_code(bank_code)
    return matched or fallback_counterparty or None
