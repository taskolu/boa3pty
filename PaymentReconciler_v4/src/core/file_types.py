from __future__ import annotations
from pathlib import Path


SUPPORTED_GPG_REPORT_EXTENSIONS = {".csv", ".xls", ".xlsx", ".xlsm"}


def is_supported_gpg_report_file(path: str) -> bool:
    return Path(path or "").suffix.lower() in SUPPORTED_GPG_REPORT_EXTENSIONS
