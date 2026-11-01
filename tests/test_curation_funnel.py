"""Unit tests for the 5-Stage Curated Ranking Funnel, Golden Number (8 deals), and Entity Gating."""

import pytest
import config
from scraper.engine import (
    extract_brand,
    extract_model_family,
    is_query_entity_match,
    get_query_price_floor,
    filter_and_curate_deals,
)
from scraper.semantic import is_ollama_available, semantic_rerank_deals


def test_golden_number_and_single_page_config():
    """Verify production constants for 8-deal curation and single-page scrape."""
    assert config.TOP_DEALS_LIMIT == 8
    assert config.TOP_DEALS_PAGES == 1
    assert config.BRAND_DIVERSITY_MAX_PER_BRAND == 2
    assert config.MIN_DEAL_SCORE_FLOOR == 60.0


def test_extract_brand():
    """Verify brand extraction across standard, renewed, and multi-word brands."""
    assert extract_brand("HP 15s Ryzen 3-5300U 15.6 inch") == "Hp"
    assert extract_brand("(Renewed) Dell Inspiron 3520 Laptop") == "Dell"
    assert extract_brand("Refurbished Lenovo IdeaPad Slim 3") == "Lenovo"
    assert extract_brand("Morphy Richards Digital OTG 40L") == "Morphy Richards"
    assert extract_brand("Fire-Boltt Ninja Call Pro Plus") == "Fire-Boltt"
    assert extract_brand("Red Tape Men's Sneaker Shoes") == "Red Tape"
    assert extract_brand("") == "Unknown"
    assert extract_brand(None) == "Unknown"


def test_extract_model_family():
    """Verify model family normalizes chassis and ignores RAM/storage/color variants."""
    t1 = "HP 15s 12th Gen Intel Core i5-1235U 15.6 FHD 16GB DDR4 512GB SSD Silver"
    t2 = "HP 15s 12th Gen Intel Core i3-1215U 15.6 FHD 8GB DDR4 512GB SSD Blue"
    fam1 = extract_model_family(t1)
    fam2 = extract_model_family(t2)
    assert fam1 == fam2
    assert fam1 == "hp 15s 12th"

    l1 = "Lenovo IdeaPad Slim 3 12th Gen Core i5 16GB/512GB SSD"
    l2 = "Lenovo IdeaPad Slim 3 12th Gen Core i3 8GB/512GB SSD"
    assert extract_model_family(l1) == extract_model_family(l2)


def test_is_query_entity_match_microwave():
    """Verify 'microwave' query accepts microwaves and rejects OTGs and toaster ovens."""
    # Genuine microwaves
    assert is_query_entity_match("LG 28 L Convection Microwave Oven (MC2846BV)", "microwave") is True
    assert is_query_entity_match("Midea 20L Solo Microwave Oven", "microwave") is True
    assert is_query_entity_match("Panasonic 25L Solo Micro Wave Oven", "microwave") is True

    # OTGs and Toasters (no microwave magnetron)
    assert is_query_entity_match("AGARO Marvel 9L OTG Oven 800W Toaster Griller", "microwave") is False
    assert is_query_entity_match("SOLARA 12L Air Fryer Oven for Home Kitchen 1800W OTG", "microwave") is False
    assert is_query_entity_match("Pigeon Oven Toaster Grill 9 Liters OTG", "microwave") is False
    assert is_query_entity_match("Glen Multi-Function OTG 35 Litre Oven Toaster", "microwave") is False


def test_get_query_price_floor():
    """Verify price floor resolution across categories."""
    assert get_query_price_floor("laptop under 50000") == 12000.0
    assert get_query_price_floor("microwave") == 3500.0
    assert get_query_price_floor("iphone 15") == 4500.0
    assert get_query_price_floor("cotton tshirt") == 0.0


def test_filter_and_curate_deals_microwave_intruders_dropped():
    """Test full 5-stage curation on 16 raw products (8 microwaves + 8 OTGs/accessories)."""
    raw_products = [
        {"asin": "OTG_1", "title": "SOLARA 12L Air Fryer Oven Kitchen 1800W OTG", "current_price": 7999.0, "discount_pct": 50, "deal_score": 65},
        {"asin": "OTG_2", "title": "AGARO Marvel Oven Toaster Griller 25L OTG", "current_price": 3899.0, "discount_pct": 55, "deal_score": 70},
        {"asin": "MW_1", "title": "LG 28 L Convection Microwave Oven (MC2846BV)", "current_price": 13990.0, "discount_pct": 35, "deal_score": 75, "is_true_deal": True},
        {"asin": "OTG_3", "title": "Pigeon Oven Toaster Grill 9 Liters OTG", "current_price": 1499.0, "discount_pct": 60, "deal_score": 68},
        {"asin": "MW_2", "title": "Midea 20L Solo Microwave Oven", "current_price": 4640.0, "discount_pct": 45, "deal_score": 78, "is_true_deal": True},
        {"asin": "MW_3", "title": "Panasonic 25L Solo Microwave Oven", "current_price": 7990.0, "discount_pct": 30, "deal_score": 72, "is_true_deal": True},
        {"asin": "MW_4", "title": "LG 20 L Solo Microwave Oven", "current_price": 7690.0, "discount_pct": 28, "deal_score": 69},
        {"asin": "MW_5", "title": "LG 28 L Charcoal Convection Microwave Oven", "current_price": 16790.0, "discount_pct": 32, "deal_score": 74},
        {"asin": "MW_6", "title": "IFB 30L Air Fry Convection Microwave Oven", "current_price": 16650.0, "discount_pct": 25, "deal_score": 71},
        {"asin": "ACC_1", "title": "Microwave Cover for 20L Oven", "current_price": 299.0, "discount_pct": 70, "deal_score": 80},
        {"asin": "OTG_4", "title": "iBELL 25 Liters Electric Oven Toaster Grill OTG", "current_price": 4245.0, "discount_pct": 48, "deal_score": 62},
        {"asin": "MW_7", "title": "Panasonic 23L Convection Microwave Oven", "current_price": 11450.0, "discount_pct": 28, "deal_score": 67},
        {"asin": "MW_8", "title": "Panasonic 27L Convection Microwave Oven", "current_price": 12990.0, "discount_pct": 30, "deal_score": 66},
    ]

    curated = filter_and_curate_deals(raw_products, limit=8, query="microwave")

    # All OTGs and accessories must be eliminated
    for p in curated:
        assert "microwave" in p["title"].lower()
        assert "otg" not in p["title"].lower()
        assert p["current_price"] >= 3500.0

    # Max 2 per brand (LG <= 2, Panasonic <= 2, Midea <= 2, IFB <= 2)
    brand_counts = {}
    for p in curated:
        b = extract_brand(p["title"])
        brand_counts[b] = brand_counts.get(b, 0) + 1
        assert brand_counts[b] <= 2

    # Exactly 6 valid distinct microwaves returned (target <= 8)
    assert len(curated) == 6


