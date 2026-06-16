# Founder Outreach Bot — Design

**Date:** 2026-06-16
**Status:** Approved design, pending implementation plan

## Purpose

A Telegram-triggered automation for **job/role outreach**. You send a LinkedIn
profile URL of a founder; the bot enriches the lead, gathers context about their
company, drafts a tailored cold email referencing a personal knowledge base, and
(on your confirmation) saves it as a Gmail draft ready to send.

This is a standalone product — *not* part of career-ops. It reuses the spirit of
career-ops `contacto` mode but runs as an always-on service.

## Non-goals (YAGNI)

- No mass-sending / blasting. One URL → one reviewed draft.
- No auto-send. The bot only ever creates a **draft**; you hit send yourself.
- No queue/worker infrastructure (personal volume; revisit if needed).
- No WhatsApp (chosen Telegram instead — no ban risk, clean bot API).

## Architecture

Single Python service deployed on a cheap cloud host (Railway/Render).
`python-telegram-bot` with long-polling. Synchronous, modular pipeline.

### Flow

```
Telegram (you send a LinkedIn URL)
        │
        ▼
[1] enrich   ── Apollo → Hunter → pattern-guess+verify ──► Lead{name,title,company,domain,email,confidence}
        │
        ▼
[2] company  ── scrape company site (home/about) + optional recent-news search ──► company context summary
        │
        ▼
[3] kb       ── load dedicated knowledge base (experience, reviews, pitch angles)
        │
        ▼
[4] draft    ── Claude (Sonnet 4.6) → {subject, body}
        │
        ▼
Telegram reply: preview + email found + [✅ Save to Gmail] button
        │  (on tap)
        ▼
[5] gmail    ── create Gmail draft (To: founder email, subject, body)
```

Step 5 is gated behind a confirmation button so bad enrichments never reach the
drafts folder. Flippable to auto-save via config later.

### Modules

Each is a small, independently testable unit with one responsibility.

| Module | Responsibility | Depends on |
|--------|---------------|------------|
| `bot.py` | Telegram handlers, button callback, orchestration, replies; whitelist on owner Telegram user ID | `pipeline` |
| `pipeline.py` | Run steps in order, per-step error handling, assemble a `Result` | all below |
| `enrich.py` | Adapter chain `ApolloProvider → HunterProvider → PatternGuessProvider`. Each implements `find(linkedin_url) -> Lead | None`; chain stops at first provider returning a usable email | Apollo/Hunter APIs |
| `company.py` | Fetch company site (home/about) + optional recent-news search → short context summary | httpx, optional search API |
| `kb.py` | Load + concatenate knowledge base markdown into prompt context | local `kb/` files |
| `drafter.py` | Build prompt from Lead + company context + KB, call Claude, parse `{subject, body}` | Anthropic SDK |
| `gmail.py` | Google OAuth + create draft | google-api-python-client |
| `config.py` | Load env vars / secrets; no hardcoded paths | — |

### Data model

```
Lead:
  name: str
  title: str | None
  company: str | None
  domain: str | None
  email: str | None
  email_confidence: "high" | "medium" | "low" | "none"
  source: "apollo" | "hunter" | "pattern"

Draft:
  subject: str
  body: str

Result:
  lead: Lead
  company_context: str | None
  draft: Draft
  warnings: list[str]
```

## Knowledge base format

A `kb/` folder of plain markdown the user owns and edits:

- `profile.md` — who you are, experience, headline pitch
- `proof.md` — projects, metrics, results
- `reviews.md` — testimonials / reviews
- `angles.md` — reusable outreach hooks

`kb.py` concatenates them into the draft prompt. Plain files = tune tone without
touching code. Files are committed as templates with placeholder content; the
user fills in real details locally.

## Error handling (fail-soft, per step)

- **No email found** → still draft; reply ⚠️ "no email found, add recipient manually." Save button still offered (draft created without To:).
- **Company scrape fails** → draft from profile + KB only; warning "limited company context."
- **Claude or Gmail error** → reply the specific error in Telegram; nothing saved.
- **Invalid/non-LinkedIn URL** → validate up front, ask user to resend.
- One failing step never crashes the bot; the polling loop keeps running.

## Config / secrets

`.env` locally → host env vars in prod:

| Var | Purpose |
|-----|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot |
| `TELEGRAM_OWNER_ID` | Whitelist — only this user ID may use the bot |
| `APOLLO_API_KEY` | Primary enrichment |
| `HUNTER_API_KEY` | Fallback enrichment |
| `ANTHROPIC_API_KEY` | Drafting (Claude Sonnet 4.6) |
| `GOOGLE_OAUTH_CLIENT` / token | Gmail draft creation |
| `SEARCH_API_KEY` (optional) | Recent-news context |

## Stack

- Python 3.11+
- `python-telegram-bot`, `httpx`, `anthropic`, `google-api-python-client`,
  `google-auth-oauthlib`, `python-dotenv`
- Deploy: Railway/Render (start local, env-var-driven so deploy is trivial)

## Testing strategy

- Each provider/module unit-tested with mocked HTTP responses.
- `pipeline.py` tested end-to-end with all external calls stubbed.
- Live smoke test: one real LinkedIn URL through the full chain before deploy.

## Ethical guardrails

- Owner-only (Telegram whitelist).
- Draft-only; never auto-send.
- Respects one-URL-one-draft; this is targeted outreach, not spam.
