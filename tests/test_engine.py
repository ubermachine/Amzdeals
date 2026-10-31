import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from scraper.engine import build_search_url, search_deals
from cache.sqlite_cache import SearchCache

@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_cache.db")


def test_build_search_url_basic():
    url = build_search_url("Perfume", 40, 90, 1)
    assert "amazon.in" in url
    assert "k=Perfume" in url or "k=perfume" in url.lower()
    # 40% maps to 35% tier: 2665402031
    assert "rh=p_n_pct-off-with-tax%3A2665402031" in url
    assert "s=exact-aware-popularity-rank" in url
    assert "page=1" in url
    assert "pct-off=" not in url  # Zero redirects: avoids legacy pct-off query param


def test_build_search_url_page_2():
    url = build_search_url("Laptop", 50, 80, 2)
    assert "page=2" in url
    # 50% maps to 50% tier: 2665401031
    assert "rh=p_n_pct-off-with-tax%3A2665401031" in url


def test_build_search_url_sort_options():
    url_reviews = build_search_url("Laptop", 50, 80, 1, sort_by="reviews")
    assert "s=review-rank" in url_reviews

    url_featured = build_search_url("Laptop", 50, 80, 1, sort_by="featured")
    assert "s=relevanceblender" in url_featured


def test_build_search_url_zero_discount():
    url = build_search_url("Laptop", 0, 80, 1)
    assert "p_n_pct-off-with-tax" not in url


@pytest.mark.asyncio
async def test_search_deals_returns_cached(test_db_path):
    """When cache has data, search_deals should return it without hitting Amazon."""
    cache = SearchCache(test_db_path)
    await cache.init()

    cached_data = {
        "query": "Perfume",
        "page": 1,
        "products": [{"asin": "CACHED123", "title": "Cached Product"}],
        "total_results": 1,
    }

    from cache.sqlite_cache import make_cache_key

    key = make_cache_key("Perfume", 40, 90, 1)
    await cache.set(key, cached_data)

    result = await search_deals("Perfume", 40, 90, 1, cache)
    assert result["cached"] is True
    assert result["products"][0]["asin"] == "CACHED123"
    await cache.close()


@pytest.mark.asyncio
async def test_search_deals_fetches_on_cache_miss(test_db_path):
    """When cache is empty, search_deals should fetch from Amazon."""
    cache = SearchCache(test_db_path)
    await cache.init()

    fake_html = """
    <div class="s-main-slot s-result-list">
      <div data-component-type="s-search-result" data-asin="FRESH001" class="s-result-item">
        <h2><a class="a-link-normal" href="/dp/FRESH001">
          <span class="a-text-normal">Fresh Product</span>
        </a></h2>
        <span class="a-price" data-a-color="base"><span class="a-offscreen">₹500</span></span>
        <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">₹1000</span></span>
      </div>
    </div>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = fake_html
    mock_response.raise_for_status = MagicMock()

    with patch("scraper.engine._get_session", new_callable=AsyncMock) as mock_get_session, \
         patch("scraper.engine.verify_product_against_flipkart", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {"match_found": False, "verdict": "unverified", "is_deal": False}
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_get_session.return_value = mock_session

        # Patch sleep (throttle delay) and semaphore to make tests fast
        with patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock):
            with patch("scraper.engine._scrape_semaphore", new_callable=AsyncMock) as mock_sem:
                mock_sem.__aenter__ = AsyncMock(return_value=None)
                mock_sem.__aexit__ = AsyncMock(return_value=None)
                result = await search_deals("Test", 40, 90, 1, cache)

        assert result["cached"] is False
        assert len(result["products"]) >= 1
        assert result["products"][0]["asin"] == "FRESH001"

    await cache.close()


@pytest.mark.asyncio
async def test_search_deals_never_caches_empty_products(test_db_path):
    """When scrape returns 0 products, search_deals must NOT cache the empty result."""
    cache = SearchCache(test_db_path)
    await cache.init()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>No products here</body></html>"
    mock_response.raise_for_status = MagicMock()

    with patch("scraper.engine._get_session", new_callable=AsyncMock) as mock_get_session, \
         patch("scraper.engine.verify_product_against_flipkart", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {"match_found": False, "verdict": "unverified", "is_deal": False}
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_get_session.return_value = mock_session

        with patch("scraper.engine.asyncio.sleep", new_callable=AsyncMock), \
             patch("scraper.engine._scrape_semaphore", new_callable=AsyncMock) as mock_sem:
            mock_sem.__aenter__ = AsyncMock(return_value=None)
            mock_sem.__aexit__ = AsyncMock(return_value=None)
            result = await search_deals("EmptyQuery", 40, 90, 1, cache)

    assert result["products"] == []
    from cache.sqlite_cache import make_cache_key
    key = make_cache_key("EmptyQuery", 40, 90, 1)
    cached = await cache.get(key)
    assert cached is None, "Empty search result should not be stored in cache"
    await cache.close()
