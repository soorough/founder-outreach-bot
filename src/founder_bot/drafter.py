import re
from typing import Optional

from founder_bot.models import Draft, Lead

_SYSTEM = (
    "You write concise, personalized cold emails for job/role outreach to founders. "
    "Warm, direct, no corporate buzzwords, no flattery padding. 90-150 words. "
    "End with a small, low-friction ask. Do NOT add a signature, sign-off with name, "
    "or contact links — a standard footer is appended automatically; end right after the ask. "
    "CRITICAL: never invent facts about the recipient or their company. Only use what "
    "is given below. If no company context is provided, do not guess what the company "
    "does — refer to it by name only and focus on the sender's relevant experience. "
    'Return ONLY a JSON object with exactly two string fields: "subject" and "body". '
    "No markdown fences, no commentary, no extra keys."
)


def _build_prompt(lead: Lead, company_context: Optional[str], kb_text: str) -> str:
    if company_context:
        company_block = (
            f"Company context (use only what's here; reference something specific and real):\n"
            f"{company_context}"
        )
    else:
        company_block = (
            "No company context is available. Do NOT invent or guess what the company does "
            "or builds — refer to it by name only and keep the email about the sender's fit."
        )
    return (
        f"About me (the sender):\n{kb_text}\n\n"
        f"Recipient: {lead.name}"
        f"{', ' + lead.title if lead.title else ''}"
        f"{' at ' + lead.company if lead.company else ''}.\n\n"
        f"{company_block}\n\n"
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
        max_tokens=2048,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_prompt(lead, company_context, kb_text)},
        ],
    )
    content = response.choices[0].message.content or ""
    # Tolerate code fences / stray prose by extracting the JSON object.
    match = re.search(r"\{.*\}", content, re.DOTALL)
    payload = match.group(0) if match else content
    return Draft.model_validate_json(payload)
