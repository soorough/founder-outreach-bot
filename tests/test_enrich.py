import httpx
from founder_bot.enrich import ApolloProvider, HunterProvider, PatternGuessProvider, EnrichmentChain
from founder_bot.models import Lead

URL = "https://www.linkedin.com/in/ada-lovelace"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


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
    assert lead.title == "CEO"
    assert lead.company == "Analytical Engines"
    assert lead.domain == "analytical.com"
    assert lead.email_confidence == "high"
    assert lead.source == "apollo"


def test_apollo_no_email_returns_lead_without_email():
    def handler(request):
        return httpx.Response(200, json={"person": {
            "name": "Ada Lovelace", "title": "CEO",
            "organization": {"name": "Analytical Engines", "website_url": "https://analytical.com"},
        }})
    provider = ApolloProvider(api_key="k", client=_client(handler))
    lead = provider.find(URL)
    assert lead.email is None
    assert lead.domain == "analytical.com"


def test_apollo_no_key_returns_none():
    provider = ApolloProvider(api_key=None, client=_client(lambda r: httpx.Response(500)))
    assert provider.find(URL) is None


def test_apollo_http_error_returns_none():
    provider = ApolloProvider(api_key="k", client=_client(lambda r: httpx.Response(429)))
    assert provider.find(URL) is None


def test_hunter_finds_email_from_existing_lead():
    def handler(request):
        assert request.url.path == "/v2/email-finder"
        params = dict(request.url.params)
        assert params["domain"] == "analytical.com"
        assert params["full_name"] == "Ada Lovelace"
        return httpx.Response(200, json={"data": {"email": "ada@analytical.com", "score": 92}})
    base = Lead(name="Ada Lovelace", company="Analytical Engines", domain="analytical.com")
    provider = HunterProvider(api_key="k", client=_client(handler))
    lead = provider.fill_email(base)
    assert lead.email == "ada@analytical.com"
    assert lead.email_confidence == "medium"
    assert lead.source == "hunter"


def test_hunter_no_domain_returns_input_unchanged():
    base = Lead(name="Ada Lovelace")
    provider = HunterProvider(api_key="k", client=_client(lambda r: httpx.Response(500)))
    assert provider.fill_email(base).email is None


def test_pattern_guess_builds_first_last_at_domain():
    base = Lead(name="Ada Lovelace", domain="analytical.com")
    out = PatternGuessProvider().fill_email(base)
    assert out.email == "ada.lovelace@analytical.com"
    assert out.email_confidence == "low"
    assert out.source == "pattern"


def test_pattern_guess_no_domain_unchanged():
    base = Lead(name="Ada Lovelace")
    assert PatternGuessProvider().fill_email(base).email is None


class _StubApollo:
    def __init__(self, lead): self._lead = lead
    def find(self, url): return self._lead

class _StubHunter:
    def __init__(self, called): self.called = called
    def fill_email(self, lead):
        self.called.append("hunter")
        return lead

class _StubPattern:
    def __init__(self, called): self.called = called
    def fill_email(self, lead):
        self.called.append("pattern")
        return lead.model_copy(update={"email": "x@y.com", "email_confidence": "low", "source": "pattern"})


def test_chain_stops_when_apollo_has_email():
    called = []
    chain = EnrichmentChain(
        apollo=_StubApollo(Lead(name="Ada", domain="y.com", email="ada@y.com", email_confidence="high")),
        hunter=_StubHunter(called),
        pattern=_StubPattern(called),
    )
    lead = chain.run(URL)
    assert lead.email == "ada@y.com"
    assert called == []  # neither fallback ran


def test_chain_falls_through_to_pattern():
    called = []
    chain = EnrichmentChain(
        apollo=_StubApollo(Lead(name="Ada", domain="y.com")),  # no email
        hunter=_StubHunter(called),                            # leaves it unchanged
        pattern=_StubPattern(called),
    )
    lead = chain.run(URL)
    assert called == ["hunter", "pattern"]
    assert lead.email == "x@y.com"


def test_chain_apollo_returns_none():
    chain = EnrichmentChain(
        apollo=_StubApollo(None),
        hunter=_StubHunter([]),
        pattern=_StubPattern([]),
    )
    assert chain.run(URL) is None
