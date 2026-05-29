import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mail.outlook_draft import (
    create_outlook_draft,
    _find_outlook_account,
    _load_default_signature_html,
    _strip_leading_signature_space,
)


class OutlookDraftTests(unittest.TestCase):
    def test_create_outlook_draft_matches_vba_order_and_preserves_signature(self):
        outlook = Mock()
        mail = Mock()
        mail.HTMLBody = "<br><br><p>Signature</p>"
        outlook.CreateItem.return_value = mail

        win32com = types.ModuleType("win32com")
        client = types.ModuleType("win32com.client")
        client.Dispatch = Mock(return_value=outlook)
        win32com.client = client
        old_win32com = sys.modules.get("win32com")
        old_client = sys.modules.get("win32com.client")
        sys.modules["win32com"] = win32com
        sys.modules["win32com.client"] = client
        try:
            result = create_outlook_draft(
                to="paymentsrelease@convera.com",
                cc="treasuryconfirms@convera.com",
                subject="Payment Breakdown",
                body="<br><br><table></table>",
                attachment_path="report.xlsx",
                from_address="TreasuryConfirms@convera.com",
                is_html=True,
            )
        finally:
            if old_win32com is None:
                sys.modules.pop("win32com", None)
            else:
                sys.modules["win32com"] = old_win32com
            if old_client is None:
                sys.modules.pop("win32com.client", None)
            else:
                sys.modules["win32com.client"] = old_client

        self.assertIs(result, mail)
        outlook.CreateItem.assert_called_once_with(0)
        self.assertEqual(mail.Subject, "Payment Breakdown")
        self.assertEqual(mail.To, "paymentsrelease@convera.com")
        self.assertEqual(mail.CC, "treasuryconfirms@convera.com")
        self.assertEqual(mail.SentOnBehalfOfName, "TreasuryConfirms@convera.com")
        mail.Display.assert_called_once_with()
        self.assertEqual(mail.HTMLBody, "<br><br><table></table><br><p>Signature</p>")
        mail.Attachments.Add.assert_called_once_with("report.xlsx")

    def test_find_outlook_account_matches_smtp_address(self):
        wanted = SimpleNamespace(
            SmtpAddress="TreasuryConfirms@Convera.com",
            DisplayName="TreasuryConfirms",
            UserName="TreasuryConfirms",
        )
        other = SimpleNamespace(
            SmtpAddress="AbduTas@Convera.com",
            DisplayName="AbduTas",
            UserName="AbduTas",
        )
        outlook = SimpleNamespace(Session=SimpleNamespace(Accounts=[other, wanted]))

        self.assertIs(_find_outlook_account(outlook, "treasuryconfirms@convera.com"), wanted)

    def test_strip_leading_signature_space_removes_outlook_empty_paragraphs(self):
        signature = (
            "<html><body>"
            "<p class=MsoNormal>&nbsp;</p>"
            "<div><br></div>"
            "<p class=MsoNormal><span>&nbsp;</span><o:p>&nbsp;</o:p></p>"
            "<p>Regards,</p>"
            "</body></html>"
        )

        cleaned = _strip_leading_signature_space(signature)

        self.assertNotIn("&nbsp;</p><div><br></div>", cleaned)
        self.assertIn("<body><p>Regards,</p>", cleaned)

    def test_signature_html_gets_base_uri_for_relative_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp)
            sig_dir = appdata / "Microsoft" / "Signatures"
            sig_dir.mkdir(parents=True)
            (sig_dir / "Treasury.htm").write_text(
                "<html><head></head><body><img src=\"Treasury_files/image001.png\"></body></html>",
                encoding="utf-8",
            )

            old_appdata = os.environ.get("APPDATA")
            os.environ["APPDATA"] = str(appdata)
            try:
                html = _load_default_signature_html()
            finally:
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata

        self.assertIn("<base href=", html)
        self.assertIn(sig_dir.as_uri(), html)


if __name__ == "__main__":
    unittest.main()
