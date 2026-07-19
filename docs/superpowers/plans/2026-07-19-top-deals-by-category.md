# Top Deals by Category — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Top Deals" tab that discovers and ranks the best 50 products per Amazon.in category using browse-node scraping and a weighted deal-quality score.

**Architecture:** Dedicated browse-node URL builder constructs `rh=n:<node>` queries instead of keyword searches. A multi-page aggregator fetches 3 pages per category, deduplicates by ASIN, computes a weighted score (60% discount + 25% rating + 15% reviews), and returns the top 50. Frontend lazy-loads one category at a time via pill bar clicks.

**Tech Stack:** Python 3.12, FastAPI, httpx, BeautifulSoup (lxml), aiosqlite, Vanilla HTML/CSS/JS

## Global Constraints

- All changes are additive — existing `/api/search`, `search_deals()`, `parse_search_results()`, `SearchCache` class, and frontend search UI remain untouched
- Follow existing code patterns (async functions, same stealth headers, same parser)
- Cache TTL: 30 minutes (reuse `config.CACHE_TTL_SECONDS`)
- Amazon throttle: 2–5s random delay between page fetches (reuse `config.THROTTLE_MIN/MAX`)
- No new dependencies — all libraries already in `requirements.txt`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `config.py` | Add `TOP_DEALS_PAGES`, `TOP_DEALS_LIMIT` constants |
| `scraper/engine.py` | Add `build_category_url()`, `compute_deal_score()`, `search_category_deals()` |
| `main.py` | Add `GET /api/top-deals` endpoint |
| `static/index.html` | Add tab bar, tab panes, category pill bar, top-deals grid |
| `static/style.css` | Add tab, pill, deal-score badge, skeleton styles |
| `static/app.js` | Add tab switching, lazy fetching, AbortController, deal-score rendering |
| `tests/test_deal_score.py` | Unit tests for `compute_deal_score()` |
| `tests/test_category_url.py` | Unit tests for `build_category_url()` |
| `tests/test_top_deals_api.py` | Integration test for `/api/top-deals` endpoint |

---

### Task 1: Config Constants & Category URL Builder

**Files:**
- Modify: `config.py:36-37` (append after `CATEGORIES` list)
- Modify: `scraper/engine.py:18-38` (add new function after existing `build_search_url`)
- Create: `tests/test_category_url.py`

**Interfaces:**
- Consumes: `config.AMAZON_BASE_URL` (existing, value `"https://www.amazon.in/s"`)
- Produces:
  - `config.TOP_DEALS_PAGES: int` (value `3`)
  - `config.TOP_DEALS_LIMIT: int` (value `50`)
  - `build_category_url(node: str, min_discount: int, max_discount: int, page: int) -> str`

- [ ] **Step 1: Write the failing test for `build_category_url`**

Create `tests/test_category_url.py`:

```python
"""Tests for build_category_url."""

from scraper.engine import build_category_url


def test_build_category_url_basic():
    url = build_category_url(
        node="976419031", min_discount=40, max_discount=90, page=1
    )
    assert "amazon.in/s" in url
    assert "rh=n%3A976419031" in url  # URL-encoded rh=n:976419031
    assert "pct-off=40-90" in url
    assert "s=discount-percent-rank" in url
    assert "page=1" in url


def test_build_category_url_page_2():
    url = build_category_url(
        node="1571271031", min_discount=10, max_discount=99, page=2
    )
    assert "rh=n%3A1571271031" in url
    assert "pct-off=10-99" in url
    assert "page=2" in url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_category_url.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_category_url'`

- [ ] **Step 3: Add config constants**

Append to `config.py` after line 37 (after the `CATEGORIES` list):

```python

# Top Deals
TOP_DEALS_PAGES = 3       # pages to scrape per category
TOP_DEALS_LIMIT = 50      # max products per category
```

- [ ] **Step 4: Implement `build_category_url`**

Add to `scraper/engine.py` after `build_search_url` (after line 38):

