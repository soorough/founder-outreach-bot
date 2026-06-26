import json
import re
from typing import Optional

from founder_bot.models import Draft, Lead

_SYSTEM = (
    "You write concise, personalized cold emails for job/role outreach to founders. "
    "Open with a short greeting using the recipient's first name (e.g., \"Hi Pablo,\"). "
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


def _parse_draft_payload(content: str) -> Draft:
    """Parse a Draft from the model's text, tolerating its common malformations:
    code fences, trailing prose, and — the recurring DeepSeek bug — a dropped
    closing brace (or a body truncated before its closing quote). Repairs the
    JSON rather than failing the whole request.
    """
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output.")
    text = text[start:]

    decoder = json.JSONDecoder()
    # First a clean decode (raw_decode also ignores any trailing prose); then
    # try minimal repairs for a truncated tail: close the object, then close an
    # unterminated string before closing the object.
    for suffix in ("", "}", '"}'):
        try:
            data, _ = decoder.raw_decode(text + suffix)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("body"):
            return Draft(subject=data.get("subject") or "Quick note", body=data["body"])
    raise ValueError("Could not parse a draft from model output.")


def draft_email(
    client, model: str, lead: Lead, company_context: Optional[str], kb_text: str
) -> Draft:
    """Call an OpenAI-compatible chat model (DeepSeek/Qwen) and return a Draft.

    Uses JSON-object response mode and tolerantly parses the content into a
    Draft. Raises on API or unrecoverable parse error (caller handles).
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
    return _parse_draft_payload(content)
