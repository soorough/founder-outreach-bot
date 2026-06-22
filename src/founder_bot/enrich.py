import re
from typing import Optional, Protocol
from urllib.parse import urlparse

import httpx

from founder_bot.models import Lead

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _domain_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else "https://" + url)
    host = parsed.netloc or parsed.path
    return host.replace("www.", "").strip("/") or None


def _clean_company(company: str) -> str:
    """Strip parentheticals like '(YC F25)' for a cleaner company-name lookup."""
    return re.sub(r"\s*\(.*?\)\s*", " ", company).strip()


# Domains that are directories/socials, never a company's own site.
_AGGREGATORS = {
    "linkedin.com", "crunchbase.com", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "wikipedia.org", "bloomberg.com", "github.com", "medium.com",
    "youtube.com", "pitchbook.com", "tracxn.com", "glassdoor.com", "ycombinator.com",
    "duckduckgo.com", "reddit.com", "producthunt.com",
}


def _is_company_domain(domain: Optional[str]) -> bool:
    return bool(domain) and not any(
        domain == s or domain.endswith("." + s) for s in _AGGREGATORS
    )


def _parse_linkedin_title(raw_title: str) -> Optional[tuple[str, Optional[str]]]:
    """Parse a LinkedIn page/result title into (name, company).

    Titles look like "Name - Company | LinkedIn" (or "Name | LinkedIn"). Returns
    None if no name can be extracted. Shared by the direct scraper and the
    search-engine identity provider, which both see the same indexed title.
    """
    title = re.sub(r"\s+", " ", raw_title).strip()
    title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE).strip()
    if not title or title.lower() == "linkedin":
        return None
    if " - " in title:
        name, company = title.split(" - ", 1)
        company = company.strip() or None
    else:
        name, company = title, None
    name = name.strip()
    if not name:
        return None
    return name, company


def _name_from_linkedin_url(linkedin_url: str) -> Optional[str]:
    """Derive a person's name from the profile slug, e.g.
    ``/in/lang-li-7a193a328`` → "Lang Li". Drops the trailing unique-id hash and
    any digit-bearing tokens. Last-resort identity when nothing else works.
    """
    path = urlparse(linkedin_url).path
    match = re.search(r"/in/([^/?#]+)", path)
    if not match:
        return None
    tokens = [t for t in match.group(1).split("-") if t.isalpha()]
    if not tokens:
        return None
    return " ".join(t.capitalize() for t in tokens)


class IdentityProvider(Protocol):
    def find(self, linkedin_url: str) -> Optional[Lead]:
        ...


class EmailFiller(Protocol):
    def fill_email(self, lead: Lead) -> Lead:
        ...


