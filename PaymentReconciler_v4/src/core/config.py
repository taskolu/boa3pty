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

    def get_counterparty_archive_path(self, name: str) -> str:
        cp = self._data.get("counterparties", {}).get(name, {})
        return cp.get("archive_path") or self.archive_path

    def get_counterparty_name_by_display(self, display_name: str) -> Optional[str]:
        for name in self._data.get("counterparties", {}):
            if self.get_display_name(name) == display_name or name == display_name:
                return name
        return None

    def get_archive_paths(self) -> list[str]:
        paths = []
        if self.archive_path:
            paths.append(self.archive_path)
        for cp in self._data.get("counterparties", {}).values():
            path = cp.get("archive_path")
            if path:
                paths.append(path)
        unique = []
        seen = set()
        for path in paths:
            key = str(path).strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    def get_display_name(self, name: str) -> str:
        """Return display_name if configured, otherwise the internal key name."""
        cp = self._data.get("counterparties", {}).get(name, {})
        return cp.get("display_name") or name

    def find_by_bank_code(self, code: str) -> Optional[str]:
        """Match code against configured counterparties.

        Pass 1: exact match against stored csv_bank_code list.
        Pass 2: 3-char suffix match against counterparty internal name
                (e.g. 'NPRCUKBOA' → suffix 'BOA' → found in 'BOA3PTY').
                This means no bank codes need to be configured — any code
                ending in 'BOA' automatically routes to the BOA3PTY counterparty.
        Pass 3: 3-char suffix match against stored csv_bank_code entries
                (legacy fallback for explicitly configured bank codes).
        """
        code = (code or "").strip()
        code_upper = code.upper()
        if not code:
            return None

        counterparties = self._data.get("counterparties", {})
        # Pass 1: exact match against stored bank codes
        for name, cp in counterparties.items():
            stored = cp.get("csv_bank_code", "")
            codes = [c.strip() for c in stored.split(",") if c.strip()]
            if code_upper in {c.upper() for c in codes}:
                return name
        # Pass 2: suffix match against counterparty internal name
        if len(code) >= 3:
            suffix = code_upper[-3:]
            matches = [
                name for name in counterparties
                if suffix in name.upper()
            ]
            if len(matches) == 1:
                return matches[0]
        # Pass 3: suffix match against stored bank codes (explicit config fallback)
        if len(code) >= 3:
            suffix = code_upper[-3:]
            matches = []
            for name, cp in counterparties.items():
                stored = cp.get("csv_bank_code", "")
                codes = [c.strip() for c in stored.split(",") if c.strip()]
                if any(c.upper().endswith(suffix) for c in codes if len(c) >= 3):
                    matches.append(name)
            if len(matches) == 1:
                return matches[0]
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
