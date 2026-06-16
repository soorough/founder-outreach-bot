# Founder Outreach Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Telegram bot that turns a founder's LinkedIn URL into a tailored cold email saved as a Gmail draft, after a confirmation tap.

**Architecture:** One Python service. `bot.py` (Telegram, long-polling) → `pipeline.py` orchestrates a sequence of small adapters: `enrich` (Apollo → Hunter → pattern-guess chain), `company` (site scrape), `kb` (load your markdown), `drafter` (Claude), `gmail_draft` (create draft). Every adapter is dependency-injected so it can be unit-tested with stubs/mock HTTP. Synchronous, fail-soft per step.

**Tech Stack:** Python 3.11+, `python-telegram-bot`, `httpx` (+ `httpx.MockTransport` in tests), `anthropic` (Claude Sonnet 4.6, `messages.parse` structured output), `google-api-python-client` + `google-auth-oauthlib`, `pydantic`, `python-dotenv`, `pytest`.

---

## File Structure

```
founder-outreach-bot/
├── pyproject.toml                 # deps + pytest config
├── .env.example                   # documented secrets template
├── run.py                         # entrypoint: build deps, start bot
├── auth_gmail.py                  # one-time Google OAuth → token.json
├── src/founder_bot/
│   ├── __init__.py
│   ├── config.py                  # Settings loaded from env
│   ├── models.py                  # Lead, Draft, Result
│   ├── urls.py                    # LinkedIn URL validation/normalization
│   ├── kb.py                      # load + concat knowledge-base markdown
│   ├── enrich.py                  # provider chain → Lead
│   ├── company.py                 # fetch company site → context text
│   ├── drafter.py                 # Claude → Draft
│   ├── gmail_draft.py             # create Gmail draft
│   ├── pipeline.py                # orchestrate steps → Result
│   └── bot.py                     # Telegram handlers + button callback
└── tests/
    ├── __init__.py
    ├── test_urls.py
    ├── test_models.py
    ├── test_config.py
    ├── test_kb.py
    ├── test_enrich.py
    ├── test_company.py
    ├── test_drafter.py
    ├── test_gmail_draft.py
    └── test_pipeline.py
```

Each module has one responsibility. `bot.py` holds no business logic beyond Telegram wiring and message formatting; everything testable lives in `pipeline.py` and the adapters.

---

### Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/founder_bot/__init__.py`
- Create: `tests/__init__.py`
- Create: `.env.example`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "founder-outreach-bot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "python-telegram-bot>=21.0",
    "httpx>=0.27",
    "anthropic>=0.69",
    "google-api-python-client>=2.130",
    "google-auth-oauthlib>=1.2",
    "pydantic>=2.7",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Create empty package files**

Create `src/founder_bot/__init__.py` with a single line:

```python
__all__ = []
```

Create `tests/__init__.py` as an empty file (zero bytes).

- [ ] **Step 3: Write `.env.example`**

```
# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_ID=

# Enrichment
APOLLO_API_KEY=
HUNTER_API_KEY=

# Drafting
ANTHROPIC_API_KEY=

# Gmail OAuth (paths to local files produced by auth_gmail.py)
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json
```

- [ ] **Step 4: Create and activate a venv, install deps**

Run:
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```
Expected: installs without error; ends with a line naming `founder-outreach-bot`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/founder_bot/__init__.py tests/__init__.py .env.example
git commit -m "Scaffold founder-outreach-bot package and deps"
```

---

### Task 1: Data models

**Files:**
- Create: `src/founder_bot/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.models'`

- [ ] **Step 3: Write minimal implementation**

```python
from typing import Literal, Optional
from pydantic import BaseModel

Confidence = Literal["high", "medium", "low", "none"]
Source = Literal["apollo", "hunter", "pattern"]


class Lead(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    email_confidence: Confidence = "none"
    source: Optional[Source] = None


class Draft(BaseModel):
    subject: str
    body: str


class Result(BaseModel):
    lead: Lead
    company_context: Optional[str] = None
    draft: Optional[Draft] = None
    warnings: list[str] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_models.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/founder_bot/models.py tests/test_models.py
git commit -m "Add Lead/Draft/Result models"
```

