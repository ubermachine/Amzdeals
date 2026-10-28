"""Flipkart cross-market scraper and 5-layer product disambiguation engine.

Provides high-confidence entity matching and +/-5% market parity verification
to determine whether an Amazon discount is a genuine market deal.
"""

import asyncio
import json
import logging
import re
import urllib.parse
from curl_cffi import requests

import config
from cache.sqlite_cache import SearchCache, make_flipkart_cache_key
from scraper.stealth import get_stealth_headers

logger = logging.getLogger(__name__)

# Known brand prefixes for accurate title tokenization
KNOWN_BRANDS = [
    "asus", "acer", "hp", "dell", "lenovo", "apple", "samsung", "realme", "xiaomi",
    "redmi", "boat", "noise", "boult", "sony", "jbl", "philips", "puma", "nike",
    "adidas", "titan", "fastrack", "casio", "safari", "american tourister", "skybags",
    "wildcraft", "oneplus", "oppo", "vivo", "motorola", "moto", "infinix", "lg",
    "whirlpool", "bajaj", "prestige", "pigeon", "havells", "crompton", "zebronics",
    "sandisk", "crucial", "western digital", "wd", "seagate", "kingston", "sol de janeiro"
]

# Fluff phrases to strip from Amazon titles
FLUFF_PATTERNS = [
    r"\(202[0-9]\)", r"Smartchoice", r"with offer", r"Deal of the day",
    r"Limited time deal", r"Made in India", r"Special Edition",
    r"\(Black\)", r"\(Blue\)", r"\(Silver\)", r"\(Grey\)", r"\(Pure Grey\)",
    r"[0-9]+(\.[0-9]+)?\s*Kg", r"[0-9]+(\.[0-9]+)?\s*cm", r"FHD", r"WUXGA",
    r"Win 11", r"Office 24", r"M365.*", r"BL Keyboard", r"Thin & Light Laptop",
    r"Gaming Laptop", r"Laptop", r"Earbuds", r"Headphones"
]


