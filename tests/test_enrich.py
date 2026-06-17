import httpx
from founder_bot.enrich import (
    ApolloProvider, LinkedInScrapeProvider, HunterProvider, PatternGuessProvider,
    CompanyDomainResolver, DuckDuckGoDomainResolver, EnrichmentChain,
)
from founder_bot.models import Lead

URL = "https://www.linkedin.com/in/ada-lovelace"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- Apollo ---

def test_apollo_returns_lead_with_email():
    def handler(request):
        assert request.url.path == "/v1/people/match"
        return httpx.Response(200, json={
            "person": {
                "name": "Ada Lovelace",
                "title": "CEO",
                "email": "ada@analytical.com",
                "organization": {"name": "Analytical Engines", "website_url": "https://analytical.com"},
            }
        })
    provider = ApolloProvider(api_key="k", client=_client(handler))
    lead = provider.find(URL)
    assert lead.email == "ada@analytical.com"
    assert lead.name == "Ada Lovelace"
    assert lead.domain == "analytical.com"
    assert lead.email_confidence == "high"
    assert lead.source == "apollo"


def test_apollo_no_key_returns_none():
    provider = ApolloProvider(api_key=None, client=_client(lambda r: httpx.Response(500)))
    assert provider.find(URL) is None


def test_apollo_forbidden_returns_none():
    provider = ApolloProvider(api_key="k", client=_client(lambda r: httpx.Response(403)))
    assert provider.find(URL) is None


# --- LinkedIn scrape ---

def _linkedin_html(title):
    return f"<html><head><title>{title}</title></head><body>authwall</body></html>"


def test_linkedin_scrape_parses_name_and_company():
    html = _linkedin_html("Pablo Omenaca Muro - Karumi (YC F25) | LinkedIn")
    provider = LinkedInScrapeProvider(_client(lambda r: httpx.Response(200, text=html)))
    lead = provider.find(URL)
    assert lead.name == "Pablo Omenaca Muro"
    assert lead.company == "Karumi (YC F25)"
    assert lead.email is None


def test_linkedin_scrape_name_only_title():
    html = _linkedin_html("Ada Lovelace | LinkedIn")
    provider = LinkedInScrapeProvider(_client(lambda r: httpx.Response(200, text=html)))
    lead = provider.find(URL)
    assert lead.name == "Ada Lovelace"
    assert lead.company is None


def test_linkedin_scrape_http_error_returns_none():
    provider = LinkedInScrapeProvider(_client(lambda r: httpx.Response(999)))
    assert provider.find(URL) is None


# --- Hunter ---

def test_hunter_uses_company_name_and_captures_domain():
    def handler(request):
        params = dict(request.url.params)
        assert params["company"] == "Karumi"  # parenthetical stripped
        assert params["full_name"] == "Pablo Omenaca Muro"
        assert "domain" not in params
        return httpx.Response(200, json={"data": {"email": "pablo@karumi.com", "domain": "karumi.com"}})
    base = Lead(name="Pablo Omenaca Muro", company="Karumi (YC F25)")
    provider = HunterProvider(api_key="k", client=_client(handler))
    lead = provider.fill_email(base)
    assert lead.email == "pablo@karumi.com"
    assert lead.domain == "karumi.com"  # captured from Hunter
    assert lead.email_confidence == "medium"
    assert lead.source == "hunter"


def test_hunter_uses_domain_when_present():
    def handler(request):
        params = dict(request.url.params)
        assert params["domain"] == "analytical.com"
        return httpx.Response(200, json={"data": {"email": "ada@analytical.com"}})
    base = Lead(name="Ada Lovelace", company="Analytical Engines", domain="analytical.com")
    provider = HunterProvider(api_key="k", client=_client(handler))
    lead = provider.fill_email(base)
    assert lead.email == "ada@analytical.com"


def test_hunter_captures_domain_even_without_email():
    handler = lambda r: httpx.Response(200, json={"data": {"domain": "karumi.com", "email": None}})
    base = Lead(name="Pablo Omenaca Muro", company="Karumi")
    lead = HunterProvider(api_key="k", client=_client(handler)).fill_email(base)
    assert lead.email is None
    assert lead.domain == "karumi.com"


def test_hunter_no_company_or_domain_unchanged():
    base = Lead(name="Ada Lovelace")
    provider = HunterProvider(api_key="k", client=_client(lambda r: httpx.Response(500)))
    assert provider.fill_email(base).email is None


# --- Company domain resolver (Serper) ---

