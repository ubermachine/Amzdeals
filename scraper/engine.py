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
import re
import statistics
from urllib.parse import urlencode

from curl_cffi import requests

import config
from cache.sqlite_cache import SearchCache, make_cache_key, make_category_cache_key
from scraper.flipkart import verify_product_against_flipkart
from scraper.parser import parse_search_results, is_accessory_title
from scraper.stealth import get_stealth_headers

logger = logging.getLogger(__name__)

# ─── Concurrency guard ───────────────────────────────────────────────
# Only one HTTP request to Amazon at a time, regardless of concurrent API users.
_scrape_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SCRAPES)

# ─── Reusable HTTPS session ──────────────────────────────────────────
# Persistent across requests for cookie jar continuity and TLS session reuse.
_session: requests.AsyncSession | None = None
_session_lock = asyncio.Lock()


_fk_session: requests.AsyncSession | None = None
_fk_session_lock = asyncio.Lock()


async def _get_flipkart_session() -> requests.AsyncSession:
    """Dedicated curl_cffi session for Flipkart with HTTP/2 multiplexing & connection pooling."""
    global _fk_session
    if _fk_session is None:
        async with _fk_session_lock:
            if _fk_session is None:
                from curl_cffi.curl import CurlOpt
                _fk_session = requests.AsyncSession(
                    impersonate="chrome",
                    timeout=5.0,
                    curl_options={
                        CurlOpt.PIPEWAIT: 1,
                        CurlOpt.DNS_CACHE_TIMEOUT: 3600,
                        CurlOpt.TCP_NODELAY: 1,
                    },
                )
    return _fk_session

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


# ─── 5-Stage Curated Ranking Pipeline & Entity Disambiguation ──────────


def extract_brand(title: str | None) -> str:
    """Extract brand name from product title.

    Amazon titles almost universally place the brand at the beginning.
    Strips noise prefixes like '(Renewed)' or 'Refurbished' before extracting.
    """
    if not title:
        return "Unknown"
    cleaned = title.strip()
    for prefix in ["(Renewed)", "(Refurbished)", "Renewed", "Refurbished", "Pre-Owned"]:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()

    known_multi = [
        "fire-boltt", "fire boltt", "noise colorfit", "red tape", "apple watch",
        "morphy richards", "eureka forbes", "havells", "crompton greaves"
    ]
    lower_c = cleaned.lower()
    for b in known_multi:
        if lower_c.startswith(b):
            return b.title()

    tokens = re.split(r"[\s\-_,]+", cleaned)
    return tokens[0].capitalize() if tokens else "Unknown"


def extract_model_family(title: str | None) -> str:
    """Extract normalized model family string to deduplicate chassis/variants.

    Groups variants of the same product (e.g. 8GB vs 16GB, color options)
    so only the best-scoring deal per model family is presented.
    """
    if not title:
        return ""
    cleaned = re.sub(r"\(.*?\)|\[.*?\]", "", title.lower())
    noise = {
        "renewed", "refurbished", "pre-owned", "deal", "laptop", "smartphone",
        "phone", "with", "and", "for", "black", "blue", "silver", "grey", "white"
    }
    tokens = [t for t in re.split(r"[^a-z0-9]+", cleaned) if t and t not in noise]
    spec_patterns = [
        r"^\d+gb$", r"^\d+tb$", r"^\d+l$", r"^\d+w$", r"^\d+hz$",
        r"^i[3579]$", r"^r[3579]$", r"^ddr\d$", r"^ssd$", r"^ram$",
        r"^fhd$", r"^uhd$", r"^\d+inch$", r"^\d+cm$"
    ]
    meaningful = [t for t in tokens if not any(re.match(p, t) for p in spec_patterns)]
    return " ".join(meaningful[:3]) if meaningful else title[:20].lower().strip()


