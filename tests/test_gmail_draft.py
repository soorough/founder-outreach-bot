from founder_bot.gmail_draft import build_message, create_draft, DRAFTS_MAILBOX
from founder_bot.models import Draft


class _FakeImap:
    def __init__(self):
        self.calls = []
    def append(self, mailbox, flags, date_time, message):
        self.calls.append((mailbox, flags, date_time, message))


def test_build_message_includes_headers_and_body():
    msg = build_message("ada@analytical.com", Draft(subject="Quick idea", body="Hi Ada,\n\nLet's talk."),
                        from_email="me@gmail.com")
    text = msg.as_bytes().decode("utf-8")
    assert "To: ada@analytical.com" in text
    assert "From: me@gmail.com" in text
    assert "Subject: Quick idea" in text
    assert "Let's talk." in text


def test_build_message_without_recipient_omits_to_header():
    msg = build_message(None, Draft(subject="S", body="B"))
    text = msg.as_bytes().decode("utf-8")
    assert "To:" not in text
    assert "Subject: S" in text


def test_create_draft_appends_to_drafts_mailbox():
    imap = _FakeImap()
    create_draft(imap, "ada@analytical.com", Draft(subject="Quick idea", body="Hello"),
                 from_email="me@gmail.com")
    assert len(imap.calls) == 1
    mailbox, flags, _date, message = imap.calls[0]
    assert mailbox == DRAFTS_MAILBOX
    assert "Draft" in flags
    decoded = message.decode("utf-8")
    assert "To: ada@analytical.com" in decoded
    assert "Subject: Quick idea" in decoded
    assert "Hello" in decoded


def test_create_draft_without_recipient_omits_to_header():
    imap = _FakeImap()
    create_draft(imap, None, Draft(subject="S", body="B"))
    _mailbox, _flags, _date, message = imap.calls[0]
    decoded = message.decode("utf-8")
    assert "To:" not in decoded
    assert "Subject: S" in decoded
