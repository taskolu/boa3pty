from __future__ import annotations
import os
import re
from pathlib import Path

_EMPTY_HTML_BLOCK = r"(?:<br\s*/?>|<(?:p|div)\b[^>]*>(?:\s|&nbsp;|&#160;|<[^>]+>)*</(?:p|div)>)"
_EMPTY_PREFIX_RE = re.compile(rf"^(?:\s|{_EMPTY_HTML_BLOCK})+", re.IGNORECASE)
_EMPTY_AFTER_BODY_RE = re.compile(rf"(<body\b[^>]*>)(?:\s|{_EMPTY_HTML_BLOCK})+", re.IGNORECASE)


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
        _set_sender(mail, outlook, from_address)

    # Match the working VBA pattern: display first so Outlook injects the
    # profile signature, then prepend our generated body to that signature.
    mail.Display()
    if from_address:
        _set_sender(mail, outlook, from_address)

    if is_html:
        signature_html = mail.HTMLBody or _load_default_signature_html()
        mail.HTMLBody = body.rstrip() + "<br>" + _strip_leading_signature_space(signature_html)
    else:
        signature_text = mail.Body
        mail.Body = body.rstrip() + "\n\n" + signature_text

    mail.Attachments.Add(attachment_path)
    if from_address:
        _set_sender(mail, outlook, from_address)
    return mail


def _set_sender(mail, outlook, from_address: str):
    wanted = from_address.strip()
    if not wanted:
        return

    account = _find_outlook_account(outlook, wanted)
    if account is not None:
        try:
            mail.SendUsingAccount = account
        except Exception:
            pass

    try:
        mail.SentOnBehalfOfName = wanted
    except Exception:
        pass

    _set_sender_mapi_properties(mail, wanted)


def _strip_leading_signature_space(html: str) -> str:
    cleaned = html or ""
    cleaned = _EMPTY_PREFIX_RE.sub("", cleaned)
    cleaned = _EMPTY_AFTER_BODY_RE.sub(r"\1", cleaned)
    return cleaned.lstrip()


def _find_outlook_account(outlook, from_address: str):
    wanted = from_address.strip().lower()
    if not wanted:
        return None

    try:
        accounts = outlook.Session.Accounts
    except Exception:
        return None

    for account in _iter_outlook_collection(accounts):
        try:
            values = [
                getattr(account, "SmtpAddress", ""),
                getattr(account, "DisplayName", ""),
                getattr(account, "UserName", ""),
            ]
        except Exception:
            continue

        for value in values:
            if str(value or "").strip().lower() == wanted:
                return account
    return None


def _iter_outlook_collection(collection):
    try:
        yield from collection
        return
    except TypeError:
        pass
    except Exception:
        return

    try:
        count = int(collection.Count)
    except Exception:
        return

    for index in range(1, count + 1):
        try:
            yield collection.Item(index)
        except Exception:
            continue


def _set_sender_mapi_properties(mail, from_address: str):
    try:
        accessor = mail.PropertyAccessor
    except Exception:
        return

    properties = {
        "http://schemas.microsoft.com/mapi/proptag/0x0042001F": from_address,
        "http://schemas.microsoft.com/mapi/proptag/0x0064001F": "SMTP",
        "http://schemas.microsoft.com/mapi/proptag/0x0065001F": from_address,
    }
    for key, value in properties.items():
        try:
            accessor.SetProperty(key, value)
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
