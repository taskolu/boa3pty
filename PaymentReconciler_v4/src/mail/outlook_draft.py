from __future__ import annotations
import os
from pathlib import Path


def create_outlook_draft(
    *,
    to: str,
    cc: str,
    subject: str,
    body: str,
    attachment_path: str,
    from_address: str = "",
    is_html: bool = False,
):
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError(
            "Outlook draft creation requires pywin32. "
            "Rebuild after installing requirements_v2.txt on Windows."
        ) from exc

    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.To = to
    mail.CC = cc
    if from_address:
        _set_sender(mail, from_address)

    # Match the working VBA pattern: display first so Outlook injects the
    # profile signature, then prepend our generated body to that signature.
    mail.Display()
    if from_address:
        _set_sender(mail, from_address)

    if is_html:
        signature_html = mail.HTMLBody or _load_default_signature_html()
        mail.HTMLBody = body.rstrip() + signature_html
    else:
        signature_text = mail.Body
        mail.Body = body.rstrip() + "\n\n" + signature_text

    mail.Attachments.Add(attachment_path)
    if from_address:
        _set_sender(mail, from_address)
    return mail


def _set_sender(mail, from_address: str):
    wanted = from_address.strip()
    if not wanted:
        return

    try:
        mail.SentOnBehalfOfName = wanted
    except Exception:
        pass


def _load_default_signature_html() -> str:
    sig_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Signatures"
    if not sig_dir.exists():
        return ""

    candidates = sorted(
        sig_dir.glob("*.htm"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            return _add_signature_base_uri(path.read_text(encoding="utf-8", errors="ignore"), path.parent)
        except Exception:
            continue
    return ""


def _add_signature_base_uri(html: str, signature_dir: Path) -> str:
    if "<base " in html.lower():
        return html

    base = f'<base href="{signature_dir.as_uri()}/">'
    lower = html.lower()
    head_idx = lower.find("<head")
    if head_idx < 0:
        return base + html

    head_end = lower.find(">", head_idx)
    if head_end < 0:
        return base + html
    return html[: head_end + 1] + base + html[head_end + 1 :]
