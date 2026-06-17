import html as _html
import imaplib
import time
from email.message import EmailMessage
from typing import Optional

from founder_bot.models import Draft

IMAP_HOST = "imap.gmail.com"
DRAFTS_MAILBOX = "[Gmail]/Drafts"

# Attachment = (filename, raw_bytes); attached as application/pdf.
Attachment = tuple[str, bytes]


def _body_to_html(text: str) -> str:
    """Convert plain email body text to simple HTML (paragraphs + line breaks)."""
    paragraphs = _html.escape(text).split("\n\n")
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())


def build_message(
    to_email: Optional[str],
    draft: Draft,
    from_email: Optional[str] = None,
    attachment: Optional[Attachment] = None,
    footer_text: str = "",
    footer_html: str = "",
) -> EmailMessage:
    """Build a MIME message from a Draft as plain text + an HTML alternative
    (so footer links are clickable), optionally with a PDF attachment.
    """
    message = EmailMessage()
    message["Subject"] = draft.subject
    if from_email:
        message["From"] = from_email
    if to_email:
        message["To"] = to_email

    plain = draft.body + (f"\n\n{footer_text}" if footer_text else "")
    message.set_content(plain)

    html_content = _body_to_html(draft.body) + (footer_html or "")
    message.add_alternative(html_content, subtype="html")

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
    footer_text: str = "",
    footer_html: str = "",
) -> None:
    """Append a draft to the Gmail Drafts folder over IMAP."""
    message = build_message(to_email, draft, from_email, attachment, footer_text, footer_html)
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
