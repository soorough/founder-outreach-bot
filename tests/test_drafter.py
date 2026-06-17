from founder_bot.drafter import draft_email
from founder_bot.models import Lead, Draft


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
