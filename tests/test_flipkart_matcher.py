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


def test_extract_product_signature_sony_not_noise():
    """Active Noise Cancellation in title must never trigger the 'noise' brand."""
    title = "Sony WH-CH720N Active Noise Cancellation Wireless Bluetooth Headphones"
    sig = extract_product_signature(title)
    assert sig["brand"] == "sony"
    assert sig["series"] == "wh-ch720n"
    assert "sony" in sig["search_query"]
    assert "noise" not in sig["search_query"]


def test_extract_product_signature_series_ideapad():
    """IdeaPad Slim 3 series is captured as a core model anchor."""
    title = "Lenovo IdeaPad Slim 3 13th Gen, Intel Core i5-13420H, 16GB RAM, 512GB SSD"
    sig = extract_product_signature(title)
    assert sig["brand"] == "lenovo"
    assert sig["series"] == "ideapad slim 3"
    assert "ideapad" in sig["search_query"]
    assert "slim" in sig["search_query"]


def test_parse_flipkart_html_beautifulsoup_fallback():
    """When window.__INITIAL_STATE__ is missing, falls back to DOM card extraction."""
    raw_html = '''
    <html><body>
    <div data-id="TESTPID123">
        <a class="pIpigb" title="SONY WH-CH720N Bluetooth Headset" href="/sony-wh-ch720n/p/itm123?pid=TESTPID123"></a>
        <div class="hZ3P6w">₹6,989</div>
        <div class="kRYCnD">₹14,990</div>
        <div class="MKiFS6">4.4</div>
    </div>
    </body></html>
    '''
    candidates = parse_flipkart_html(raw_html)
    assert len(candidates) == 1
    assert candidates[0]["title"] == "SONY WH-CH720N Bluetooth Headset"
    assert candidates[0]["price"] == 6989.0
    assert candidates[0]["mrp"] == 14990.0
    assert candidates[0]["rating"] == 4.4
    assert "TESTPID123" in candidates[0]["url"]


def test_score_flipkart_match_rejects_ram_mismatch():
    """8GB RAM laptop must NEVER match a 16GB RAM laptop."""
    amz_title = "ASUS TUF Gaming A15, 16GB RAM, 512GB SSD, RTX 4050"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "ASUS TUF Gaming A15 AMD Ryzen 7 - (8 GB/512 GB SSD/RTX 4050)",
        "price": 68990.0,
    }
    score = score_flipkart_match(sig, amazon_price=74990.0, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_rejects_gpu_mismatch_3050_vs_4050():
    """RTX 3050 laptop must NEVER match an RTX 4050 laptop."""
    amz_title = "ASUS TUF Gaming A15, 16GB RAM, 512GB SSD, RTX 3050"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "ASUS TUF Gaming A15 AMD Ryzen 7 - (16 GB/512 GB SSD/RTX 4050)",
        "price": 76990.0,
    }
    score = score_flipkart_match(sig, amazon_price=61990.0, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_rejects_gpu_mismatch_2050_vs_3050():
    """RTX 2050 laptop must NEVER match an RTX 3050 laptop."""
    amz_title = "Lenovo LOQ 12th Gen i5-12450HX, 16GB RAM, 512GB SSD, RTX 3050"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Lenovo LOQ Intel Core i5 12th Gen - (16 GB/512 GB SSD/RTX 2050)",
        "price": 54990.0,
    }
    score = score_flipkart_match(sig, amazon_price=64990.0, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_rejects_dedicated_vs_integrated_gpu():
    """Laptop with RTX 3050 must NEVER match a model with integrated Intel UHD/Iris graphics."""
    amz_title = "Lenovo LOQ 12th Gen i5-12450HX, 16GB RAM, 512GB SSD, RTX 3050"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Lenovo LOQ Intel Core i5 12th Gen - (16 GB/512 GB SSD/Integrated Intel UHD Graphics)",
        "price": 49990.0,
    }
    score = score_flipkart_match(sig, amazon_price=64990.0, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_accepts_exact_hardware_specs():
    """Identical brand, series, RAM, storage, and GPU yields confirmed high match score."""
    amz_title = "ASUS TUF Gaming A15, 16GB DDR5, 512GB SSD, NVIDIA GeForce RTX 4050"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "ASUS TUF Gaming A15 AMD Ryzen 7 7735HS - (16 GB/512 GB SSD/NVIDIA GeForce RTX 4050)",
        "price": 73990.0,
    }
    score = score_flipkart_match(sig, amazon_price=74990.0, candidate=candidate)
    assert score >= 85.0





def test_score_flipkart_match_rejects_audio_form_factor_mismatch():
    """Over-ear headphones must NEVER match in-ear earbuds."""
    amz_title = "CMF BY Nothing Over Ear Headphone Pro, Hi-Res+LDAC, 40mm Driver"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "CMF by Nothing Buds Pro 2 with 50 dB ANC, Spatial Audio, Dual Drivers",
        "price": 3499.0,
    }
    score = score_flipkart_match(sig, amazon_price=5499.0, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_rejects_model_code_mismatch_300c_vs_211():
    """Boat Bassheads 300C must NEVER match Bassheads 211."""
    amz_title = "Boat Bassheads 300C Wired Earphones, Type-C Jack, in-Line Mic"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "boAt BassHeads 211, 10mm Drivers, In-Line Mic Wired Earphones",
        "price": 249.0,
    }
    score = score_flipkart_match(sig, amazon_price=449.0, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_rejects_smartwatch_series_mismatch():
    """Fire-Boltt Ninja must NEVER match Fire-Boltt Hurricane."""
    amz_title = "Fire-Boltt Ninja Calling Pro Plus 1.83 inch Display Smartwatch"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Fire-Boltt Hurricane Air 1.26 Round Display Rotating Crown Smartwatch",
        "price": 999.0,
    }
    score = score_flipkart_match(sig, amazon_price=1299.0, candidate=candidate)
    assert score == 0.0


