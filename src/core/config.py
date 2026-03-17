import json
import os
from typing import Optional


class ConfigManager:
    def __init__(self, config_path: str):
        self._path = config_path
        with open(config_path, "r") as f:
            self._data = json.load(f)

    @property
    def archive_path(self) -> str:
        # Default ".." = folder above Settings/ = BOA3PTY Archive/ on OneDrive
        return self._data.get("archive_path", "..")

    @property
    def ignored_currencies(self) -> list[str]:
        """Upper-cased currency codes to skip when parsing WallStreet paste."""
        raw = self._data.get("ignored_currencies", "")
        return [c.strip().upper() for c in raw.split(",") if c.strip()]

    @ignored_currencies.setter
    def ignored_currencies(self, codes: list[str]):
        self._data["ignored_currencies"] = ", ".join(c.upper() for c in codes)

    @archive_path.setter
    def archive_path(self, value: str):
        self._data["archive_path"] = value

    @property
    def counterparty_names(self) -> list:
        return list(self._data.get("counterparties", {}).keys())

    def get_counterparty(self, name: str) -> dict:
        return self._data["counterparties"].get(name, {})

    def get_display_name(self, name: str) -> str:
        """Return display_name if configured, otherwise the internal key name."""
        cp = self._data.get("counterparties", {}).get(name, {})
        return cp.get("display_name") or name

    def find_by_bank_code(self, code: str) -> Optional[str]:
        """Match code against csv_bank_code (exact) or a comma-separated list of codes."""
        for name, cp in self._data.get("counterparties", {}).items():
            stored = cp.get("csv_bank_code", "")
            codes = [c.strip() for c in stored.split(",") if c.strip()]
            if code in codes:
                return name
        return None

    def find_by_ws_name(self, ws_name: str) -> Optional[str]:
        for name, cp in self._data.get("counterparties", {}).items():
            if cp.get("wallstreet_counterparty_name") == ws_name:
                return name
        return None

    def add_counterparty(self, name: str, config: dict):
        self._data.setdefault("counterparties", {})[name] = config

    def update_counterparty(self, name: str, config: dict):
        self._data["counterparties"][name] = config

    def remove_counterparty(self, name: str):
        self._data["counterparties"].pop(name, None)

    def save(self):
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)