---

### Task 2: LinkedIn URL validation

**Files:**
- Create: `src/founder_bot/urls.py`
- Test: `tests/test_urls.py`

- [ ] **Step 1: Write the failing test**

```python
from founder_bot.urls import normalize_linkedin_url


def test_valid_profile_url_normalized():
    assert normalize_linkedin_url(
        "https://www.linkedin.com/in/ada-lovelace/?trk=x"
    ) == "https://www.linkedin.com/in/ada-lovelace"


def test_adds_scheme_and_strips_trailing_slash():
    assert normalize_linkedin_url("linkedin.com/in/ada-lovelace/") == \
        "https://www.linkedin.com/in/ada-lovelace"


def test_non_linkedin_url_returns_none():
    assert normalize_linkedin_url("https://example.com/in/foo") is None


def test_non_profile_linkedin_url_returns_none():
    assert normalize_linkedin_url("https://www.linkedin.com/company/foo") is None


def test_garbage_returns_none():
    assert normalize_linkedin_url("hello there") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_urls.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.urls'`

- [ ] **Step 3: Write minimal implementation**

```python
import re
from typing import Optional

_PROFILE_RE = re.compile(
    r"^https?://([a-z]{2,3}\.)?linkedin\.com/in/(?P<slug>[A-Za-z0-9\-_%]+)",
    re.IGNORECASE,
)


def normalize_linkedin_url(raw: str) -> Optional[str]:
    """Return a canonical https://www.linkedin.com/in/<slug> URL, or None if not a profile URL."""
    text = raw.strip()
    if not text:
        return None
    if not text.lower().startswith(("http://", "https://")):
        text = "https://" + text
    match = _PROFILE_RE.match(text)
    if not match:
        return None
    return f"https://www.linkedin.com/in/{match.group('slug')}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_urls.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/founder_bot/urls.py tests/test_urls.py
git commit -m "Add LinkedIn URL validation/normalization"
```

---

### Task 3: Config

**Files:**
- Create: `src/founder_bot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from founder_bot.config import Settings


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "12345")
    monkeypatch.setenv("APOLLO_API_KEY", "ap")
    monkeypatch.setenv("HUNTER_API_KEY", "hu")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an")
    settings = Settings.from_env()
    assert settings.telegram_bot_token == "tok"
    assert settings.telegram_owner_id == 12345
    assert settings.apollo_api_key == "ap"
    assert settings.google_token_path == "token.json"  # default


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an")
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Settings.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.config'`

- [ ] **Step 3: Write minimal implementation**

```python
import os
from dataclasses import dataclass
from typing import Optional


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@dataclass
class Settings:
    telegram_bot_token: str
    telegram_owner_id: int
    anthropic_api_key: str
    apollo_api_key: Optional[str]
    hunter_api_key: Optional[str]
    google_credentials_path: str
    google_token_path: str
    kb_dir: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            telegram_owner_id=int(_require("TELEGRAM_OWNER_ID")),
            anthropic_api_key=_require("ANTHROPIC_API_KEY"),
            apollo_api_key=os.getenv("APOLLO_API_KEY") or None,
            hunter_api_key=os.getenv("HUNTER_API_KEY") or None,
            google_credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
            google_token_path=os.getenv("GOOGLE_TOKEN_PATH", "token.json"),
            kb_dir=os.getenv("KB_DIR", "kb"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/founder_bot/config.py tests/test_config.py
git commit -m "Add Settings loaded from env"
```

---

### Task 4: Knowledge base loader

**Files:**
- Create: `src/founder_bot/kb.py`
- Test: `tests/test_kb.py`

- [ ] **Step 1: Write the failing test**

