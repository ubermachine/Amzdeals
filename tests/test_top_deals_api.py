"""Tests for /api/top-deals and /api/categories endpoints."""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_categories_returns_all_categories():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 10
    assert data[0]["name"] == "Electronics"
    assert "node" in data[0]


@pytest.mark.asyncio
async def test_top_deals_returns_scored_products():
    mock_result = {
        "category": "Electronics",
        "node": "976419031",
        "products": [
            {"asin": "B001", "title": "Test", "deal_score": 85, "discount_pct": 70},
        ],
        "total_results": 1,
        "cached": False,
    }

    with patch("main.search_category_deals", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = mock_result
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/top-deals?category=976419031")

    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "Electronics"
    assert data["products"][0]["deal_score"] == 85


@pytest.mark.asyncio
async def test_top_deals_requires_category():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/top-deals")
    assert resp.status_code == 422  # FastAPI validation error
