# Top 100 Popular Deals by Category Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Top Deals to fetch up to 100 items per category with multi-mode sorting (defaulting to Amazon's native Popularity / Best Sellers).

**Architecture:** Update `config.py` to 5 scrape pages and 100 product limit; update `make_category_cache_key` with `sort_by`; update `scraper/engine.py` URL builder and sorting logic; expose `sort_by` on `GET /api/top-deals`; and add a glassmorphic Sort selector to the frontend UI.

**Tech Stack:** Python 3.12+, FastAPI, curl_cffi, aiosqlite, pytest, Vanilla HTML5 / CSS3 / ES6+.

## Global Constraints

- Default sort order MUST be `popularity` (Amazon `s=popularity-rank`).
- Supported sort options: `popularity`, `deal_score`, `discount`, `reviews`.
- Cache key in SQLite MUST partition by `sort_by`.
- Must not break any existing tests or routes (`/api/search`, `/api/categories`, `/api/keepa-graph`).
- UI must maintain glassmorphic aesthetic and responsive grid.

---

### Task 1: Configuration & Cache Key Updates

**Files:**
- Modify: `config.py:40-42`
- Modify: `cache/sqlite_cache.py:17-21`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: Nothing
- Produces: `config.TOP_DEALS_PAGES = 5`, `config.TOP_DEALS_LIMIT = 100`, `make_category_cache_key(node, min_discount, max_discount, sort_by="popularity") -> str`

- [ ] **Step 1: Write test for updated `make_category_cache_key` with sort_by**

Add to `tests/test_cache.py`:
```python
def test_make_category_cache_key_with_sort():
    from cache.sqlite_cache import make_category_cache_key
    k1 = make_category_cache_key("976419031", 40, 90, sort_by="popularity")
    k2 = make_category_cache_key("976419031", 40, 90, sort_by="deal_score")
    k_default = make_category_cache_key("976419031", 40, 90)
    assert k1 != k2
    assert k1 == k_default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_cache.py -v`

- [ ] **Step 3: Update `config.py` and `cache/sqlite_cache.py`**

In `config.py`:
```python
TOP_DEALS_PAGES = 5       # pages to scrape per category
TOP_DEALS_LIMIT = 100     # max products per category
```

In `cache/sqlite_cache.py`:
```python
def make_category_cache_key(node: str, min_discount: int, max_discount: int, sort_by: str = "popularity") -> str:
    """Generate a deterministic SHA256 cache key for category deals."""
    raw = f"top-deals:{node}:{min_discount}:{max_discount}:{sort_by}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/test_cache.py -v`

- [ ] **Step 5: Commit changes**

```bash
git add config.py cache/sqlite_cache.py tests/test_cache.py
git commit -m "feat(config,cache): expand top deals limit to 100 and partition category cache by sort_by"
```

---

### Task 2: Scraper Engine URL Builder & Sorting Logic

**Files:**
- Modify: `scraper/engine.py:75-96, 134-221`
- Test: `tests/test_category_url.py`
- Test: `tests/test_search_category_deals.py`

**Interfaces:**
- Consumes: `make_category_cache_key`, `config.TOP_DEALS_PAGES`, `config.TOP_DEALS_LIMIT`
- Produces: `build_category_url(node, min_discount, max_discount, page, sort_by="popularity")`, `search_category_deals(node, category_name, min_discount, max_discount, cache, sort_by="popularity")`

- [ ] **Step 1: Write tests for `build_category_url` with sort options**

In `tests/test_category_url.py`:
```python
def test_build_category_url_popularity_default():
    url = build_category_url("976419031", 40, 90, 1)
    assert "s=popularity-rank" in url

def test_build_category_url_sort_options():
    assert "s=popularity-rank" in build_category_url("976419031", 40, 90, 1, sort_by="popularity")
    assert "s=discount-percent-rank" in build_category_url("976419031", 40, 90, 1, sort_by="discount")
    assert "s=review-rank" in build_category_url("976419031", 40, 90, 1, sort_by="reviews")
    assert "s=discount-percent-rank" in build_category_url("976419031", 40, 90, 1, sort_by="deal_score")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_category_url.py -v`

- [ ] **Step 3: Implement `build_category_url` and `search_category_deals` in `scraper/engine.py`**

In `scraper/engine.py`:
```python
def build_category_url(
    node: str, min_discount: int, max_discount: int, page: int, sort_by: str = "popularity"
) -> str:
    amazon_sort_map = {
        "popularity": "popularity-rank",
        "discount": "discount-percent-rank",
        "reviews": "review-rank",
        "deal_score": "discount-percent-rank",
    }
    amazon_sort = amazon_sort_map.get(sort_by, "popularity-rank")
    params = {
        "rh": f"n:{node}",
        "pct-off": f"{min_discount}-{max_discount}",
        "s": amazon_sort,
        "page": page,
    }
    return f"{config.AMAZON_BASE_URL}?{urlencode(params)}"
```

And in `search_category_deals`:
Add `sort_by: str = "popularity"` parameter:
```python
async def search_category_deals(
    node: str,
    category_name: str,
    min_discount: int,
    max_discount: int,
    cache: SearchCache,
    sort_by: str = "popularity",
) -> dict:
    cache_key = make_category_cache_key(node, min_discount, max_discount, sort_by=sort_by)
    ...
```
In loop:
`url = build_category_url(node, min_discount, max_discount, page_num, sort_by=sort_by)`

