import httpx
from founder_bot.company import fetch_company_context


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extracts_visible_text_truncated():
    html = "<html><head><title>T</title><style>x{}</style></head>" \
           "<body><h1>Analytical Engines</h1><p>We build " + ("data " * 50) + "</p>" \
           "<script>var a=1;</script></body></html>"
    client = _client(lambda r: httpx.Response(200, text=html))
    text = fetch_company_context("analytical.com", client=client, max_chars=120)
    assert "Analytical Engines" in text
    assert "var a=1" not in text  # script stripped
    assert "x{}" not in text       # style stripped
    assert len(text) <= 120


def test_none_domain_returns_none():
    assert fetch_company_context(None, client=_client(lambda r: httpx.Response(200))) is None


def test_http_error_returns_none():
    client = _client(lambda r: httpx.Response(500))
    assert fetch_company_context("analytical.com", client=client) is None
