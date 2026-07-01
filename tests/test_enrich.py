import httpx
from founder_bot.enrich import (
    ApolloProvider, LinkedInScrapeProvider, HunterProvider, PatternGuessProvider,
    CompanyDomainResolver, DuckDuckGoDomainResolver, EmailVerifier, TeamFinder,
    EnrichmentChain, ProxycurlProvider, SerperIdentityProvider, SlugNameProvider,
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


def test_apollo_prefers_primary_domain_over_website_url():
    def handler(request):
        return httpx.Response(200, json={"person": {
            "name": "Sahil Dhull", "title": "Founder",
            "organization": {"name": "Kyra", "primary_domain": "kyra.co",
                             "website_url": "https://shop.kyra.co/collections/all"},
        }})
    lead = ApolloProvider(api_key="k", client=_client(handler)).find(URL)
    assert lead.domain == "kyra.co"          # canonical company domain, not the shop URL host
    assert lead.company == "Kyra"


def test_apollo_ignores_locked_email_placeholder():
    def handler(request):
        return httpx.Response(200, json={"person": {
            "name": "Sahil Dhull", "email": "email_not_unlocked@domain.com",
            "organization": {"name": "Kyra", "primary_domain": "kyra.co"},
        }})
    lead = ApolloProvider(api_key="k", client=_client(handler)).find(URL)
    assert lead.email is None                # placeholder dropped
    assert lead.domain == "kyra.co"          # but the real domain still flows through
    assert lead.email_confidence == "none"


# --- Proxycurl (paid, authoritative current employer) ---

def test_proxycurl_returns_current_employer_from_work_history():
    def handler(request):
        assert request.url.host == "nubela.co"
        assert request.url.params["url"] == URL
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(200, json={
            "first_name": "Sahil", "last_name": "Dhull",
            "experiences": [
                {"company": "KYRA", "title": "Founder", "ends_at": None,
                 "company_website": "https://thekyra.com"},
                {"company": "OldCo", "title": "Engineer", "ends_at": {"year": 2022}},
            ],
        })
    lead = ProxycurlProvider(api_key="k", client=_client(handler)).find(URL)
    assert lead.name == "Sahil Dhull"
    assert lead.company == "KYRA"           # real current employer, not a headline
    assert lead.title == "Founder"
    assert lead.domain == "thekyra.com"     # from company_website when present


def test_proxycurl_no_key_returns_none():
    assert ProxycurlProvider(api_key=None, client=_client(lambda r: httpx.Response(500))).find(URL) is None


def test_proxycurl_http_error_returns_none():
    assert ProxycurlProvider(api_key="k", client=_client(lambda r: httpx.Response(402))).find(URL) is None


# --- LinkedIn scrape ---

def _linkedin_html(title):
    return f"<html><head><title>{title}</title></head><body>authwall</body></html>"


def test_linkedin_scrape_parses_name_and_company():
    html = _linkedin_html("Pablo Omenaca Muro - Karumi (YC F25) | LinkedIn")
    provider = LinkedInScrapeProvider(_client(lambda r: httpx.Response(200, text=html)))
    lead = provider.find(URL)
    assert lead.name == "Pablo Omenaca Muro"
    assert lead.company == "Karumi"          # accolade parenthetical stripped
    assert lead.email is None


def test_linkedin_scrape_name_only_title():
    html = _linkedin_html("Ada Lovelace | LinkedIn")
    provider = LinkedInScrapeProvider(_client(lambda r: httpx.Response(200, text=html)))
    lead = provider.find(URL)
    assert lead.name == "Ada Lovelace"
    assert lead.company is None


def test_linkedin_scrape_cleans_polluted_headline_and_dash_trailer():
    # Real-world title: "- LinkedIn" trailer + role prefix + accolades.
    html = _linkedin_html("Sasha Collin - Building Lemrock | YC S24 | Forbes 30u30 - LinkedIn")
    provider = LinkedInScrapeProvider(_client(lambda r: httpx.Response(200, text=html)))
    lead = provider.find(URL)
    assert lead.name == "Sasha Collin"
    assert lead.company == "Lemrock"         # not "...Forbes 30u30 - LinkedIn"


def test_linkedin_scrape_strips_role_prefix():
    html = _linkedin_html("Jane Doe - Founder at Acme Corp | LinkedIn")
    lead = LinkedInScrapeProvider(_client(lambda r: httpx.Response(200, text=html))).find(URL)
    assert lead.company == "Acme Corp"


def test_linkedin_scrape_generic_headline_is_not_a_company():
    html = _linkedin_html("Martin Lopez - Professional Profile | LinkedIn")
    lead = LinkedInScrapeProvider(_client(lambda r: httpx.Response(200, text=html))).find(URL)
    assert lead.name == "Martin Lopez"
    assert lead.company is None              # placeholder, not a real employer


def test_linkedin_scrape_http_error_returns_none():
    provider = LinkedInScrapeProvider(_client(lambda r: httpx.Response(999)))
    assert provider.find(URL) is None


# --- Serper identity (robust against the 999 block) ---

def test_serper_identity_parses_name_and_company_from_indexed_title():
    def handler(request):
        assert request.url.host == "google.serper.dev"
        assert "lang-li-7a193a328" in request.read().decode()
        return httpx.Response(200, json={"organic": [
            {"title": "Some Article", "link": "https://example.com/x"},
            {"title": "Lang Li - Acme Robotics | LinkedIn",
             "link": "https://www.linkedin.com/in/lang-li-7a193a328"},
        ]})
    provider = SerperIdentityProvider(api_key="k", client=_client(handler))
    lead = provider.find("https://www.linkedin.com/in/lang-li-7a193a328/")
    assert lead.name == "Lang Li"
    assert lead.company == "Acme Robotics"
    assert lead.email is None


def test_serper_identity_no_key_returns_none():
    provider = SerperIdentityProvider(api_key=None, client=_client(lambda r: httpx.Response(500)))
    assert provider.find(URL) is None


def test_serper_identity_http_error_returns_none():
    provider = SerperIdentityProvider(api_key="k", client=_client(lambda r: httpx.Response(429)))
    assert provider.find(URL) is None


def test_serper_identity_no_linkedin_result_returns_none():
    handler = lambda r: httpx.Response(200, json={"organic": [
        {"title": "Unrelated", "link": "https://example.com"}]})
    assert SerperIdentityProvider(api_key="k", client=_client(handler)).find(URL) is None


# --- Slug name (last resort) ---

def test_slug_name_drops_hash_and_titlecases():
    lead = SlugNameProvider().find("https://www.linkedin.com/in/lang-li-7a193a328/")
    assert lead.name == "Lang Li"
    assert lead.company is None


def test_slug_name_clean_vanity_slug():
    lead = SlugNameProvider().find("https://www.linkedin.com/in/pablo-omenaca-muro?utm_source=share")
    assert lead.name == "Pablo Omenaca Muro"


def test_slug_name_no_alpha_tokens_returns_none():
    assert SlugNameProvider().find("https://www.linkedin.com/in/12345/") is None


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


def test_resolver_query_includes_person_name_for_disambiguation():
    seen = {}
    def handler(request):
        seen["q"] = request.read().decode()
        return httpx.Response(200, json={"organic": [{"link": "https://kyra.co"}]})
    CompanyDomainResolver(api_key="k", client=_client(handler)).fill_email(
        Lead(name="Sahil Dhull", company="Kyra")
    )
    assert "Kyra" in seen["q"] and "Sahil Dhull" in seen["q"]  # name disambiguates the brand


def test_resolver_skips_wellfound_and_prefers_name_match():
    # Revley's Wellfound listing ranks first, but it's a directory; the real
    # name-matching site (revley.io) should win.
    def handler(request):
        return httpx.Response(200, json={"organic": [
            {"link": "https://wellfound.com/company/revley"},   # directory, skipped
            {"link": "https://news.example.com/revley-raises"}, # generic, no name match
            {"link": "https://revley.io/about"},                # real site, name match
        ]})
    out = CompanyDomainResolver(api_key="k", client=_client(handler)).fill_email(
        Lead(name="Lang Li", company="Revley")
    )
    assert out.domain == "revley.io"


def test_resolver_falls_back_to_first_when_no_name_match():
    handler = lambda r: httpx.Response(200, json={"organic": [
        {"link": "https://getsomeapp.com"}, {"link": "https://another.com"}]})
    out = CompanyDomainResolver(api_key="k", client=_client(handler)).fill_email(
        Lead(name="X", company="Acme")
    )
    assert out.domain == "getsomeapp.com"


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


def test_pattern_folds_accents_to_ascii_emails():
    out = PatternGuessProvider().fill_email(Lead(name="Martín Añazco", domain="acme.uy"))
    assert out.email == "martin.anazco@acme.uy"          # ñ/í folded, no non-ASCII
    assert all(e.isascii() for e in [out.email, *out.email_alternatives])
    assert "martin@acme.uy" in out.email_alternatives


def test_pattern_low_guess_offers_alternatives():
    out = PatternGuessProvider().fill_email(Lead(name="Ada Lovelace", domain="ae.com"))
    assert out.email == "ada.lovelace@ae.com"
    assert out.email_confidence == "low"
    # at least the first@ pattern is offered as a backup
    assert "ada@ae.com" in out.email_alternatives
    assert out.email not in out.email_alternatives  # no duplicate of the primary


def test_pattern_verified_email_has_no_alternatives():
    out = PatternGuessProvider(verify=lambda e: "valid").fill_email(
        Lead(name="Ada Lovelace", domain="ae.com")
    )
    assert out.email_confidence == "high"
    assert out.email_alternatives == []


def test_pattern_kept_email_gets_backup_alternatives():
    out = PatternGuessProvider(verify=lambda e: "invalid").fill_email(
        Lead(name="Ada Lovelace", domain="ae.com", email="found@ae.com",
             email_confidence="medium", source="hunter")
    )
    assert out.email == "found@ae.com"            # kept the real find
    assert "ada.lovelace@ae.com" in out.email_alternatives  # but offers patterns to try


def test_pattern_tries_combos_and_keeps_first_valid():
    # Only "flast" (alovelace@) verifies valid; provider must land on it.
    def verify(email):
        return "valid" if email == "alovelace@analytical.com" else "invalid"
    out = PatternGuessProvider(verify=verify).fill_email(
        Lead(name="Ada Lovelace", domain="analytical.com")
    )
    assert out.email == "alovelace@analytical.com"
    assert out.email_confidence == "high"
    assert out.email_status == "valid"


def test_pattern_stops_checking_after_first_valid():
    calls = []
    def verify(email):
        calls.append(email)
        return "valid"  # first candidate already valid
    PatternGuessProvider(verify=verify).fill_email(Lead(name="Ada Lovelace", domain="a.com"))
    assert len(calls) == 1  # stopped immediately


def test_pattern_no_valid_falls_back_to_top_guess():
    out = PatternGuessProvider(verify=lambda e: "invalid").fill_email(
        Lead(name="Ada Lovelace", domain="a.com")
    )
    assert out.email == "ada.lovelace@a.com"  # most-common pattern
    assert out.email_confidence == "low"


def test_pattern_verifies_existing_email_first_and_keeps_source():
    calls = []
    def verify(email):
        calls.append(email)
        return "valid" if email == "found@ae.com" else "invalid"
    out = PatternGuessProvider(verify=verify).fill_email(
        Lead(name="Ada Lovelace", domain="ae.com", email="found@ae.com",
             email_confidence="medium", source="hunter")
    )
    assert calls[0] == "found@ae.com"        # checked the existing email first
    assert out.email == "found@ae.com"
    assert out.email_confidence == "high"
    assert out.source == "hunter"            # not overwritten to 'pattern'


def test_pattern_upgrades_bad_email_to_verified_combo():
    def verify(email):
        return "valid" if email == "alovelace@ae.com" else "invalid"
    out = PatternGuessProvider(verify=verify).fill_email(
        Lead(name="Ada Lovelace", domain="ae.com", email="wrong@ae.com",
             email_confidence="low", source="hunter")
    )
    assert out.email == "alovelace@ae.com"
    assert out.email_confidence == "high"
    assert out.source == "pattern"           # a guessed combo replaced the bad find


def test_pattern_keeps_existing_email_when_nothing_verifies():
    out = PatternGuessProvider(verify=lambda e: "invalid").fill_email(
        Lead(name="Ada Lovelace", domain="ae.com", email="found@ae.com",
             email_confidence="medium", source="hunter")
    )
    assert out.email == "found@ae.com"       # not downgraded to a guess
    assert out.email_confidence == "medium"


def test_pattern_respects_max_checks():
    calls = []
    def verify(email):
        calls.append(email)
        return "unknown"
    PatternGuessProvider(verify=verify, max_checks=3).fill_email(
        Lead(name="Ada Lovelace", domain="a.com")
    )
    assert len(calls) == 3


# --- Email verifier ---

def test_verifier_valid_sets_status_and_high_confidence():
    handler = lambda r: httpx.Response(200, json={"data": {"status": "valid", "score": 88}})
    out = EmailVerifier("k", _client(handler)).verify(Lead(name="P", email="p@k.ai", email_confidence="low"))
    assert out.email_status == "valid"
    assert out.email_confidence == "high"


def test_verifier_invalid_zeroes_confidence():
    handler = lambda r: httpx.Response(200, json={"data": {"status": "invalid"}})
    out = EmailVerifier("k", _client(handler)).verify(Lead(name="P", email="p@k.ai", email_confidence="low"))
    assert out.email_status == "invalid"
    assert out.email_confidence == "none"


def test_verifier_no_email_unchanged():
    out = EmailVerifier("k", _client(lambda r: httpx.Response(500))).verify(Lead(name="P"))
    assert out.email_status is None


# --- Team finder ---

def test_team_finder_returns_founders_excluding_primary():
    def handler(request):
        assert request.url.path == "/v2/domain-search"
        return httpx.Response(200, json={"data": {"emails": [
            {"value": "ada@ae.com", "first_name": "Ada", "last_name": "L", "position": "CEO & Founder"},
            {"value": "bob@ae.com", "first_name": "Bob", "last_name": "M", "position": "CTO, Co-founder"},
            {"value": "sue@ae.com", "first_name": "Sue", "last_name": "K", "position": "Sales Rep"},  # not founder
        ]}})
    primary = Lead(name="Ada L", domain="ae.com", email="ada@ae.com")
    team = TeamFinder("k", _client(handler)).find(primary)
    names = [t.name for t in team]
    assert names == ["Bob M"]            # Sue excluded (not founder), Ada excluded (primary)
    assert team[0].email == "bob@ae.com"
    assert team[0].domain == "ae.com"


def test_team_finder_no_domain_returns_empty():
    assert TeamFinder("k", _client(lambda r: httpx.Response(500))).find(Lead(name="Ada")) == []


def test_team_finder_no_key_returns_empty():
    assert TeamFinder(None, _client(lambda r: httpx.Response(500))).find(Lead(name="Ada", domain="ae.com")) == []


# --- Chain ---

class _StubIdentity:
    def __init__(self, lead): self._lead = lead
    def find(self, url): return self._lead


class _StubFiller:
    def __init__(self, name, called, email=None, confidence="low"):
        self.name, self.called, self.email, self.confidence = name, called, email, confidence
    def fill_email(self, lead):
        self.called.append(self.name)
        if self.email:
            return lead.model_copy(update={
                "email": self.email, "email_confidence": self.confidence, "source": "pattern"})
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


def test_chain_continues_past_low_confidence_email_until_high():
    # A low/medium email must NOT short-circuit the chain — later fillers
    # (the pattern verifier) get a chance to upgrade it.
    called = []
    chain = EnrichmentChain(
        identity_providers=[_StubIdentity(Lead(name="Ada", company="AE"))],
        email_fillers=[
            _StubFiller("hunter", called, email="ada@guess.com"),                  # low
            _StubFiller("pattern", called, email="ada@ae.com", confidence="high"), # verified
        ],
    )
    lead = chain.run(URL)
    assert called == ["hunter", "pattern"]   # did not stop at hunter's low-confidence email
    assert lead.email == "ada@ae.com"
    assert lead.email_confidence == "high"


def test_chain_stops_at_first_high_confidence_email():
    called = []
    chain = EnrichmentChain(
        identity_providers=[_StubIdentity(Lead(name="Ada", company="AE"))],
        email_fillers=[
            _StubFiller("hunter", called, email="ada@ae.com", confidence="high"),
            _StubFiller("pattern", called, email="x@y.com"),
        ],
    )
    lead = chain.run(URL)
    assert called == ["hunter"]              # stopped once we had a verified email
    assert lead.email == "ada@ae.com"


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
