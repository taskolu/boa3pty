from __future__ import annotations
from pathlib import Path

from src.core.config import ConfigManager


def matched_counterparty_for_bank_code(
    config: ConfigManager,
    bank_code: str,
    fallback_counterparty: str = "",
    file_path: str = "",
) -> str | None:
    filename_match = matched_counterparty_for_filename(config, file_path)
    if filename_match:
        return filename_match

    matched = config.find_by_bank_code(bank_code)
    return matched or fallback_counterparty or None


def matched_counterparty_for_filename(
    config: ConfigManager,
    file_path: str,
) -> str | None:
    filename = Path(file_path or "").name.strip().lower()
    if not filename:
        return None

    matches = []
    for cp_name in config.counterparty_names:
        cp = config.get_counterparty(cp_name)
        for keyword in _filename_keywords(cp):
            if keyword.lower() in filename:
                matches.append((cp_name, keyword))
                break

    if len(matches) == 1:
        return matches[0][0]
    return None


def _filename_keywords(counterparty_config: dict) -> list[str]:
    raw = counterparty_config.get("filename_keywords", "")
    return [part.strip() for part in raw.split(",") if part.strip()]
