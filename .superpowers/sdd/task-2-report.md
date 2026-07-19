# Task 2 Report: Deal Score Calculator

## What was Implemented
1. **Deal Score Calculator**: Implemented `compute_deal_score(product: dict) -> int` in [scraper/engine.py](file:///d:/antigravity_sandbox/DealFinderAmazonPy/scraper/engine.py) to calculate a 0–100 quality score for a scraped product using a weighted formula:
   - 60% discount percentage (0–100)
   - 25% rating normalized to a 0–100 scale (rating / 5.0 * 100)
   - 15% review count normalized to a 0–100 scale, capped at 5,000 reviews (min(reviews, 5000) / 5000 * 100)
   - Products with no discount (`discount_pct` is `None`) are automatically given a score of 0.
   - Resulting float score is rounded to the nearest integer.
2. **Unit Tests**: Created a dedicated test suite in [tests/test_deal_score.py](file:///d:/antigravity_sandbox/DealFinderAmazonPy/tests/test_deal_score.py) covering all requirements and edge cases (all components filled, perfect score, null discount, null rating/reviews, capping of reviews, and all zeros).

## TDD Evidence

### RED (Failing Test Output)
- **Command run**: `python -m pytest tests/test_deal_score.py -v`
- **Output**:
```
ImportError while importing test module 'D:\antigravity_sandbox\DealFinderAmazonPy\tests\test_deal_score.py'.
...
tests\test_deal_score.py:3: in <module>
    from scraper.engine import compute_deal_score
E   ImportError: cannot import name 'compute_deal_score' from 'scraper.engine' (D:\antigravity_sandbox\DealFinderAmazonPy\scraper\engine.py)
```
- **Why the failure was expected**: The function `compute_deal_score` had not been defined in the engine module.

### GREEN (Passing Test Output)
- **Command run**: `python -m pytest tests/test_deal_score.py -v`
- **Output**:
```
tests/test_deal_score.py::test_full_score_components PASSED              [ 16%]
tests/test_deal_score.py::test_perfect_score PASSED                      [ 33%]
tests/test_deal_score.py::test_null_discount_scores_zero PASSED          [ 50%]
tests/test_deal_score.py::test_null_rating_and_reviews PASSED            [ 66%]
tests/test_deal_score.py::test_review_count_capped_at_5000 PASSED        [ 83%]
tests/test_deal_score.py::test_zero_everything PASSED                    [100%]

============================== 6 passed in 0.95s ==============================
```

## Files Changed/Created
- **Modified**: [scraper/engine.py](file:///d:/antigravity_sandbox/DealFinderAmazonPy/scraper/engine.py)
- **Created**: [tests/test_deal_score.py](file:///d:/antigravity_sandbox/DealFinderAmazonPy/tests/test_deal_score.py)

## Self-Review Findings
- **Completeness**: Evaluated all requirements for `compute_deal_score`. The function correctly handles missing `rating` and `review_count` fields by defaulting them, caps the normalized review count at 5,000, and returns 0 for any missing/null discount.
- **Quality**: The calculation matches the exact weighted formula (60/25/15) and rounds properly using Python's `round` function. Docstring matches the implementation and details the scoring logic.
- **Testing**: Added unit test coverage containing 6 comprehensive test cases. Verified that the entire test suite (30 tests) passes successfully.

## Issues or Concerns
- None.
