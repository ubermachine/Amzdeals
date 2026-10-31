"""Scraper engine: orchestrates URL construction, HTTP fetching, parsing, and caching.

Safety features:
  - curl_cffi with Chrome TLS impersonation (no httpx)
  - Reusable AsyncSession for cookie persistence & connection reuse
  - asyncio.Semaphore(1) concurrency guard — only one Amazon request at a time
  - Stealth headers with Referer + Sec-Fetch (realistic browser footprint)
  - Exponential backoff + CAPTCHA detection
  - SQLite cache with 30-minute TTL
"""

import asyncio
import logging
import math
import random
import statistics
from urllib.parse import urlencode

from curl_cffi import requests

import config
from cache.sqlite_cache import SearchCache, make_cache_key, make_category_cache_key
from scraper.flipkart import verify_product_against_flipkart
from scraper.parser import parse_search_results
from scraper.stealth import get_stealth_headers

logger = logging.getLogger(__name__)

# ─── Concurrency guard ───────────────────────────────────────────────
# Only one HTTP request to Amazon at a time, regardless of concurrent API users.
_scrape_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SCRAPES)

# ─── Reusable HTTPS session ──────────────────────────────────────────
# Persistent across requests for cookie jar continuity and TLS session reuse.
_session: requests.AsyncSession | None = None
_session_lock = asyncio.Lock()


async def _get_session() -> requests.AsyncSession:
    """Get or create the shared curl_cffi AsyncSession (Chrome impersonation)."""
    global _session
    if _session is None:
        async with _session_lock:
            if _session is None:
                _session = requests.AsyncSession(
                    impersonate="chrome",
                    timeout=config.REQUEST_TIMEOUT,
                )
    return _session


# ─── Discount Tiers & Refinement Nodes ───────────────────────────────

# Universal Amazon.in discount refinement taxonomy nodes
DISCOUNT_TIERS = [
    (70, "27060457031"),  # 70% Off or more
    (60, "27060456031"),  # 60% Off or more
    (50, "2665401031"),   # 50% Off or more
    (35, "2665402031"),   # 35% Off or more
    (25, "2665400031"),   # 25% Off or more
    (10, "2665399031"),   # 10% Off or more
]


def get_discount_tier_node(min_discount: int) -> str | None:
    """Return the Amazon.in taxonomical discount refinement node for min_discount.

    Maps min_discount down to the highest tier threshold <= min_discount.
    For example, 40% maps to the 35% tier ('2665402031').
    Returns None if min_discount < 10.
    """
    for threshold, node_id in DISCOUNT_TIERS:
        if min_discount >= threshold:
            return node_id
    return None


# ─── URL builders ────────────────────────────────────────────────────


def build_search_url(
    query: str,
    min_discount: int,
    max_discount: int,
    page: int,
    sort_by: str = "bestsellers",
) -> str:
    """Construct an Amazon.in search URL with taxonomical discount filters.

    Args:
        query: Search term (e.g. "Perfume", "laptops").
        min_discount: Minimum discount percentage (e.g. 40).
        max_discount: Maximum discount percentage (e.g. 90).
        page: Page number (1-indexed).
        sort_by: Sort mode ('bestsellers', 'popularity', 'reviews', 'featured').

    Returns:
        Full Amazon.in search URL string.
    """
    amazon_sort_map = {
        "bestsellers": "exact-aware-popularity-rank",
        "popularity": "exact-aware-popularity-rank",
        "reviews": "review-rank",
        "featured": "relevanceblender",
        "price_asc": "price-asc-rank",
        "price_desc": "price-desc-rank",
    }
    amazon_sort = amazon_sort_map.get(sort_by, "exact-aware-popularity-rank")

    params = {
        "k": query,
        "s": amazon_sort,
        "page": page,
    }

    tier_node = get_discount_tier_node(min_discount)
    if tier_node:
        params["rh"] = f"p_n_pct-off-with-tax:{tier_node}"

    return f"{config.AMAZON_BASE_URL}?{urlencode(params)}"


