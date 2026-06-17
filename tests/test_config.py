import pytest
from founder_bot.config import Settings


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "12345")
    monkeypatch.setenv("APOLLO_API_KEY", "ap")
    monkeypatch.setenv("HUNTER_API_KEY", "hu")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an")
    settings = Settings.from_env()
    assert settings.telegram_bot_token == "tok"
    assert settings.telegram_owner_id == 12345
    assert settings.apollo_api_key == "ap"
    assert settings.google_token_path == "token.json"  # default


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an")
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Settings.from_env()
