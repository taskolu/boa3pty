import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.app_dir import resolve_archive_path


class OneDrivePathTests(unittest.TestCase):
    def test_percent_onedrive_prefers_commercial_root_when_available(self):
        env = {
            "OneDrive": "/personal/OneDrive",
            "OneDriveCommercial": "/work/OneDrive - Convera",
        }
        with patch.dict(os.environ, env, clear=True):
            resolved = resolve_archive_path(
                "%OneDrive%/Documents - Trade Confirmations Team site/TRADE CONFIRMATION"
            )

        self.assertEqual(
            resolved,
            os.path.normpath(
                "/work/OneDrive - Convera/"
                "Documents - Trade Confirmations Team site/TRADE CONFIRMATION"
            ),
        )

    def test_sharepoint_documents_folder_variant_uses_existing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "OneDrive - Convera"
            existing = (
                root
                / "Trade Confirmations Team site - Documents"
                / "TRADE CONFIRMATION"
                / "Exotic Archives"
                / "PAGO Archive"
            )
            existing.mkdir(parents=True)

            env = {"OneDriveCommercial": str(root)}
            with patch.dict(os.environ, env, clear=True):
                resolved = resolve_archive_path(
                    "%OneDrive%/Documents - Trade Confirmations Team site/"
                    "TRADE CONFIRMATION/Exotic Archives/PAGO Archive"
                )

        self.assertEqual(resolved, os.path.normpath(str(existing)))

    def test_sharepoint_documents_folder_variant_prefers_canonical_when_both_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "OneDrive - Convera"
            wrong = (
                root
                / "Documents - Trade Confirmations Team site"
                / "TRADE CONFIRMATION"
                / "Exotic Archives"
                / "PAGO Archive"
            )
            canonical = (
                root
                / "Trade Confirmations Team site - Documents"
                / "TRADE CONFIRMATION"
                / "Exotic Archives"
                / "PAGO Archive"
            )
            wrong.mkdir(parents=True)
            canonical.mkdir(parents=True)

            env = {"OneDriveCommercial": str(root)}
            with patch.dict(os.environ, env, clear=True):
                resolved = resolve_archive_path(
                    "%OneDrive%/Documents - Trade Confirmations Team site/"
                    "TRADE CONFIRMATION/Exotic Archives/PAGO Archive"
                )

        self.assertEqual(resolved, os.path.normpath(str(canonical)))


if __name__ == "__main__":
    unittest.main()
