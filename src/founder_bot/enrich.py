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
        # Title looks like "Name - Company | LinkedIn" (or "Name | LinkedIn").
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE).strip()
        if not title:
            return None
        if " - " in title:
            name, company = title.split(" - ", 1)
            company = company.strip() or None
        else:
            name, company = title, None
        name = name.strip()
        if not name:
            return None
        return Lead(name=name, company=company)


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
