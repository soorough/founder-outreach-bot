from typing import Optional, Protocol
from urllib.parse import urlparse

import httpx

from founder_bot.models import Lead


def _domain_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else "https://" + url)
    host = parsed.netloc or parsed.path
    return host.replace("www.", "").strip("/") or None


class Provider(Protocol):
    def find(self, linkedin_url: str) -> Optional[Lead]:
        ...


class ApolloProvider:
    """Primary enrichment via Apollo people-match. Returns a Lead (email optional) or None."""

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
            source="apollo",
        )


class HunterProvider:
    """Fallback: given a Lead with name + domain, find the email via Hunter."""

    BASE = "https://api.hunter.io"

    def __init__(self, api_key: Optional[str], client: httpx.Client):
        self.api_key = api_key
        self.client = client

    def fill_email(self, lead: Lead) -> Lead:
        if not self.api_key or not lead.domain or not lead.name:
            return lead
        try:
            resp = self.client.get(
                f"{self.BASE}/v2/email-finder",
                params={"domain": lead.domain, "full_name": lead.name, "api_key": self.api_key},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return lead
        data = (resp.json() or {}).get("data") or {}
        email = data.get("email")
        if not email:
            return lead
        return lead.model_copy(update={
            "email": email,
            "email_confidence": "medium",
            "source": "hunter",
        })


class PatternGuessProvider:
    """Last resort: guess first.last@domain from the name."""

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
    """Apollo identifies the person; Hunter then pattern-guess fill a missing email."""

    def __init__(self, apollo, hunter, pattern):
        self.apollo = apollo
        self.hunter = hunter
        self.pattern = pattern

    def run(self, linkedin_url: str) -> Optional[Lead]:
        lead = self.apollo.find(linkedin_url)
        if lead is None:
            return None
        if lead.email:
            return lead
        lead = self.hunter.fill_email(lead)
        if lead.email:
            return lead
        return self.pattern.fill_email(lead)
