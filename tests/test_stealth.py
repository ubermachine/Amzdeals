from scraper.stealth import get_stealth_headers, USER_AGENTS


def test_get_stealth_headers_returns_dict():
    headers = get_stealth_headers()
    assert isinstance(headers, dict)


def test_get_stealth_headers_has_required_keys():
    headers = get_stealth_headers()
    required = [
        "Accept",
        "Accept-Language",
        "Accept-Encoding",
        "Connection",
        "Upgrade-Insecure-Requests",
    ]
    for key in required:
        assert key in headers, f"Missing header: {key}"


def test_user_agents_pool_size():
    assert len(USER_AGENTS) >= 10, "Need at least 10 UAs for good rotation"
