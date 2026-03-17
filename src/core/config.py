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
        return self._data.get("archive_path", "./archive")

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
        for name, cp in self._data.get("counterparties", {}).items():
            if cp.get("csv_bank_code") == code:
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
