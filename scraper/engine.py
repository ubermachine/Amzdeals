"""Scraper engine: orchestrates URL construction, HTTP fetching, parsing, and caching."""

import asyncio
import logging
import random
from urllib.parse import urlencode

import httpx

import config
from cache.sqlite_cache import SearchCache, make_cache_key
from scraper.parser import parse_search_results
from scraper.stealth import get_stealth_headers

logger = logging.getLogger(__name__)


def build_search_url(
    query: str, min_discount: int, max_discount: int, page: int
) -> str:
    """Construct an Amazon.in search URL with discount filters.

    Args:
        query: Search term (e.g. "Perfume").
        min_discount: Minimum discount percentage (e.g. 40).
        max_discount: Maximum discount percentage (e.g. 90).
        page: Page number (1-indexed).

    Returns:
        Full Amazon.in search URL string.
    """
    params = {
        "k": query,
        "pct-off": f"{min_discount}-{max_discount}",
        "s": "discount-percent-rank",
        "page": page,
    }
    return f"{config.AMAZON_BASE_URL}?{urlencode(params)}"


async def _fetch_with_retry(url: str) -> str | None:
    """Fetch a URL with stealth headers, retries, and exponential backoff.

    Returns:
        HTML string on success, None on failure after all retries.
    """
    for attempt in range(config.MAX_RETRIES):
        headers = get_stealth_headers()
        try:
            async with httpx.AsyncClient(
                http2=True,
                timeout=config.REQUEST_TIMEOUT,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                # Check for CAPTCHA
                text = response.text
                if "captcha" in text.lower() or "robot" in text.lower():
                    logger.warning(
                        "CAPTCHA detected on attempt %d/%d",
                        attempt + 1,
                        config.MAX_RETRIES,
                    )
                    if attempt < config.MAX_RETRIES - 1:
                        wait = config.BACKOFF_BASE ** (attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    return None

                return text

        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.warning(
                "Request failed on attempt %d/%d: %s",
                attempt + 1,
                config.MAX_RETRIES,
                str(e),
            )
            if attempt < config.MAX_RETRIES - 1:
                wait = config.BACKOFF_BASE ** (attempt + 1)
                await asyncio.sleep(wait)
            else:
                return None

    return None


async def search_deals(
    query: str,
    min_discount: int,
    max_discount: int,
    page: int,
    cache: SearchCache,
) -> dict:
    """Search for deals on Amazon.in with caching.

    Args:
        query: Search term.
        min_discount: Minimum discount percentage.
        max_discount: Maximum discount percentage.
        page: Page number.
        cache: SearchCache instance.

    Returns:
        Dict with keys: query, page, products, total_results, cached.
    """
    cache_key = make_cache_key(query, min_discount, max_discount, page)

    # Check cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    # Throttle: random delay before hitting Amazon
    delay = random.uniform(config.THROTTLE_MIN, config.THROTTLE_MAX)
    await asyncio.sleep(delay)

    # Fetch from Amazon
    url = build_search_url(query, min_discount, max_discount, page)
    html = await _fetch_with_retry(url)

    if html is None:
        return {
            "query": query,
            "page": page,
            "products": [],
            "total_results": 0,
            "cached": False,
            "error": "Failed to fetch results from Amazon. Please try again later.",
        }

    # Parse
    products = parse_search_results(html)

    result = {
        "query": query,
        "page": page,
        "products": products,
        "total_results": len(products),
        "cached": False,
    }

    # Store in cache
    await cache.set(cache_key, result)

    return result
