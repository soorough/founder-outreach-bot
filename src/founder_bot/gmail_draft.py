import base64
from email.message import EmailMessage
from typing import Optional

from founder_bot.models import Draft


def create_draft(service, to_email: Optional[str], draft: Draft) -> str:
    """Create a Gmail draft from a Draft. Returns the created draft id."""
    message = EmailMessage()
    message["Subject"] = draft.subject
    if to_email:
        message["To"] = to_email
    message.set_content(draft.body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    created = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return created["id"]


from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def build_service(token_path: str):
    """Build an authenticated Gmail service from a token.json produced by auth_gmail.py."""
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build("gmail", "v1", credentials=creds)