def test_resolver_picks_first_non_aggregator_domain():
    def handler(request):
        assert request.url.host == "google.serper.dev"
        return httpx.Response(200, json={"organic": [
            {"link": "https://www.linkedin.com/company/karumi"},   # skipped (aggregator)
            {"link": "https://www.crunchbase.com/organization/karumi"},  # skipped
            {"link": "https://karumi.ai/about"},                   # real site
        ]})
    base = Lead(name="Pablo", company="Karumi (YC F25)")
    out = CompanyDomainResolver(api_key="k", client=_client(handler)).fill_email(base)
    assert out.domain == "karumi.ai"


def test_resolver_skips_when_domain_already_known():
    base = Lead(name="Pablo", company="Karumi", domain="known.com")
    out = CompanyDomainResolver(api_key="k", client=_client(lambda r: httpx.Response(500))).fill_email(base)
    assert out.domain == "known.com"


def test_resolver_no_key_unchanged():
    base = Lead(name="Pablo", company="Karumi")
    out = CompanyDomainResolver(api_key=None, client=_client(lambda r: httpx.Response(500))).fill_email(base)
    assert out.domain is None


def test_resolver_never_sets_email():
    handler = lambda r: httpx.Response(200, json={"organic": [{"link": "https://karumi.ai"}]})
    out = CompanyDomainResolver(api_key="k", client=_client(handler)).fill_email(Lead(name="P", company="Karumi"))
    assert out.email is None


# --- DuckDuckGo domain resolver (keyless) ---

def test_ddg_resolver_picks_real_domain_from_hrefs():
    html = (
        '<a href="//duckduckgo.com/favicon.ico">x</a>'
        '<a href="https://www.ycombinator.com/companies/karumi">yc</a>'
        '<a href="https://www.karumi.ai/">site</a>'
    )
    out = DuckDuckGoDomainResolver(_client(lambda r: httpx.Response(200, text=html))).fill_email(
        Lead(name="Pablo", company="Karumi (YC F25)")
    )
    assert out.domain == "karumi.ai"


def test_ddg_resolver_skips_when_domain_known():
    out = DuckDuckGoDomainResolver(_client(lambda r: httpx.Response(500))).fill_email(
        Lead(name="Pablo", company="Karumi", domain="known.com")
    )
    assert out.domain == "known.com"


def test_ddg_resolver_no_company_unchanged():
    out = DuckDuckGoDomainResolver(_client(lambda r: httpx.Response(500))).fill_email(Lead(name="Pablo"))
    assert out.domain is None


# --- Pattern guess ---

def test_pattern_guess_builds_first_last_at_domain():
    out = PatternGuessProvider().fill_email(Lead(name="Ada Lovelace", domain="analytical.com"))
    assert out.email == "ada.lovelace@analytical.com"
    assert out.email_confidence == "low"
    assert out.source == "pattern"


def test_pattern_guess_no_domain_unchanged():
    assert PatternGuessProvider().fill_email(Lead(name="Ada Lovelace")).email is None


# --- Chain ---

class _StubIdentity:
    def __init__(self, lead): self._lead = lead
    def find(self, url): return self._lead


class _StubFiller:
    def __init__(self, name, called, email=None):
        self.name, self.called, self.email = name, called, email
    def fill_email(self, lead):
        self.called.append(self.name)
        if self.email:
            return lead.model_copy(update={"email": self.email, "email_confidence": "low", "source": "pattern"})
        return lead


def test_chain_stops_when_identity_has_email():
    called = []
    chain = EnrichmentChain(
        identity_providers=[_StubIdentity(Lead(name="Ada", email="ada@y.com", email_confidence="high"))],
        email_fillers=[_StubFiller("hunter", called)],
    )
    assert chain.run(URL).email == "ada@y.com"
    assert called == []


def test_chain_falls_through_fillers_in_order():
    called = []
    chain = EnrichmentChain(
        identity_providers=[_StubIdentity(Lead(name="Ada", company="AE"))],
        email_fillers=[_StubFiller("hunter", called), _StubFiller("pattern", called, email="x@y.com")],
    )
    lead = chain.run(URL)
    assert called == ["hunter", "pattern"]
    assert lead.email == "x@y.com"


def test_chain_second_identity_provider_used_when_first_returns_none():
    chain = EnrichmentChain(
        identity_providers=[_StubIdentity(None), _StubIdentity(Lead(name="Ada", company="AE"))],
        email_fillers=[],
    )
    assert chain.run(URL).name == "Ada"


def test_chain_all_identity_none_returns_none():
    chain = EnrichmentChain(
        identity_providers=[_StubIdentity(None), _StubIdentity(None)],
        email_fillers=[],
    )
    assert chain.run(URL) is None
