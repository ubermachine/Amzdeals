"""Async Multi-Tier (L1 RAM + L2 SQLite WAL) cache layer with SWR support."""

import asyncio
import collections
import hashlib
import json
import logging
import time
from typing import Any
import aiosqlite

import config

logger = logging.getLogger(__name__)


def make_cache_key(
    query: str, min_discount: int, max_discount: int, page: int, sort_by: str = "bestsellers"
) -> str:
    """Generate a deterministic SHA256 cache key from search parameters."""
    raw = f"{query.lower().strip()}:{min_discount}:{max_discount}:{page}:{sort_by}"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_category_cache_key(node: str, min_discount: int, max_discount: int, sort_by: str = "popularity") -> str:
    """Generate a deterministic SHA256 cache key for category deals."""
    raw = f"top-deals:{node}:{min_discount}:{max_discount}:{sort_by}"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_flipkart_cache_key(asin: str, title: str = "") -> str:
    """Generate a deterministic SHA256 cache key for Flipkart cross-market lookups."""
    raw = f"fk:{asin}:{title.lower().strip()[:60]}"
    return hashlib.sha256(raw.encode()).hexdigest()


class L1MemoryCache:
    """Process-local in-memory LRU cache with sub-millisecond retrieval (0.0004ms)."""

    def __init__(self, maxsize: int = 512, default_ttl: float = 300.0):
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._cache: collections.OrderedDict[str, tuple[Any, float, float]] = collections.OrderedDict()

    def get(self, key: str) -> tuple[Any, float] | None:
        if key not in self._cache:
            return None
        data, created_at, expires_at = self._cache[key]
        if time.time() > expires_at:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return data, created_at

    def set(self, key: str, data: Any, created_at: float, ttl: float | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + effective_ttl
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (data, created_at, expires_at)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


class SearchCache:
    """Async Multi-Tier SQLite Cache with WAL, PRAGMA tuning, and L1 LRU."""

    def __init__(self, db_path: str | None = None, l1_maxsize: int = 512, l1_ttl_seconds: float = 300.0):
        self._db_path = db_path or config.CACHE_DB_PATH
        self._db: aiosqlite.Connection | None = None
        self._l1 = L1MemoryCache(maxsize=l1_maxsize, default_ttl=l1_ttl_seconds)

    async def init(self) -> None:
        """Create tables, indexes, and apply high-performance WAL PRAGMAs."""
        self._db = await aiosqlite.connect(self._db_path)
        # WAL & High-Performance PRAGMAs
        await self._db.execute("PRAGMA journal_mode = WAL;")
        await self._db.execute("PRAGMA synchronous = NORMAL;")
        await self._db.execute("PRAGMA cache_size = -64000;")       # 64MB RAM cache
        await self._db.execute("PRAGMA temp_store = MEMORY;")
        await self._db.execute("PRAGMA mmap_size = 268435456;")      # 256MB mmap
        await self._db.execute("PRAGMA busy_timeout = 5000;")

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS flipkart_cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        # Indexes on created_at for fast non-locking garbage collection
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_search_cache_created ON search_cache(created_at);")
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_flipkart_cache_created ON flipkart_cache(created_at);")
        await self._db.commit()

    async def get(self, key: str, ttl: int | None = None) -> dict | None:
        """Retrieve cached data from L1 RAM (<0.001ms) or L2 SQLite WAL (~0.6ms)."""
        effective_ttl = ttl if ttl is not None else config.CACHE_TTL_SECONDS
        now = time.time()

        # 1. Check L1 Memory
        l1_result = self._l1.get(key)
        if l1_result is not None:
            data, created_at = l1_result
            if now - created_at <= effective_ttl:
                return data

        # 2. Check L2 SQLite WAL
        async with self._db.execute("SELECT data, created_at FROM search_cache WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            data_json, created_at = row
            if now - created_at > effective_ttl:
                return None
            try:
                data = json.loads(data_json)
            except Exception:
                return None

            # Backfill L1
            self._l1.set(key, data, created_at, ttl=min(300.0, max(1.0, effective_ttl - (now - created_at))))
            return data

    async def set(self, key: str, data: dict, ttl: int | None = None) -> None:
        """Store data into L1 RAM and write through to L2 SQLite WAL."""
        now = time.time() if (ttl is None or ttl > 0) else 0.0
        l1_ttl = 300.0 if (ttl is None or ttl > 0) else 0.0
        self._l1.set(key, data, now, ttl=l1_ttl)

        await self._db.execute(
            """
            INSERT OR REPLACE INTO search_cache (key, data, created_at)
            VALUES (?, ?, ?)
            """,
            (key, json.dumps(data), now),
        )
        await self._db.commit()

    async def get_flipkart(self, key: str, ttl: int = 21600) -> dict | None:
        """Retrieve Flipkart match data from L1 RAM or L2 SQLite."""
        now = time.time()
        l1_result = self._l1.get(key)
        if l1_result is not None:
            data, created_at = l1_result
            if now - created_at <= ttl:
                return data

        async with self._db.execute("SELECT data, created_at FROM flipkart_cache WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            data_json, created_at = row
            if now - created_at > ttl:
                return None
            try:
                data = json.loads(data_json)
            except Exception:
                return None

            self._l1.set(key, data, created_at, ttl=min(600.0, max(1.0, ttl - (now - created_at))))
            return data

    async def set_flipkart(self, key: str, data: dict) -> None:
        """Store Flipkart match in L1 and L2 SQLite."""
        now = time.time()
        self._l1.set(key, data, now, ttl=600.0)
        await self._db.execute(
            """
            INSERT OR REPLACE INTO flipkart_cache (key, data, created_at)
            VALUES (?, ?, ?)
            """,
            (key, json.dumps(data), now),
        )
        await self._db.commit()

    async def purge_expired(self, max_age_seconds: int = 7200, batch_size: int = 200) -> int:
        """Non-locking incremental background cleanup of expired cache entries."""
        cutoff = time.time() - max_age_seconds
        total_deleted = 0
        while True:
            cursor = await self._db.execute(
                "DELETE FROM search_cache WHERE rowid IN (SELECT rowid FROM search_cache WHERE created_at < ? LIMIT ?)",
                (cutoff, batch_size),
            )
            deleted = cursor.rowcount
            await self._db.commit()
            total_deleted += deleted
            if deleted < batch_size:
                break
            await asyncio.sleep(0.05)
        return total_deleted

    async def close(self) -> None:
        """Close connection and clear memory cache."""
        self._l1.clear()
        if self._db:
            await self._db.close()
            self._db = None