def build_category_url(
    node: str,
    min_discount: int,
    max_discount: int,
    page: int,
    sort_by: str = "popularity",
) -> str:
    """Construct an Amazon.in category browse URL with taxonomical discount filters.

    Args:
        node: Amazon browse-node ID (e.g. "976419031" for Electronics).
        min_discount: Minimum discount percentage.
        max_discount: Maximum discount percentage.
        page: Page number (1-indexed).
        sort_by: Sort mode ('popularity', 'bestsellers', 'discount', 'reviews', 'deal_score').

    Returns:
        Full Amazon.in browse-node URL string.
    """
    amazon_sort_map = {
        "popularity": "popularity-rank",
        "bestsellers": "exact-aware-popularity-rank",
        "discount": "popularity-rank",
        "reviews": "review-rank",
        "deal_score": "popularity-rank",
    }
    amazon_sort = amazon_sort_map.get(sort_by, "popularity-rank")

    rh_parts = [f"n:{node}"]
    tier_node = get_discount_tier_node(min_discount)
    if tier_node:
        rh_parts.append(f"p_n_pct-off-with-tax:{tier_node}")

    params = {
        "rh": ",".join(rh_parts),
        "s": amazon_sort,
        "page": page,
    }
    return f"{config.AMAZON_BASE_URL}?{urlencode(params)}"


# ─── Deal scoring ────────────────────────────────────────────────────


def compute_deal_score(product: dict) -> int:
    """Compute Multi-Dimensional Deal Quality Score (MDQS v3.0) for a product (0–100).

    Weighted Utility:
        - 35% Relative discount percentage utility U_relative (0–100)
        - 35% Absolute cash savings utility U_cash(delta_INR) (log-concave up to Rs. 50,000)
        - 18% Shifted Bayesian rating utility U_rating over [3.0, 5.0]
        - 12% CLT logarithmic review scaling U_reviews (log10 up to 10,000)

    Trust & Catalog Adjustments:
        - Prime boost: +6
        - Best Seller / Amazon's Choice boost: +4
        - Unreviewed non-Prime dropshipper penalty: -15 (if not is_prime and reviews < 20)
        - Refurbished / Renewed penalty: -20

    Products with no discount or non-positive price are scored 0.

    Args:
        product: Dict with product attributes.

    Returns:
        Integer score from 0 to 100.
    """
    discount = (
        product.get("effective_discount_pct")
        if product.get("effective_discount_pct") is not None
        else product.get("discount_pct")
    )
    if discount is None or discount <= 0:
        return 0

    u_relative = max(0.0, min(100.0, float(discount)))

    # 1. Absolute Cash Savings Utility (log-concave up to 50,000 INR)
    cur_price = (
        product.get("effective_price")
        if product.get("effective_price") is not None
        else product.get("current_price")
    )
    if cur_price is None:
        cur_price = product.get("price")
    orig_price = product.get("original_price")

    if orig_price and cur_price and orig_price > cur_price:
        delta_inr = orig_price - cur_price
    elif cur_price and 0 < discount < 100:
        delta_inr = cur_price * (discount / (100.0 - discount))
    else:
        delta_inr = 0.0

    if delta_inr > 0:
        # log10(1 + 50000) ~= 4.69897
        u_cash = min(100.0, (math.log10(1.0 + delta_inr) / 4.69897) * 100.0)
    else:
        u_cash = u_relative

    # 2. Shifted Bayesian Rating Utility over [3.0, 5.0]
    rating = product.get("rating")
    reviews = product.get("review_count") or 0

    if rating is not None and rating > 0:
        smoothed_rating = (rating * reviews + 3.8 * 10) / (reviews + 10)
        u_rating = max(0.0, min(100.0, ((smoothed_rating - 3.0) / 2.0) * 100.0))
    else:
        u_rating = 0.0

    # 3. CLT Logarithmic Review Scaling
    # log10(1 + 10000) ~= 4.00004
    u_reviews = min(100.0, (math.log10(1.0 + min(reviews, 10000)) / 4.00004) * 100.0)

    base_score = (
        u_relative * 0.35 +
        u_cash * 0.35 +
        u_rating * 0.18 +
        u_reviews * 0.12
    )

    # 4. Trust & Catalog Integrity Adjustments
    delta_trust = 0
    if product.get("is_prime"):
        delta_trust += 6
    if product.get("badge") in ("Best Seller", "Amazon's Choice"):
        delta_trust += 4
    if not product.get("is_prime") and reviews < 20:
        delta_trust -= 15
    if product.get("is_refurbished"):
        delta_trust -= 20

    final_score = round(base_score + delta_trust)
    return max(0, min(100, final_score))