```python
from founder_bot.kb import load_kb


def test_loads_and_concatenates_known_files(tmp_path):
    (tmp_path / "profile.md").write_text("I am Souravh.")
    (tmp_path / "proof.md").write_text("Built Nexus.")
    (tmp_path / "reviews.md").write_text("Great engineer.")
    (tmp_path / "angles.md").write_text("Direct tone.")
    text = load_kb(str(tmp_path))
    assert "I am Souravh." in text
    assert "Built Nexus." in text
    assert "Great engineer." in text
    assert "Direct tone." in text
    # section headers present so the model can tell parts apart
    assert "# profile" in text
    assert "# proof" in text


def test_missing_files_are_skipped(tmp_path):
    (tmp_path / "profile.md").write_text("Only profile.")
    text = load_kb(str(tmp_path))
    assert "Only profile." in text
    assert "# proof" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_kb.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.kb'`

- [ ] **Step 3: Write minimal implementation**

```python
import os

_FILES = ["profile.md", "proof.md", "reviews.md", "angles.md"]


def load_kb(kb_dir: str) -> str:
    """Concatenate known knowledge-base markdown files into one prompt-ready string."""
    parts: list[str] = []
    for filename in _FILES:
        path = os.path.join(kb_dir, filename)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
        if content:
            section = os.path.splitext(filename)[0]
            parts.append(f"# {section}\n\n{content}")
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_kb.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/founder_bot/kb.py tests/test_kb.py
git commit -m "Add knowledge-base loader"
```

---

### Task 5: Enrichment provider chain

**Files:**
- Create: `src/founder_bot/enrich.py`
- Test: `tests/test_enrich.py`

This task has multiple steps because there are three providers plus the chain. All HTTP is tested with `httpx.MockTransport` — no network.

- [ ] **Step 1: Write the failing test (Apollo provider)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_enrich.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.enrich'`

- [ ] **Step 3: Implement ApolloProvider**

Create `src/founder_bot/enrich.py`:

```python
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
```

- [ ] **Step 4: Run Apollo tests**

Run: `.venv/bin/pytest tests/test_enrich.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Write the failing test (Hunter provider)**

Append to `tests/test_enrich.py`:

```python
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
```

- [ ] **Step 6: Implement HunterProvider (append to `enrich.py`)**

```python
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
```

- [ ] **Step 7: Run Hunter tests**

Run: `.venv/bin/pytest tests/test_enrich.py -q`
Expected: PASS (6 passed)

- [ ] **Step 8: Write the failing test (pattern guess)**

Append to `tests/test_enrich.py`:

```python
def test_pattern_guess_builds_first_last_at_domain():
    base = Lead(name="Ada Lovelace", domain="analytical.com")
    out = PatternGuessProvider().fill_email(base)
    assert out.email == "ada.lovelace@analytical.com"
    assert out.email_confidence == "low"
    assert out.source == "pattern"


def test_pattern_guess_no_domain_unchanged():
    base = Lead(name="Ada Lovelace")
    assert PatternGuessProvider().fill_email(base).email is None
```

- [ ] **Step 9: Implement PatternGuessProvider (append to `enrich.py`)**

```python
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
```

- [ ] **Step 10: Run pattern tests**

Run: `.venv/bin/pytest tests/test_enrich.py -q`
Expected: PASS (8 passed)

- [ ] **Step 11: Write the failing test (chain)**

Append to `tests/test_enrich.py`:

```python
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
```

- [ ] **Step 12: Implement EnrichmentChain (append to `enrich.py`)**

```python
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
```

- [ ] **Step 13: Run all enrich tests**

Run: `.venv/bin/pytest tests/test_enrich.py -q`
Expected: PASS (11 passed)

- [ ] **Step 14: Commit**

```bash
git add src/founder_bot/enrich.py tests/test_enrich.py
git commit -m "Add enrichment provider chain (Apollo, Hunter, pattern guess)"
```

---

### Task 6: Company context

**Files:**
- Create: `src/founder_bot/company.py`
- Test: `tests/test_company.py`

- [ ] **Step 1: Write the failing test**

```python
import httpx
from founder_bot.company import fetch_company_context


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extracts_visible_text_truncated():
    html = "<html><head><title>T</title><style>x{}</style></head>" \
           "<body><h1>Analytical Engines</h1><p>We build " + ("data " * 50) + "</p>" \
           "<script>var a=1;</script></body></html>"
    client = _client(lambda r: httpx.Response(200, text=html))
    text = fetch_company_context("analytical.com", client=client, max_chars=120)
    assert "Analytical Engines" in text
    assert "var a=1" not in text  # script stripped
    assert "x{}" not in text       # style stripped
    assert len(text) <= 120


