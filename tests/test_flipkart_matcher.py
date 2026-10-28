"""Tests for Flipkart cross-market entity matching and deal verification."""

import pytest
from scraper.flipkart import (
    classify_cross_market_verdict,
    extract_product_signature,
    parse_flipkart_html,
    score_flipkart_match,
)


def test_extract_product_signature_laptop():
    title = 'ASUS TUF A15 (2026),Smartchoice,AMD Ryzen 7 8845HS,RTX 3050,16GB RAM,512GB SSD,FA506NCG-HN192WS'
    sig = extract_product_signature(title)
    assert sig["brand"] == "asus"
    assert "FA506NCG-HN192WS" in sig["models"] or "FA506NCG" in sig["models"]
    assert "16GB" in sig["specs"]
    assert "512GB" in sig["specs"]


def test_extract_product_signature_airfryer():
    title = "PHILIPS Air Fryer HD9200/90 with Rapid Air Technology, 4.1L"
    sig = extract_product_signature(title)
    assert sig["brand"] == "philips"
    assert any("HD9200" in m for m in sig["models"])
    assert "4.1L" in sig["specs"]


def test_score_flipkart_match_identical_item():
    amz_title = 'ASUS TUF A15, AMD Ryzen 7, RTX 3050, 16GB RAM, 512GB SSD, FA506NCG-HN192WS'
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "ASUS TUF Gaming A15 AMD Ryzen 7 FA506NCG (16 GB/512 GB SSD)",
        "price": 96990,
    }
    score = score_flipkart_match(sig, amazon_price=99990, candidate=candidate)
    assert score >= 80.0  # Confirmed match


def test_score_flipkart_match_rejects_brand_mismatch():
    amz_title = 'ASUS TUF A15 Gaming Laptop'
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "MIRCHI FASHION Women Kurta Palazzo Set",
        "price": 853,
    }
    score = score_flipkart_match(sig, amazon_price=99990, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_rejects_cheap_accessory():
    amz_title = 'Realme Narzo 60X 5G (128 GB)'
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Realme Narzo 60X Silicone Transparent Back Cover",
        "price": 249,
    }
    score = score_flipkart_match(sig, amazon_price=11999, candidate=candidate)
    # Fails price corridor (249 / 11999 < 0.35)
    assert score == 0.0


def test_score_flipkart_match_penalizes_variant_mismatch():
    amz_title = 'ASUS TUF A15, 16GB RAM, 512GB SSD, FA506NCG'
    sig = extract_product_signature(amz_title)
    # Higher tier variant with 32GB RAM / 1TB SSD
    candidate = {
        "title": "ASUS TUF Gaming A15 AMD Ryzen 7 FA506NCG (32 GB/1 TB SSD)",
        "price": 135000,
    }
    score = score_flipkart_match(sig, amazon_price=99990, candidate=candidate)
    assert score < 80.0  # Mismatched specs drop score below 80 threshold


def test_classify_verdict_market_parity():
    """Within +-5% is Market Parity, NOT a deal."""
    # Amazon ₹11,999 vs Flipkart ₹11,499 (4.3% difference -> within 5%)
    res = classify_cross_market_verdict(amazon_price=11999, flipkart_price=11499)
    assert res["verdict"] == "market_parity"
    assert res["is_deal"] is False

    # Exact same price
    res_exact = classify_cross_market_verdict(amazon_price=10000, flipkart_price=10000)
    assert res_exact["verdict"] == "market_parity"
    assert res_exact["is_deal"] is False


def test_classify_verdict_true_deal():
    """Amazon > 5% cheaper than Flipkart is a True Deal."""
    # Amazon ₹8,999 vs Flipkart ₹11,499 (21.7% cheaper)
    res = classify_cross_market_verdict(amazon_price=8999, flipkart_price=11499)
    assert res["verdict"] == "true_deal"
    assert res["is_deal"] is True
    assert res["price_diff"] == 2500  # Flipkart - Amazon savings


def test_classify_verdict_cheaper_on_flipkart():
    """Flipkart > 5% cheaper than Amazon is a Fake Deal."""
    # Amazon ₹14,999 vs Flipkart ₹11,499 (Amazon is 30% more expensive)
    res = classify_cross_market_verdict(amazon_price=14999, flipkart_price=11499)
    assert res["verdict"] == "cheaper_on_flipkart"
    assert res["is_deal"] is False
    assert res["flipkart_savings"] == 3500


