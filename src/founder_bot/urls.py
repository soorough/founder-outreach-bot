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
