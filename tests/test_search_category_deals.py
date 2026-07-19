"""Tests for category deals aggregation."""

import pytest
from unittest.mock import AsyncMock, patch

from cache.sqlite_cache import make_category_cache_key
from scraper.engine import search_category_deals


def test_category_cache_key_deterministic():
    key1 = make_category_cache_key("976419031", 40, 90)
    key2 = make_category_cache_key("976419031", 40, 90)
    assert key1 == key2
    assert len(key1) == 64  # SHA256 hex


def test_category_cache_key_differs_by_node():
    key1 = make_category_cache_key("976419031", 40, 90)
    key2 = make_category_cache_key("1571271031", 40, 90)
    assert key1 != key2


MOCK_HTML = """
<div data-component-type="s-search-result" data-asin="B001">
  <h2><a class="a-link-normal" href="/dp/B001">
    <span class="a-text-normal">Test Product 1</span>
  </a></h2>
  <span class="a-price" data-a-color="base"><span class="a-offscreen">₹499</span></span>
  <span class="a-price" data-a-strike="true"><span class="a-offscreen">₹1,999</span></span>
  <span class="a-icon-alt">4.2 out of 5 stars</span>
  <span class="a-size-base">1,543</span>
  <img class="s-image" src="https://img.example.com/1.jpg">
</div>
<div data-component-type="s-search-result" data-asin="B002">
  <h2><a class="a-link-normal" href="/dp/B002">
    <span class="a-text-normal">Test Product 2</span>
  </a></h2>
  <span class="a-price" data-a-color="base"><span class="a-offscreen">₹299</span></span>
  <span class="a-price" data-a-strike="true"><span class="a-offscreen">₹999</span></span>
  <span class="a-icon-alt">3.8 out of 5 stars</span>
  <span class="a-size-base">500</span>
  <img class="s-image" src="https://img.example.com/2.jpg">
</div>
"""


@pytest.mark.asyncio
async def test_search_category_deals_returns_scored_products():
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    with patch("scraper.engine._fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
        mock_fetch.return_value = MOCK_HTML

        result = await search_category_deals(
            node="976419031",
            category_name="Electronics",
            min_discount=40,
            max_discount=90,
            cache=mock_cache,
        )

    assert result["category"] == "Electronics"
    assert result["node"] == "976419031"
    assert len(result["products"]) > 0
    # Every product should have deal_score
    for p in result["products"]:
        assert "deal_score" in p
        assert isinstance(p["deal_score"], int)
    # Products should be sorted by deal_score descending
    scores = [p["deal_score"] for p in result["products"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_search_category_deals_deduplicates_asins():
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    # Return same HTML for all pages → duplicate ASINs
    with patch("scraper.engine._fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
        mock_fetch.return_value = MOCK_HTML

        result = await search_category_deals(
            node="976419031",
            category_name="Electronics",
            min_discount=40,
            max_discount=90,
            cache=mock_cache,
        )

    asins = [p["asin"] for p in result["products"]]
    assert len(asins) == len(set(asins)), "Duplicate ASINs found"


@pytest.mark.asyncio
async def test_search_category_deals_uses_cache():
    cached_data = {
        "category": "Electronics",
        "node": "976419031",
        "products": [{"asin": "B001", "deal_score": 80}],
        "total_results": 1,
        "cached": False,
    }
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=cached_data)

    result = await search_category_deals(
        node="976419031",
        category_name="Electronics",
        min_discount=40,
        max_discount=90,
        cache=mock_cache,
    )

    assert result["cached"] is True
    assert result["products"][0]["asin"] == "B001"
