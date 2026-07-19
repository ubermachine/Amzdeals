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

