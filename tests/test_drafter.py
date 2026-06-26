import pytest

from founder_bot.drafter import draft_email, _parse_draft_payload
from founder_bot.models import Lead, Draft


# --- tolerant JSON parsing (handles DeepSeek's occasional malformed output) ---

def test_parse_plain_object():
    d = _parse_draft_payload('{"subject": "S", "body": "B"}')
    assert (d.subject, d.body) == ("S", "B")


def test_parse_strips_code_fences():
    d = _parse_draft_payload('```json\n{"subject": "S", "body": "B"}\n```')
    assert (d.subject, d.body) == ("S", "B")


def test_parse_repairs_missing_closing_brace():
    # Body string is closed, but the final } was dropped (the reported bug).
    d = _parse_draft_payload('{"subject": "2x founder", "body": "Hi Lang,\\n\\nBest,\\nSouravh"')
    assert d.subject == "2x founder"
    assert d.body.endswith("Best,\nSouravh")


def test_parse_repairs_truncated_mid_body():
    # Truncated before the body's closing quote — keep what we have.
    d = _parse_draft_payload('{"subject": "Hi", "body": "Hello there')
    assert d.subject == "Hi"
    assert "Hello there" in d.body


def test_parse_ignores_trailing_prose():
    d = _parse_draft_payload('{"subject": "S", "body": "B"}\n\nHope that helps!')
    assert (d.subject, d.body) == ("S", "B")


def test_parse_allows_literal_newlines_in_body():
    # DeepSeek occasionally emits real newlines inside the string (invalid in
    # strict JSON) instead of escaped \\n.
    d = _parse_draft_payload('{"subject": "S", "body": "Hi Oleh,\n\nBest,\nSouravh"}')
    assert d.subject == "S"
    assert "Hi Oleh," in d.body and "Souravh" in d.body


def test_parse_recovers_body_with_unescaped_inner_quotes():
    # An unescaped " inside the body makes the JSON unrecoverable; salvage it.
    content = '{"subject": "Idea", "body": "I build "agentic" systems for you"}'
    d = _parse_draft_payload(content)
    assert d.subject == "Idea"
    assert "agentic" in d.body


def test_parse_unrecoverable_raises():
    with pytest.raises(ValueError):
        _parse_draft_payload("totally not json and no braces at all")


class _Message:
    content = '{"subject": "Quick idea for Analytical Engines", "body": "Hi Ada, ..."}'


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]


class _FakeCompletions:
    def __init__(self, recorder):
        self.recorder = recorder
    def create(self, **kwargs):
        self.recorder["kwargs"] = kwargs
        return _Response()


class _FakeChat:
    def __init__(self, recorder):
        self.completions = _FakeCompletions(recorder)


class _FakeClient:
    def __init__(self, recorder):
        self.chat = _FakeChat(recorder)


class _FencedMessage:
    content = '```json\n{"subject": "S", "body": "B"}\n```'


class _FencedResponse:
    choices = [type("C", (), {"message": _FencedMessage()})()]


class _FencedCompletions:
    def create(self, **kwargs):
        return _FencedResponse()


class _FencedClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _FencedCompletions()})()


def test_draft_email_tolerates_code_fences():
    draft = draft_email(client=_FencedClient(), model="deepseek-chat",
                        lead=Lead(name="Ada"), company_context=None, kb_text="kb")
    assert draft.subject == "S"
    assert draft.body == "B"


def test_draft_email_builds_prompt_and_returns_draft():
    recorder = {}
    client = _FakeClient(recorder)
    lead = Lead(name="Ada Lovelace", title="CEO", company="Analytical Engines",
                domain="analytical.com", email="ada@analytical.com")
    draft = draft_email(
        client=client,
        model="deepseek-chat",
        lead=lead,
        company_context="We build analytical engines.",
        kb_text="# profile\nI am Souravh.",
    )
    assert isinstance(draft, Draft)
    assert draft.subject == "Quick idea for Analytical Engines"
    assert draft.body == "Hi Ada, ..."
    kwargs = recorder["kwargs"]
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["response_format"] == {"type": "json_object"}
    # prompt carries the inputs
    prompt = kwargs["messages"][1]["content"]
    assert "Ada Lovelace" in prompt
    assert "Analytical Engines" in prompt
    assert "We build analytical engines." in prompt
    assert "I am Souravh." in prompt


def test_no_company_context_instructs_no_fabrication():
    recorder = {}
    draft_email(client=_FakeClient(recorder), model="deepseek-chat",
                lead=Lead(name="Ada", company="Karumi"), company_context=None, kb_text="kb")
    prompt = recorder["kwargs"]["messages"][1]["content"]
    assert "No company context is available" in prompt
    assert "Do NOT invent" in prompt
