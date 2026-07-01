import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_FOOTER = (
    "Souravh Pateriya\n"
    "Portfolio: https://sourav.live | GitHub: https://github.com/soorough | "
    "LinkedIn: https://www.linkedin.com/in/souravhpateriya\n"
    "souravhpateriyad04@gmail.com"
)

# HTML footer — clickable link text instead of raw URLs.
DEFAULT_FOOTER_HTML = (
    '<p><strong>Souravh Pateriya</strong><br>'
    '<a href="https://sourav.live">Portfolio</a> | '
    '<a href="https://github.com/soorough">GitHub</a> | '
    '<a href="https://www.linkedin.com/in/souravhpateriya">LinkedIn</a></p>'
    '<p>📩 <a href="mailto:souravhpateriyad04@gmail.com">souravhpateriyad04@gmail.com</a></p>'
)


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@dataclass
class Settings:
    telegram_bot_token: str
    telegram_owner_id: int
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    apollo_api_key: Optional[str]
    proxycurl_api_key: Optional[str]
    hunter_api_key: Optional[str]
    serper_api_key: Optional[str]
    gmail_address: str
    gmail_app_password: str
    kb_dir: str
    kb_text: Optional[str]  # if set (e.g. on Railway), used instead of kb/ files
    email_footer: str
    email_footer_html: str
    resume_path: Optional[str]  # local PDF to attach to every draft
    resume_url: Optional[str]   # or a hosted PDF URL (for cloud deploys)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            telegram_owner_id=int(_require("TELEGRAM_OWNER_ID")),
            llm_api_key=_require("LLM_API_KEY"),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
            apollo_api_key=os.getenv("APOLLO_API_KEY") or None,
            proxycurl_api_key=os.getenv("PROXYCURL_API_KEY") or None,
            hunter_api_key=os.getenv("HUNTER_API_KEY") or None,
            serper_api_key=os.getenv("SERPER_API_KEY") or None,
            gmail_address=_require("GMAIL_ADDRESS"),
            gmail_app_password=_require("GMAIL_APP_PASSWORD"),
            kb_dir=os.getenv("KB_DIR", "kb"),
            kb_text=os.getenv("KB_TEXT") or None,
            email_footer=os.getenv("EMAIL_FOOTER") or DEFAULT_FOOTER,
            email_footer_html=os.getenv("EMAIL_FOOTER_HTML") or DEFAULT_FOOTER_HTML,
            resume_path=os.getenv("RESUME_PATH") or None,
            resume_url=os.getenv("RESUME_URL") or None,
        )
