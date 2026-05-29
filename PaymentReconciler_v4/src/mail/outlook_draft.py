from __future__ import annotations


def create_outlook_draft(
    *,
    to: str,
    cc: str,
    subject: str,
    body: str,
    attachment_path: str,
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
    mail.Display(False)
    # Set after Display so Outlook can insert the user's default signature first.
    mail.Body = body.rstrip() + "\n\n" + mail.Body
    return mail