def test_score_flipkart_match_rejects_audio_series_mismatch():
    """boAt Bassheads wired must NEVER match boAt Rockerz bluetooth neckband."""
    amz_title = "boAt Bassheads 225 Wired in Ear Earphone with Mic"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "boAt Rockerz 255 Pro+ Bluetooth Neckband with Mic",
        "price": 999.0,
    }
    score = score_flipkart_match(sig, amazon_price=556.0, candidate=candidate)
    assert score == 0.0



def test_score_flipkart_match_rejects_cpu_processor_mismatch_125h_vs_115u():
    """Intel Core Ultra 125H must NEVER match 115U."""
    amz_title = 'Acer Swift Pro AI PC,Intel Core Ultra 5 Processor 125H,Office 2024,16GB LPDDR5 RAM/512 SSD,14" WUXGA Display'
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Acer Swift Neo 14 Office 2024 Intel Core Ultra 5 115U - (16 GB/512 GB SSD) SFN14-54H Laptop",
        "price": 73990.0,
    }
    assert score_flipkart_match(sig, amazon_price=67300.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_laptop_subseries_mismatch_aspire_one_vs_aspire_15():
    """Acer Aspire One must NEVER match Aspire 15."""
    amz_title = 'Acer Smartchoice Aspire One, AMD Ryzen 3-7320U, 8GB LPDDR5 RAM/ 512GB SSD, 14.0" TN HD Display, A114-43 Laptop'
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Acer Aspire 15 AMD Ryzen 3 Quad Core 7330U - (8 GB/512 GB SSD) AS15 42 / A325 42 Laptop",
        "price": 45623.0,
    }
    assert score_flipkart_match(sig, amazon_price=45990.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_connectivity_mismatch_5g_vs_4g():
    """5G phone must NEVER match non-5G / 4G model."""
    amz_title = "Redmi 13C 5G (Starlight Black, 4GB RAM, 128GB Storage)"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "REDMI 13C (Starshine Green, 128 GB) (4 GB RAM)",
        "price": 7999.0,
    }
    assert score_flipkart_match(sig, amazon_price=10499.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_mobile_tier_mismatch_pro_plus_vs_pro():
    """Pro+ phone must NEVER match standard Pro model."""
    amz_title = "Realme 12 Pro+ 5G (Submarine Blue, 8GB RAM, 256GB Storage)"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Realme 12 Pro 5G (Navigator Beige, 8GB RAM, 256GB Storage)",
        "price": 23999.0,
    }
    assert score_flipkart_match(sig, amazon_price=29999.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_appliance_wattage_mismatch():
    """750W appliance must NEVER match 500W appliance."""
    amz_title = "Philips HL7756/00 Mixer Grinder 750 Watt, 3 Stainless Steel Jars"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Philips HL1606/03 500 W Mixer Grinder",
        "price": 2199.0,
    }
    assert score_flipkart_match(sig, amazon_price=3499.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_appliance_capacity_mismatch():
    """1.8L kettle must NEVER match 1.2L kettle."""
    amz_title = "Pigeon by Stovekraft Cruise 1.8 Litre Stainless Steel Electric Kettle"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Pigeon by Stovekraft 1.2 L Electric Kettle",
        "price": 599.0,
    }
    assert score_flipkart_match(sig, amazon_price=799.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_storage_capacity_mismatch_1tb_vs_500gb():
    """1TB SSD must NEVER match 500GB SSD."""
    amz_title = "Crucial P3 Plus 1TB PCIe 4.0 3D NAND NVMe M.2 SSD"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Crucial P3 Plus 500GB PCIe 4.0 3D NAND NVMe M.2 SSD",
        "price": 3199.0,
    }
    assert score_flipkart_match(sig, amazon_price=5499.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_tv_resolution_mismatch_4k_vs_fhd():
    """4K TV must NEVER match Full HD TV."""
    amz_title = "Sony Bravia 108 cm (43 inches) 4K Ultra HD Smart LED Google TV KD-43X74L"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Sony Bravia 108 cm (43 inches) Full HD Smart LED Google TV KD-43W830K",
        "price": 28990.0,
    }
    assert score_flipkart_match(sig, amazon_price=39990.0, candidate=candidate) == 0.0


def test_score_flipkart_match_rejects_monitor_refresh_rate_mismatch_180hz_vs_75hz():
    """180Hz gaming monitor must NEVER match 75Hz monitor."""
    amz_title = "Acer Nitro VG240Y 23.8 Inch IPS Full HD 180Hz 0.5ms Gaming Monitor"
    sig = extract_product_signature(amz_title)
    candidate = {
        "title": "Acer EK240Y 23.8 inch Full HD IPS 75Hz Monitor",
        "price": 5999.0,
    }
    assert score_flipkart_match(sig, amazon_price=8999.0, candidate=candidate) == 0.0
