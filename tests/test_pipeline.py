import pytest
from founder_bot.pipeline import Pipeline, InvalidUrlError
from founder_bot.models import Lead, Draft


def _pipeline(**overrides):
    defaults = dict(
        normalize=lambda u: "https://www.linkedin.com/in/ada",
        enrich=lambda url: Lead(name="Ada", company="AE", domain="ae.com",
                                email="ada@ae.com", email_confidence="high"),
        verify_email=lambda lead: lead,
        find_team=lambda lead: [],
        fetch_company=lambda domain: "We build engines.",
        load_kb=lambda: "# profile\nMe.",
        draft=lambda lead, ctx, kb: Draft(subject=f"S-{lead.name}", body="B"),
        signature="",
    )
    defaults.update(overrides)
    return Pipeline(**defaults)


def test_signature_footer_appended_to_body():
    results = _pipeline(signature="Souravh\nsourav.live").run("https://linkedin.com/in/ada")
    assert results[0].draft.body.endswith("Souravh\nsourav.live")
    assert results[0].draft.body.startswith("B")


def test_happy_path_returns_single_primary_result():
    results = _pipeline().run("https://linkedin.com/in/ada")
    assert len(results) == 1
    assert results[0].lead.email == "ada@ae.com"
    assert results[0].company_context == "We build engines."
    assert results[0].draft.subject == "S-Ada"
    assert results[0].warnings == []


def test_invalid_url_raises():
    with pytest.raises(InvalidUrlError):
        _pipeline(normalize=lambda u: None).run("garbage")


def test_enrich_returns_none_raises():
    with pytest.raises(RuntimeError, match="Could not identify"):
        _pipeline(enrich=lambda url: None).run("https://linkedin.com/in/ada")


def test_no_email_still_drafts_with_warning():
    lead = Lead(name="Ada", company="AE", domain="ae.com")  # no email
    results = _pipeline(enrich=lambda url: lead).run("https://linkedin.com/in/ada")
    assert results[0].draft is not None
    assert any("email" in w.lower() for w in results[0].warnings)


def test_company_fetch_failure_warns_but_continues():
    results = _pipeline(fetch_company=lambda domain: None).run("https://linkedin.com/in/ada")
    assert results[0].draft is not None
    assert any("company" in w.lower() for w in results[0].warnings)


def test_verify_email_is_applied_to_primary():
    def verify(lead):
        return lead.model_copy(update={"email_status": "valid", "email_confidence": "high"})
    results = _pipeline(verify_email=verify).run("https://linkedin.com/in/ada")
    assert results[0].lead.email_status == "valid"


def test_cofounders_each_get_their_own_result():
    cofounders = [
        Lead(name="Bob", title="CTO", company="AE", domain="ae.com", email="bob@ae.com"),
        Lead(name="Cara", title="COO", company="AE", domain="ae.com", email="cara@ae.com"),
    ]
    results = _pipeline(find_team=lambda lead: cofounders).run("https://linkedin.com/in/ada")
    assert len(results) == 3
    assert [r.lead.name for r in results] == ["Ada", "Bob", "Cara"]
    # each got its own draft
    assert results[1].draft.subject == "S-Bob"
    assert results[2].draft.subject == "S-Cara"


def test_invalid_email_status_warns():
    def verify(lead):
        return lead.model_copy(update={"email_status": "accept_all"})
    results = _pipeline(verify_email=verify).run("https://linkedin.com/in/ada")
    assert any("accept_all" in w for w in results[0].warnings)
