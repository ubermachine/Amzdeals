import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

import config
from cache.sqlite_cache import SearchCache
from scraper.engine import search_deals, search_category_deals

# Ensure static directory exists to prevent FastAPI mount from crashing
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
index_path = os.path.join(STATIC_DIR, "index.html")
if not os.path.exists(index_path):
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("<html><body>Frontend coming soon</body></html>")

# Global cache instance
_cache: SearchCache | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global _cache
    _cache = SearchCache()
    await _cache.init()
    yield
    # Shutdown
    if _cache:
        await _cache.close()


app = FastAPI(title="Amazon.in Deal Finder API", lifespan=lifespan)

@app.get("/api/search")
async def api_search(
    query: str = Query(..., min_length=1, description="Search term (e.g., Perfume)"),
    min_discount: int = Query(10, ge=0, le=99, description="Minimum discount %"),
    max_discount: int = Query(99, ge=1, le=100, description="Maximum discount %"),
    page: int = Query(1, ge=1, le=100, description="Page number"),
):
    """Search for deals on Amazon.in."""
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
):
    """Get top deals for a specific Amazon.in category."""
    global _cache
    if not _cache:
        _cache = SearchCache()
        await _cache.init()

    # Look up category name from node
    category_name = "Unknown"
    for cat in config.CATEGORIES:
        if cat["node"] == category:
            category_name = cat["name"]
            break

    result = await search_category_deals(
        node=category,
        category_name=category_name,
        min_discount=min_discount,
        max_discount=max_discount,
        cache=_cache,
    )
    return result


# Mount static files at root
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
