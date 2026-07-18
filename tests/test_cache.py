import asyncio
import os
import time
import pytest
from cache.sqlite_cache import SearchCache, make_cache_key

TEST_DB = "test_cache.db"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def cache():
    c = SearchCache(TEST_DB)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(c.init())
    yield c
    loop.run_until_complete(c.close())


def test_make_cache_key_deterministic():
    k1 = make_cache_key("Perfume", 40, 90, 1)
    k2 = make_cache_key("Perfume", 40, 90, 1)
    assert k1 == k2


def test_make_cache_key_different_inputs():
    k1 = make_cache_key("Perfume", 40, 90, 1)
    k2 = make_cache_key("Laptop", 40, 90, 1)
    assert k1 != k2


def test_cache_get_miss(cache):
    result = asyncio.get_event_loop().run_until_complete(cache.get("nonexistent"))
    assert result is None


def test_cache_set_and_get(cache):
    loop = asyncio.get_event_loop()
    data = {"products": [{"asin": "B123", "title": "Test"}], "total_results": 1}
    loop.run_until_complete(cache.set("testkey", data))
    result = loop.run_until_complete(cache.get("testkey"))
    assert result is not None
    assert result["products"][0]["asin"] == "B123"


def test_cache_expired_returns_none(cache):
    loop = asyncio.get_event_loop()
    data = {"products": []}
    loop.run_until_complete(cache.set("expkey", data, ttl=0))
    time.sleep(0.1)
    result = loop.run_until_complete(cache.get("expkey"))
    assert result is None
