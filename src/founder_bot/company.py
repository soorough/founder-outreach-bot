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