def extract_product_signature(title: str) -> dict:
    """Extract brand, alphanumeric model numbers, specs, and search query from title."""
    clean_text = title
    for p in FLUFF_PATTERNS:
        clean_text = re.sub(p, " ", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    title_lower = title.lower()

    # 1. Brand Detection
    brand = ""
    for b in KNOWN_BRANDS:
        if title_lower.startswith(b) or f" {b} " in f" {title_lower} ":
            brand = b
            break
    if not brand:
        words = title.split()
        brand = words[0].lower() if words else ""

    # 2. Model / Part Number Extraction
    model_patterns = re.findall(
        r"\b([A-Z0-9]{2,}-[A-Z0-9]{2,}|\b[A-Z]{1,3}[0-9]{3,}[A-Z0-9]*\b|\b[0-9]{3,4}\b)",
        title
    )
    # Ignore standalone common years or generic round numbers
    excluded_numbers = {"2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027", "1000", "5000"}
    models = []
    for m in model_patterns:
        if m not in excluded_numbers:
            models.append(m.upper())
            # Include base prefix before hyphen (e.g. FA506NCG from FA506NCG-HN192WS)
            if "-" in m:
                base = m.split("-")[0].strip().upper()
                if len(base) >= 3 and base not in models:
                    models.append(base)

    # 3. Spec Extraction (RAM, Storage, Volume)
    raw_specs = re.findall(r"\b([0-9]+(?:\.[0-9]+)?\s*(?:GB|TB|MB|L|ml))\b", title, flags=re.IGNORECASE)
    specs = {s.upper().replace(" ", "") for s in raw_specs}

    # 4. Formulate targeted search query for Flipkart
    query_parts = [brand]
    for m in models:
        if not m.isdigit():  # Prioritize alphanumeric models like FA506NCG, HD9200
            query_parts.append(m)
            break
    if len(query_parts) == 1 and models:
        query_parts.append(models[0])

    # If no model found, take first 3 clean words
    if len(query_parts) == 1:
        query_parts.extend(clean_text.split()[:3])

    search_query = " ".join(dict.fromkeys(query_parts))

    return {
        "brand": brand,
        "models": models,
        "specs": specs,
        "search_query": search_query,
        "raw_title": title,
    }


def parse_flipkart_html(html: str) -> list[dict]:
    """Parse candidate products from Flipkart's window.__INITIAL_STATE__ payload."""
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*<\/script>", html, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except Exception as e:
        logger.warning("Failed to parse Flipkart JSON payload: %s", e)
        return []

    page_data = data.get("pageDataV4", {}).get("page", {}).get("data", {})
    found_nodes = []

    def _traverse(obj):
        if isinstance(obj, dict):
            if "productInfo" in obj and isinstance(obj["productInfo"], dict):
                found_nodes.append(obj)
            for v in obj.values():
                _traverse(v)
        elif isinstance(obj, list):
            for item in obj:
                _traverse(item)

    _traverse(page_data)

    candidates = []
    for node in found_nodes:
        info = node["productInfo"].get("value", {})
        title = info.get("titles", {}).get("title")
        pricing = info.get("pricing", {})
        prices = pricing.get("prices", [])

        cur_price = next((p["value"] for p in prices if not p.get("strikeOff")), None)
        mrp = next((p["value"] for p in prices if p.get("strikeOff")), None)
        rating = info.get("rating", {}).get("average")
        base_url = info.get("baseUrl")
        url = f"https://www.flipkart.com{base_url}" if base_url else None

        if title and cur_price:
            candidates.append({
                "title": title,
                "price": float(cur_price),
                "mrp": float(mrp) if mrp else None,
                "rating": float(rating) if rating else None,
                "url": url,
            })

    return candidates


def has_chipset_or_series_conflict(amz_title: str, fk_title: str) -> bool:
    """Detect architectural, chipset, or model-family conflicts (e.g. Intel vs AMD, V15 vs LOQ)."""
    amz_lower = amz_title.lower()
    fk_lower = fk_title.lower()

    # 1. CPU Brand Conflict (Intel vs AMD)
    has_amz_intel = "intel" in amz_lower or bool(re.search(r"\b(i3|i5|i7|i9|celeron|pentium|core ultra)\b", amz_lower))
    has_amz_amd = "amd" in amz_lower or "ryzen" in amz_lower
    has_fk_intel = "intel" in fk_lower or bool(re.search(r"\b(i3|i5|i7|i9|celeron|pentium|core ultra)\b", fk_lower))
    has_fk_amd = "amd" in fk_lower or "ryzen" in fk_lower

    if has_amz_intel and not has_amz_amd and has_fk_amd and not has_fk_intel:
        return True
    if has_amz_amd and not has_amz_intel and has_fk_intel and not has_fk_amd:
        return True

    # 2. CPU Tier Conflict (i3 vs i5 vs i7 vs i9)
    tiers = ["i3", "i5", "i7", "i9", "ryzen 3", "ryzen 5", "ryzen 7", "ryzen 9"]
    for tier in tiers:
        if bool(re.search(rf"\b{tier}\b", amz_lower)) and not bool(re.search(rf"\b{tier}\b", fk_lower)):
            for other in tiers:
                if other != tier and bool(re.search(rf"\b{other}\b", fk_lower)):
                    return True

    # 3. Known series conflicts
    series_list = [
        "loq", "legion", "ideapad", "thinkpad", "thinkbook", "v15", "v14",
        "tuf", "rog", "zenbook", "vivobook",
        "victus", "pavilion", "omen", "envy", "spectre",
        "aspire", "swift", "predator", "nitro",
    ]
    for s in series_list:
        if bool(re.search(rf"\b{s}\b", amz_lower)) and not bool(re.search(rf"\b{s}\b", fk_lower)):
            for other_s in series_list:
                if other_s != s and bool(re.search(rf"\b{other_s}\b", fk_lower)):
                    return True

    return False


def score_flipkart_match(amazon_sig: dict, amazon_price: float, candidate: dict) -> float:
    """Compute 0–100 match confidence score between Amazon item and Flipkart candidate.

    Strict rules:
    - Must be within realistic price corridor (0.50x to 1.85x) or rejected (0.0).
    - Brand must match or rejected (0.0).
    - No chipset or model-family conflicts (e.g. Intel vs AMD, LOQ vs V15).
    - Base score: 30 pts.
    - Model/MPN match: +40 pts.
    - Spec match (RAM/Storage/Capacity): +20 pts on match, -25 pts penalty on conflict.
    - Token Jaccard overlap: up to 15 pts.
    """
    fk_title = candidate["title"].lower()
    fk_price = candidate.get("price")

    # 1. Price corridor sanity check (realistic market corridor: 0.50x to 1.85x)
    if amazon_price and fk_price:
        ratio = fk_price / amazon_price
        if ratio < 0.50 or ratio > 1.85:
            return 0.0

    # 2. Strict Brand Match
    brand = amazon_sig.get("brand", "").lower()
    if not brand or brand not in fk_title:
        return 0.0

    # 3. Conflict Check (Intel vs AMD, LOQ vs V15, etc.)
    if has_chipset_or_series_conflict(amazon_sig.get("raw_title", ""), candidate["title"]):
        return 0.0

    score = 30.0

    # 3. Model number match
    for m in amazon_sig.get("models", []):
        m_lower = m.lower()
        base_model = m_lower.split("-")[0]
        if (len(m_lower) >= 3 and m_lower in fk_title) or (len(base_model) >= 3 and base_model in fk_title):
            score += 40.0
            break

    # 4. Spec match
    raw_fk_specs = re.findall(r"\b([0-9]+(?:\.[0-9]+)?\s*(?:GB|TB|MB|L|ml))\b", candidate["title"], flags=re.IGNORECASE)
    fk_specs = {s.upper().replace(" ", "") for s in raw_fk_specs}

    amz_specs = amazon_sig.get("specs", set())
    if amz_specs and fk_specs:
        overlap = amz_specs.intersection(fk_specs)
        diff = amz_specs.symmetric_difference(fk_specs)
        if overlap:
            score += 20.0
        if diff and not overlap:
            score -= 25.0

    # 5. Token Jaccard Overlap
    amz_tokens = set(re.findall(r"[a-z0-9]+", amazon_sig.get("raw_title", "").lower()))
    fk_tokens = set(re.findall(r"[a-z0-9]+", fk_title))
    if amz_tokens:
        jaccard = len(amz_tokens.intersection(fk_tokens)) / len(amz_tokens.union(fk_tokens))
        score += jaccard * 15.0

    return min(max(0.0, score), 100.0)


def classify_cross_market_verdict(amazon_price: float, flipkart_price: float) -> dict:
    """Classify the price difference under the +/-5% market parity rule."""
    if not flipkart_price or flipkart_price <= 0:
        return {"verdict": "unverified", "is_deal": False}

    diff = amazon_price - flipkart_price
    diff_pct = diff / flipkart_price

    if abs(diff_pct) < 0.05:
        # Market Parity: Prices match within +/- 5%. NOT a deal!
        return {
            "verdict": "market_parity",
            "is_deal": False,
            "price_diff": round(diff, 2),
            "diff_pct": round(diff_pct * 100, 1),
        }
    elif diff_pct <= -0.05:
        # Amazon is >= 5% cheaper than Flipkart -> Genuine True Deal!
        return {
            "verdict": "true_deal",
            "is_deal": True,
            "price_diff": round(abs(diff), 2),
            "diff_pct": round(abs(diff_pct) * 100, 1),
        }
    else:
        # Flipkart is >= 5% cheaper than Amazon -> Fake Deal / Marked up!
        return {
            "verdict": "cheaper_on_flipkart",
            "is_deal": False,
            "flipkart_savings": round(diff, 2),
            "diff_pct": round(diff_pct * 100, 1),
        }


async def fetch_flipkart_candidates(query: str, session: requests.AsyncSession) -> list[dict]:
    """Fetch search results from Flipkart using Chrome TLS impersonation."""
    url = f"https://www.flipkart.com/search?q={urllib.parse.quote(query)}"
    headers = get_stealth_headers()

    try:
        resp = await session.get(url, headers=headers)
        if resp.status_code == 200:
            return parse_flipkart_html(resp.text)
        else:
            logger.warning("Flipkart search returned HTTP %d for query %s", resp.status_code, query)
            return []
    except Exception as e:
        logger.warning("Error querying Flipkart for %s: %s", query, e)
        return []


async def verify_product_against_flipkart(
    amazon_product: dict,
    session: requests.AsyncSession,
    cache: SearchCache,
) -> dict:
    """Verify an Amazon product against Flipkart using entity disambiguation & +/-5% parity.

    Returns dict with keys:
        - match_found: bool
        - verdict: 'true_deal' | 'market_parity' | 'cheaper_on_flipkart' | 'unverified'
        - is_deal: bool
        - flipkart_price: float | None
        - flipkart_title: str | None
        - flipkart_url: str | None
        - match_confidence: float (0-100)
        - price_diff: float
        - diff_pct: float
    """
    asin = amazon_product.get("asin")
    title = amazon_product.get("title", "")
    amazon_price = amazon_product.get("current_price") or amazon_product.get("price")

    fallback_unverified = {
        "match_found": False,
        "verdict": "unverified",
        "is_deal": False,
        "flipkart_price": None,
        "flipkart_title": None,
        "flipkart_url": None,
        "match_confidence": 0.0,
        "price_diff": 0.0,
        "diff_pct": 0.0,
    }

    if not asin or not title or not amazon_price:
        return fallback_unverified

    cache_key = make_flipkart_cache_key(asin, title)

    # 1. Check persistent SQLite cache
    cached = await cache.get_flipkart(cache_key)
    if cached is not None:
        return cached

    # 2. Extract signature & query Flipkart
    sig = extract_product_signature(title)
    candidates = await fetch_flipkart_candidates(sig["search_query"], session)

    if not candidates:
        await cache.set_flipkart(cache_key, fallback_unverified)
        return fallback_unverified

    # 3. Score candidates with 5-layer disambiguation
    scored_candidates = []
    for c in candidates:
        score = score_flipkart_match(sig, amazon_price, c)
        if score >= 80.0:  # Strict confidence threshold
            scored_candidates.append((score, c))

    if not scored_candidates:
        await cache.set_flipkart(cache_key, fallback_unverified)
        return fallback_unverified

    # 4. Pick highest-scoring verified match
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_cand = scored_candidates[0]

    # 5. Classify against +/-5% market parity
    verdict_info = classify_cross_market_verdict(amazon_price, best_cand["price"])

    result = {
        "match_found": True,
        "verdict": verdict_info["verdict"],
        "is_deal": verdict_info["is_deal"],
        "flipkart_price": best_cand["price"],
        "flipkart_title": best_cand["title"],
        "flipkart_url": best_cand["url"],
        "flipkart_mrp": best_cand.get("mrp"),
        "match_confidence": round(best_score, 1),
        "price_diff": verdict_info.get("price_diff", 0.0),
        "diff_pct": verdict_info.get("diff_pct", 0.0),
    }

    await cache.set_flipkart(cache_key, result)
    return result

