"""Tests for compute_deal_score (MDQS v3.0)."""

from scraper.engine import compute_deal_score


def test_full_score_components():
    """Product with all fields filled under MDQS v3.0."""
    product = {"discount_pct": 75, "rating": 4.2, "review_count": 1543}
    score = compute_deal_score(product)
    assert score == 73


def test_perfect_score():
    """Max discount, perfect rating, tons of reviews, Prime."""
    product = {
        "discount_pct": 100,
        "rating": 5.0,
        "review_count": 10000,
        "is_prime": True,
        "badge": "Best Seller",
    }
    score = compute_deal_score(product)
    assert score == 100


def test_null_discount_scores_zero():
    """Products with no discount get score 0."""
    product = {"discount_pct": None, "rating": 4.5, "review_count": 2000}
    score = compute_deal_score(product)
    assert score == 0


def test_null_rating_and_reviews_dropshipper_penalized():
    """Missing rating and reviews from non-prime seller is penalized as unverified dropshipper."""
    product = {"discount_pct": 60, "rating": None, "review_count": None, "is_prime": False}
    score = compute_deal_score(product)
    # Base: 60*0.70 = 42, Dropshipper penalty: -15 -> 27
    assert score == 27


def test_review_count_capped_at_10000():
    """Reviews above 10,000 don't increase score under CLT log scale."""
    p1 = {"discount_pct": 50, "rating": 4.0, "review_count": 10000}
    p2 = {"discount_pct": 50, "rating": 4.0, "review_count": 50000}
    assert compute_deal_score(p1) == compute_deal_score(p2)


def test_zero_everything():
    """All zeros."""
    product = {"discount_pct": 0, "rating": 0.0, "review_count": 0}
    score = compute_deal_score(product)
    assert score == 0


def test_bayesian_fake_review_penalized():
    """Single-review 5-star fake product is penalized compared to a proven product with same discount."""
    # Fake product: 1 review, 5.0 stars, 60% discount, non-prime
    fake_product = {"discount_pct": 60, "rating": 5.0, "review_count": 1, "is_prime": False}
    # Proven product: 2000 reviews, 4.2 stars, 60% discount, prime
    proven_product = {"discount_pct": 60, "rating": 4.2, "review_count": 2000, "is_prime": True}

    fake_score = compute_deal_score(fake_product)
    proven_score = compute_deal_score(proven_product)

    assert fake_score < proven_score
    assert fake_score == 36
    assert proven_score >= 68
    assert proven_score > fake_score + 30


def test_refurbished_deduction():
    """Refurbished product gets a 20-point penalty against new counterpart."""
    new_prod = {"discount_pct": 50, "rating": 4.2, "review_count": 500, "is_refurbished": False}
    refurb_prod = {"discount_pct": 50, "rating": 4.2, "review_count": 500, "is_refurbished": True}
    assert compute_deal_score(refurb_prod) == compute_deal_score(new_prod) - 20


def test_cash_savings_boost():
    """High absolute rupee savings boosts score over identical percentage discount with small savings."""
    cheap_item = {
        "discount_pct": 30,
        "current_price": 210,
        "original_price": 300,  # Save Rs 90
        "rating": 4.0,
        "review_count": 500,
    }
    laptop = {
        "discount_pct": 30,
        "current_price": 70000,
        "original_price": 100000,  # Save Rs 30,000
        "rating": 4.0,
        "review_count": 500,
    }
    assert compute_deal_score(laptop) > compute_deal_score(cheap_item)