class ApolloProvider:
    """Paid identity provider: Apollo people-match (LinkedIn URL → person + email).

    Returns None on free plans (403) or any error, letting the chain fall through.
    """

    BASE = "https://api.apollo.io"

    def __init__(self, api_key: Optional[str], client: httpx.Client):
        self.api_key = api_key
        self.client = client

    def find(self, linkedin_url: str) -> Optional[Lead]:
        if not self.api_key:
            return None
        try:
            resp = self.client.post(
                f"{self.BASE}/v1/people/match",
                headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"},
                json={"linkedin_url": linkedin_url, "reveal_personal_emails": True},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        person = (resp.json() or {}).get("person") or {}
        if not person.get("name"):
            return None
        org = person.get("organization") or {}
        domain = _domain_from_url(org.get("website_url"))
        email = person.get("email")
        return Lead(
            name=person["name"],
            title=person.get("title"),
            company=org.get("name"),
            domain=domain,
            email=email,
            email_confidence="high" if email else "none",
            source="apollo" if email else None,
        )


class LinkedInScrapeProvider:
    """Free identity provider: read name + current company from a public LinkedIn
    profile's SEO meta tags (works around the authwall, which still exposes them).

    Best-effort and unofficial — LinkedIn may change markup or rate-limit.
    """

    _TITLE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)

    def __init__(self, client: httpx.Client):
        self.client = client

    def find(self, linkedin_url: str) -> Optional[Lead]:
        try:
            resp = self.client.get(
                linkedin_url, follow_redirects=True, headers={"User-Agent": _BROWSER_UA}
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        match = self._TITLE.search(resp.text)
        if not match:
            return None
        parsed = _parse_linkedin_title(match.group(1))
        if not parsed:
            return None
        name, company = parsed
        return Lead(name=name, company=company)


class SerperIdentityProvider:
    """Identity via Serper (Google) search — robust against LinkedIn's 999 block.

    Searches for the profile URL and reads the indexed "Name - Company | LinkedIn"
    title from the organic result that points back at this profile. No-ops without
    a key (Serper free tier: ~2,500 queries/month).
    """

    SEARCH_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: Optional[str], client: httpx.Client):
        self.api_key = api_key
        self.client = client

    def find(self, linkedin_url: str) -> Optional[Lead]:
        if not self.api_key:
            return None
        slug = ""
        match = re.search(r"/in/([^/?#]+)", urlparse(linkedin_url).path)
        if match:
            slug = match.group(1)
        try:
            resp = self.client.post(
                self.SEARCH_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": f"{slug} site:linkedin.com/in", "num": 10},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        organic = (resp.json() or {}).get("organic", [])
        # Prefer the result whose link is this exact profile; else first /in/ result.
        candidates = [i for i in organic if slug and slug in (i.get("link") or "")]
        candidates += [i for i in organic if "/in/" in (i.get("link") or "")]
        for item in candidates:
            parsed = _parse_linkedin_title(item.get("title") or "")
            if parsed:
                name, company = parsed
                return Lead(name=name, company=company)
        return None


class SlugNameProvider:
    """Last-resort identity: derive the name from the profile URL slug. Always
    yields a name (no company), so the pipeline can still draft something.
    """

    def find(self, linkedin_url: str) -> Optional[Lead]:
        name = _name_from_linkedin_url(linkedin_url)
        return Lead(name=name) if name else None


class HunterProvider:
    """Fallback email finder. Uses the company domain if known, otherwise the
    company name (Hunter resolves the domain itself). Captures the resolved
    domain back onto the Lead even when no email is found.
    """

    BASE = "https://api.hunter.io"

    def __init__(self, api_key: Optional[str], client: httpx.Client):
        self.api_key = api_key
        self.client = client

    def fill_email(self, lead: Lead) -> Lead:
        if not self.api_key or not lead.name:
            return lead
        params = {"full_name": lead.name, "api_key": self.api_key}
        if lead.domain:
            params["domain"] = lead.domain
        elif lead.company:
            params["company"] = _clean_company(lead.company)
        else:
            return lead
        try:
            resp = self.client.get(f"{self.BASE}/v2/email-finder", params=params)
            resp.raise_for_status()
        except httpx.HTTPError:
            return lead
        data = (resp.json() or {}).get("data") or {}
        updates: dict = {}
        if data.get("domain") and not lead.domain:
            updates["domain"] = data["domain"]
        email = data.get("email")
        if email:
            updates.update({"email": email, "email_confidence": "medium", "source": "hunter"})
        return lead.model_copy(update=updates) if updates else lead


class CompanyDomainResolver:
    """Resolve a company's real website domain via Serper (Google) search when the
    domain is unknown. Sets ``lead.domain`` (never an email), so it slots into the
    filler chain *before* Hunter — everything downstream then uses the real domain.
    """

    SEARCH_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: Optional[str], client: httpx.Client):
        self.api_key = api_key
        self.client = client

    def fill_email(self, lead: Lead) -> Lead:
        if lead.domain or not self.api_key or not lead.company:
            return lead
        try:
            resp = self.client.post(
                self.SEARCH_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": f"{lead.company} official website", "num": 10},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return lead
        for item in (resp.json() or {}).get("organic", []):
            domain = _domain_from_url(item.get("link"))
            if _is_company_domain(domain):
                return lead.model_copy(update={"domain": domain})
        return lead


class DuckDuckGoDomainResolver:
    """Keyless fallback domain resolver via DuckDuckGo HTML results (free, no signup;
    may rate-limit). Sets ``lead.domain`` only — slots into the chain before Hunter.
    """

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    _HREF = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)

    def __init__(self, client: httpx.Client):
        self.client = client

    def fill_email(self, lead: Lead) -> Lead:
        if lead.domain or not lead.company:
            return lead
        try:
            resp = self.client.post(
                self.SEARCH_URL,
                data={"q": f"{lead.company} startup official website"},
                headers={"User-Agent": _BROWSER_UA},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return lead
        for match in self._HREF.finditer(resp.text):
            domain = _domain_from_url(match.group(1))
            if _is_company_domain(domain):
                return lead.model_copy(update={"domain": domain})
        return lead


class PatternGuessProvider:
    """Last resort: guess first.last@domain from the name (needs a known domain)."""

    def fill_email(self, lead: Lead) -> Lead:
        if not lead.domain or not lead.name:
            return lead
        parts = [p for p in lead.name.lower().split() if p.isalpha()]
        if len(parts) < 2:
            return lead
        guess = f"{parts[0]}.{parts[-1]}@{lead.domain}"
        return lead.model_copy(update={
            "email": guess,
            "email_confidence": "low",
            "source": "pattern",
        })


_FOUNDER_TITLES = (
    "founder", "co-founder", "cofounder", "ceo", "cto", "coo", "cfo",
    "chief", "president", "owner", "partner",
)


class EmailVerifier:
    """Verify an email via Hunter's email-verifier. Sets ``email_status`` and raises
    confidence to 'high' when the address verifies as valid.
    """

    BASE = "https://api.hunter.io"

    def __init__(self, api_key: Optional[str], client: httpx.Client):
        self.api_key = api_key
        self.client = client

    def verify(self, lead: Lead) -> Lead:
        if not self.api_key or not lead.email:
            return lead
        try:
            resp = self.client.get(
                f"{self.BASE}/v2/email-verifier",
                params={"email": lead.email, "api_key": self.api_key},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return lead
        data = (resp.json() or {}).get("data") or {}
        status = data.get("status")
        if not status:
            return lead
        updates: dict = {"email_status": status}
        if status == "valid":
            updates["email_confidence"] = "high"
        elif status in ("invalid", "disposable"):
            updates["email_confidence"] = "none"
        return lead.model_copy(update=updates)


class TeamFinder:
    """Find a company's other founders/execs via Hunter domain-search.

    Returns Leads (with email + company + domain) for founder-ish roles, excluding
    the primary person. Empty for companies Hunter hasn't indexed.
    """

    BASE = "https://api.hunter.io"

    def __init__(self, api_key: Optional[str], client: httpx.Client, max_people: int = 5):
        self.api_key = api_key
        self.client = client
        self.max_people = max_people

    def find(self, primary: Lead) -> list[Lead]:
        if not self.api_key or not primary.domain:
            return []
        try:
            resp = self.client.get(
                f"{self.BASE}/v2/domain-search",
                params={"domain": primary.domain, "api_key": self.api_key, "limit": 10},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []
        data = (resp.json() or {}).get("data") or {}
        primary_email = (primary.email or "").lower()
        team: list[Lead] = []
        for entry in data.get("emails", []):
            email = entry.get("value")
            position = (entry.get("position") or "").lower()
            if not email or email.lower() == primary_email:
                continue
            if not any(t in position for t in _FOUNDER_TITLES):
                continue
            name = " ".join(p for p in [entry.get("first_name"), entry.get("last_name")] if p)
            if not name:
                continue
            team.append(Lead(
                name=name,
                title=entry.get("position"),
                company=primary.company,
                domain=primary.domain,
                email=email,
                email_confidence="medium",
                source="hunter",
            ))
            if len(team) >= self.max_people:
                break
        return team


class EnrichmentChain:
    """Identify the person (first identity provider that yields a name wins),
    then fill a missing email through the email fillers in order.
    """

    def __init__(self, identity_providers: list, email_fillers: list):
        self.identity_providers = identity_providers
        self.email_fillers = email_fillers

    def run(self, linkedin_url: str) -> Optional[Lead]:
        lead: Optional[Lead] = None
        for provider in self.identity_providers:
            lead = provider.find(linkedin_url)
            if lead and lead.name:
                break
        if lead is None:
            return None
        if lead.email:
            return lead
        for filler in self.email_fillers:
            lead = filler.fill_email(lead)
            if lead.email:
                return lead
        return lead
