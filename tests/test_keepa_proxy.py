import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_keepa_proxy_missing_asin(client):
    response = client.get("/api/keepa-graph")
    assert response.status_code == 422


def test_keepa_proxy_invalid_asin(client):
    response = client.get("/api/keepa-graph?asin=toolongasinstring1234567")
    assert response.status_code in (400, 422)


def test_keepa_proxy_success(client, monkeypatch):
    import main

    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy"

    async def mock_fetch_keepa(asin: str, range_days: int = 365):
        return dummy_png

    monkeypatch.setattr(main, "fetch_keepa_graph", mock_fetch_keepa)

    response = client.get("/api/keepa-graph?asin=B0DNTCMFRG&range=365")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == dummy_png
    assert "public" in response.headers.get("cache-control", "")


def test_keepa_proxy_upstream_failure(client, monkeypatch):
    import main

    async def mock_fetch_keepa(asin: str, range_days: int = 365):
        return None

    monkeypatch.setattr(main, "fetch_keepa_graph", mock_fetch_keepa)

    response = client.get("/api/keepa-graph?asin=B0DNTCMFRG")
    assert response.status_code == 502
