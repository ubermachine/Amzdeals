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

