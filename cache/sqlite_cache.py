"""Async SQLite cache layer with TTL support."""

import hashlib
import json
import time
import aiosqlite

import config


def make_cache_key(query: str, min_discount: int, max_discount: int, page: int) -> str:
    """Generate a deterministic SHA256 cache key from search parameters."""
    raw = f"{query.lower().strip()}:{min_discount}:{max_discount}:{page}"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_category_cache_key(node: str, min_discount: int, max_discount: int) -> str:
    """Generate a deterministic SHA256 cache key for category deals."""
    raw = f"top-deals:{node}:{min_discount}:{max_discount}"
    return hashlib.sha256(raw.encode()).hexdigest()



class SearchCache:
    """Async SQLite cache for Amazon search results."""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or config.CACHE_DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Create the cache table if it doesn't exist."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        await self._db.commit()

    async def get(self, key: str, ttl: int | None = None) -> dict | None:
        """Retrieve cached data if it exists and hasn't expired.

        Args:
            key: Cache key (SHA256 hex).
            ttl: Override TTL in seconds. Uses config.CACHE_TTL_SECONDS by default.

        Returns:
            Cached dict or None if miss/expired.
        """
        if ttl is None:
            ttl = config.CACHE_TTL_SECONDS
        async with self._db.execute(
            "SELECT data, created_at FROM search_cache WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            data_json, created_at = row
            if time.time() - created_at > ttl:
                # Expired — delete and return None
                await self._db.execute(
                    "DELETE FROM search_cache WHERE key = ?", (key,)
                )
                await self._db.commit()
                return None
            return json.loads(data_json)

    async def set(self, key: str, data: dict, ttl: int | None = None) -> None:
        """Store data in the cache.

        Args:
            key: Cache key (SHA256 hex).
            data: Dict to cache (will be JSON-serialized).
            ttl: Not used for storage — TTL is checked on read. Param exists
                 for test convenience (to store with an effectively-zero TTL).
        """
        # If ttl=0 is passed (for tests), store with a timestamp far in the past
        created_at = time.time() if ttl is None or ttl > 0 else 0.0
        await self._db.execute(
            """
            INSERT OR REPLACE INTO search_cache (key, data, created_at)
            VALUES (?, ?, ?)
            """,
            (key, json.dumps(data), created_at),
        )
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
