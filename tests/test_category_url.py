"""Tests for build_category_url."""

from scraper.engine import build_category_url


def test_build_category_url_basic():
    url = build_category_url(
        node="976419031", min_discount=40, max_discount=90, page=1
    )
    assert "amazon.in/s" in url
    assert "rh=n%3A976419031" in url  # URL-encoded rh=n:976419031
    assert "pct-off=40-90" in url
    assert "s=popularity-rank" in url
    assert "page=1" in url


def test_build_category_url_sort_options():
    assert "s=popularity-rank" in build_category_url("976419031", 40, 90, 1, sort_by="popularity")
    assert "s=discount-percent-rank" in build_category_url("976419031", 40, 90, 1, sort_by="discount")
    assert "s=review-rank" in build_category_url("976419031", 40, 90, 1, sort_by="reviews")
    assert "s=discount-percent-rank" in build_category_url("976419031", 40, 90, 1, sort_by="deal_score")


def test_build_category_url_page_2():
    url = build_category_url(
        node="1571271031", min_discount=10, max_discount=99, page=2
    )
    assert "rh=n%3A1571271031" in url
    assert "pct-off=10-99" in url
    assert "page=2" in url


def test_build_category_url_bestsellers_alias():
    url = build_category_url("976419031", 40, 90, 1, sort_by="bestsellers")
    assert "s=popularity-rank" in url
