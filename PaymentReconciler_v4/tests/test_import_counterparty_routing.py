import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import ConfigManager
from src.core.counterparty_routing import matched_counterparty_for_bank_code


class ImportCounterpartyRoutingTests(unittest.TestCase):
    def test_upload_uses_inventory_code_match_not_current_loop_counterparty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({
                "counterparties": {
                    "BOA3PTY": {"csv_bank_code": "BOA-CODE"},
                    "PAGONXT": {"csv_bank_code": "PAGONXT-CODE"},
                }
            }))
            cfg = ConfigManager(str(cfg_path))

            matched = matched_counterparty_for_bank_code(cfg, "BOA-CODE", "PAGONXT")

        self.assertEqual(matched, "BOA3PTY")

    def test_inventory_code_exact_match_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({
                "counterparties": {
                    "BOA3PTY": {"csv_bank_code": "ALLCUKBOA"},
                    "PAGONXT": {"csv_bank_code": "PAGONXT-CODE"},
                }
            }))
            cfg = ConfigManager(str(cfg_path))

            self.assertEqual(cfg.find_by_bank_code("allcukboa"), "BOA3PTY")

    def test_suffix_fallback_does_not_guess_when_multiple_counterparties_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({
                "counterparties": {
                    "BOA3PTY": {"csv_bank_code": "ALLCUKBOA"},
                    "SECOND_BOA": {"csv_bank_code": "MGACUKBOA"},
                }
            }))
            cfg = ConfigManager(str(cfg_path))

            self.assertIsNone(cfg.find_by_bank_code("UNKNOWNBOA"))

    def test_specific_boa_mxn_code_overrides_boa_catchall(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({
                "counterparties": {
                    "BOA3PTY": {"csv_bank_code": ""},
                    "BOA Exotic MXN": {"csv_bank_code": "MXNCUKBOA"},
                }
            }))
            cfg = ConfigManager(str(cfg_path))

            self.assertEqual(cfg.find_by_bank_code("MXNCUKBOA"), "BOA Exotic MXN")

    def test_non_mxn_boa_codes_use_blank_code_boa_catchall(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({
                "counterparties": {
                    "BOA3PTY": {"csv_bank_code": ""},
                    "BOA Exotic MXN": {"csv_bank_code": "MXNCUKBOA"},
                    "PAGONXT": {"csv_bank_code": "BRLCUKPAGO,CNYCUKPAGO"},
                }
            }))
            cfg = ConfigManager(str(cfg_path))

            self.assertEqual(cfg.find_by_bank_code("ALLCUKBOA"), "BOA3PTY")
            self.assertEqual(cfg.find_by_bank_code("NPRCUKBOA"), "BOA3PTY")


if __name__ == "__main__":
    unittest.main()