def test_none_domain_returns_none():
    assert fetch_company_context(None, client=_client(lambda r: httpx.Response(200))) is None


def test_http_error_returns_none():
    client = _client(lambda r: httpx.Response(500))
    assert fetch_company_context("analytical.com", client=client) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_company.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.company'`

- [ ] **Step 3: Write minimal implementation**

```python
import re
from typing import Optional

import httpx

_TAG_BLOCK = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def fetch_company_context(
    domain: Optional[str], client: httpx.Client, max_chars: int = 1500
) -> Optional[str]:
    """Fetch the company homepage and return cleaned visible text, truncated. None on failure."""
    if not domain:
        return None
    try:
        resp = client.get(
            f"https://{domain}",
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (founder-outreach-bot)"},
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    html = resp.text
    html = _TAG_BLOCK.sub(" ", html)
    text = _TAGS.sub(" ", html)
    text = _WS.sub(" ", text).strip()
    return text[:max_chars] or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_company.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/founder_bot/company.py tests/test_company.py
git commit -m "Add company context fetcher"
```

---

### Task 7: Drafter (Claude)

**Files:**
- Create: `src/founder_bot/drafter.py`
- Test: `tests/test_drafter.py`

The drafter takes an Anthropic-like client by injection. In tests we pass a fake whose `messages.parse(...)` returns an object with a `parsed_output` of type `Draft`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_drafter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.drafter'`

- [ ] **Step 3: Write minimal implementation**

```python
from typing import Optional

from founder_bot.models import Draft, Lead

MODEL = "claude-sonnet-4-6"

_SYSTEM = (
    "You write concise, personalized cold emails for job/role outreach to founders. "
    "Warm, direct, no corporate buzzwords, no flattery padding. 90-150 words. "
    "Reference something specific about the founder's company. End with a small, low-friction ask."
)


def _build_prompt(lead: Lead, company_context: Optional[str], kb_text: str) -> str:
    company_block = company_context or "(no company context available)"
    return (
        f"About me (the sender):\n{kb_text}\n\n"
        f"Recipient: {lead.name}"
        f"{', ' + lead.title if lead.title else ''}"
        f"{' at ' + lead.company if lead.company else ''}.\n\n"
        f"Company context:\n{company_block}\n\n"
        "Write a cold email from me to this founder. Return a subject and body."
    )


def draft_email(client, lead: Lead, company_context: Optional[str], kb_text: str) -> Draft:
    """Call Claude with structured output and return a Draft. Raises on API error (caller handles)."""
    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(lead, company_context, kb_text)}],
        output_format=Draft,
    )
    return response.parsed_output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_drafter.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/founder_bot/drafter.py tests/test_drafter.py
git commit -m "Add Claude-backed email drafter"
```

---

### Task 8: Gmail draft creation

**Files:**
- Create: `src/founder_bot/gmail_draft.py`
- Test: `tests/test_gmail_draft.py`

The function takes a Gmail `service` object by injection and builds a base64url-encoded MIME message. In tests we pass a fake service that records the call.

- [ ] **Step 1: Write the failing test**

```python
import base64
from founder_bot.gmail_draft import create_draft
from founder_bot.models import Draft


class _FakeCreate:
    def __init__(self, recorder, *, userId, body):
        recorder["userId"] = userId
        recorder["body"] = body
    def execute(self):
        return {"id": "draft_123"}


class _FakeDrafts:
    def __init__(self, recorder): self.recorder = recorder
    def create(self, *, userId, body):
        return _FakeCreate(self.recorder, userId=userId, body=body)


class _FakeUsers:
    def __init__(self, recorder): self._drafts = _FakeDrafts(recorder)
    def drafts(self): return self._drafts


class _FakeService:
    def __init__(self, recorder): self._users = _FakeUsers(recorder)
    def users(self): return self._users


def test_create_draft_encodes_message_and_calls_api():
    recorder = {}
    draft = Draft(subject="Quick idea", body="Hi Ada,\n\nLet's talk.")
    draft_id = create_draft(
        service=_FakeService(recorder),
        to_email="ada@analytical.com",
        draft=draft,
    )
    assert draft_id == "draft_123"
    assert recorder["userId"] == "me"
    raw = recorder["body"]["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw).decode("utf-8")
    assert "To: ada@analytical.com" in decoded
    assert "Subject: Quick idea" in decoded
    assert "Let's talk." in decoded


def test_create_draft_without_recipient_omits_to_header():
    recorder = {}
    draft = Draft(subject="S", body="B")
    create_draft(service=_FakeService(recorder), to_email=None, draft=draft)
    decoded = base64.urlsafe_b64decode(recorder["body"]["message"]["raw"]).decode("utf-8")
    assert "To:" not in decoded
    assert "Subject: S" in decoded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gmail_draft.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.gmail_draft'`