# ─── Category deals (multi-page) ─────────────────────────────────────


async def search_category_deals(
    node: str,
    category_name: str,
    min_discount: int,
    max_discount: int,
    cache: SearchCache,
    sort_by: str = "popularity",
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
        sort_by: Sort mode ('popularity', 'deal_score', 'discount', 'reviews').

    Returns:
        Dict with keys: category, node, products, total_results, cached.
    """
    # Normalize sort aliases
    if sort_by == "bestsellers":
        sort_by = "popularity"

    cache_key = make_category_cache_key(node, min_discount, max_discount, sort_by=sort_by)

    # Check cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    # Look up category metadata for price floors and true deal calibration
    cat_meta = getattr(config, "CATEGORY_METADATA", {}).get(node, {})
    min_price = cat_meta.get("min_price", 0)
    min_true_deal_pct = cat_meta.get("min_true_deal_pct", 35)
    is_device_node = node in getattr(config, "DEVICE_NODES_FOR_ACCESSORY_FILTER", set())

    # Fetch multiple pages
    all_products = []
    seen_asins = set()
    any_success = False

    for page_num in range(1, config.TOP_DEALS_PAGES + 1):
        # Throttle only between successive pages, avoiding delay on page 1
        if page_num > 1:
            delay = random.uniform(config.THROTTLE_MIN, config.THROTTLE_MAX)
            await asyncio.sleep(delay)

        url = build_category_url(node, min_discount, max_discount, page_num, sort_by=sort_by)
        html = await _fetch_with_retry(url)

        if html is None:
            logger.warning(
                "Failed to fetch page %d for category %s (node %s)",
                page_num, category_name, node,
            )
            continue

        any_success = True
        products = parse_search_results(html)
        if not products and page_num > 1:
            # Reached end of available results on Amazon
            break

        for p in products:
            price = p.get("current_price") if p.get("current_price") is not None else p.get("price")
            if price is not None and price < min_price:
                continue
            if is_device_node and p.get("is_accessory"):
                continue
            asin = p.get("asin")
            if asin and asin not in seen_asins:
                seen_asins.add(asin)
                all_products.append(p)

        # Early exit if we have already accumulated target limit of deals
        if len(all_products) >= config.TOP_DEALS_LIMIT:
            break

    if not any_success:
        return {
            "category": category_name,
            "node": node,
            "products": [],
            "total_results": 0,
            "cached": False,
            "error": "Failed to fetch results from Amazon. Please try again later.",
        }

    # Recompute is_true_deal statistically across the entire category sample
    valid_discounts = [
        p.get("effective_discount_pct") or p.get("discount_pct")
        for p in all_products
        if (p.get("effective_discount_pct") or p.get("discount_pct")) is not None
    ]
    category_median_discount = statistics.median(valid_discounts) if valid_discounts else 0

    for p in all_products:
        d = p.get("effective_discount_pct") if p.get("effective_discount_pct") is not None else p.get("discount_pct")
        min_threshold = max(50, min_true_deal_pct) if p.get("is_refurbished") else min_true_deal_pct
        if d is not None and d >= min_threshold and d >= category_median_discount + 8:
            p["is_true_deal"] = True
        else:
            p["is_true_deal"] = False
        p["deal_score"] = compute_deal_score(p)

    # ── Strict Category Batch: Cross-Market Flipkart Verification ──
    # Prioritize candidate deals (is_true_deal) PLUS top category products to ensure
    # users see Flipkart price parity / deal verdicts across top cards.
    candidate_deals = [p for p in all_products if p.get("is_true_deal")]
    target_prods = list(candidate_deals[:6])
    for p in all_products[:3]:
        if p not in target_prods and len(target_prods) < 8:
            target_prods.append(p)

    if target_prods:
        session = await _get_session()
        fk_semaphore = asyncio.Semaphore(5)

        async def _verify_one(prod):
            async with fk_semaphore:
                try:
                    fk_res = await verify_product_against_flipkart(prod, session, cache)
                    prod["cross_market"] = fk_res
                    verdict = fk_res.get("verdict")
                    fk_savings = fk_res.get("flipkart_savings", 0.0)
                    diff_pct = fk_res.get("diff_pct", 0.0)

                    if verdict == "market_parity":
                        prod["is_true_deal"] = False
                        prod["deal_score"] = max(0, prod["deal_score"] - 15)
                    elif verdict == "cheaper_on_flipkart":
                        prod["is_true_deal"] = False
                        if diff_pct >= 20.0 or fk_savings >= 2000.0:
                            prod["deal_score"] = min(12, max(0, round(prod["deal_score"] * 0.15)))
                        else:
                            prod["deal_score"] = max(0, prod["deal_score"] - 25)
                    elif verdict == "true_deal":
                        prod["is_true_deal"] = True
                        prod["deal_score"] = min(100, prod["deal_score"] + 10)
                except Exception as e:
                    logger.warning("Error verifying product %s on Flipkart: %s", prod.get("asin"), e)

        # Batch verify target products (limit to 20 to keep latency tight)
        await asyncio.gather(*[_verify_one(p) for p in target_prods])

    if sort_by == "deal_score":
        all_products.sort(key=lambda p: p["deal_score"], reverse=True)
    elif sort_by == "discount":
        all_products.sort(key=lambda p: p.get("discount_pct") or 0, reverse=True)
    elif sort_by == "reviews":
        all_products.sort(key=lambda p: p.get("review_count") or 0, reverse=True)
    # When sort_by == "popularity", keep Amazon's scraped order (already bestseller popularity ranked)

    top_products = all_products[: config.TOP_DEALS_LIMIT]

    result = {
        "category": category_name,
        "node": node,
        "products": top_products,
        "total_results": len(top_products),
        "cached": False,
    }

    # Store in cache only when non-empty to avoid caching transient bot-checks/errors
    if top_products:
        await cache.set(cache_key, result)

    return result


# ─── HTTP fetch with retry ───────────────────────────────────────────


async def _fetch_with_retry(url: str) -> str | None:
    """Fetch a URL using curl_cffi with Chrome TLS impersonation.

    Concurrency is serialized via _scrape_semaphore — only one request
    to Amazon at a time.  Retries with exponential backoff and detects
    CAPTCHA pages.

    Args:
        url: The full Amazon URL to fetch.

    Returns:
        HTML string on success, None on failure after all retries.
    """
    global _session
    async with _scrape_semaphore:
        session = await _get_session()

        for attempt in range(config.MAX_RETRIES):
            headers = get_stealth_headers()
            try:
                response = await session.get(url, headers=headers)
                response.raise_for_status()

                # Check for CAPTCHA page
                text = response.text
                lower_text = text.lower()
                is_captcha = (
                    ("captcha" in lower_text and "type the characters you see" in lower_text)
                    or "/errors/validatecaptcha" in lower_text
                    or "<title>robot check</title>" in lower_text
                    or ("robot check" in lower_text and "amazon" in lower_text)
                    or "enter the characters you see below" in lower_text
                    or "bm-verify=" in lower_text
                )
                if is_captcha:
                    logger.warning(
                        "Bot challenge / CAPTCHA detected on attempt %d/%d",
                        attempt + 1,
                        config.MAX_RETRIES,
                    )
                    # Reset session so retry gets a fresh connection & cookie state
                    if _session is not None:
                        try:
                            await _session.close()
                        except Exception:
                            pass
                        _session = None
                    if attempt < config.MAX_RETRIES - 1:
                        wait = config.BACKOFF_BASE ** (attempt + 1)
                        await asyncio.sleep(wait)
                        session = await _get_session()
                        continue
                    return None

                return text

            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Request failed on attempt %d/%d: %s",
                    attempt + 1,
                    config.MAX_RETRIES,
                    str(e),
                )
                # Reset dead/stalled connection session so retry gets a fresh TLS state
                if _session is not None:
                    try:
                        await _session.close()
                    except Exception:
                        pass
                    _session = None
                if attempt < config.MAX_RETRIES - 1:
                    wait = config.BACKOFF_BASE ** (attempt + 1)
                    await asyncio.sleep(wait)
                    session = await _get_session()
                else:
                    return None

    return None


# ─── Search deals (single page) ──────────────────────────────────────


async def search_deals(
    query: str,
    min_discount: int,
    max_discount: int,
    page: int,
    cache: SearchCache,
    sort_by: str = "bestsellers",
) -> dict:
    """Search for deals on Amazon.in with caching.

    Args:
        query: Search term.
        min_discount: Minimum discount percentage.
        max_discount: Maximum discount percentage.
        page: Page number.
        cache: SearchCache instance.
        sort_by: Sort mode ('bestsellers', 'popularity', 'reviews', 'featured').

    Returns:
        Dict with keys: query, page, products, total_results, cached.
    """
    cache_key = make_cache_key(query, min_discount, max_discount, page, sort_by=sort_by)

    # Check cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    # Throttle: random delay before hitting Amazon
    delay = random.uniform(config.THROTTLE_MIN, config.THROTTLE_MAX)
    await asyncio.sleep(delay)

    # Fetch from Amazon
    url = build_search_url(query, min_discount, max_discount, page, sort_by=sort_by)
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

    for p in products:
        p["deal_score"] = compute_deal_score(p)

    # Cross-Market Flipkart Verification on top search results
    if products:
        session = await _get_session()
        fk_semaphore = asyncio.Semaphore(5)

        async def _verify_one_search(prod):
            async with fk_semaphore:
                try:
                    fk_res = await verify_product_against_flipkart(prod, session, cache)
                    prod["cross_market"] = fk_res
                    verdict = fk_res.get("verdict")
                    fk_savings = fk_res.get("flipkart_savings", 0.0)
                    diff_pct = fk_res.get("diff_pct", 0.0)

                    if verdict == "market_parity":
                        prod["deal_score"] = max(0, prod["deal_score"] - 15)
                    elif verdict == "cheaper_on_flipkart":
                        if diff_pct >= 20.0 or fk_savings >= 2000.0:
                            prod["deal_score"] = min(12, max(0, round(prod["deal_score"] * 0.15)))
                        else:
                            prod["deal_score"] = max(0, prod["deal_score"] - 25)
                    elif verdict == "true_deal":
                        prod["deal_score"] = min(100, prod["deal_score"] + 10)
                except Exception as e:
                    logger.warning("Error verifying search product %s on Flipkart: %s", prod.get("asin"), e)

        await asyncio.gather(*[_verify_one_search(p) for p in products[:5]])

    result = {
        "query": query,
        "page": page,
        "products": products,
        "total_results": len(products),
        "cached": False,
    }

    # Store in cache only when non-empty to avoid caching transient bot-checks/errors
    if products:
        await cache.set(cache_key, result)

    return result
