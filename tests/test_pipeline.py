import pytest
from founder_bot.pipeline import Pipeline, InvalidUrlError
from founder_bot.models import Lead, Draft


def _pipeline(**overrides):
    defaults = dict(
        normalize=lambda u: "https://www.linkedin.com/in/ada",
        enrich=lambda url: Lead(name="Ada", company="AE", domain="ae.com",
                                email="ada@ae.com", email_confidence="high"),
        fetch_company=lambda domain: "We build engines.",
        load_kb=lambda: "# profile\nMe.",
        draft=lambda lead, ctx, kb: Draft(subject="S", body="B"),
    )
    defaults.update(overrides)
    return Pipeline(**defaults)


def test_happy_path_builds_result():
    result = _pipeline().run("https://linkedin.com/in/ada")
    assert result.lead.email == "ada@ae.com"
    assert result.company_context == "We build engines."
    assert result.draft.subject == "S"
    assert result.warnings == []


def test_invalid_url_raises():
    with pytest.raises(InvalidUrlError):
        _pipeline(normalize=lambda u: None).run("garbage")


def test_enrich_returns_none_raises():
    with pytest.raises(RuntimeError, match="Could not identify"):
        _pipeline(enrich=lambda url: None).run("https://linkedin.com/in/ada")


def test_no_email_still_drafts_with_warning():
    lead = Lead(name="Ada", company="AE", domain="ae.com")  # no email
    result = _pipeline(enrich=lambda url: lead).run("https://linkedin.com/in/ada")
    assert result.draft is not None
    assert any("email" in w.lower() for w in result.warnings)


def test_company_fetch_failure_warns_but_continues():
    result = _pipeline(fetch_company=lambda domain: None).run("https://linkedin.com/in/ada")
    assert result.draft is not None
    assert any("company" in w.lower() for w in result.warnings)
