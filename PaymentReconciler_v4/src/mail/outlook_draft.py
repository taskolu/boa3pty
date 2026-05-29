from __future__ import annotations


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
    if from_address:
        _set_sender(mail, outlook, from_address)
    mail.To = to
    mail.CC = cc
    mail.Subject = subject
    mail.Attachments.Add(attachment_path)
    mail.Display(False)
    # Set after Display so Outlook can insert the user's default signature first.
    if is_html:
        mail.HTMLBody = body.rstrip() + "<br><br>" + mail.HTMLBody
    else:
        mail.Body = body.rstrip() + "\n\n" + mail.Body
    return mail


def _set_sender(mail, outlook, from_address: str):
    wanted = from_address.strip().lower()
    if not wanted:
        return

    try:
        for account in outlook.Session.Accounts:
            smtp = str(getattr(account, "SmtpAddress", "") or "").lower()
            if smtp == wanted:
                mail.SendUsingAccount = account
                return
    except Exception:
        pass

    # Shared mailboxes often appear as "send on behalf of" rather than a full account.
    try:
        mail.SentOnBehalfOfName = from_address
    except Exception:
        pass
