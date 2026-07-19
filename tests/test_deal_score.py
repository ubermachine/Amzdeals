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
