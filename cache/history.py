"""Historical Deal Snapshots & Day-over-Day Price Tracker.

Stores daily snapshots of curated top deals in a dedicated SQLite database (deal_history.db).
Enables day-over-day price delta tracking, new deal alerts, expired deal detection,
and arbitrage trend analysis.
"""

from datetime import datetime
import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DB = "deal_history.db"


def init_history_db(db_path: str = DEFAULT_HISTORY_DB) -> None:
    """Initialize the deal history database with optimized indexes."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deal_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                recorded_at REAL NOT NULL,
                category TEXT NOT NULL,
                node TEXT,
                asin TEXT NOT NULL,
                title TEXT NOT NULL,
                current_price REAL,
                effective_price REAL,
                original_price REAL,
                discount_pct REAL,
                effective_discount_pct REAL,
                deal_score REAL,
                is_true_deal INTEGER,
                badge TEXT,
                rating REAL,
                review_count INTEGER,
                flipkart_price REAL,
                flipkart_verdict TEXT,
                flipkart_diff_pct REAL,
                flipkart_url TEXT,
                product_url TEXT,
                image_url TEXT,
                raw_json TEXT,
                UNIQUE(snapshot_date, category, asin) ON CONFLICT REPLACE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON deal_snapshots(snapshot_date);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_asin ON deal_snapshots(asin);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_cat ON deal_snapshots(category);")
        conn.commit()
    finally:
        conn.close()


def has_snapshot_for_date(snapshot_date: str | None = None, db_path: str = DEFAULT_HISTORY_DB) -> bool:
    """Check if a deal snapshot has already been recorded for a specific date."""
    init_history_db(db_path)
    today = snapshot_date or datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        count = cursor.execute(
            "SELECT COUNT(*) FROM deal_snapshots WHERE snapshot_date = ?", (today,)
        ).fetchone()[0]
        return count > 0
    finally:
        conn.close()


def get_snapshot_count_for_date(snapshot_date: str | None = None, db_path: str = DEFAULT_HISTORY_DB) -> int:
    """Return the number of unique deals recorded for a specific date."""
    init_history_db(db_path)
    today = snapshot_date or datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        count = cursor.execute(
            "SELECT COUNT(DISTINCT asin) FROM deal_snapshots WHERE snapshot_date = ?", (today,)
        ).fetchone()[0]
        return count
    finally:
        conn.close()


def get_snapshot_categories_for_date(snapshot_date: str | None = None, db_path: str = DEFAULT_HISTORY_DB) -> set[str]:
    """Return the set of categories recorded for a specific date."""
    init_history_db(db_path)
    today = snapshot_date or datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT DISTINCT category FROM deal_snapshots WHERE snapshot_date = ?", (today,)
        ).fetchall()
        return {r[0] for r in rows if r[0]}
    finally:
        conn.close()


def is_daily_snapshot_complete(
    snapshot_date: str | None = None,
    expected_categories: int = 18,
    db_path: str = DEFAULT_HISTORY_DB,
) -> bool:
    """Check if all expected categories have been recorded for the day."""
    cats = get_snapshot_categories_for_date(snapshot_date, db_path)
    return len(cats) >= expected_categories


def record_deal_snapshot(
    product: dict,
    category: str,
    snapshot_date: str | None = None,
    node: str | None = None,
    db_path: str = DEFAULT_HISTORY_DB,
) -> None:
    """Record a single deal into the snapshot database."""
    init_history_db(db_path)
    today = snapshot_date or datetime.now().strftime("%Y-%m-%d")
    now_ts = time.time()

    asin = product.get("asin")
    title = product.get("title")
    if not asin or not title:
        return

    fk_info = product.get("cross_market") or {}
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO deal_snapshots (
                snapshot_date, recorded_at, category, node, asin, title,
                current_price, effective_price, original_price, discount_pct,
                effective_discount_pct, deal_score, is_true_deal, badge,
                rating, review_count, flipkart_price, flipkart_verdict,
                flipkart_diff_pct, flipkart_url, product_url, image_url, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                today,
                now_ts,
                category,
                node,
                asin,
                title,
                product.get("current_price"),
                product.get("effective_price") or product.get("current_price"),
                product.get("original_price"),
                product.get("discount_pct"),
                product.get("effective_discount_pct") or product.get("discount_pct"),
                product.get("deal_score"),
                1 if product.get("is_true_deal") else 0,
                product.get("badge"),
                product.get("rating"),
                product.get("review_count"),
                fk_info.get("flipkart_price"),
                fk_info.get("verdict"),
                fk_info.get("diff_pct"),
                fk_info.get("flipkart_url"),
                product.get("product_url"),
                product.get("image_url"),
                json.dumps(product),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def dump_cache_to_snapshots(
    cache_db_path: str = "cache.db",
    history_db_path: str = DEFAULT_HISTORY_DB,
    snapshot_date: str | None = None,
) -> int:
    """Extract all cached deals from search_cache and insert them into deal_snapshots."""
    init_history_db(history_db_path)
    today = snapshot_date or datetime.now().strftime("%Y-%m-%d")

    cache_conn = sqlite3.connect(cache_db_path)
    hist_conn = sqlite3.connect(history_db_path)
    recorded_count = 0

    try:
        cursor = cache_conn.cursor()
        rows = cursor.execute("SELECT data, created_at FROM search_cache").fetchall()

        for data_json, created_at in rows:
            try:
                data = json.loads(data_json)
            except Exception:
                continue

            products = data.get("products") or []
            cat = data.get("category") or data.get("query") or "General"
            node = data.get("node")

            for p in products:
                asin = p.get("asin")
                title = p.get("title")
                if not asin or not title:
                    continue

                fk_info = p.get("cross_market") or {}
                hist_conn.execute(
                    """
                    INSERT OR REPLACE INTO deal_snapshots (
                        snapshot_date, recorded_at, category, node, asin, title,
                        current_price, effective_price, original_price, discount_pct,
                        effective_discount_pct, deal_score, is_true_deal, badge,
                        rating, review_count, flipkart_price, flipkart_verdict,
                        flipkart_diff_pct, flipkart_url, product_url, image_url, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        today,
                        created_at or time.time(),
                        cat,
                        node,
                        asin,
                        title,
                        p.get("current_price"),
                        p.get("effective_price") or p.get("current_price"),
                        p.get("original_price"),
                        p.get("discount_pct"),
                        p.get("effective_discount_pct") or p.get("discount_pct"),
                        p.get("deal_score"),
                        1 if p.get("is_true_deal") else 0,
                        p.get("badge"),
                        p.get("rating"),
                        p.get("review_count"),
                        fk_info.get("flipkart_price"),
                        fk_info.get("verdict"),
                        fk_info.get("diff_pct"),
                        fk_info.get("flipkart_url"),
                        p.get("product_url"),
                        p.get("image_url"),
                        json.dumps(p),
                    ),
                )
                recorded_count += 1

        hist_conn.commit()
    finally:
        cache_conn.close()
        hist_conn.close()

    return recorded_count