def is_query_entity_match(title: str | None, query: str | None) -> bool:
    """Check if product title matches user query entity and filter intruders.

    Rejects known cross-category intruders:
    - microwave: drops OTGs, toaster ovens, air fryers (unless microwave is explicit)
    - laptop/notebook: drops desktop towers, all-in-one PCs, barebones, docking stations
    - headphones/earbuds: drops standalone microphones, speakers, audio interfaces, soundbars
    - mobile/smartphone/phone: drops tablets, iPads, smartwatches, gimbals, power banks
    - tv/television: drops projectors, wall mount brackets, streaming sticks
    """
    if not query or not title:
        return True

    q_lower = query.lower().strip()
    t_lower = title.lower()

    # 1. Query: Microwave
    if "microwave" in q_lower:
        if "microwave" not in t_lower and "micro wave" not in t_lower:
            return False
        if any(intruder in t_lower for intruder in ["otg", "oven toaster griller", "toaster oven"]):
            if "microwave" not in t_lower:
                return False

    # 2. Query: Laptop / Notebook
    elif any(k in q_lower for k in ["laptop", "notebook", "macbook"]):
        if any(intruder in t_lower for intruder in ["desktop pc", "all-in-one pc", "tower pc", "barebone", "docking station", "motherboard"]):
            return False

    # 3. Query: Headphones / Earbuds (checked before phone to avoid 'phone' in 'headphone' collision)
    elif any(k in q_lower for k in ["headphone", "earphone", "earbud", "tws", "airpod"]):
        if any(intruder in t_lower for intruder in ["microphone", "soundbar", "home theater", "audio interface"]):
            if not any(valid in t_lower for valid in ["headphone", "earphone", "earbud", "tws"]):
                return False

    # 4. Query: Mobile / Smartphone / Phone
    elif any(k in q_lower for k in ["smartphone", "mobile", "iphone"]) or ("phone" in q_lower and "headphone" not in q_lower and "earphone" not in q_lower):
        if any(intruder in t_lower for intruder in ["tablet", "ipad", "smartwatch", "smart watch", "gimbal", "tripod mount", "power bank", "selfie stick"]):
            return False

    # 5. Query: TV / Television
    elif any(k in q_lower for k in ["tv", "television", "smart tv"]):
        if any(intruder in t_lower for intruder in ["projector", "wall mount bracket", "tv stick", "streaming stick"]):
            return False

    return True


def get_query_price_floor(query: str | None) -> float:
    """Determine minimum price floor based on search query keywords."""
    if not query:
        return 0.0
    q = query.lower()
    if any(k in q for k in ["laptop", "notebook", "macbook"]):
        return 12000.0
    if any(k in q for k in ["headphone", "earphone", "earbuds", "headset"]):
        return 499.0
    if any(k in q for k in ["smartphone", "iphone", "mobile phone", "mobile", "cellphone"]) or ("phone" in q and "headphone" not in q and "earphone" not in q):
        return 4500.0
    if "microwave" in q:
        return 3500.0
    if any(k in q for k in ["tablet", "ipad"]):
        return 4000.0
    if any(k in q for k in ["tv", "television", "smart tv"]):
        return 4500.0
    if "monitor" in q:
        return 3500.0
    if any(k in q for k in ["refrigerator", "fridge"]):
        return 6000.0
    if "washing machine" in q:
        return 6000.0
    if any(k in q for k in ["ac", "air conditioner"]):
        return 15000.0
    if any(k in q for k in ["smartwatch", "smart watch"]):
        return 999.0
    return 0.0


