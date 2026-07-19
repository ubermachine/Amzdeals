### Task 3: Category Deals Aggregator

**Files:**
- Modify: `scraper/engine.py` (add `search_category_deals` after `compute_deal_score`)
- Modify: `cache/sqlite_cache.py:11-14` (add `make_category_cache_key`)
- Create: `tests/test_search_category_deals.py`

**Interfaces:**
- Consumes:
  - `build_category_url(node: str, min_discount: int, max_discount: int, page: int) -> str` (Task 1)
  - `compute_deal_score(product: dict) -> int` (Task 2)
  - `_fetch_with_retry(url: str) -> str | None` (existing, `scraper/engine.py:41`)
  - `parse_search_results(html: str) -> list[dict]` (existing, `scraper/parser.py:56`)
  - `SearchCache` (existing, `cache/sqlite_cache.py:17`)
  - `config.TOP_DEALS_PAGES`, `config.TOP_DEALS_LIMIT`, `config.THROTTLE_MIN`, `config.THROTTLE_MAX`
- Produces:
  - `make_category_cache_key(node: str, min_discount: int, max_discount: int) -> str`
  - `search_category_deals(node: str, category_name: str, min_discount: int, max_discount: int, cache: SearchCache) -> dict`
    Returns: `{"category": str, "node": str, "products": list[dict], "total_results": int, "cached": bool}`

- [ ] **Step 1: Write failing test for `make_category_cache_key`**

Create `tests/test_search_category_deals.py`:

```python
"""Tests for category deals aggregation."""

from cache.sqlite_cache import make_category_cache_key


def test_category_cache_key_deterministic():
    key1 = make_category_cache_key("976419031", 40, 90)
    key2 = make_category_cache_key("976419031", 40, 90)
    assert key1 == key2
    assert len(key1) == 64  # SHA256 hex


def test_category_cache_key_differs_by_node():
    key1 = make_category_cache_key("976419031", 40, 90)
    key2 = make_category_cache_key("1571271031", 40, 90)
    assert key1 != key2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_search_category_deals.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_category_cache_key'`

- [ ] **Step 3: Add `make_category_cache_key` to cache module**

Add to `cache/sqlite_cache.py` after the existing `make_cache_key` function (after line 14):

```python


def make_category_cache_key(node: str, min_discount: int, max_discount: int) -> str:
    """Generate a deterministic SHA256 cache key for category deals."""
    raw = f"top-deals:{node}:{min_discount}:{max_discount}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

- [ ] **Step 4: Run cache key tests to verify they pass**

Run: `python -m pytest tests/test_search_category_deals.py -v`
Expected: 2 passed

- [ ] **Step 5: Add async integration test for `search_category_deals`**

Append to `tests/test_search_category_deals.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from scraper.engine import search_category_deals


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
```

- [ ] **Step 6: Implement `search_category_deals`**

Add to `scraper/engine.py` after `compute_deal_score`. Also add the import for `make_category_cache_key` at line 11:

Update import at line 11:
```python
from cache.sqlite_cache import SearchCache, make_cache_key, make_category_cache_key
```

Add the function:

```python


async def search_category_deals(
    node: str,
    category_name: str,
    min_discount: int,
    max_discount: int,
    cache: SearchCache,
) -> dict:
    """Fetch top deals for a category by browse-node, score, and rank.

    Fetches up to TOP_DEALS_PAGES pages, deduplicates by ASIN,
    computes deal scores, and returns the top TOP_DEALS_LIMIT products.

    Args:
        node: Amazon browse-node ID.
        category_name: Human-readable category name.
        min_discount: Minimum discount percentage.
        max_discount: Maximum discount percentage.
        cache: SearchCache instance.

    Returns:
        Dict with keys: category, node, products, total_results, cached.
    """
    cache_key = make_category_cache_key(node, min_discount, max_discount)

    # Check cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    # Fetch multiple pages
    all_products = []
    seen_asins = set()

    for page_num in range(1, config.TOP_DEALS_PAGES + 1):
        # Throttle between pages
        delay = random.uniform(config.THROTTLE_MIN, config.THROTTLE_MAX)
        await asyncio.sleep(delay)

        url = build_category_url(node, min_discount, max_discount, page_num)
        html = await _fetch_with_retry(url)

        if html is None:
            logger.warning(
                "Failed to fetch page %d for category %s (node %s)",
                page_num, category_name, node,
            )
            continue

        products = parse_search_results(html)
        for p in products:
            asin = p.get("asin")
            if asin and asin not in seen_asins:
                seen_asins.add(asin)
                all_products.append(p)

    # Score and rank
    for p in all_products:
        p["deal_score"] = compute_deal_score(p)

    all_products.sort(key=lambda p: p["deal_score"], reverse=True)
    top_products = all_products[: config.TOP_DEALS_LIMIT]

    result = {
        "category": category_name,
        "node": node,
        "products": top_products,
        "total_results": len(top_products),
        "cached": False,
    }

    # Store in cache
    await cache.set(cache_key, result)

    return result
```

- [ ] **Step 7: Run all tests to verify they pass**

Run: `python -m pytest tests/test_search_category_deals.py tests/test_deal_score.py tests/test_category_url.py -v`
Expected: All passed

- [ ] **Step 8: Commit**

```bash
git add cache/sqlite_cache.py scraper/engine.py tests/test_search_category_deals.py
git commit -m "feat: add search_category_deals aggregator with dedup and scoring"
```

---

