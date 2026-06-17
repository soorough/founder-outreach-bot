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