def filter_and_curate_deals(
    products: list[dict],
    limit: int = config.TOP_DEALS_LIMIT,
    query: str | None = None,
    node: str | None = None,
    sort_by: str = "popularity",
) -> list[dict]:
    """Execute the 5-Stage Filtration & Curation Funnel to yield elite deals.

    Stage 1: Semantic & Entity Gating (accessory exclusion, query entity match, price floors)
    Stage 2: Fraud & Dropshipper Filter (unreviewed non-Prime drop, rating floor)
    Stage 3: MDQS v3.0 Multi-Utility Scoring
    Stage 4: Cross-Market Flipkart Arbitrage Gating
    Stage 5: Anti-Cannibalization & Diversity Guard (model family dedup, brand saturation cap, quality floor)
    """
    if not products:
        return []

    # Stage 1: Semantic & Entity Gating
    cat_meta = getattr(config, "CATEGORY_METADATA", {}).get(node, {}) if node else {}
    min_price_cat = cat_meta.get("min_price", 0.0)
    min_price_query = get_query_price_floor(query)
    effective_min_price = max(min_price_cat, min_price_query)
    is_device_node = (
        node in getattr(config, "DEVICE_NODES_FOR_ACCESSORY_FILTER", set())
        if node
        else bool(query and effective_min_price >= 2000)
    )

    stage1_passed = []
    for p in products:
        title = p.get("title", "")
        price = p.get("current_price") if p.get("current_price") is not None else p.get("price")

        # Price floor gating
        if price is not None and price < effective_min_price:
            continue

        # Accessory gating
        if (is_device_node or p.get("is_accessory")) and is_accessory_title(title):
            continue

        # Query entity disambiguation (e.g. microwave vs OTG)
        if query and not is_query_entity_match(title, query):
            continue

        stage1_passed.append(p)

    # Stage 2: Fraud & Dropshipper Filter
    stage2_passed = []
    for p in stage1_passed:
        reviews = p.get("review_count") or 0
        is_prime = p.get("is_prime", False)
        rating = p.get("rating")

        # Discard zero-reputation dropshippers
        if not is_prime and reviews < 10:
            continue
        # Discard severely bad rated products (sub-2.8 with reviews)
        if rating is not None and rating < 2.8 and reviews >= 10:
            continue

        stage2_passed.append(p)

    working_pool = stage2_passed if len(stage2_passed) >= 4 else stage1_passed
    if not working_pool:
        working_pool = products

    # Determine sorting order
    if sort_by == "deal_score":
        working_pool.sort(key=lambda x: x.get("deal_score", 0), reverse=True)
    elif sort_by == "discount":
        working_pool.sort(key=lambda x: x.get("discount_pct") or 0, reverse=True)
    elif sort_by == "reviews":
        working_pool.sort(key=lambda x: x.get("review_count") or 0, reverse=True)
    # When sort_by in ("popularity", "bestsellers"), keep Amazon's scraped order

    # Stage 5: Diversity & Anti-Cannibalization Guard
    # First, deduplicate variants within the same model family, retaining the highest scoring deal
    best_per_family = {}
    family_order = []
    for p in working_pool:
        mf = extract_model_family(p.get("title", ""))
        key = mf if mf else (p.get("asin") or id(p))
        if key not in best_per_family:
            best_per_family[key] = p
            family_order.append(key)
        else:
            existing = best_per_family[key]
            p_metric = (p.get("deal_score", 0), p.get("discount_pct") or 0)
            ex_metric = (existing.get("deal_score", 0), existing.get("discount_pct") or 0)
            if p_metric > ex_metric:
                best_per_family[key] = p

    deduped_pool = [best_per_family[k] for k in family_order]

    curated = []
    brand_counts = {}
    generic_brands = {"unknown", "product", "item", "generic"}
    max_per_brand = getattr(config, "BRAND_DIVERSITY_MAX_PER_BRAND", 2)
    score_floor = getattr(config, "MIN_DEAL_SCORE_FLOOR", 60.0)

    # Pass 1: Products meeting the quality score floor
    overflow_candidates = []
    for p in deduped_pool:
        title = p.get("title", "")
        brand = extract_brand(title)
        score = p.get("deal_score", 0)

        # Skip saturated brand (unless generic/unidentified)
        if brand.lower() not in generic_brands and brand_counts.get(brand, 0) >= max_per_brand:
            continue

        if score >= score_floor or p.get("is_true_deal"):
            if brand.lower() not in generic_brands:
                brand_counts[brand] = brand_counts.get(brand, 0) + 1
            curated.append(p)
            if len(curated) >= limit:
                break
        else:
            overflow_candidates.append((p, brand))

    # Pass 2: If fewer than 6 deals made the strict floor, allow top overflow candidates
    if len(curated) < min(6, limit):
        for p, brand in overflow_candidates:
            if brand.lower() not in generic_brands and brand_counts.get(brand, 0) >= max_per_brand:
                continue
            if brand.lower() not in generic_brands:
                brand_counts[brand] = brand_counts.get(brand, 0) + 1
            curated.append(p)
            if len(curated) >= limit:
                break

    return curated[:limit]


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
        if len(cached.get("products", [])) > config.TOP_DEALS_LIMIT:
            cached["products"] = cached["products"][: config.TOP_DEALS_LIMIT]
            cached["total_results"] = len(cached["products"])
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
        products = parse_search_results(html, category_name)
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
    for p in all_products[:4]:
        if p not in target_prods and len(target_prods) < config.TOP_DEALS_LIMIT:
            target_prods.append(p)

    if target_prods:
        session = await _get_flipkart_session()
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

        # Batch verify target products
        await asyncio.gather(*[_verify_one(p) for p in target_prods])

    # Apply 5-Stage Curated Ranking Pipeline (dedup model families, brand saturation cap, score floor)
    top_products = filter_and_curate_deals(
        all_products,
        limit=config.TOP_DEALS_LIMIT,
        node=node,
        sort_by=sort_by,
    )

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
        if len(cached.get("products", [])) > config.TOP_DEALS_LIMIT:
            cached["products"] = cached["products"][: config.TOP_DEALS_LIMIT]
            cached["total_results"] = len(cached["products"])
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
    products = parse_search_results(html, query)

    for p in products:
        d = p.get("effective_discount_pct") or p.get("discount_pct") or 0
        p["is_true_deal"] = d >= 35
        p["deal_score"] = compute_deal_score(p)

    # Cross-Market Flipkart Verification on top candidates
    target_prods = products[: config.TOP_DEALS_LIMIT]
    if target_prods:
        session = await _get_flipkart_session()
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
                    logger.warning("Error verifying search product %s on Flipkart: %s", prod.get("asin"), e)

        await asyncio.gather(*[_verify_one_search(p) for p in target_prods])

    # Apply 5-Stage Curated Ranking Pipeline (dedup model families, brand saturation cap, score floor)
    top_products = filter_and_curate_deals(
        products,
        limit=config.TOP_DEALS_LIMIT,
        query=query,
        sort_by=sort_by,
    )

    result = {
        "query": query,
        "page": page,
        "products": top_products,
        "total_results": len(top_products),
        "cached": False,
    }

    # Store in cache only when non-empty to avoid caching transient bot-checks/errors
    if top_products:
        await cache.set(cache_key, result)

    return result
