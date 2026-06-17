from founder_bot.gmail_draft import build_message, create_draft, DRAFTS_MAILBOX
from founder_bot.models import Draft


def test_build_message_attaches_pdf():
    msg = build_message("a@b.com", Draft(subject="S", body="B"),
                        attachment=("resume.pdf", b"%PDF-1.4 fake"))
    parts = list(msg.iter_attachments())
    assert len(parts) == 1
    assert parts[0].get_filename() == "resume.pdf"
    assert parts[0].get_content_type() == "application/pdf"
    assert parts[0].get_payload(decode=True) == b"%PDF-1.4 fake"


def test_build_message_no_attachment_has_none():
    msg = build_message("a@b.com", Draft(subject="S", body="B"))
    assert list(msg.iter_attachments()) == []


def test_build_message_renders_html_alternative_with_footer_links():
    footer_html = '<p><a href="https://sourav.live">Portfolio</a></p>'
    msg = build_message(
        "a@b.com", Draft(subject="S", body="Hi Ada,\n\nLet's talk."),
        footer_text="Souravh\nsourav.live", footer_html=footer_html,
    )
    html_parts = [p for p in msg.walk() if p.get_content_type() == "text/html"]
    plain_parts = [p for p in msg.walk() if p.get_content_type() == "text/plain"]
    assert html_parts and plain_parts
    html = html_parts[0].get_content()
    assert '<a href="https://sourav.live">Portfolio</a>' in html
    assert "<p>Hi Ada,</p>" in html  # body converted to HTML paragraphs
    assert "Souravh" in plain_parts[0].get_content()  # plain footer in text part


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
