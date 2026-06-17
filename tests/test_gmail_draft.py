import base64
from founder_bot.gmail_draft import create_draft
from founder_bot.models import Draft


class _FakeCreate:
    def __init__(self, recorder, *, userId, body):
        recorder["userId"] = userId
        recorder["body"] = body
    def execute(self):
        return {"id": "draft_123"}


class _FakeDrafts:
    def __init__(self, recorder): self.recorder = recorder
    def create(self, *, userId, body):
        return _FakeCreate(self.recorder, userId=userId, body=body)


class _FakeUsers:
    def __init__(self, recorder): self._drafts = _FakeDrafts(recorder)
    def drafts(self): return self._drafts


class _FakeService:
    def __init__(self, recorder): self._users = _FakeUsers(recorder)
    def users(self): return self._users


def test_create_draft_encodes_message_and_calls_api():
    recorder = {}
    draft = Draft(subject="Quick idea", body="Hi Ada,\n\nLet's talk.")
    draft_id = create_draft(
        service=_FakeService(recorder),
        to_email="ada@analytical.com",
        draft=draft,
    )
    assert draft_id == "draft_123"
    assert recorder["userId"] == "me"
    raw = recorder["body"]["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw).decode("utf-8")
    assert "To: ada@analytical.com" in decoded
    assert "Subject: Quick idea" in decoded
    assert "Let's talk." in decoded


def test_create_draft_without_recipient_omits_to_header():
    recorder = {}
    draft = Draft(subject="S", body="B")
    create_draft(service=_FakeService(recorder), to_email=None, draft=draft)
    decoded = base64.urlsafe_b64decode(recorder["body"]["message"]["raw"]).decode("utf-8")
    assert "To:" not in decoded
    assert "Subject: S" in decoded
