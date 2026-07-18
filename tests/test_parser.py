from scraper.parser import parse_search_results

SAMPLE_RESULT_HTML = """
<div class="s-main-slot s-result-list">
  <div data-component-type="s-search-result" data-asin="B0DNTCMFRG" class="s-result-item">
    <div class="a-section">
      <img class="s-image" src="https://m.media-amazon.com/images/I/test.jpg" alt="Park Avenue Oud Perfume"/>
      <h2 class="a-size-mini">
        <a class="a-link-normal" href="/dp/B0DNTCMFRG/ref=test">
          <span class="a-size-medium a-color-base a-text-normal">Park Avenue Oud Perfume 100ml EDP</span>
        </a>
      </h2>
      <div class="a-row a-size-small">
        <span class="a-icon-alt">4.2 out of 5 stars</span>
        <span class="a-size-base">1,543</span>
      </div>
      <div class="a-row">
        <span class="a-price" data-a-color="base">
          <span class="a-offscreen">₹239</span>
        </span>
        <span class="a-price a-text-price" data-a-strike="true">
          <span class="a-offscreen">₹999</span>
        </span>
      </div>
      <span class="a-badge-text" data-a-badge-color="sx-orange">76% off</span>
      <i class="a-icon a-icon-prime" aria-label="Amazon Prime"></i>
      <span class="s-coupon-highlight-color">Extra 5% off with coupon</span>
    </div>
  </div>
  <div data-component-type="s-search-result" data-asin="" class="s-result-item">
    <span>Sponsored ad placeholder</span>
  </div>
</div>
"""


def test_parse_returns_list():
    results = parse_search_results(SAMPLE_RESULT_HTML)
    assert isinstance(results, list)


def test_parse_skips_empty_asin():
    results = parse_search_results(SAMPLE_RESULT_HTML)
    asins = [r["asin"] for r in results]
    assert "" not in asins


def test_parse_extracts_product_fields():
    results = parse_search_results(SAMPLE_RESULT_HTML)
    assert len(results) >= 1
    product = results[0]
    assert product["asin"] == "B0DNTCMFRG"
    assert "Park Avenue" in product["title"]
    assert product["current_price"] == 239.0
    assert product["original_price"] == 999.0
    assert product["discount_pct"] == 76
    assert product["rating"] == 4.2
    assert product["review_count"] == 1543
    assert product["image_url"] == "https://m.media-amazon.com/images/I/test.jpg"
    assert "B0DNTCMFRG" in product["product_url"]
    assert product["is_prime"] is True
    assert "coupon" in product["coupon"].lower()


def test_parse_empty_html():
    results = parse_search_results("<html><body>No results</body></html>")
    assert results == []


def test_parse_partial_product():
    """Product with missing price should still be parsed with None values."""
    html = """
    <div class="s-main-slot s-result-list">
      <div data-component-type="s-search-result" data-asin="B099TEST" class="s-result-item">
        <h2 class="a-size-mini">
          <a class="a-link-normal" href="/dp/B099TEST">
            <span class="a-size-medium a-color-base a-text-normal">Test Product No Price</span>
          </a>
        </h2>
      </div>
    </div>
    """
    results = parse_search_results(html)
    assert len(results) == 1
    assert results[0]["asin"] == "B099TEST"
    assert results[0]["current_price"] is None
    assert results[0]["original_price"] is None