- [ ] **Step 3: Write minimal implementation**

```python
import base64
from email.message import EmailMessage
from typing import Optional

from founder_bot.models import Draft


def create_draft(service, to_email: Optional[str], draft: Draft) -> str:
    """Create a Gmail draft from a Draft. Returns the created draft id."""
    message = EmailMessage()
    message["Subject"] = draft.subject
    if to_email:
        message["To"] = to_email
    message.set_content(draft.body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    created = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return created["id"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_gmail_draft.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Add the real service builder (not unit-tested — exercised in smoke test)**

Append to `src/founder_bot/gmail_draft.py`:

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def build_service(token_path: str):
    """Build an authenticated Gmail service from a token.json produced by auth_gmail.py."""
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build("gmail", "v1", credentials=creds)
```

- [ ] **Step 6: Run the full test file again (ensure no import break)**

Run: `.venv/bin/pytest tests/test_gmail_draft.py -q`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add src/founder_bot/gmail_draft.py tests/test_gmail_draft.py
git commit -m "Add Gmail draft creation"
```

---

### Task 9: Pipeline orchestration

**Files:**
- Create: `src/founder_bot/pipeline.py`
- Test: `tests/test_pipeline.py`

The pipeline ties the steps together with injected callables so it is fully testable with stubs. It is fail-soft: company-scrape failure adds a warning, no-email still drafts.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'founder_bot.pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
from typing import Callable, Optional

from founder_bot.models import Draft, Lead, Result


class InvalidUrlError(ValueError):
    """Raised when the input is not a valid LinkedIn profile URL."""


class Pipeline:
    """Orchestrate: validate URL → enrich → company context → draft. Fail-soft per step."""

    def __init__(
        self,
        normalize: Callable[[str], Optional[str]],
        enrich: Callable[[str], Optional[Lead]],
        fetch_company: Callable[[Optional[str]], Optional[str]],
        load_kb: Callable[[], str],
        draft: Callable[[Lead, Optional[str], str], Draft],
    ):
        self.normalize = normalize
        self.enrich = enrich
        self.fetch_company = fetch_company
        self.load_kb = load_kb
        self.draft = draft

    def run(self, raw_url: str) -> Result:
        url = self.normalize(raw_url)
        if url is None:
            raise InvalidUrlError("That doesn't look like a LinkedIn profile URL.")

        lead = self.enrich(url)
        if lead is None:
            raise RuntimeError("Could not identify this person from the LinkedIn URL.")

        warnings: list[str] = []
        if not lead.email:
            warnings.append("No email found — draft saved without a recipient; add it manually.")

        company_context = self.fetch_company(lead.domain)
        if company_context is None:
            warnings.append("Limited company context — drafted from profile + your knowledge base only.")

        draft = self.draft(lead, company_context, self.load_kb())
        return Result(lead=lead, company_context=company_context, draft=draft, warnings=warnings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (all tests across all files green)

- [ ] **Step 6: Commit**

```bash
git add src/founder_bot/pipeline.py tests/test_pipeline.py
git commit -m "Add pipeline orchestration"
```

---

### Task 10: Telegram bot + assembly + Gmail auth

**Files:**
- Create: `src/founder_bot/bot.py`
- Create: `run.py`
- Create: `auth_gmail.py`

This task is wiring (no new unit tests — logic lives in tested modules). Verified by the manual smoke test in Task 11.

- [ ] **Step 1: Write `auth_gmail.py` (one-time OAuth)**

```python
"""Run once locally: python auth_gmail.py
Opens a browser, authorizes Gmail compose scope, writes token.json."""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def main():
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_path, "w", encoding="utf-8") as handle:
        handle.write(creds.to_json())
    print(f"Wrote {token_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `src/founder_bot/bot.py`**

```python
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters,
)

from founder_bot.models import Result
from founder_bot.pipeline import InvalidUrlError

logger = logging.getLogger(__name__)


def _format_preview(result: Result) -> str:
    lead = result.lead
    email = lead.email or "(none found)"
    confidence = lead.email_confidence
    warnings = "\n".join(f"⚠️ {w}" for w in result.warnings)
    return (
        f"*To:* {lead.name}"
        f"{' — ' + lead.title if lead.title else ''}"
        f"{' @ ' + lead.company if lead.company else ''}\n"
        f"*Email:* {email} ({confidence})\n\n"
        f"*Subject:* {result.draft.subject}\n\n"
        f"{result.draft.body}\n\n"
        f"{warnings}"
    ).strip()


class Bot:
    """Telegram wiring. Owns the pipeline + gmail-draft creator; holds pending results per chat."""

    def __init__(self, owner_id: int, pipeline, create_gmail_draft):
        self.owner_id = owner_id
        self.pipeline = pipeline
        self.create_gmail_draft = create_gmail_draft
        self._pending: dict[int, Result] = {}

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self.owner_id:
            return  # whitelist: ignore everyone else
        chat_id = update.effective_chat.id
        await update.message.reply_text("Working on it…")
        try:
            result = self.pipeline.run(update.message.text)
        except InvalidUrlError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        except Exception as exc:  # fail-soft: surface the error, don't crash
            logger.exception("pipeline failed")
            await update.message.reply_text(f"❌ Something went wrong: {exc}")
            return
        self._pending[chat_id] = result
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Save to Gmail", callback_data="save")]]
        )
        await update.message.reply_text(
            _format_preview(result), parse_mode="Markdown", reply_markup=keyboard
        )

    async def handle_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.from_user.id != self.owner_id:
            return
        result = self._pending.pop(query.message.chat_id, None)
        if result is None:
            await query.edit_message_text("Nothing to save (already saved or expired).")
            return
        try:
            self.create_gmail_draft(result.lead.email, result.draft)
        except Exception as exc:
            logger.exception("gmail draft failed")
            await query.edit_message_text(f"❌ Could not save draft: {exc}")
            return
        await query.edit_message_text("✅ Saved to Gmail Drafts.")

    def build_application(self, token: str) -> Application:
        app = Application.builder().token(token).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        app.add_handler(CallbackQueryHandler(self.handle_save, pattern="^save$"))
        return app
```

- [ ] **Step 3: Write `run.py` (composition root)**

```python
import logging

import httpx
from anthropic import Anthropic
from dotenv import load_dotenv

from founder_bot.bot import Bot
from founder_bot.company import fetch_company_context
from founder_bot.config import Settings
from founder_bot.drafter import draft_email
from founder_bot.enrich import (
    ApolloProvider, EnrichmentChain, HunterProvider, PatternGuessProvider,
)
from founder_bot.gmail_draft import build_service, create_draft
from founder_bot.kb import load_kb
from founder_bot.pipeline import Pipeline
from founder_bot.urls import normalize_linkedin_url


def main():
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    settings = Settings.from_env()

    http = httpx.Client(timeout=20.0)
    anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    gmail_service = build_service(settings.google_token_path)

    chain = EnrichmentChain(
        apollo=ApolloProvider(settings.apollo_api_key, http),
        hunter=HunterProvider(settings.hunter_api_key, http),
        pattern=PatternGuessProvider(),
    )

    pipeline = Pipeline(
        normalize=normalize_linkedin_url,
        enrich=chain.run,
        fetch_company=lambda domain: fetch_company_context(domain, http),
        load_kb=lambda: load_kb(settings.kb_dir),
        draft=lambda lead, ctx, kb: draft_email(anthropic_client, lead, ctx, kb),
    )

    bot = Bot(
        owner_id=settings.telegram_owner_id,
        pipeline=pipeline,
        create_gmail_draft=lambda email, draft: create_draft(gmail_service, email, draft),
    )
    app = bot.build_application(settings.telegram_bot_token)
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify the package imports cleanly**

Run: `.venv/bin/python -c "import founder_bot.bot, founder_bot.pipeline; import run; print('imports ok')"`
Expected: prints `imports ok` (no import errors). It will NOT start the bot (guarded by `__main__`).

- [ ] **Step 5: Run the full test suite once more**

Run: `.venv/bin/pytest -q`
Expected: PASS (all green)

- [ ] **Step 6: Commit**

```bash
git add src/founder_bot/bot.py run.py auth_gmail.py
git commit -m "Add Telegram bot, composition root, and Gmail OAuth helper"
```

---

### Task 11: Live smoke test (manual, requires real keys)

**Files:** none (uses real `.env`, `credentials.json`, `token.json`).

This is the only step that touches real services. Do it once before deploying.

- [ ] **Step 1: Fill secrets**

Copy `.env.example` → `.env` and fill every value. Get `TELEGRAM_OWNER_ID` by messaging `@userinfobot` on Telegram. Create the bot + token via `@BotFather`. Download Google OAuth desktop-app `credentials.json` into the repo root.

- [ ] **Step 2: Authorize Gmail**

Run: `.venv/bin/python auth_gmail.py`
Expected: a browser opens, you approve, and `token.json` is written. Console prints `Wrote token.json`.

- [ ] **Step 3: Fill the knowledge base**

Edit `kb/profile.md`, `kb/proof.md`, `kb/reviews.md`, `kb/angles.md` with your real details (templates already exist).

- [ ] **Step 4: Start the bot and send a URL**

Run: `.venv/bin/python run.py`
In Telegram, send a real founder LinkedIn profile URL to your bot.
Expected: bot replies "Working on it…", then a preview with To/Email/Subject/body and a "✅ Save to Gmail" button.

- [ ] **Step 5: Tap Save and verify**

Tap "✅ Save to Gmail". Expected: message edits to "✅ Saved to Gmail Drafts." Open Gmail → Drafts → the draft is present with the right recipient, subject, and body.

- [ ] **Step 6: Stop the bot** (`Ctrl+C`).

---

## Self-Review

**Spec coverage:**
- Telegram trigger → Task 10 (`bot.py`). ✅
- Enrich Apollo→Hunter→pattern chain → Task 5. ✅
- Company context → Task 6. ✅
- Dedicated KB → Task 4 (+ templates already committed). ✅
- Claude draft (Sonnet 4.6, structured output) → Task 7. ✅
- Preview + confirmation button before Gmail → Task 10 (`handle_url`/`handle_save`). ✅
- Gmail draft creation → Task 8. ✅
- Fail-soft error handling (no email, company fail, invalid URL, API error) → Task 9 + Task 10. ✅
- Owner-only whitelist → Task 10 (`owner_id` checks). ✅
- Config/secrets, env-var driven, deploy-ready → Task 3 + `.env.example` + `run.py`. ✅
- Per-module unit tests with mocked HTTP / injected stubs → Tasks 1–9. ✅
- Live smoke test before deploy → Task 11. ✅

**Type consistency:** `Lead`, `Draft`, `Result` defined in Task 1 are used identically downstream. Provider interface: `ApolloProvider.find(url) -> Lead | None`; `HunterProvider.fill_email(lead) -> Lead` and `PatternGuessProvider.fill_email(lead) -> Lead` (chain calls `.find` then `.fill_email`, matching Task 5 Step 12). `draft_email(client, lead, company_context, kb_text)` signature matches the pipeline's `draft` callable (Task 9) and `run.py` lambda (Task 10). `create_draft(service, to_email, draft)` matches the bot's `create_gmail_draft` lambda. No naming drift.

**Placeholder scan:** none — every code step is complete.

**Scope:** single service, one implementation plan. No decomposition needed.