```python


def build_category_url(
    node: str, min_discount: int, max_discount: int, page: int
) -> str:
    """Construct an Amazon.in category browse URL with discount filters.

    Args:
        node: Amazon browse-node ID (e.g. "976419031" for Electronics).
        min_discount: Minimum discount percentage.
        max_discount: Maximum discount percentage.
        page: Page number (1-indexed).

    Returns:
        Full Amazon.in browse-node URL string.
    """
    params = {
        "rh": f"n:{node}",
        "pct-off": f"{min_discount}-{max_discount}",
        "s": "discount-percent-rank",
        "page": page,
    }
    return f"{config.AMAZON_BASE_URL}?{urlencode(params)}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_category_url.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add config.py scraper/engine.py tests/test_category_url.py
git commit -m "feat: add config constants and build_category_url for browse-node scraping"
```

---

### Task 2: Deal Score Calculator

**Files:**
- Modify: `scraper/engine.py` (add new function after `build_category_url`)
- Create: `tests/test_deal_score.py`

**Interfaces:**
- Consumes: Product dicts from `parse_search_results()` with keys: `discount_pct: int | None`, `rating: float | None`, `review_count: int | None`
- Produces: `compute_deal_score(product: dict) -> int` — returns 0–100 integer

- [ ] **Step 1: Write failing tests for `compute_deal_score`**

Create `tests/test_deal_score.py`:

```python
"""Tests for compute_deal_score."""

from scraper.engine import compute_deal_score


def test_full_score_components():
    """Product with all fields filled."""
    product = {"discount_pct": 75, "rating": 4.2, "review_count": 1543}
    score = compute_deal_score(product)
    # 75*0.6 + (4.2/5*100)*0.25 + (1543/5000*100)*0.15
    # = 45 + 21.0 + 4.629 = 70.629 → 71
    assert score == 71


def test_perfect_score():
    """Max discount, perfect rating, tons of reviews."""
    product = {"discount_pct": 100, "rating": 5.0, "review_count": 10000}
    score = compute_deal_score(product)
    # 100*0.6 + 100*0.25 + 100*0.15 = 60 + 25 + 15 = 100
    assert score == 100


def test_null_discount_scores_zero():
    """Products with no discount get score 0."""
    product = {"discount_pct": None, "rating": 4.5, "review_count": 2000}
    score = compute_deal_score(product)
    assert score == 0


def test_null_rating_and_reviews():
    """Missing rating and reviews only use discount component."""
    product = {"discount_pct": 60, "rating": None, "review_count": None}
    score = compute_deal_score(product)
    # 60*0.6 + 0 + 0 = 36
    assert score == 36


def test_review_count_capped_at_5000():
    """Reviews above 5000 don't increase score."""
    p1 = {"discount_pct": 50, "rating": 4.0, "review_count": 5000}
    p2 = {"discount_pct": 50, "rating": 4.0, "review_count": 50000}
    assert compute_deal_score(p1) == compute_deal_score(p2)


def test_zero_everything():
    """All zeros."""
    product = {"discount_pct": 0, "rating": 0.0, "review_count": 0}
    score = compute_deal_score(product)
    assert score == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deal_score.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_deal_score'`

- [ ] **Step 3: Implement `compute_deal_score`**

Add to `scraper/engine.py` after the `build_category_url` function:

```python


def compute_deal_score(product: dict) -> int:
    """Compute a 0–100 deal quality score for a product.

    Weighted formula:
        - 60% discount percentage (0–100)
        - 25% rating normalized to 0–100 scale
        - 15% review count normalized to 0–100 (capped at 5000)

    Products with no discount are scored 0.

    Args:
        product: Dict with keys discount_pct, rating, review_count.

    Returns:
        Integer score from 0 to 100.
    """
    discount = product.get("discount_pct")
    if discount is None:
        return 0

    rating = product.get("rating") or 0.0
    reviews = product.get("review_count") or 0

    norm_rating = (rating / 5.0) * 100
    norm_reviews = (min(reviews, 5000) / 5000) * 100

    score = discount * 0.6 + norm_rating * 0.25 + norm_reviews * 0.15
    return round(score)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deal_score.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/engine.py tests/test_deal_score.py
git commit -m "feat: add compute_deal_score with weighted ranking formula"
```

---

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

### Task 4: API Endpoint & Categories List

