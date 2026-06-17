from founder_bot.urls import normalize_linkedin_url


def test_valid_profile_url_normalized():
    assert normalize_linkedin_url(
        "https://www.linkedin.com/in/ada-lovelace/?trk=x"
    ) == "https://www.linkedin.com/in/ada-lovelace"


def test_adds_scheme_and_strips_trailing_slash():
    assert normalize_linkedin_url("linkedin.com/in/ada-lovelace/") == \
        "https://www.linkedin.com/in/ada-lovelace"


def test_non_linkedin_url_returns_none():
    assert normalize_linkedin_url("https://example.com/in/foo") is None


def test_non_profile_linkedin_url_returns_none():
    assert normalize_linkedin_url("https://www.linkedin.com/company/foo") is None


def test_garbage_returns_none():
    assert normalize_linkedin_url("hello there") is None
