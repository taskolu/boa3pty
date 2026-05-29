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
    mail.To = to
    mail.CC = cc
    mail.Subject = subject
    mail.Attachments.Add(attachment_path)

    # Display first so Outlook inserts the user's normal default signature.
    mail.Display(False)
    signature_html = mail.HTMLBody
    signature_text = mail.Body

    # Set the shared/from mailbox after signature insertion. Setting it before
    # Display can make Outlook use the shared mailbox signature, or no signature.
    if from_address:
        _set_sender(mail, outlook, from_address)

    if is_html:
        mail.HTMLBody = body.rstrip() + "<br><br>" + signature_html
    else:
        mail.Body = body.rstrip() + "\n\n" + signature_text
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
