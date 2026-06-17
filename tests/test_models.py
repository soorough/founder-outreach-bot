from founder_bot.models import Lead, Draft, Result


def test_lead_defaults():
    lead = Lead(name="Ada Lovelace")
    assert lead.name == "Ada Lovelace"
    assert lead.email is None
    assert lead.email_confidence == "none"
    assert lead.source is None


def test_draft_fields():
    draft = Draft(subject="Hi", body="Hello there")
    assert draft.subject == "Hi"
    assert draft.body == "Hello there"


def test_result_holds_parts():
    lead = Lead(name="Ada Lovelace", email="ada@x.com", email_confidence="high")
    draft = Draft(subject="Hi", body="Body")
    result = Result(lead=lead, company_context="ctx", draft=draft, warnings=["w"])
    assert result.lead.email == "ada@x.com"
    assert result.warnings == ["w"]
