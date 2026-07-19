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

