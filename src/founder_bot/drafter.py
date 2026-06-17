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
