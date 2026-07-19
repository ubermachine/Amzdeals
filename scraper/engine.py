"""Scraper engine: orchestrates URL construction, HTTP fetching, parsing, and caching."""

import asyncio
import logging
import random
from urllib.parse import urlencode

import httpx

import config
from cache.sqlite_cache import SearchCache, make_cache_key, make_category_cache_key
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


def build_category_url(
    node: str, min_discount: int, max_discount: int, page: int
) -> str:
    """Construct an Amazon.in category browse URL with discount filters.

    Args:
        node: Amazon browse-node ID (e.g. "976419031" for Electronics).
        min_discount: Minimum discount percentage.
        max_discount: Maximum discount percentage.
        page: Page number (1-indexed).

    Returns:
        Full Amazon.in browse-node URL string.
    """
    params = {
        "rh": f"n:{node}",
        "pct-off": f"{min_discount}-{max_discount}",
        "s": "discount-percent-rank",
        "page": page,
    }
    return f"{config.AMAZON_BASE_URL}?{urlencode(params)}"


def compute_deal_score(product: dict) -> int:
    """Compute a 0–100 deal quality score for a product.

    Weighted formula:
        - 60% discount percentage (0–100)
        - 25% rating normalized to 0–100 scale
        - 15% review count normalized to 0–100 (capped at 5000)

    Products with no discount are scored 0.

    Args:
        product: Dict with keys discount_pct, rating, review_count.

    Returns:
        Integer score from 0 to 100.
    """
    discount = product.get("discount_pct")
    if discount is None:
        return 0

    rating = product.get("rating") or 0.0
    reviews = product.get("review_count") or 0

    norm_rating = (rating / 5.0) * 100
    norm_reviews = (min(reviews, 5000) / 5000) * 100

    score = discount * 0.6 + norm_rating * 0.25 + norm_reviews * 0.15
    return round(score)


async def search_category_deals(
    node: str,
    category_name: str,
    min_discount: int,
    max_discount: int,
    cache: SearchCache,
) -> dict:
    """Fetch top deals for a category by browse-node, score, and rank.

    Fetches up to TOP_DEALS_PAGES pages, deduplicates by ASIN,
    computes deal scores, and returns the top TOP_DEALS_LIMIT products.

    Args:
        node: Amazon browse-node ID.
        category_name: Human-readable category name.
        min_discount: Minimum discount percentage.
        max_discount: Maximum discount percentage.
        cache: SearchCache instance.

    Returns:
        Dict with keys: category, node, products, total_results, cached.
    """
    cache_key = make_category_cache_key(node, min_discount, max_discount)

    # Check cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    # Fetch multiple pages
    all_products = []
    seen_asins = set()
    any_success = False

    for page_num in range(1, config.TOP_DEALS_PAGES + 1):
        # Throttle between pages
        delay = random.uniform(config.THROTTLE_MIN, config.THROTTLE_MAX)
        await asyncio.sleep(delay)

        url = build_category_url(node, min_discount, max_discount, page_num)
        html = await _fetch_with_retry(url)

        if html is None:
            logger.warning(
                "Failed to fetch page %d for category %s (node %s)",
                page_num, category_name, node,
            )
            continue

        any_success = True
        products = parse_search_results(html)
        for p in products:
            asin = p.get("asin")
            if asin and asin not in seen_asins:
                seen_asins.add(asin)
                all_products.append(p)

    if not any_success:
        return {
            "category": category_name,
            "node": node,
            "products": [],
            "total_results": 0,
            "cached": False,
            "error": "Failed to fetch results from Amazon. Please try again later.",
        }

    # Score and rank
    for p in all_products:
        p["deal_score"] = compute_deal_score(p)

    all_products.sort(key=lambda p: p["deal_score"], reverse=True)
    top_products = all_products[: config.TOP_DEALS_LIMIT]

    result = {
        "category": category_name,
        "node": node,
        "products": top_products,
        "total_results": len(top_products),
        "cached": False,
    }

    # Store in cache
    await cache.set(cache_key, result)

    return result


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

                # Check for CAPTCHA page (not just the word "robot" which
                # appears in normal meta tags like <meta name="robots">)
                text = response.text
                is_captcha = (
                    "captcha" in text.lower()
                    and "Type the characters you see" in text
                ) or (
                    "/errors/validateCaptcha" in text
                )
                if is_captcha:
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
