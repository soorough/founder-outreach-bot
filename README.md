# Founder Outreach Bot

Telegram-triggered cold-outreach assistant for **job/role outreach**. Send a
founder's LinkedIn URL; the bot enriches the lead, gathers company context,
drafts a tailored email from your knowledge base, and saves it as a Gmail draft
on your confirmation.

> One URL → one reviewed draft. Draft-only, never auto-sends.

## How it works

```
You send a LinkedIn URL in Telegram
   → enrich (Apollo → Hunter → pattern-guess)   find name/role/company/email
   → company context (site + recent news)
   → load your knowledge base
   → draft email with Claude
   → preview in Telegram + [✅ Save to Gmail] button
   → Gmail draft created, ready to review and send
```

## Status

Design complete — see
[`docs/superpowers/specs/2026-06-16-founder-outreach-bot-design.md`](docs/superpowers/specs/2026-06-16-founder-outreach-bot-design.md).
Implementation pending.

## Knowledge base

Your details live in `kb/` as plain markdown (`profile.md`, `proof.md`,
`reviews.md`, `angles.md`). Edit these to tune what the bot says about you — no
code changes needed.

## Setup

_To be filled in during implementation._ Requires API keys for Telegram, Apollo,
Hunter, Anthropic, and Google OAuth (Gmail). See the design doc for the full
config list.

## License

MIT
