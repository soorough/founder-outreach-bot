from typing import Optional

from founder_bot.models import Draft, Lead

_SYSTEM = (
    "You write concise, personalized cold emails for job/role outreach to founders. "
    "Warm, direct, no corporate buzzwords, no flattery padding. 90-150 words. "
    "Reference something specific about the founder's company. End with a small, low-friction ask. "
    'Return ONLY a JSON object with exactly two string fields: "subject" and "body". '
    "No markdown fences, no commentary, no extra keys."
)


def _build_prompt(lead: Lead, company_context: Optional[str], kb_text: str) -> str:
    company_block = company_context or "(no company context available)"
    return (
        f"About me (the sender):\n{kb_text}\n\n"
        f"Recipient: {lead.name}"
        f"{', ' + lead.title if lead.title else ''}"
        f"{' at ' + lead.company if lead.company else ''}.\n\n"
        f"Company context:\n{company_block}\n\n"
        "Write a cold email from me to this founder as a JSON object with "
        '"subject" and "body".'
    )


def draft_email(
    client, model: str, lead: Lead, company_context: Optional[str], kb_text: str
) -> Draft:
    """Call an OpenAI-compatible chat model (DeepSeek/Qwen) and return a Draft.

    Uses JSON-object response mode and validates the content into a Draft.
    Raises on API or parse error (caller handles).
    """
    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_prompt(lead, company_context, kb_text)},
        ],
    )
    content = response.choices[0].message.content
    return Draft.model_validate_json(content)