def test_parse_flipkart_html_extracts_products():
    mock_html = '''
    <html>
      <head>
        <script>
          window.__INITIAL_STATE__ = {
            "pageDataV4": {
              "page": {
                "data": {
                  "10003": [
                    {
                      "productInfo": {
                        "value": {
                          "titles": {"title": "Realme Narzo 60X 5G (Stellar Green, 128 GB)"},
                          "pricing": {
                            "prices": [
                              {"strikeOff": true, "value": 14999},
                              {"strikeOff": false, "value": 11499}
                            ],
                            "totalDiscount": 23
                          },
                          "rating": {"average": 4.3},
                          "baseUrl": "/realme-narzo-60x-5g/p/itm123"
                        }
                      }
                    }
                  ]
                }
              }
            }
          };
        </script>
      </head>
    </html>
    '''
    candidates = parse_flipkart_html(mock_html)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["title"] == "Realme Narzo 60X 5G (Stellar Green, 128 GB)"
    assert c["price"] == 11499
    assert c["mrp"] == 14999
    assert c["rating"] == 4.3
    assert c["url"] == "https://www.flipkart.com/realme-narzo-60x-5g/p/itm123"


@pytest.mark.asyncio
async def test_verify_product_against_flipkart_uses_cache():
    from unittest.mock import AsyncMock
    from scraper.flipkart import verify_product_against_flipkart

    mock_cache = AsyncMock()
    mock_cache.get_flipkart = AsyncMock(return_value={
        "match_found": True,
        "verdict": "true_deal",
        "is_deal": True,
        "flipkart_price": 11499,
        "flipkart_title": "Realme Narzo 60X 5G",
        "flipkart_url": "https://www.flipkart.com/realme",
        "match_confidence": 95.0,
    })
    mock_session = AsyncMock()

    product = {"asin": "B0REALME", "title": "Realme Narzo 60X 5G 128GB", "current_price": 9999}
    res = await verify_product_against_flipkart(product, mock_session, mock_cache)

    assert res["match_found"] is True
    assert res["verdict"] == "true_deal"
    assert res["flipkart_price"] == 11499
    # Session.get should NOT have been called due to cache hit
    assert mock_session.get.call_count == 0


@pytest.mark.asyncio
async def test_verify_product_against_flipkart_e2e_market_parity():
    from unittest.mock import AsyncMock, patch
    from scraper.flipkart import verify_product_against_flipkart

    mock_cache = AsyncMock()
    mock_cache.get_flipkart = AsyncMock(return_value=None)
    mock_cache.set_flipkart = AsyncMock()

    mock_session = AsyncMock()

    mock_candidates = [
        {
            "title": "Realme Narzo 60X 5G (Stellar Green, 128 GB)",
            "price": 11499.0,
            "mrp": 14999.0,
            "rating": 4.3,
            "url": "https://www.flipkart.com/realme",
        }
    ]

    with patch("scraper.flipkart.fetch_flipkart_candidates", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_candidates

        # Amazon price is 11,999 (Flipkart is 11,499 -> 4.3% difference -> within 5% parity)
        product = {"asin": "B0REALME", "title": "Realme Narzo 60X 5G (128 GB)", "current_price": 11999}
        res = await verify_product_against_flipkart(product, mock_session, mock_cache)

        assert res["match_found"] is True
        assert res["verdict"] == "market_parity"
        assert res["is_deal"] is False
        assert mock_cache.set_flipkart.call_count == 1


def test_score_flipkart_match_rejects_chipset_and_series_conflict():
    """Intel V15 office laptop must never match AMD LOQ gaming laptop."""
    amz_title = "Lenovo Smartchoice V15, Intel Core i5-13420H, 16GB RAM, 512GB SSD"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Lenovo LOQ 2025 AMD Ryzen 7 Octa Core 250 - (16 GB/512 GB SSD/RTX 5050)",
        "price": 159990.0,
    }
    score = score_flipkart_match(sig, amazon_price=71990.0, candidate=candidate)
    assert score == 0.0


