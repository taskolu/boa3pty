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

    def test_sharepoint_documents_folder_variant_rewrites_to_documents_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "OneDrive - Convera"
            correct = (
                root
                / "Documents - Trade Confirmations Team site"
                / "TRADE CONFIRMATION"
                / "Exotic Archives"
                / "PAGO Archive"
            )
            correct.mkdir(parents=True)

            env = {"OneDriveCommercial": str(root)}
            with patch.dict(os.environ, env, clear=True):
                resolved = resolve_archive_path(
                    "%OneDrive%/Trade Confirmations Team site - Documents/"
                    "TRADE CONFIRMATION/Exotic Archives/PAGO Archive"
                )

        self.assertEqual(resolved, os.path.normpath(str(correct)))

    def test_sharepoint_documents_folder_variant_prefers_documents_name_when_both_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "OneDrive - Convera"
            correct = (
                root
                / "Documents - Trade Confirmations Team site"
                / "TRADE CONFIRMATION"
                / "Exotic Archives"
                / "PAGO Archive"
            )
            alternate = (
                root
                / "Trade Confirmations Team site - Documents"
                / "TRADE CONFIRMATION"
                / "Exotic Archives"
                / "PAGO Archive"
            )
            correct.mkdir(parents=True)
            alternate.mkdir(parents=True)

            env = {"OneDriveCommercial": str(root)}
            with patch.dict(os.environ, env, clear=True):
                resolved = resolve_archive_path(
                    "%OneDrive%/Trade Confirmations Team site - Documents/"
                    "TRADE CONFIRMATION/Exotic Archives/PAGO Archive"
                )

        self.assertEqual(resolved, os.path.normpath(str(correct)))


if __name__ == "__main__":
    unittest.main()
