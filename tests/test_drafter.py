from founder_bot.drafter import draft_email
from founder_bot.models import Lead, Draft


class _FakeMessages:
    def __init__(self, recorder):
        self.recorder = recorder
    def parse(self, **kwargs):
        self.recorder["kwargs"] = kwargs
        class _Resp:
            parsed_output = Draft(subject="Quick idea for Analytical Engines",
                                  body="Hi Ada, ...")
        return _Resp()


class _FakeClient:
    def __init__(self, recorder):
        self.messages = _FakeMessages(recorder)


def test_draft_email_builds_prompt_and_returns_draft():
    recorder = {}
    client = _FakeClient(recorder)
    lead = Lead(name="Ada Lovelace", title="CEO", company="Analytical Engines",
                domain="analytical.com", email="ada@analytical.com")
    draft = draft_email(
        client=client,
        lead=lead,
        company_context="We build analytical engines.",
        kb_text="# profile\nI am Souravh.",
    )
    assert isinstance(draft, Draft)
    assert draft.subject == "Quick idea for Analytical Engines"
    kwargs = recorder["kwargs"]
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["output_format"] is Draft
    # prompt carries the inputs
    prompt = kwargs["messages"][0]["content"]
    assert "Ada Lovelace" in prompt
    assert "Analytical Engines" in prompt
    assert "We build analytical engines." in prompt
    assert "I am Souravh." in prompt
