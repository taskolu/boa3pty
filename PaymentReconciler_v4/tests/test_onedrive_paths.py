import os
import sys
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


if __name__ == "__main__":
    unittest.main()
