import imaplib
import time
from email.message import EmailMessage
from typing import Optional

from founder_bot.models import Draft

IMAP_HOST = "imap.gmail.com"
DRAFTS_MAILBOX = "[Gmail]/Drafts"

# Attachment = (filename, raw_bytes); attached as application/pdf.
Attachment = tuple[str, bytes]


def build_message(
    to_email: Optional[str],
    draft: Draft,
    from_email: Optional[str] = None,
    attachment: Optional[Attachment] = None,
) -> EmailMessage:
    """Build a MIME message from a Draft, optionally with a PDF attachment."""
    message = EmailMessage()
    message["Subject"] = draft.subject
    if from_email:
        message["From"] = from_email
    if to_email:
        message["To"] = to_email
    message.set_content(draft.body)
    if attachment:
        filename, data = attachment
        message.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    return message


def create_draft(
    imap,
    to_email: Optional[str],
    draft: Draft,
    from_email: Optional[str] = None,
    attachment: Optional[Attachment] = None,
) -> None:
    """Append a draft to the Gmail Drafts folder over IMAP."""
    message = build_message(to_email, draft, from_email, attachment)
    imap.append(
        DRAFTS_MAILBOX,
        "\\Draft",
        imaplib.Time2Internaldate(time.time()),
        message.as_bytes(),
    )


def connect(email_addr: str, app_password: str) -> imaplib.IMAP4_SSL:
    """Open an authenticated IMAP connection to Gmail using an app password."""
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(email_addr, app_password)
    return imap