**Files:**
- Modify: `main.py:36-56` (add new endpoint and categories list endpoint)
- Create: `tests/test_top_deals_api.py`

**Interfaces:**
- Consumes:
  - `search_category_deals(node, category_name, min_discount, max_discount, cache)` (Task 3)
  - `config.CATEGORIES` (existing, list of `{"name": str, "node": str}` dicts)
  - `SearchCache` (existing)
- Produces:
  - `GET /api/top-deals?category=<node>&min_discount=40&max_discount=90` → JSON response
  - `GET /api/categories` → `[{"name": "Electronics", "node": "976419031"}, ...]`

- [ ] **Step 1: Write failing test for `/api/categories`**

Create `tests/test_top_deals_api.py`:

```python
"""Tests for /api/top-deals and /api/categories endpoints."""

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_top_deals_api.py::test_categories_returns_all_categories -v`
Expected: FAIL with 404 (endpoint doesn't exist)

- [ ] **Step 3: Implement both endpoints**

Add to `main.py` after the existing `/api/search` endpoint (after line 56) and before the static files mount (before line 60):

```python

@app.get("/api/categories")
async def api_categories():
    """Return the list of available Amazon.in categories."""
    return config.CATEGORIES


@app.get("/api/top-deals")
async def api_top_deals(
    category: str = Query(..., min_length=1, description="Amazon browse-node ID"),
    min_discount: int = Query(40, ge=0, le=99, description="Minimum discount %"),
    max_discount: int = Query(90, ge=1, le=100, description="Maximum discount %"),
):
    """Get top deals for a specific Amazon.in category."""
    global _cache
    if not _cache:
        _cache = SearchCache()
        await _cache.init()

    # Look up category name from node
    category_name = "Unknown"
    for cat in config.CATEGORIES:
        if cat["node"] == category:
            category_name = cat["name"]
            break

    result = await search_category_deals(
        node=category,
        category_name=category_name,
        min_discount=min_discount,
        max_discount=max_discount,
        cache=_cache,
    )
    return result
```

Also add the import at the top of `main.py` (line 8):

```python
from scraper.engine import search_deals, search_category_deals
```

And add:
```python
import config
```

- [ ] **Step 4: Add test for `/api/top-deals` with mocked scraping**

Append to `tests/test_top_deals_api.py`:

```python
from unittest.mock import AsyncMock, patch


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
```

- [ ] **Step 5: Run all API tests**

Run: `python -m pytest tests/test_top_deals_api.py -v`
Expected: All passed

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_top_deals_api.py
git commit -m "feat: add /api/top-deals and /api/categories endpoints"
```

---

### Task 5: Frontend — Tab Bar, Category Pills & Top Deals UI

**Files:**
- Modify: `static/index.html` (restructure with tabs)
- Modify: `static/style.css` (add tab bar, pill bar, deal-score badge, skeleton styles)
- Modify: `static/app.js` (add tab switching, lazy fetching, AbortController, deal-score rendering)

**Interfaces:**
- Consumes:
  - `GET /api/categories` → `[{"name": str, "node": str}, ...]` (Task 4)
  - `GET /api/top-deals?category=<node>` → `{category, node, products: [{...deal_score}], ...}` (Task 4)
- Produces: Complete frontend UI with two tabs and lazy-loaded category deals

- [ ] **Step 1: Rewrite `static/index.html` with tab structure**

Replace entire contents of `static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amazon Deal Finder — Best Deals & Top Category Deals</title>
    <meta name="description" content="Discover the best discounts and top deals across Amazon India categories. Find verified deals with price history.">
    <!-- Google Fonts: Inter -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="app-container">
        <header class="glass-header">
            <h1><span class="accent">Amazon</span> Deal Finder</h1>
            <p class="subtitle">Discover the best discounts across Amazon India</p>
        </header>

        <nav class="tab-bar glass-panel" id="tab-bar">
            <button class="tab-btn active" data-tab="tab-search" id="tab-btn-search">
                <span class="tab-icon">🔍</span> Search Deals
            </button>
            <button class="tab-btn" data-tab="tab-top-deals" id="tab-btn-top-deals">
                <span class="tab-icon">🏆</span> Top Deals
            </button>
            <div class="tab-indicator" id="tab-indicator"></div>
        </nav>

        <main>
            <!-- Tab 1: Search Deals (existing) -->
            <div class="tab-pane active" id="tab-search">
                <section class="search-section glass-panel">
                    <form id="search-form">
                        <div class="input-group">
                            <label for="query">Search Query</label>
                            <input type="text" id="query" name="query" placeholder="e.g. Laptops" required>
                        </div>
                        <div class="input-group">
                            <label for="min_discount">Min Discount (%)</label>
                            <input type="number" id="min_discount" name="min_discount" min="0" max="100" value="40" step="5">
                        </div>
                        <div class="input-group">
                            <label for="max_discount">Max Discount (%)</label>
                            <input type="number" id="max_discount" name="max_discount" min="0" max="100" placeholder="100" step="5">
                        </div>
                        <div class="button-container">
                            <button type="submit" id="search-btn">Find Deals</button>
                        </div>
                    </form>
                </section>

                <section id="results-section" class="hidden">
                    <div class="results-header">
                        <h2>Found Deals</h2>
                        <span id="cache-status" class="badge hidden"></span>
                    </div>
                    <div id="loading-spinner" class="spinner-container hidden">
                        <div class="spinner"></div>
                        <p>Scraping deals, this might take a moment...</p>
                    </div>
                    <div id="error-message" class="error hidden"></div>
                    <div id="product-grid" class="product-grid">
                        <!-- Products will be injected here -->
                    </div>
                </section>
            </div>

            <!-- Tab 2: Top Deals by Category -->
            <div class="tab-pane" id="tab-top-deals">
                <div class="category-pill-bar" id="category-pill-bar">
                    <!-- Category pills injected by JS -->
                </div>
                <div id="top-deals-error" class="error hidden"></div>
                <div id="top-deals-skeleton" class="product-grid hidden">
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                </div>
                <div id="top-deals-grid" class="product-grid">
                    <!-- Top deal products injected by JS -->
                </div>
            </div>
        </main>
    </div>
    <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Add new styles to `static/style.css`**

Append the following to the end of `static/style.css` (after line 448):

```css

/* ───────────── Tab Bar ───────────── */
.tab-bar {
    display: flex;
    position: relative;
    gap: 0;
    padding: 0.5rem;
    margin-bottom: 2rem;
    overflow: hidden;
}

.tab-btn {
    flex: 1;
    background: transparent;
    color: var(--text-secondary);
    border: none;
    border-radius: var(--radius-sm);
    padding: 1rem 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    font-family: var(--font-family);
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
}

.tab-btn:hover {
    color: var(--text-primary);
    transform: none;
    box-shadow: none;
}

.tab-btn.active {
    color: var(--text-primary);
}

.tab-icon {
    font-size: 1.2rem;
}

.tab-indicator {
    position: absolute;
    bottom: 0.5rem;
    left: 0.5rem;
    height: calc(100% - 1rem);
    width: calc(50% - 0.5rem);
    background: rgba(123, 44, 191, 0.15);
    border: 1px solid rgba(123, 44, 191, 0.3);
    border-radius: var(--radius-sm);
    transition: transform 0.35s cubic-bezier(0.25, 0.8, 0.25, 1);
    z-index: 0;
}

.tab-indicator.pos-1 {
    transform: translateX(calc(100% + 0.5rem));
}

/* ───────────── Tab Panes ───────────── */
.tab-pane {
    display: none;
    animation: fadeIn 0.3s ease;
}

.tab-pane.active {
    display: block;
}

/* ───────────── Category Pill Bar ───────────── */
.category-pill-bar {
    display: flex;
    gap: 0.75rem;
    overflow-x: auto;
    padding: 0.5rem 0 1.5rem 0;
    scrollbar-width: thin;
    scrollbar-color: rgba(123, 44, 191, 0.3) transparent;
    -webkit-overflow-scrolling: touch;
}

.category-pill-bar::-webkit-scrollbar {
    height: 4px;
}

.category-pill-bar::-webkit-scrollbar-track {
    background: transparent;
}

.category-pill-bar::-webkit-scrollbar-thumb {
    background: rgba(123, 44, 191, 0.3);
    border-radius: 4px;
}

.category-pill {
    flex-shrink: 0;
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--panel-border);
    border-radius: 24px;
    padding: 0.6rem 1.4rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: var(--transition);
    font-family: var(--font-family);
    white-space: nowrap;
}

.category-pill:hover {
    color: var(--text-primary);
    border-color: var(--accent-color);
    transform: none;
    box-shadow: none;
}

.category-pill.active {
    background: var(--accent-color);
    color: white;
    border-color: var(--accent-color);
    box-shadow: 0 0 20px var(--accent-glow);
}

.category-pill.loading {
    animation: pillPulse 1.2s ease-in-out infinite;
}

@keyframes pillPulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ───────────── Deal Score Badge ───────────── */
.deal-score-badge {
    position: absolute;
    top: 1rem;
    left: 1rem;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    color: white;
    z-index: 2;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
}

.deal-score-badge.score-high {
    background: linear-gradient(135deg, #06d6a0, #00b894);
}

.deal-score-badge.score-mid {
    background: linear-gradient(135deg, #ffd166, #f4a261);
}

.deal-score-badge.score-low {
    background: linear-gradient(135deg, #ef476f, #e63946);
}

/* ───────────── Skeleton Loading ───────────── */
.skeleton-card {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: var(--radius-md);
    overflow: hidden;
    min-height: 360px;
}

.skeleton-img {
    width: 100%;
    height: 200px;
    background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
}

.skeleton-text {
    height: 16px;
    margin: 1rem 1.5rem 0;
    border-radius: 4px;
    background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
}

.skeleton-text.short {
    width: 60%;
    margin-top: 0.75rem;
}

@keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}
```

- [ ] **Step 3: Rewrite `static/app.js` with tab logic and category fetching**

Replace entire contents of `static/app.js`:

```javascript
document.addEventListener('DOMContentLoaded', () => {
    // ─── Existing Search Tab Elements ───
    const searchForm = document.getElementById('search-form');
    const resultsSection = document.getElementById('results-section');
    const loadingSpinner = document.getElementById('loading-spinner');
    const productGrid = document.getElementById('product-grid');
    const errorMessage = document.getElementById('error-message');
    const cacheStatus = document.getElementById('cache-status');

    // ─── Tab Elements ───
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const tabIndicator = document.getElementById('tab-indicator');

    // ─── Top Deals Elements ───
    const categoryPillBar = document.getElementById('category-pill-bar');
    const topDealsGrid = document.getElementById('top-deals-grid');
    const topDealsSkeleton = document.getElementById('top-deals-skeleton');
    const topDealsError = document.getElementById('top-deals-error');

    let topDealsInitialized = false;
    let currentAbortController = null;

    // ─── Tab Switching ───
    tabBtns.forEach((btn, index) => {
        btn.addEventListener('click', () => {
            // Update active tab button
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Move indicator
            tabIndicator.className = 'tab-indicator';
            if (index > 0) {
                tabIndicator.classList.add(`pos-${index}`);
            }

            // Show corresponding pane
            const targetId = btn.getAttribute('data-tab');
            tabPanes.forEach(pane => pane.classList.remove('active'));
            document.getElementById(targetId).classList.add('active');

            // Initialize top deals on first visit
            if (targetId === 'tab-top-deals' && !topDealsInitialized) {
                topDealsInitialized = true;
                loadCategories();
            }
        });
    });

    // ─── Load Categories ───
    async function loadCategories() {
        try {
            const resp = await fetch('/api/categories');
            const categories = await resp.json();
            renderCategoryPills(categories);

            // Auto-load first category
            if (categories.length > 0) {
                fetchCategoryDeals(categories[0].node, categories[0].name);
            }
        } catch (err) {
            topDealsError.textContent = 'Failed to load categories.';
            topDealsError.classList.remove('hidden');
        }
    }

    function renderCategoryPills(categories) {
        categoryPillBar.innerHTML = '';
        categories.forEach((cat, idx) => {
            const pill = document.createElement('button');
            pill.className = 'category-pill' + (idx === 0 ? ' active' : '');
            pill.textContent = cat.name;
            pill.setAttribute('data-node', cat.node);
            pill.setAttribute('data-name', cat.name);
            pill.addEventListener('click', () => {
                // Update active pill
                document.querySelectorAll('.category-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                fetchCategoryDeals(cat.node, cat.name);
            });
            categoryPillBar.appendChild(pill);
        });
    }

    // ─── Fetch Category Deals ───
    async function fetchCategoryDeals(node, name) {
        // Abort previous request
        if (currentAbortController) {
            currentAbortController.abort();
        }
        currentAbortController = new AbortController();

        // Show skeleton, hide grid and error
        topDealsSkeleton.classList.remove('hidden');
        topDealsGrid.innerHTML = '';
        topDealsError.classList.add('hidden');

        // Mark pill as loading
        const activePill = document.querySelector(`.category-pill[data-node="${node}"]`);
        if (activePill) activePill.classList.add('loading');

        try {
            const resp = await fetch(
                `/api/top-deals?category=${encodeURIComponent(node)}`,
                { signal: currentAbortController.signal }
            );

            if (!resp.ok) {
                const errData = await resp.json();
                throw new Error(errData.detail || 'Failed to fetch top deals');
            }

            const data = await resp.json();

            if (data.error) {
                topDealsError.textContent = data.error;
                topDealsError.classList.remove('hidden');
            } else {
                renderProducts(data.products, topDealsGrid, true);
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                topDealsError.textContent = err.message || 'Failed to load deals for this category.';
                topDealsError.classList.remove('hidden');
            }
        } finally {
            topDealsSkeleton.classList.add('hidden');
            if (activePill) activePill.classList.remove('loading');
        }
    }

    // ─── Existing Search Form Handler ───
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const query = document.getElementById('query').value.trim();
        const minDiscount = document.getElementById('min_discount').value;
        const maxDiscount = document.getElementById('max_discount').value;

        if (!query) return;

        let url = `/api/search?query=${encodeURIComponent(query)}`;
        if (minDiscount) url += `&min_discount=${minDiscount}`;
        if (maxDiscount) url += `&max_discount=${maxDiscount}`;

        resultsSection.classList.remove('hidden');
        loadingSpinner.classList.remove('hidden');
        productGrid.innerHTML = '';
        errorMessage.classList.add('hidden');
        cacheStatus.classList.add('hidden');
        cacheStatus.textContent = '';
        cacheStatus.className = 'badge hidden';

        try {
            const response = await fetch(url);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to fetch deals');
            }

            const data = await response.json();

            if (data.metadata && data.metadata.source) {
                cacheStatus.classList.remove('hidden');
                if (data.metadata.source === 'cache') {
                    cacheStatus.textContent = 'Served from Cache';
                    cacheStatus.classList.add('cached');
                } else {
                    cacheStatus.textContent = 'Live Fetch';
                    cacheStatus.classList.add('live');
                }
            }

            renderProducts(data.products, productGrid, false);

        } catch (error) {
            errorMessage.textContent = error.message;
            errorMessage.classList.remove('hidden');
        } finally {
            loadingSpinner.classList.add('hidden');
        }
    });

    // ─── Shared Product Renderer ───
    function renderProducts(products, targetGrid, showDealScore) {
        if (!products || products.length === 0) {
            const errorEl = targetGrid === productGrid ? errorMessage : topDealsError;
            errorEl.textContent = 'No deals found matching your criteria.';
            errorEl.classList.remove('hidden');
            return;
        }

        targetGrid.innerHTML = '';

        products.forEach(product => {
            const card = document.createElement('div');
            card.className = 'product-card';

            const imgUrl = product.image_url || 'https://via.placeholder.com/200x200?text=No+Image';

            const formatPrice = (price) => {
                if (price === null || price === undefined) return 'N/A';
                return `₹${price.toLocaleString('en-IN')}`;
            };

            const currentPriceText = formatPrice(product.current_price);
            const originalPriceText = product.original_price ? formatPrice(product.original_price) : '';

            let discountBadge = '';
            if (product.discount_pct) {
                discountBadge = `<div class="discount-badge">${product.discount_pct}% OFF</div>`;
            }

            let verifiedBadge = '';
            if (product.is_true_deal) {
                verifiedBadge = `<div class="verified-badge">✓ Verified Deal</div>`;
                card.classList.add('true-deal');
            }

            // Deal score badge (only in Top Deals tab)
            let dealScoreBadge = '';
            if (showDealScore && product.deal_score != null) {
                const score = product.deal_score;
                let scoreClass = 'score-low';
                if (score >= 80) scoreClass = 'score-high';
                else if (score >= 60) scoreClass = 'score-mid';
                dealScoreBadge = `<div class="deal-score-badge ${scoreClass}">${score}</div>`;
            }

            const ratingHtml = product.rating ?
                `<span class="star-icon">★</span> <span class="rating-text">${product.rating}</span>` :
                `<span class="rating-text">No rating</span>`;

            card.innerHTML = `
                ${discountBadge}
                ${showDealScore ? dealScoreBadge : verifiedBadge}
                <div class="image-container">
                    <img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(product.title)}" class="product-image" loading="lazy">
                </div>
                <div class="product-info">
                    <h3 class="product-title" title="${escapeHtml(product.title)}">${escapeHtml(product.title)}</h3>
                    <div class="product-rating">
                        ${ratingHtml}
                    </div>
                    <div class="price-container">
                        <span class="current-price">${currentPriceText}</span>
                        ${originalPriceText ? `<span class="original-price">${originalPriceText}</span>` : ''}
                    </div>
                    <a href="${escapeHtml(product.product_url)}" target="_blank" rel="noopener noreferrer" class="view-btn">View on Amazon</a>
                    ${product.asin ? `<button class="keepa-btn" data-asin="${escapeHtml(product.asin)}">View Price History</button>` : ''}
                    <div class="keepa-graph-container">
                        <div class="keepa-loading">Loading graph...</div>
                        <img alt="Price History Graph" class="keepa-img" style="display:none;" />
                    </div>
                </div>
            `;

            // Keepa button handler
            const keepaBtn = card.querySelector('.keepa-btn');
            if (keepaBtn) {
                keepaBtn.addEventListener('click', () => {
                    const container = card.querySelector('.keepa-graph-container');
                    const img = container.querySelector('.keepa-img');
                    const loading = container.querySelector('.keepa-loading');

                    if (container.classList.contains('active')) {
                        container.classList.remove('active');
                        keepaBtn.textContent = 'View Price History';
                    } else {
                        container.classList.add('active');
                        keepaBtn.textContent = 'Hide Price History';

                        if (!img.getAttribute('src')) {
                            const asin = keepaBtn.getAttribute('data-asin');
                            img.setAttribute('src', `https://graph.keepa.com/pricehistory?asin=${asin}&domain=10&range=365`);
                            img.onload = () => {
                                loading.style.display = 'none';
                                img.style.display = 'block';
                            };
                            img.onerror = () => {
                                loading.textContent = 'Failed to load graph';
                                loading.style.color = '#ef233c';
                            };
                        }
                    }
                });
            }

            targetGrid.appendChild(card);
        });
    }

    // ─── XSS Prevention Helper ───
    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
             .toString()
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }
});
```

- [ ] **Step 4: Manual verification — start the server and test both tabs**

Run: `python main.py`
Then open `http://localhost:8000` in the browser and verify:
1. Tab bar renders with "Search Deals" and "Top Deals" tabs
2. Search tab works identically to before
3. Clicking "Top Deals" tab shows category pills and auto-loads Electronics
4. Clicking a category pill shows skeleton loading then product cards with deal scores
5. Deal score badges show correct color tiers (green/amber/red)
6. Rapid pill switching doesn't cause stale data

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/style.css static/app.js
git commit -m "feat: add Top Deals tab with category pills, deal scores, and skeleton loading"
```

---

### Task 6: Final Integration Test & Cleanup

**Files:**
- All test files
- No new files

**Interfaces:**
- Consumes: All previous tasks
- Produces: Clean test run confirming full feature works

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Run the existing tests to confirm no regressions**

Run: `python -m pytest test_example.py test_parse.py test_parse_price.py test_true_deal.py -v`
Expected: All existing tests still pass

- [ ] **Step 3: Commit and tag**

```bash
git add -A
git commit -m "chore: final integration — Top Deals by Category feature complete"
```
