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


def test_category_cache_key_differs_by_sort():
    key1 = make_category_cache_key("976419031", 40, 90, sort_by="popularity")
    key2 = make_category_cache_key("976419031", 40, 90, sort_by="deal_score")
    assert key1 != key2


MOCK_HTML = """
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
"""


@pytest.mark.asyncio
async def test_search_category_deals_popularity_default():
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
    assert len(result["products"]) == 2
    # Both products have deal_score
    for p in result["products"]:
        assert "deal_score" in p
        assert isinstance(p["deal_score"], int)
    # Default is popularity, preserving scraped order B002 then B001
    assert result["products"][0]["asin"] == "B002"
    assert result["products"][1]["asin"] == "B001"


@pytest.mark.asyncio
async def test_search_category_deals_deal_score_sort():
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
            sort_by="deal_score",
        )

    scores = [p["deal_score"] for p in result["products"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_search_category_deals_reviews_sort():
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
            sort_by="reviews",
        )

    reviews = [p["review_count"] for p in result["products"]]
    assert reviews == sorted(reviews, reverse=True)
    assert result["products"][0]["asin"] == "B001"  # 1543 reviews vs 500


@pytest.mark.asyncio
async def test_search_category_deals_deduplicates_asins():
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


@pytest.mark.asyncio
async def test_search_category_deals_all_fetches_fail_no_cache():
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    with patch("scraper.engine._fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
        mock_fetch.return_value = None

        result = await search_category_deals(
            node="976419031",
            category_name="Electronics",
            min_discount=40,
            max_discount=90,
            cache=mock_cache,
        )

    assert "error" in result
    assert result["error"] == "Failed to fetch results from Amazon. Please try again later."
    assert result["products"] == []
    assert result["total_results"] == 0
    assert result["cached"] is False
    mock_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_search_category_deals_never_caches_empty_products():
    """If Amazon returns HTML with 0 products, the result MUST NOT be cached."""
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    # Empty HTML with no products
    with patch("scraper.engine._fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
        mock_fetch.return_value = "<html><body>No products here</body></html>"

        result = await search_category_deals(
            node="976419031",
            category_name="Electronics",
            min_discount=40,
            max_discount=90,
            cache=mock_cache,
            sort_by="popularity",
        )

    assert result["products"] == []
    assert result["total_results"] == 0
    # Invariant: Never cache empty products!
    mock_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_search_category_deals_bestsellers_alias():
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
            sort_by="bestsellers",
        )

    assert len(result["products"]) == 2
    assert result["products"][0]["asin"] == "B002"


@pytest.mark.asyncio
async def test_search_category_deals_stops_early_when_limit_reached():
    """If 100 products are collected, it should not fetch remaining pages."""
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    # Generate HTML with 100 distinct items
    many_items = "".join([
        f'''<div data-component-type="s-search-result" data-asin="ASIN_{i}">
            <h2><a href="/dp/ASIN_{i}"><span class="a-text-normal">Product {i}</span></a></h2>
            <span class="a-price"><span class="a-offscreen">₹100</span></span>
            <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">₹200</span></span>
        </div>''' for i in range(110)
    ])

    with patch("scraper.engine._fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
        mock_fetch.return_value = many_items

        result = await search_category_deals(
            node="976419031",
            category_name="Electronics",
            min_discount=40,
            max_discount=90,
            cache=mock_cache,
        )

    # Should have called fetch only once because page 1 had >= 100 products
    assert mock_fetch.call_count == 1
    assert len(result["products"]) == 100


@pytest.mark.asyncio
async def test_search_category_deals_price_floor_filters_cheap_accessories():
    """Smartphones category (node 1805560031) must filter out items under min_price (4500)."""
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    html_with_accessories = """
    <div data-component-type="s-search-result" data-asin="CASE_001">
      <h2><a href="/dp/CASE_001"><span class="a-text-normal">Silicone Back Cover for Phone</span></a></h2>
      <span class="a-price"><span class="a-offscreen">₹249</span></span>
      <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">₹999</span></span>
    </div>
    <div data-component-type="s-search-result" data-asin="PHONE_001">
      <h2><a href="/dp/PHONE_001"><span class="a-text-normal">Realme Narzo 60X 5G</span></a></h2>
      <span class="a-price"><span class="a-offscreen">₹11,999</span></span>
      <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">₹14,999</span></span>
    </div>
    """

    with patch("scraper.engine._fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
        mock_fetch.return_value = html_with_accessories

        result = await search_category_deals(
            node="1805560031",
            category_name="Smartphones",
            min_discount=10,
            max_discount=90,
            cache=mock_cache,
        )

    # CASE_001 (₹249) filtered out by min_price (4500); only PHONE_001 remains
    assert len(result["products"]) == 1
    assert result["products"][0]["asin"] == "PHONE_001"
    assert result["products"][0]["current_price"] == 11999.0


@pytest.mark.asyncio
async def test_search_category_deals_calibrated_true_deal():
    """Laptops category (node 1375424031) should award is_true_deal for genuine discounts (min_true_deal_pct=25)."""
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    laptop_html = """
    <div data-component-type="s-search-result" data-asin="LAPTOP_001">
      <h2><a href="/dp/LAPTOP_001"><span class="a-text-normal">High End Gaming Laptop</span></a></h2>
      <span class="a-price"><span class="a-offscreen">₹34,000</span></span>
      <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">₹50,000</span></span>
    </div>
    <div data-component-type="s-search-result" data-asin="LAPTOP_002">
      <h2><a href="/dp/LAPTOP_002"><span class="a-text-normal">Budget Everyday Laptop</span></a></h2>
      <span class="a-price"><span class="a-offscreen">₹42,500</span></span>
      <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">₹50,000</span></span>
    </div>
    """

    with patch("scraper.engine._fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
        mock_fetch.return_value = laptop_html

        result = await search_category_deals(
            node="1375424031",
            category_name="Laptops",
            min_discount=10,
            max_discount=90,
            cache=mock_cache,
        )

    # LAPTOP_001 has 32% discount (>= 25% min_true_deal_pct and >= median(23.5) + 8 = 31.5)
    laptop_1 = next(p for p in result["products"] if p["asin"] == "LAPTOP_001")
    assert laptop_1["discount_pct"] == 32
    assert laptop_1["is_true_deal"] is True