Sort result before truncation:
```python
    if sort_by == "deal_score":
        all_products.sort(key=lambda p: p["deal_score"], reverse=True)
    elif sort_by == "discount":
        all_products.sort(key=lambda p: p.get("discount_pct") or 0, reverse=True)
    elif sort_by == "reviews":
        all_products.sort(key=lambda p: p.get("review_count") or 0, reverse=True)
    # popularity keeps Amazon's scraped order

    top_products = all_products[: config.TOP_DEALS_LIMIT]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_category_url.py tests/test_search_category_deals.py -v`

- [ ] **Step 5: Commit changes**

```bash
git add scraper/engine.py tests/test_category_url.py tests/test_search_category_deals.py
git commit -m "feat(engine): support Amazon popularity rank and multi-mode sorting in category deals"
```

---

### Task 3: API Route Updates

**Files:**
- Modify: `main.py:90-117`
- Test: `tests/test_top_deals_api.py`

**Interfaces:**
- Consumes: `search_category_deals` with `sort_by`
- Produces: `GET /api/top-deals?category={node}&sort_by=popularity`

- [ ] **Step 1: Write test for `sort_by` validation and passing**

In `tests/test_top_deals_api.py`:
```python
def test_api_top_deals_sort_by_validation(client):
    response = client.get("/api/top-deals?category=976419031&sort_by=invalid")
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_top_deals_api.py -v`

- [ ] **Step 3: Update `main.py`**

In `main.py`:
```python
@app.get("/api/top-deals")
async def api_top_deals(
    category: str = Query(..., min_length=1, description="Amazon browse-node ID"),
    min_discount: int = Query(40, ge=0, le=99, description="Minimum discount %"),
    max_discount: int = Query(90, ge=1, le=100, description="Maximum discount %"),
    sort_by: str = Query("popularity", pattern="^(popularity|deal_score|discount|reviews)$", description="Sort order"),
):
    ...
    result = await search_category_deals(
        node=category,
        category_name=category_name,
        min_discount=min_discount,
        max_discount=max_discount,
        cache=_cache,
        sort_by=sort_by,
    )
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/test_top_deals_api.py -v`

- [ ] **Step 5: Commit changes**

```bash
git add main.py tests/test_top_deals_api.py
git commit -m "feat(api): add sort_by query parameter to /api/top-deals with popularity default"
```

---

### Task 4: Frontend UI Toolbar & Sort Dropdown

**Files:**
- Modify: `static/index.html:70-88`
- Modify: `static/style.css`
- Modify: `static/app.js:15-135`

- [ ] **Step 1: Update `static/index.html`**

In `#tab-top-deals`, wrap category pills and add the sort control toolbar:
```html
<div class="top-deals-controls glass-panel">
    <div class="category-pill-bar" id="category-pill-bar">
        <!-- Injected by JS -->
    </div>
    <div class="top-deals-filter-bar">
        <div class="sort-wrapper">
            <label for="top-deals-sort">Sort by:</label>
            <select id="top-deals-sort" class="sort-select">
                <option value="popularity" selected>🔥 Most Popular</option>
                <option value="deal_score">🏆 Deal Score</option>
                <option value="discount">💰 Highest Discount</option>
                <option value="reviews">⭐ Most Reviewed</option>
            </select>
        </div>
        <span id="top-deals-count" class="deals-count-badge hidden"></span>
    </div>
</div>
```

- [ ] **Step 2: Add styles in `static/style.css`**

Add styling for `.top-deals-controls`, `.top-deals-filter-bar`, `.sort-wrapper`, `.sort-select`, and `.deals-count-badge`.

- [ ] **Step 3: Update `static/app.js`**

Add state tracking for `currentCategoryNode`, `currentCategoryName`, and `currentSortBy = 'popularity'`.
Hook `top-deals-sort` change event:
```javascript
const sortSelect = document.getElementById('top-deals-sort');
if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
        currentSortBy = e.target.value;
        if (currentCategoryNode) {
            fetchCategoryDeals(currentCategoryNode, currentCategoryName, currentSortBy);
        }
    });
}
```
Update `fetchCategoryDeals`:
```javascript
async function fetchCategoryDeals(node, name, sortBy = currentSortBy) {
    ...
    const resp = await fetch(`/api/top-deals?category=${encodeURIComponent(node)}&sort_by=${encodeURIComponent(sortBy)}`, { signal: controller.signal });
    ...
```
Update count badge `#top-deals-count` with `data.products.length` deals.

- [ ] **Step 4: Commit frontend changes**

```bash
git add static/index.html static/style.css static/app.js
git commit -m "feat(ui): add sort dropdown with popularity default and count badge to Top Deals"
```

---

### Task 5: End-to-End Verification, Documentation & GitHub Push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run full test suite**

Run: `py -m pytest tests/`
Expected: All tests pass.

- [ ] **Step 2: Update `README.md`**

Update `README.md` to document the 100-item limit, `sort_by` parameter on `/api/top-deals`, and new test count.

- [ ] **Step 3: Commit and Push**

```bash
git add README.md
git commit -m "docs: update README with top 100 deals and popularity sort reference"
git push origin master
```
