import asyncio
from datetime import datetime
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

import config
from cache.history import (
    dump_cache_to_snapshots,
    list_snapshot_dates,
    get_snapshots_by_date,
    compare_snapshots,
    has_snapshot_for_date,
    get_snapshot_count_for_date,
    get_snapshot_categories_for_date,
    is_daily_snapshot_complete,
)
from cache.sqlite_cache import SearchCache
from scraper.engine import search_deals, search_category_deals

logger = logging.getLogger(__name__)

# Ensure static directory exists to prevent FastAPI mount from crashing
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
index_path = os.path.join(STATIC_DIR, "index.html")
if not os.path.exists(index_path):
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("<html><body>Frontend coming soon</body></html>")

# Global cache instance
_cache: SearchCache | None = None


async def _run_startup_snapshot_check(cache: SearchCache) -> None:
    """Non-blocking startup check: automatically records daily deal snapshot across all 18 categories once per day."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        all_categories = config.CATEGORIES
        recorded_cats = get_snapshot_categories_for_date(today)
        missing_cats = [c for c in all_categories if c["name"] not in recorded_cats]

        # 1. If already complete across all categories, skip in 0.5ms (no redundant work on restart)
        if not missing_cats:
            count = get_snapshot_count_for_date(today)
            logger.info(
                "[DealTracker] Today's snapshot (%s) is already complete across all %d categories (%d deals). Skipping.",
                today,
                len(all_categories),
                count,
            )
            return

        logger.info(
            "[DealTracker] Snapshot for %s has %d categories recorded (%d missing). Ensuring all categories are captured...",
            today,
            len(recorded_cats),
            len(missing_cats),
        )

        # 2. First dump any existing cached deals for today
        dump_cache_to_snapshots(snapshot_date=today)
        recorded_cats = get_snapshot_categories_for_date(today)
        missing_cats = [c for c in all_categories if c["name"] not in recorded_cats]

        # 3. Sweep any remaining missing categories in the background
        if missing_cats:
            logger.info("[DealTracker] Sweeping %d missing categories in background...", len(missing_cats))
            for cat in missing_cats:
                try:
                    res = await search_category_deals(
                        node=cat["node"],
                        category_name=cat["name"],
                        min_discount=config.DEFAULT_MIN_DISCOUNT,
                        max_discount=config.DEFAULT_MAX_DISCOUNT,
                        cache=cache,
                    )
                    for p in res.get("products", []):
                        from cache.history import record_deal_snapshot
                        record_deal_snapshot(p, category=cat["name"], snapshot_date=today, node=cat["node"])
                except Exception as e:
                    logger.warning("[DealTracker] Daily sweep failed for category %s: %s", cat["name"], e)
                # Polite pacing between uncached category scrapes
                await asyncio.sleep(1.0)

        total_now = get_snapshot_count_for_date(today)
        cats_now = get_snapshot_categories_for_date(today)
        logger.info(
            "[DealTracker] Daily snapshot for %s complete: %d categories, %d unique deals recorded.",
            today,
            len(cats_now),
            total_now,
        )
    except Exception as e:
        logger.error("[DealTracker] Error during daily snapshot check: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global _cache
    _cache = SearchCache()
    await _cache.init()
    # Non-blocking background task: ensures snapshot is taken once for that day
    asyncio.create_task(_run_startup_snapshot_check(_cache))
    yield
    # Shutdown
    if _cache:
        await _cache.close()


app = FastAPI(title="Amazon.in Deal Finder API", version=config.APP_VERSION, lifespan=lifespan)

# Enable GZip compression (>500 bytes) for ~75% wire size reduction
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.get("/api/version")
async def get_version():
    """Return application release version metadata."""
    return {
        "version": config.APP_VERSION,
        "release": f"v{config.APP_VERSION}",
        "name": "Amazon Deal Finder",
        "status": "healthy"
    }


async def fetch_keepa_graph(asin: str, range_days: int = 365) -> bytes | None:
    """Fetch Keepa price history graph image for an Amazon.in ASIN.

    Uses authentic browser headers (including Amazon.in referer) to bypass Keepa WAF.
    """
    url = f"https://graph.keepa.com/pricehistory?asin={asin}&domain=10&range={range_days}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://www.amazon.in/",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200 and resp.content:
                return resp.content
            return None
    except Exception as e:
        logger.warning("Failed to fetch Keepa graph for ASIN %s: %s", asin, e)
        return None


@app.get("/api/search")
async def api_search(
    query: str = Query(..., min_length=1, description="Search term (e.g., Perfume)"),
    min_discount: int = Query(10, ge=0, le=99, description="Minimum discount %"),
    max_discount: int = Query(99, ge=1, le=100, description="Maximum discount %"),
    page: int = Query(1, ge=1, le=100, description="Page number"),
    sort_by: str = Query("bestsellers", description="Sort order: bestsellers, popularity, reviews, featured"),
):
    """Search for deals on Amazon.in."""
    if min_discount > max_discount:
        raise HTTPException(status_code=400, detail="min_discount cannot be greater than max_discount")

    global _cache
    if not _cache:
        _cache = SearchCache()
        await _cache.init()
        
    result = await search_deals(
        query=query,
        min_discount=min_discount,
        max_discount=max_discount,
        page=page,
        cache=_cache,
        sort_by=sort_by,
    )
    return result


@app.get("/api/categories")
async def api_categories():
    """Return the list of available Amazon.in categories."""
    return config.CATEGORIES


@app.get("/api/top-deals")
async def api_top_deals(
    category: str = Query(..., min_length=1, description="Amazon browse-node ID"),
    min_discount: int = Query(40, ge=0, le=99, description="Minimum discount %"),
    max_discount: int = Query(90, ge=1, le=100, description="Maximum discount %"),
    sort_by: str = Query("popularity", pattern="^(popularity|bestsellers|deal_score|discount|reviews)$", description="Sort order"),
):
    """Get top deals for a specific Amazon.in category."""
    if min_discount > max_discount:
        raise HTTPException(status_code=400, detail="min_discount cannot be greater than max_discount")

    global _cache
    if not _cache:
        _cache = SearchCache()
        await _cache.init()

    # Look up category node and name
    node = category
    category_name = "Unknown"
    for cat in config.CATEGORIES:
        if cat["node"] == category:
            category_name = cat["name"]
            break
        elif cat["name"].lower() == category.lower().replace("-", " ") or cat["name"].lower().startswith(category.lower()):
            node = cat["node"]
            category_name = cat["name"]
            break

    result = await search_category_deals(
        node=node,
        category_name=category_name,
        min_discount=min_discount,
        max_discount=max_discount,
        cache=_cache,
        sort_by=sort_by,
    )
    return result


@app.get("/api/keepa-graph")
async def api_keepa_graph(
    asin: str = Query(..., min_length=10, max_length=10, pattern=r"^[A-Za-z0-9]{10}$", description="10-character Amazon ASIN"),
    range: int = Query(365, ge=1, le=1000, description="Price history range in days"),
):
    """Proxy Keepa price history graph to bypass CORS, localhost referer blocks, and ad blockers."""
    content = await fetch_keepa_graph(asin=asin, range_days=range)
    if not content:
        raise HTTPException(status_code=502, detail="Failed to load price history graph from Keepa.")
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/snapshots/dates")
async def api_snapshot_dates():
    """List all available daily deal snapshot dates with aggregate metrics."""
    return list_snapshot_dates()


@app.post("/api/snapshots/dump")
async def api_snapshot_dump(date: str | None = None):
    """Dump all current cached deals into daily snapshot history."""
    count = dump_cache_to_snapshots(snapshot_date=date)
    return {
        "status": "success",
        "recorded_count": count,
        "snapshot_date": date or "today",
    }


@app.get("/api/snapshots/deals")
async def api_snapshot_deals(date: str = Query(..., description="Snapshot date in YYYY-MM-DD format")):
    """Get all deal records for a specific snapshot date."""
    deals = get_snapshots_by_date(date)
    return {
        "snapshot_date": date,
        "count": len(deals),
        "deals": deals,
    }


@app.get("/api/snapshots/compare")
async def api_snapshot_compare(
    date1: str = Query(..., description="Earlier snapshot date (e.g. 2026-11-01)"),
    date2: str = Query(..., description="Later snapshot date (e.g. 2026-11-02)"),
):
    """Compare two snapshot dates to detect price drops, hikes, new deals, and expired deals."""
    return compare_snapshots(date1, date2)


# Mount static files at root
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
