import pytest
from founder_bot.config import Settings


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "12345")
    monkeypatch.setenv("APOLLO_API_KEY", "ap")
    monkeypatch.setenv("HUNTER_API_KEY", "hu")
    monkeypatch.setenv("LLM_API_KEY", "llm")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    settings = Settings.from_env()
    assert settings.telegram_bot_token == "tok"
    assert settings.telegram_owner_id == 12345
    assert settings.apollo_api_key == "ap"
    assert settings.llm_api_key == "llm"
    assert settings.llm_base_url == "https://api.deepseek.com"  # default
    assert settings.llm_model == "deepseek-chat"  # default
    assert settings.gmail_address == "me@gmail.com"


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "1")
    monkeypatch.setenv("LLM_API_KEY", "llm")
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Settings.from_env()
