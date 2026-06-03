import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.file_types import is_supported_gpg_report_file


class FileTypeTests(unittest.TestCase):
    def test_gpg_report_file_accepts_csv_and_excel_extensions(self):
        for name in [
            "report.csv",
            "report.xls",
            "report.xlsx",
            "report.xlsm",
            "REPORT.XLSX",
        ]:
            self.assertTrue(is_supported_gpg_report_file(name), name)

    def test_gpg_report_file_rejects_other_extensions(self):
        for name in ["report.txt", "report.pdf", "report", ""]:
            self.assertFalse(is_supported_gpg_report_file(name), name)


if __name__ == "__main__":
    unittest.main()