def test_brand_saturation_cap_laptops():
    """Verify that a single dominant brand cannot monopolize the 8-deal slot."""
    laptops = [
        {"asin": "HP_1", "title": "HP Pavilion 15 Laptop Intel i5", "current_price": 55000.0, "discount_pct": 30, "deal_score": 85, "is_true_deal": True},
        {"asin": "HP_2", "title": "HP Envy 13 Ultrabook Intel i7", "current_price": 75000.0, "discount_pct": 28, "deal_score": 83, "is_true_deal": True},
        {"asin": "HP_3", "title": "HP Victus 15 Gaming Laptop", "current_price": 62000.0, "discount_pct": 32, "deal_score": 81, "is_true_deal": True},
        {"asin": "HP_4", "title": "HP Omen 16 High Performance Laptop", "current_price": 95000.0, "discount_pct": 25, "deal_score": 79, "is_true_deal": True},
        {"asin": "DELL_1", "title": "Dell Inspiron 3520 Laptop", "current_price": 48000.0, "discount_pct": 32, "deal_score": 80, "is_true_deal": True},
        {"asin": "DELL_2", "title": "Dell XPS 13 Ultrabook", "current_price": 88000.0, "discount_pct": 27, "deal_score": 78, "is_true_deal": True},
        {"asin": "DELL_3", "title": "Dell G15 Gaming Laptop", "current_price": 69000.0, "discount_pct": 29, "deal_score": 76, "is_true_deal": True},
        {"asin": "ASUS_1", "title": "Asus Vivobook 15 Laptop", "current_price": 42000.0, "discount_pct": 35, "deal_score": 78, "is_true_deal": True},
        {"asin": "ASUS_2", "title": "Asus Zenbook 14 OLED Laptop", "current_price": 72000.0, "discount_pct": 30, "deal_score": 77, "is_true_deal": True},
        {"asin": "ASUS_3", "title": "Asus TUF Gaming A15 Laptop", "current_price": 61000.0, "discount_pct": 33, "deal_score": 75, "is_true_deal": True},
    ]

    curated = filter_and_curate_deals(laptops, limit=8, query="laptop")

    brand_counts = {}
    for p in curated:
        b = extract_brand(p["title"])
        brand_counts[b] = brand_counts.get(b, 0) + 1
        assert brand_counts[b] <= 2

    # With 3 brands (HP: 2, Dell: 2, Asus: 2), total curated should be 6
    assert len(curated) == 6


def test_model_family_deduplication():
    """Verify that multiple chassis variants of the same laptop model are deduplicated."""
    variants = [
        {"asin": "HP1", "title": "HP 15s 12th Gen Intel Core i5 16GB 512GB Silver", "current_price": 52000.0, "deal_score": 72, "is_true_deal": True},
        {"asin": "HP2", "title": "HP 15s 12th Gen Intel Core i3 8GB 512GB Blue", "current_price": 38000.0, "deal_score": 84, "is_true_deal": True},
        {"asin": "HP3", "title": "HP 15s 12th Gen Intel Core i5 8GB 512GB Grey", "current_price": 49000.0, "deal_score": 68, "is_true_deal": True},
        {"asin": "LEN1", "title": "Lenovo IdeaPad Slim 3 12th Gen Core i5 16GB 512GB", "current_price": 54000.0, "deal_score": 79, "is_true_deal": True},
    ]

    curated = filter_and_curate_deals(variants, limit=8)

    # HP 15s variants must be collapsed to the single highest-scoring variant (HP2 with score 84)
    hp_deals = [p for p in curated if "hp 15s" in p["title"].lower()]
    assert len(hp_deals) == 1
    assert hp_deals[0]["asin"] == "HP2"
    assert hp_deals[0]["deal_score"] == 84


@pytest.mark.asyncio
async def test_fail_open_semantic_reranker():
    """Verify that semantic reranker is 100% fail-open and never raises exceptions."""
    prods = [
        {"title": "Apple MacBook Air M2", "current_price": 89000.0, "deal_score": 88},
        {"title": "Lenovo IdeaPad Slim 3", "current_price": 38000.0, "deal_score": 82},
    ]
    # Even if Ollama daemon is offline or library not installed, must fail open cleanly
    result = await semantic_rerank_deals("laptop", prods)
    assert len(result) == 2
    assert result[0]["title"] == "Apple MacBook Air M2"
