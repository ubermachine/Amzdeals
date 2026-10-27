"""Tests for build_category_url and discount tier refinement mapping."""

from scraper.engine import build_category_url, get_discount_tier_node


def test_get_discount_tier_node():
    assert get_discount_tier_node(75) == "27060457031"
    assert get_discount_tier_node(70) == "27060457031"
    assert get_discount_tier_node(65) == "27060456031"
    assert get_discount_tier_node(60) == "27060456031"
    assert get_discount_tier_node(50) == "2665401031"
    assert get_discount_tier_node(40) == "2665402031"
    assert get_discount_tier_node(35) == "2665402031"
    assert get_discount_tier_node(25) == "2665400031"
    assert get_discount_tier_node(10) == "2665399031"
    assert get_discount_tier_node(5) is None
    assert get_discount_tier_node(0) is None


def test_build_category_url_basic():
    url = build_category_url(
        node="976419031", min_discount=40, max_discount=90, page=1
    )
    assert "amazon.in/s" in url
    # 40% maps to 35% tier: 2665402031
    assert "rh=n%3A976419031%2Cp_n_pct-off-with-tax%3A2665402031" in url
    assert "s=popularity-rank" in url
    assert "page=1" in url
    assert "pct-off=" not in url  # Zero redirects: avoids legacy pct-off query param


def test_build_category_url_sort_options():
    assert "s=popularity-rank" in build_category_url("976419031", 40, 90, 1, sort_by="popularity")
    assert "s=exact-aware-popularity-rank" in build_category_url("976419031", 40, 90, 1, sort_by="bestsellers")
    assert "s=review-rank" in build_category_url("976419031", 40, 90, 1, sort_by="reviews")
    assert "s=popularity-rank" in build_category_url("976419031", 40, 90, 1, sort_by="discount")
    assert "s=popularity-rank" in build_category_url("976419031", 40, 90, 1, sort_by="deal_score")


def test_build_category_url_page_2():
    url = build_category_url(
        node="1571271031", min_discount=10, max_discount=99, page=2
    )
    assert "rh=n%3A1571271031%2Cp_n_pct-off-with-tax%3A2665399031" in url
    assert "page=2" in url


def test_build_category_url_zero_discount():
    # If min_discount is 0 (<10), no discount refinement is appended
    url = build_category_url("976419031", 0, 90, 1)
    assert "rh=n%3A976419031" in url
    assert "p_n_pct-off-with-tax" not in url
