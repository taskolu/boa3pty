import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import ConfigManager


class CounterpartyArchivePathTests(unittest.TestCase):
    def test_counterparty_archive_path_does_not_fall_back_to_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({
                "archive_path": "DEFAULT_ARCHIVE",
                "counterparties": {
                    "BOA3PTY": {"display_name": "BOA Exotic"}
                }
            }))
            cfg = ConfigManager(str(cfg_path))

            self.assertEqual(cfg.get_counterparty_archive_path("BOA3PTY"), "")

    def test_archive_paths_only_include_counterparty_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({
                "archive_path": "DEFAULT_ARCHIVE",
                "counterparties": {
                    "BOA3PTY": {
                        "display_name": "BOA Exotic",
                        "archive_path": "BOA_ARCHIVE",
                    },
                    "CITI3PTY": {
                        "display_name": "Citi Exotic",
                        "archive_path": "CITI_ARCHIVE",
                    },
                }
            }))
            cfg = ConfigManager(str(cfg_path))

            self.assertEqual(cfg.get_counterparty_archive_path("BOA3PTY"), "BOA_ARCHIVE")
            self.assertEqual(cfg.get_counterparty_name_by_display("Citi Exotic"), "CITI3PTY")
            self.assertEqual(
                cfg.get_archive_paths(),
                ["BOA_ARCHIVE", "CITI_ARCHIVE"],
            )


if __name__ == "__main__":
    unittest.main()
