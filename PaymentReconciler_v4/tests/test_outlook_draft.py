import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mail.outlook_draft import _create_mail_item, _load_default_signature_html


class OutlookDraftTests(unittest.TestCase):
    def test_create_mail_item_uses_shared_drafts_for_from_address(self):
        outlook = Mock()
        recipient = Mock()
        recipient.Resolved = True
        drafts = Mock()
        shared_mail = Mock()

        outlook.Session.CreateRecipient.return_value = recipient
        outlook.Session.GetSharedDefaultFolder.return_value = drafts
        drafts.Items.Add.return_value = shared_mail

        mail = _create_mail_item(outlook, "TreasuryConfirms@convera.com")

        self.assertIs(mail, shared_mail)
        outlook.Session.CreateRecipient.assert_called_once_with("TreasuryConfirms@convera.com")
        recipient.Resolve.assert_called_once()
        outlook.Session.GetSharedDefaultFolder.assert_called_once_with(recipient, 16)
        drafts.Items.Add.assert_called_once_with("IPM.Note")
        outlook.CreateItem.assert_not_called()

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