def list_snapshot_dates(db_path: str = DEFAULT_HISTORY_DB) -> list[dict]:
    """Return all available snapshot dates with metadata counts."""
    init_history_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                snapshot_date,
                COUNT(DISTINCT asin) as unique_deals,
                COUNT(*) as total_entries,
                COUNT(DISTINCT category) as categories_count,
                ROUND(AVG(effective_price), 2) as avg_price,
                ROUND(AVG(deal_score), 1) as avg_score,
                SUM(is_true_deal) as true_deals_count
            FROM deal_snapshots
            GROUP BY snapshot_date
            ORDER BY snapshot_date DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_snapshots_by_date(snapshot_date: str, db_path: str = DEFAULT_HISTORY_DB) -> list[dict]:
    """Retrieve all deals captured on a specific date."""
    init_history_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT * FROM deal_snapshots
            WHERE snapshot_date = ?
            ORDER BY category ASC, deal_score DESC
            """,
            (snapshot_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def compare_snapshots(
    date_earlier: str,
    date_later: str,
    db_path: str = DEFAULT_HISTORY_DB,
) -> dict:
    """Compare two snapshot dates to detect price changes, new deals, and expired deals.

    Returns:
    - summary: counts of changes
    - price_drops: items where price decreased (deals got better)
    - price_hikes: items where price increased
    - new_deals: ASINs present in date_later but not in date_earlier
    - expired_deals: ASINs present in date_earlier but absent in date_later
    - score_changes: items whose deal score changed
    """
    earlier_deals = get_snapshots_by_date(date_earlier, db_path)
    later_deals = get_snapshots_by_date(date_later, db_path)

    # Index by ASIN (deduplicated by ASIN)
    earlier_map: dict[str, dict] = {}
    for d in earlier_deals:
        asin = d["asin"]
        if asin not in earlier_map or (d.get("deal_score") or 0) > (earlier_map[asin].get("deal_score") or 0):
            earlier_map[asin] = d

    later_map: dict[str, dict] = {}
    for d in later_deals:
        asin = d["asin"]
        if asin not in later_map or (d.get("deal_score") or 0) > (later_map[asin].get("deal_score") or 0):
            later_map[asin] = d

    price_drops = []
    price_hikes = []
    score_changes = []
    unchanged_count = 0

    # Check common ASINs for price/score changes
    common_asins = set(earlier_map.keys()).intersection(later_map.keys())
    for asin in common_asins:
        e = earlier_map[asin]
        l = later_map[asin]

        p_early = e.get("effective_price") or e.get("current_price") or 0.0
        p_late = l.get("effective_price") or l.get("current_price") or 0.0

        diff = p_late - p_early
        diff_pct = (diff / p_early * 100) if p_early > 0 else 0.0

        score_early = e.get("deal_score") or 0.0
        score_late = l.get("deal_score") or 0.0

        if diff < -1.0:  # Dropped by more than Rs 1
            price_drops.append({
                "asin": asin,
                "title": l["title"],
                "category": l["category"],
                "old_price": p_early,
                "new_price": p_late,
                "savings_inr": round(abs(diff), 2),
                "drop_pct": round(abs(diff_pct), 1),
                "deal_score": score_late,
                "product_url": l.get("product_url"),
            })
        elif diff > 1.0:  # Increased by more than Rs 1
            price_hikes.append({
                "asin": asin,
                "title": l["title"],
                "category": l["category"],
                "old_price": p_early,
                "new_price": p_late,
                "hike_inr": round(diff, 2),
                "hike_pct": round(diff_pct, 1),
                "deal_score": score_late,
                "product_url": l.get("product_url"),
            })
        else:
            unchanged_count += 1

        if abs(score_late - score_early) >= 2.0:
            score_changes.append({
                "asin": asin,
                "title": l["title"],
                "category": l["category"],
                "old_score": score_early,
                "new_score": score_late,
                "score_delta": round(score_late - score_early, 1),
            })

    # Sort drops by highest absolute savings
    price_drops.sort(key=lambda x: x["savings_inr"], reverse=True)
    price_hikes.sort(key=lambda x: x["hike_inr"], reverse=True)

    # New deals (in later, not in earlier)
    new_asins = set(later_map.keys()) - set(earlier_map.keys())
    new_deals = [
        {
            "asin": asin,
            "title": later_map[asin]["title"],
            "category": later_map[asin]["category"],
            "price": later_map[asin].get("effective_price") or later_map[asin].get("current_price"),
            "discount_pct": later_map[asin].get("discount_pct"),
            "deal_score": later_map[asin].get("deal_score"),
            "is_true_deal": bool(later_map[asin].get("is_true_deal")),
            "product_url": later_map[asin].get("product_url"),
        }
        for asin in new_asins
    ]
    new_deals.sort(key=lambda x: x.get("deal_score") or 0, reverse=True)

    # Expired deals (in earlier, no longer in later)
    expired_asins = set(earlier_map.keys()) - set(later_map.keys())
    expired_deals = [
        {
            "asin": asin,
            "title": earlier_map[asin]["title"],
            "category": earlier_map[asin]["category"],
            "last_price": earlier_map[asin].get("effective_price") or earlier_map[asin].get("current_price"),
            "deal_score": earlier_map[asin].get("deal_score"),
        }
        for asin in expired_asins
    ]

    return {
        "date_earlier": date_earlier,
        "date_later": date_later,
        "summary": {
            "earlier_total_deals": len(earlier_map),
            "later_total_deals": len(later_map),
            "price_drops_count": len(price_drops),
            "price_hikes_count": len(price_hikes),
            "unchanged_price_count": unchanged_count,
            "new_deals_count": len(new_deals),
            "expired_deals_count": len(expired_deals),
        },
        "price_drops": price_drops,
        "price_hikes": price_hikes,
        "new_deals": new_deals,
        "expired_deals": expired_deals,
        "score_changes": score_changes,
    }
