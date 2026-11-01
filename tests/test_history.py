"""Tests for historical deal snapshot storage and day-over-day comparison engine."""

import os
import sqlite3
import pytest

from cache.history import (
    init_history_db,
    record_deal_snapshot,
    list_snapshot_dates,
    get_snapshots_by_date,
    compare_snapshots,
    dump_cache_to_snapshots,
    has_snapshot_for_date,
    get_snapshot_count_for_date,
)


@pytest.fixture
def temp_history_db(tmp_path):
    """Provide an isolated temporary SQLite database for history tests."""
    db_file = str(tmp_path / "test_history.db")
    init_history_db(db_file)
    return db_file


def test_init_history_db_creates_table_and_indexes(temp_history_db):
    conn = sqlite3.connect(temp_history_db)
    cursor = conn.cursor()
    tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "deal_snapshots" in tables
    indexes = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]
    assert "idx_snapshots_date" in indexes
    assert "idx_snapshots_asin" in indexes
    conn.close()


def test_record_deal_snapshot_and_retrieve(temp_history_db):
    product = {
        "asin": "B0TESTASIN1",
        "title": "Lenovo IdeaPad Slim 3 15.6 inch Laptop",
        "current_price": 54990.0,
        "effective_price": 53990.0,
        "original_price": 79990.0,
        "discount_pct": 32,
        "deal_score": 85.0,
        "is_true_deal": True,
        "badge": "Limited time deal",
        "rating": 4.3,
        "review_count": 1250,
        "product_url": "https://www.amazon.in/dp/B0TESTASIN1",
        "image_url": "https://m.media-amazon.com/test.jpg",
        "cross_market": {
            "flipkart_price": 57990.0,
            "verdict": "true_deal",
            "diff_pct": 6.9,
            "flipkart_url": "https://www.flipkart.com/test",
        },
    }

    record_deal_snapshot(product, category="Laptops", snapshot_date="2026-11-01", db_path=temp_history_db)

    deals = get_snapshots_by_date("2026-11-01", db_path=temp_history_db)
    assert len(deals) == 1
    d = deals[0]
    assert d["asin"] == "B0TESTASIN1"
    assert d["category"] == "Laptops"
    assert d["effective_price"] == 53990.0
    assert d["deal_score"] == 85.0
    assert d["is_true_deal"] == 1
    assert d["flipkart_price"] == 57990.0
    assert d["flipkart_verdict"] == "true_deal"


def test_compare_snapshots_detects_price_drops_and_new_deals(temp_history_db):
    # Day 1: 2026-11-01
    item_drop = {
        "asin": "B0LAPTOP01",
        "title": "ASUS TUF A15 Gaming Laptop",
        "current_price": 60000.0,
        "deal_score": 75.0,
    }
    item_expired = {
        "asin": "B0SHOE0001",
        "title": "Puma Smashic Retro Sneaker",
        "current_price": 2499.0,
        "deal_score": 70.0,
    }
    item_stable = {
        "asin": "B0PHONE001",
        "title": "Realme Narzo 60X 5G",
        "current_price": 11999.0,
        "deal_score": 80.0,
    }

    record_deal_snapshot(item_drop, "Laptops", snapshot_date="2026-11-01", db_path=temp_history_db)
    record_deal_snapshot(item_expired, "Shoes", snapshot_date="2026-11-01", db_path=temp_history_db)
    record_deal_snapshot(item_stable, "Mobiles", snapshot_date="2026-11-01", db_path=temp_history_db)

    # Day 2: 2026-11-02
    # item_drop gets cheaper (60,000 -> 54,000)
    item_drop_cheaper = {
        "asin": "B0LAPTOP01",
        "title": "ASUS TUF A15 Gaming Laptop",
        "current_price": 54000.0,
        "deal_score": 88.0,
    }
    # item_stable remains unchanged (11,999)
    # item_new appears today
    item_new = {
        "asin": "B0WATCH001",
        "title": "boAt Wave Call 3 Smartwatch",
        "current_price": 1299.0,
        "deal_score": 82.0,
    }

    record_deal_snapshot(item_drop_cheaper, "Laptops", snapshot_date="2026-11-02", db_path=temp_history_db)
    record_deal_snapshot(item_stable, "Mobiles", snapshot_date="2026-11-02", db_path=temp_history_db)
    record_deal_snapshot(item_new, "Watches", snapshot_date="2026-11-02", db_path=temp_history_db)

    comparison = compare_snapshots("2026-11-01", "2026-11-02", db_path=temp_history_db)

    summary = comparison["summary"]
    assert summary["earlier_total_deals"] == 3
    assert summary["later_total_deals"] == 3
    assert summary["price_drops_count"] == 1
    assert summary["new_deals_count"] == 1
    assert summary["expired_deals_count"] == 1
    assert summary["unchanged_price_count"] == 1

    # Verify price drop details
    drop = comparison["price_drops"][0]
    assert drop["asin"] == "B0LAPTOP01"
    assert drop["old_price"] == 60000.0
    assert drop["new_price"] == 54000.0
    assert drop["savings_inr"] == 6000.0

    # Verify new deal
    new_deal = comparison["new_deals"][0]
    assert new_deal["asin"] == "B0WATCH001"

    # Verify expired deal
    expired = comparison["expired_deals"][0]
    assert expired["asin"] == "B0SHOE0001"


def test_has_snapshot_for_date_and_count(temp_history_db):
    assert not has_snapshot_for_date("2026-11-05", db_path=temp_history_db)
    assert get_snapshot_count_for_date("2026-11-05", db_path=temp_history_db) == 0

    item = {
        "asin": "B0TESTAUTO1",
        "title": "Test Item",
        "current_price": 999.0,
    }
    record_deal_snapshot(item, "TestCat", snapshot_date="2026-11-05", db_path=temp_history_db)

    assert has_snapshot_for_date("2026-11-05", db_path=temp_history_db)
    assert get_snapshot_count_for_date("2026-11-05", db_path=temp_history_db) == 1
