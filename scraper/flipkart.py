"""Flipkart cross-market scraper and 5-layer product disambiguation engine.

Provides high-confidence entity matching and +/-5% market parity verification
to determine whether an Amazon discount is a genuine market deal.
"""

import asyncio
import json
import logging
import re
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests

import config
from cache.sqlite_cache import SearchCache, make_flipkart_cache_key
from scraper.stealth import get_stealth_headers

logger = logging.getLogger(__name__)

# Known brand prefixes for accurate title tokenization (ordered by length descending)
KNOWN_BRANDS = [
    "american tourister", "sol de janeiro", "western digital",
    "asus", "acer", "hp", "dell", "lenovo", "apple", "samsung", "realme", "xiaomi",
    "redmi", "boat", "noise", "boult", "sony", "jbl", "philips", "puma", "nike",
    "adidas", "titan", "fastrack", "casio", "safari", "skybags",
    "wildcraft", "oneplus", "oppo", "vivo", "motorola", "moto", "infinix", "lg",
    "whirlpool", "bajaj", "prestige", "pigeon", "havells", "crompton", "zebronics",
    "sandisk", "crucial", "wd", "seagate", "kingston"
]

# Recognizable model series for cross-market matching & query formulation
SERIES_PATTERNS = [
    r"ideapad slim \d+", r"ideapad \d+", r"ideapad", r"thinkbook \d+", r"thinkbook",
    r"thinkpad \w+", r"thinkpad", r"loq", r"legion \d+", r"legion",
    r"victus \d+", r"victus", r"pavilion \d+", r"pavilion", r"omen \d+", r"omen",
    r"tuf gaming", r"tuf", r"rog strix", r"rog zephyrus", r"rog", r"zenbook", r"vivobook",
    r"aspire \d+", r"aspire one", r"aspire", r"swift \d+", r"swift go", r"swift",
    r"predator helios", r"predator", r"nitro \d+", r"nitro v", r"nitro",
    r"galaxy s\d+(?: ultra| plus|\+)?", r"galaxy z (?:fold|flip)\d*", r"galaxy a\d+", r"galaxy m\d+",
    r"nord ce\d*(?: lite)?", r"nord \d+",
    r"narzo\s*\d+[a-z]*", r"redmi note\s*\d+[a-z]*", r"redmi\s*\d+[a-z]*",
    r"realme\s*\d+[a-z]*", r"poco\s*[xmf]\d+[a-z]*",
    r"moto g\d+[a-z]*", r"moto edge\s*\d+[a-z]*",
    r"iqoo\s*z\d+[a-z]*", r"iqoo\s*neo\s*\d+[a-z]*",
    r"airdopes \d+(?: pro| plus| max)?", r"rockerz \d+(?: pro| plus)?",
    r"wh-ch\d+[a-z]*", r"wf-c\d+[a-z]*", r"wh-\d+[a-z]*",
    r"chromebook \d+", r"chromebook",
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


GENERIC_EXCLUDED_TOKENS = {
    "IN-LINE", "TYPE-C", "ON-EAR", "OVER-EAR", "IN-EAR", "BUILT-IN",
    "ANTI-GLARE", "ALL-DAY", "HANDS-FREE", "NOISE-CANCELLATION", "NO-COST",
    "MICRO-EDGE", "FAST-CHARGE", "FAST-CHARGING", "DUAL-PAIRING", "DUAL-DEVICE",
    "DUAL-TONE", "TRULY-WIRELESS", "TOUCH-CONTROL", "NOISE-CANCELLING",
    "NOISE-ISOLATION", "NOISE-REDUCTION", "HI-RES", "BEE-RATED", "FHD", "WUXGA",
    "2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027", "1000", "5000", "1200",
    "128", "256", "512", "1024", "2048", "1TB", "2TB",
    "128GB", "256GB", "512GB", "1024GB", "2048GB",
    "4GB", "6GB", "8GB", "12GB", "16GB", "18GB", "24GB", "32GB", "36GB", "48GB", "64GB",
    "32G", "64G", "128G", "256G", "512G",
    "1080P", "1440P", "2160P", "144HZ", "120HZ", "165HZ", "240HZ", "60HZ",
    "40MM", "50MM", "10MM", "12MM", "13MM", "5G", "4G", "3G", "LTE",
}


def extract_audio_form_factor(title: str) -> str | None:
    """Extract audio form factor (over_ear, in_ear, or neckband) to prevent cross-type mismatches."""
    t = title.lower()
    if re.search(r"\b(over[\s\-]?ear|on[\s\-]?ear|headphone)\b", t):
        if not re.search(r"\b(earbud|earbuds|bud|buds|tws|neckband)\b", t):
            return "over_ear"
    if re.search(r"\b(neckband|collar)\b", t):
        return "neckband"
    if re.search(r"\b(earbud|earbuds|bud|buds|tws|in[\s\-]?ear|airpod|airdopes)\b", t):
        return "in_ear"
    return None


def extract_device_tier(title: str) -> str | None:
    """Extract mobile/device tier suffix (e.g. Pro+, Pro Max, Ultra, Pro, Plus, Lite)."""
    t = title.lower()
    if re.search(r"\b(?:pro\s*\+|pro\s*plus)(?=[^a-z0-9]|$)", t):
        return "pro_plus"
    if re.search(r"\bpro\s*max\b", t):
        return "pro_max"
    if re.search(r"\bultra\b", t):
        return "ultra"
    if re.search(r"\bpro\b", t):
        return "pro"
    if re.search(r"\bplus\b", t):
        return "plus"
    if re.search(r"\b(?:lite|fe|se)\b", t):
        return "lite"
    return None


def extract_cpu_model(title: str) -> str | None:
    """Extract specific CPU processor model code (e.g. 125H, 115U, 7320U, 7330U, 12450H, 13420H, 120U, 100U)."""
    t = title.lower()
    m = re.search(r"\b(?:ultra\s*[3579]\s+)?([12][0-9]{2}[huv])\b", t)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(?:core\s*[357]\s+)?([12][0-9]{2}u)\b", t)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(?:i[3579][\s\-]?)?(1[1-4][0-9]{3}[a-z]{1,2})\b", t)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(?:ryzen\s*[3579][\s\-]?)?([3578][0-9]{3}[a-z]{1,2})\b", t)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(n[14][0-9]{2,3}|n95|n200)\b", t)
    if m:
        return m.group(1).upper()
    return None


def extract_wattage(title: str) -> int | None:
    """Extract appliance power wattage (e.g. 500W, 750W, 1000W, 1200W, 2000W)."""
    t = title.lower()
    m = re.search(r"\b([4-9][0-9]{2}|1[0-9]{3}|2[0-9]{3})\s*(?:w|watt|watts)\b", t)
    if m:
        return int(m.group(1))
    return None


def extract_capacity_liters(title: str) -> float | None:
    """Extract appliance volume capacity in Litres (e.g. 1.2L, 1.5L, 1.8L, 3L, 4.5L, 5L, 6L)."""
    t = title.lower()
    m = re.search(r"\b([0-9](?:\.[0-9])?)\s*(?:l|ltr|litre|litres|liter|liters)\b", t)
    if m:
        return float(m.group(1))
    return None


def extract_device_model_numbers(title: str) -> set[str]:
    """Extract alphanumeric device model codes (e.g. 300C, 211, FA506, 720N)."""
    raw = re.findall(
        r"\b([A-Z0-9]{2,}-[A-Z0-9]{2,}|\b[A-Z]{1,3}[0-9]{2,}[A-Z0-9]*\b|\b[0-9]{1,4}[A-Z]{1,3}\b|\b[0-9]{3,4}\b)",
        title,
        flags=re.IGNORECASE,
    )
    res = set()
    for m in raw:
        m_up = m.upper().strip()
        if m_up not in GENERIC_EXCLUDED_TOKENS and len(m_up) >= 3:
            if not m_up.endswith("W") and not m_up.endswith("V") and not m_up.endswith("KG"):
                if not extract_cpu_model(m_up):
                    res.add(m_up)
    return res


def extract_gpu(title: str) -> str | None:
    """Extract normalized dedicated GPU model from title."""
    t = title.lower()
    # NVIDIA RTX (e.g. RTX 2050, 3050, 3050 Ti, 4050, 4060, 4070, 5050)
    m = re.search(r"\b(rtx\s*[2-5]0[5-9]0(?:\s*ti)?)\b", t)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    # NVIDIA GTX (e.g. GTX 1650, 1660, 1660 Ti, 1050, 1060)
    m = re.search(r"\b(gtx\s*(?:1650(?:\s*ti)?|1660(?:\s*ti)?|1050|1060))\b", t)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    # Intel Arc (e.g. Arc A350M, Arc A530M, Arc A550M)
    m = re.search(r"\b(arc\s*a[357][0-9]0m?)\b", t)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    # AMD Radeon RX dedicated (e.g. RX 6500M, RX 7600S)
    m = re.search(r"\b(rx\s*[6-7][0-9]00[a-z]*)\b", t)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    return None


def has_dedicated_gpu(title: str) -> bool:
    """Check if title explicitly specifies a dedicated gaming GPU."""
    t = title.lower()
    if extract_gpu(t):
        return True
    if re.search(r"\b(?:geforce|nvidia|dedicated graphics|[468]\s*gb graphics)\b", t):
        return True
    return False


def extract_ram_gb(title: str) -> int | None:
    """Extract system RAM capacity in GB without confusing with storage/screen."""
    t = title.lower()
    # Slash notation in laptops: (16GB/512GB, 16 GB / 512 GB, 16GB / 1TB, etc.)
    m = re.search(r"\b(4|6|8|12|16|18|24|32|36|48|64)\s*gb?\s*\/\s*(?:128|256|512|1tb|2tb)", t)
    if m:
        return int(m.group(1))
    # DDR / LPDDR / RAM / Unified Memory
    m = re.search(r"\b(4|6|8|12|16|18|24|32|36|48|64)\s*(?:gb)?\s*(?:ddr[45]x?|lpddr[45]x?|ram|unified memory)\b", t)
    if m:
        return int(m.group(1))
    # Flipkart title format: (16 GB/512 GB SSD/...)
    m = re.search(r"\(\s*(4|6|8|12|16|18|24|32|36|48|64)\s*gb\s*\/", t)
    if m:
        return int(m.group(1))
    # Mobile RAM: e.g. 8GB RAM, 8 GB RAM, 8GB+128GB
    m = re.search(r"\b(4|6|8|12|16)\s*gb\s*ram\b", t)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(4|6|8|12|16)\s*gb\s*\+\s*(?:64|128|256|512)\b", t)
    if m:
        return int(m.group(1))
    return None


def extract_storage_gb(title: str) -> int | None:
    """Extract primary SSD/storage capacity in GB."""
    t = title.lower()
    # 1TB or 2TB
    m = re.search(r"\b(1|2)\s*tb\b", t)
    if m:
        return int(m.group(1)) * 1024
    # Slash notation storage: e.g. /512GB or / 512 GB SSD
    m = re.search(r"\/\s*(128|256|512)\s*(?:gb)?", t)
    if m:
        return int(m.group(1))
    # Explicit SSD / ROM / Storage
    m = re.search(r"\b(128|256|512)\s*(?:gb)?\s*(?:ssd|hdd|emmc|rom|storage|nvme|ufs)\b", t)
    if m:
        return int(m.group(1))
    return None


def extract_screen_size(title: str) -> float | None:
    """Extract laptop or TV screen display size in inches."""
    t = title.lower()
    # Match inches (e.g. 14", 14.0", 15.6", 13.3", 16", 17.3", 11.6")
    m = re.search(r"\b(11\.6|12\.[24]|13\.3|14(?:\.0)?|15\.3|15\.6|16(?:\.0)?|17\.3)\s*(?:\"|\'\'|inch|\-inch|\s*in\b|\s*fhd|\s*ips|\s*oled|\s*display|\s*screen|\s*laptop)", t)
    if m:
        val = float(m.group(1))
        return 14.0 if val == 14 else (16.0 if val == 16 else val)
    # Series name class inference (e.g. Aspire 15 -> 15.6, Vivobook 14 -> 14.0, Vivobook 15 -> 15.6, Swift 14 -> 14.0)
    m = re.search(r"\b(?:vivobook|ideapad|aspire|swift|inspiron|tuf|victus|legion|zenbook|expertbook|latitude)\s*(14|15|16|17)\b", t)
    if m:
        num = int(m.group(1))
        if num == 14:
            return 14.0
        elif num == 15:
            return 15.6
        elif num == 16:
            return 16.0
        elif num == 17:
            return 17.3
    # TVs & Monitors
    m = re.search(r"\b(24|27|32|40|43|50|55|65|75|85)\s*(?:\"|\'\'|inch|\-inch|\s*in\b|\s*led|\s*tv|\s*smart|\s*monitor|\s*oled|\s*4k)", t)
    if m:
        return float(m.group(1))
    return None


def extract_cpu_gen(title: str) -> str | None:
    """Extract CPU architecture generation (e.g. 12th, 13th, Core Ultra, Ryzen 7000)."""
    t = title.lower()
    if "core ultra" in t:
        return "core_ultra"
    m = re.search(r"\b(1[1-4])th\s*gen\b", t)
    if m:
        return f"{m.group(1)}th"
    m = re.search(r"\b(1[1-4][0-9]{3}[a-z]*)\b", t)
    if m:
        return f"{m.group(1)[:2]}th"
    m = re.search(r"\bryzen\s*[3579]\s*([578][0-9]{3}[a-z]*)\b", t)
    if m:
        return f"ryzen_{m.group(1)[0]}000"
    return None


def extract_product_signature(title: str) -> dict:
    """Extract brand, series, alphanumeric model numbers, specs, and search query from title."""
    clean_text = title
    for p in FLUFF_PATTERNS:
        clean_text = re.sub(p, " ", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    title_lower = title.lower()

    # 1. Brand Detection (prioritize prefix, exclude false positives like 'noise cancellation')
    brand = ""
    for b in KNOWN_BRANDS:
        if title_lower.startswith(b + " ") or title_lower.startswith(b + ",") or title_lower.startswith(b + "-"):
            brand = b
            break

    if not brand:
        for b in KNOWN_BRANDS:
            if b == "noise":
                if re.search(r"\bnoise\s+(cancellation|cancelling|canceling|isolation|isolating|reduction)\b", title_lower):
                    continue
            if re.search(rf"\b{re.escape(b)}\b", title_lower):
                brand = b
                break

    if not brand:
        words = title.split()
        brand = words[0].lower() if words else ""

    # 2. Series Detection
    series = ""
    for pat in SERIES_PATTERNS:
        m = re.search(rf"\b({pat})\b", title_lower)
        if m:
            series = m.group(1).strip()
            break

    # 3. Model / Part Number / CPU Extraction
    model_patterns = re.findall(
        r"\b([A-Z0-9]{2,}-[A-Z0-9]{2,}|\b[A-Z]{1,3}[0-9]{3,}[A-Z0-9]*\b|\b[0-9]{4,5}[A-Z]{1,3}\b|\b[0-9]{2}[A-Z]{2,3}[0-9]{4}[A-Z]{2,3}\b|\b(?:i[3579]|ryzen [3579])[- ]?[0-9]{4,5}[A-Z]*\b|\b[0-9]{3,4}\b)",
        title,
        flags=re.IGNORECASE,
    )
    models = []
    if series:
        models.append(series.upper())

    for m in model_patterns:
        m_up = m.upper().strip()
        if m_up not in GENERIC_EXCLUDED_TOKENS and m_up not in models:
            models.append(m_up)
            if "-" in m_up:
                base = m_up.split("-")[0].strip()
                if len(base) >= 3 and base not in GENERIC_EXCLUDED_TOKENS and base not in models:
                    models.append(base)

    # 4. Spec Extraction (RAM, Storage, Volume)
    raw_specs = re.findall(r"\b([0-9]+(?:\.[0-9]+)?\s*(?:GB|TB|MB|L|ml))\b", title, flags=re.IGNORECASE)
    specs = {s.upper().replace(" ", "") for s in raw_specs}

    # Dedicated GPU and RAM extraction for query precision
    gpu = extract_gpu(title)
    ram = extract_ram_gb(title)

    # 5. Formulate targeted search query for Flipkart
    query_parts = []
    if brand:
        query_parts.append(brand)
    if series:
        query_parts.append(series)

    # Inject GPU (e.g. rtx 4050, rtx 3050) to target exact graphical tier
    if gpu:
        query_parts.append(gpu)

    # Inject RAM (e.g. 16gb, 8gb) to avoid variant mix-ups
    if ram:
        query_parts.append(f"{ram}gb")

    for m in models:
        m_str = str(m)
        if not m_str.isdigit() and m_str.lower() != (brand or "") and m_str.lower() != (series or ""):
            query_parts.append(m_str)
            break

    if len(query_parts) <= 1:
        clean_words = [w for w in re.sub(r"[^\w\s]", " ", clean_text).split() if len(w) > 2]
        query_parts.extend(clean_words[:3])

    # De-duplicate while preserving order and clean tokens
    seen_tokens = set()
    final_tokens = []
    for part in query_parts:
        for t in part.split():
            clean_t = re.sub(r"[^\w]", "", t.lower())
            if clean_t and clean_t not in seen_tokens:
                seen_tokens.add(clean_t)
                final_tokens.append(clean_t)

    search_query = " ".join(final_tokens)

    return {
        "brand": brand,
        "series": series,
        "models": models,
        "specs": specs,
        "gpu": gpu,
        "ram": ram,
        "search_query": search_query,
        "raw_title": title,
    }


def parse_flipkart_html(html: str) -> list[dict]:
    """Parse candidate products from Flipkart HTML.

    Dual-layer parsing:
    1. Try JSON state payload (window.__INITIAL_STATE__)
    2. Fallback to BeautifulSoup HTML DOM parsing if JSON state is absent or empty.
    """
    candidates = []

    # Layer 1: JSON state
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*<\/script>", html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
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
        except Exception as e:
            logger.warning("Failed to parse Flipkart JSON payload: %s", e)

    if candidates:
        return candidates

    # Layer 2: BeautifulSoup HTML DOM parsing
    try:
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select("div[data-id]"):
            title_el = card.select_one("div.KzDlHZ, a.pIpigb, a[title], img[alt]")
            title = (title_el.get("title") or title_el.get("alt") or title_el.get_text(strip=True)) if title_el else ""

            price_el = card.select_one(".hZ3P6w, .Nx9bqj")
            if not price_el:
                for el in card.find_all(string=re.compile(r"₹")):
                    t = el.strip()
                    if t.startswith("₹"):
                        price_el = el.parent
                        break
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_m = re.search(r"₹([\d,]+)", price_text)
            price = float(price_m.group(1).replace(",", "")) if price_m else None

            mrp_el = card.select_one(".kRYCnD, .yKfB63")
            mrp_text = mrp_el.get_text(strip=True) if mrp_el else ""
            mrp_m = re.search(r"₹([\d,]+)", mrp_text)
            mrp = float(mrp_m.group(1).replace(",", "")) if mrp_m else None

            link_el = card.select_one("a[href*='/p/']")
            base_url = link_el.get("href") if link_el else None
            url = f"https://www.flipkart.com{base_url}" if base_url else None

            rating_el = card.select_one(".MKiFS6, .XqdRHH")
            rating_text = rating_el.get_text(strip=True) if rating_el else None
            try:
                rating = float(rating_text) if rating_text else None
            except (ValueError, TypeError):
                rating = None

            if title and price:
                candidates.append({
                    "title": title,
                    "price": price,
                    "mrp": mrp,
                    "rating": rating,
                    "url": url,
                })
    except Exception as e:
        logger.warning("Failed to parse Flipkart DOM: %s", e)

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

    # 3. CPU Generation Conflict (e.g. 12th Gen vs 13th Gen, Core Ultra vs 13th)
    amz_gen = extract_cpu_gen(amz_title)
    fk_gen = extract_cpu_gen(fk_title)
    if amz_gen and fk_gen and amz_gen != fk_gen:
        return True

    # 4. GPU Model Conflict (e.g. RTX 3050 vs RTX 4050, RTX 2050 vs 3050)
    amz_gpu = extract_gpu(amz_title)
    fk_gpu = extract_gpu(fk_title)
    if amz_gpu and fk_gpu and amz_gpu != fk_gpu:
        return True

    # 5. Dedicated vs Integrated GPU Conflict
    amz_has_ded_gpu = has_dedicated_gpu(amz_title)
    fk_has_ded_gpu = has_dedicated_gpu(fk_title)
    if amz_has_ded_gpu != fk_has_ded_gpu:
        if amz_has_ded_gpu and ("integrated" in fk_lower or "iris" in fk_lower or "uhd" in fk_lower or "graphics card: integrated" in fk_lower):
            return True
        if fk_has_ded_gpu and ("integrated" in amz_lower or "iris" in amz_lower or "uhd" in amz_lower):
            return True

    # 6. RAM Capacity Conflict (e.g. 8GB vs 16GB, 16GB vs 32GB)
    amz_ram = extract_ram_gb(amz_title)
    fk_ram = extract_ram_gb(fk_title)
    if amz_ram and fk_ram and amz_ram != fk_ram:
        return True

    # 7. Primary Storage Capacity Conflict (e.g. 512GB vs 1TB SSD)
    amz_storage = extract_storage_gb(amz_title)
    fk_storage = extract_storage_gb(fk_title)
    if amz_storage and fk_storage and amz_storage != fk_storage:
        return True

    # 8. Display Screen Size Conflict (e.g. 14" vs 15.6", 43" vs 55")
    amz_screen = extract_screen_size(amz_title)
    fk_screen = extract_screen_size(fk_title)
    if amz_screen and fk_screen and abs(amz_screen - fk_screen) > 0.5:
        return True

    # 9. Audio Form Factor Conflict (Over-Ear Headphones vs In-Ear Buds vs Neckband)
    amz_form = extract_audio_form_factor(amz_title)
    fk_form = extract_audio_form_factor(fk_title)
    if amz_form and fk_form and amz_form != fk_form:
        return True

    # 10. CPU Processor Model Conflict (e.g. 125H vs 115U, 7320U vs 7330U, 12450H vs 13420H)
    amz_cpu = extract_cpu_model(amz_title)
    fk_cpu = extract_cpu_model(fk_title)
    if amz_cpu and fk_cpu and amz_cpu != fk_cpu:
        return True

    # 11. Mobile / Tablet Connectivity Conflict (5G vs 4G)
    has_amz_5g = bool(re.search(r"\b5g\b", amz_lower)) and not bool(re.search(r"\b5\s*g(?:ms|ram|rams)\b", amz_lower))
    has_fk_5g = bool(re.search(r"\b5g\b", fk_lower)) and not bool(re.search(r"\b5\s*g(?:ms|ram|rams)\b", fk_lower))
    if has_amz_5g != has_fk_5g:
        mobile_tech = bool(re.search(r"\b(phone|mobile|smartphone|redmi|realme|samsung|oneplus|vivo|oppo|poco|motorola|moto|iqoo|xiaomi|infinix|narzo|tecno|galaxy)\b", amz_lower + " " + fk_lower))
        if mobile_tech:
            return True

    # 12. Mobile / Device Tier Conflict (e.g. Pro+ vs Pro vs Ultra vs Plus vs Lite)
    amz_tier = extract_device_tier(amz_title)
    fk_tier = extract_device_tier(fk_title)
    if amz_tier and fk_tier and amz_tier != fk_tier:
        return True

    # 13. Appliance Wattage Conflict (e.g. 500W vs 750W vs 1000W)
    amz_watt = extract_wattage(amz_title)
    fk_watt = extract_wattage(fk_title)
    if amz_watt and fk_watt and amz_watt != fk_watt:
        return True

    # 14. Appliance Volume Capacity Conflict (e.g. 1.8L vs 3.0L)
    amz_cap = extract_capacity_liters(amz_title)
    fk_cap = extract_capacity_liters(fk_title)
    if amz_cap and fk_cap and abs(amz_cap - fk_cap) > 0.3:
        return True

    # 15. Laptop Sub-series Conflicts
    laptop_subseries = [
        # Acer Aspire sub-series
        ["aspire one", "aspire lite", "aspire 3", "aspire 5", "aspire 7"],
        # Acer Swift sub-series
        ["swift pro", "swift neo", "swift go", "swift air"],
        # Asus Vivobook sub-series
        ["vivobook go", "vivobook s", "vivobook pro"],
        # Lenovo IdeaPad sub-series
        ["ideapad slim 1", "ideapad slim 3", "ideapad slim 5", "ideapad pro"],
        # Asus TUF sub-series
        ["tuf a15", "tuf f15", "tuf a16", "tuf f16"],
    ]
    for group in laptop_subseries:
        for sub in group:
            if sub in amz_lower and sub not in fk_lower:
                for other_sub in group:
                    if other_sub != sub and other_sub in fk_lower:
                        return True

    # 16. Known Brand-Level Series Conflicts (Laptops, Smartwatches, and Audio)
    series_list = [
        # Laptops
        "loq", "legion", "ideapad", "thinkpad", "thinkbook", "v15", "v14",
        "tuf", "rog", "zenbook", "vivobook",
        "victus", "pavilion", "omen", "envy", "spectre",
        "aspire", "swift", "predator", "nitro",
        # Smartwatches
        "ninja", "hurricane", "gladiator", "invincible", "visionary", "commando",
        "wave", "lunar", "storm", "xtend", "matrix",
        "colorfit", "pulse", "evolve", "caliber", "icon", "vortex",
        # Audio
        "bassheads", "rockerz", "airdopes", "nirvana",
    ]
    for s in series_list:
        if bool(re.search(rf"\b{s}\b", amz_lower)) and not bool(re.search(rf"\b{s}\b", fk_lower)):
            for other_s in series_list:
                if other_s != s and bool(re.search(rf"\b{other_s}\b", fk_lower)):
                    return True

    # 17. Numeric Device Model Code Conflict (e.g. 300C vs 211, A114 vs A325)
    amz_models = extract_device_model_numbers(amz_title)
    fk_models = extract_device_model_numbers(fk_title)
    if amz_models and fk_models:
        overlap = amz_models.intersection(fk_models)
        if not overlap:
            base_overlap = any(am in fm or fm in am for am in amz_models for fm in fk_models)
            if not base_overlap:
                return True

    return False


def score_flipkart_match(amazon_sig: dict, amazon_price: float, candidate: dict) -> float:
    """Compute 0–100 match confidence score between Amazon item and Flipkart candidate.

    Strict rules:
    - Must be within realistic price corridor (0.50x to 1.85x) or rejected (0.0).
    - Brand must match or rejected (0.0).
    - Zero tolerance hardware & spec conflict check (RAM, GPU, CPU gen, storage, screen size, series).
    - Base score: 30 pts.
    - Model/MPN/Series match: +40 pts.
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

    # 3. Conflict Check (RAM, GPU, CPU Gen, Series, Display Size)
    if has_chipset_or_series_conflict(amazon_sig.get("raw_title", ""), candidate["title"]):
        return 0.0

    score = 30.0

    # 4. Model / Series match (+40 pts)
    matched_model = False
    for m in amazon_sig.get("models", []):
        m_lower = str(m).lower()
        base_model = m_lower.split("-")[0]
        if (len(m_lower) >= 3 and m_lower in fk_title) or (len(base_model) >= 3 and base_model in fk_title):
            score += 40.0
            matched_model = True
            break

    if not matched_model and amazon_sig.get("series"):
        series_lower = amazon_sig["series"].lower()
        if len(series_lower) >= 3 and series_lower in fk_title:
            score += 35.0

    # 5. Spec match
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

    # 6. Token Jaccard Overlap
    amz_tokens = set(re.findall(r"[a-z0-9]+", amazon_sig.get("raw_title", "").lower()))
    fk_tokens = set(re.findall(r"[a-z0-9]+", fk_title))
    if amz_tokens:
        jaccard = len(amz_tokens.intersection(fk_tokens)) / len(amz_tokens.union(fk_tokens))
        score += jaccard * 15.0

    return min(max(0.0, score), 100.0)


def classify_cross_market_verdict(amazon_price: float, flipkart_price: float) -> dict:
    """Classify pricing verdict between Amazon and Flipkart using +/-5% parity threshold."""
    if not amazon_price or not flipkart_price:
        return {
            "verdict": "unverified",
            "is_deal": False,
            "price_diff": 0.0,
            "diff_pct": 0.0,
        }

    diff = amazon_price - flipkart_price
    diff_pct = diff / flipkart_price

    if abs(diff_pct) <= 0.05:
        return {
            "verdict": "market_parity",
            "is_deal": False,
            "price_diff": round(diff, 2),
            "diff_pct": round(diff_pct * 100, 1),
        }
    elif diff_pct <= -0.05:
        return {
            "verdict": "true_deal",
            "is_deal": True,
            "price_diff": round(abs(diff), 2),
            "diff_pct": round(abs(diff_pct) * 100, 1),
        }
    else:
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
    """Verify an Amazon product against Flipkart using entity disambiguation & +/-5% parity."""
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

    # 3. Score candidates with 5-layer disambiguation (brand + model/series match >= 70.0)
    scored_candidates = []
    for c in candidates:
        score = score_flipkart_match(sig, amazon_price, c)
        if score >= 70.0:
            scored_candidates.append((score, c))

    if not scored_candidates:
        await cache.set_flipkart(cache_key, fallback_unverified)
        return fallback_unverified

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_match = scored_candidates[0]

    # 4. Classify cross-market verdict
    verdict_info = classify_cross_market_verdict(amazon_price, best_match["price"])

    result = {
        "match_found": True,
        "verdict": verdict_info["verdict"],
        "is_deal": verdict_info["is_deal"],
        "flipkart_price": best_match["price"],
        "flipkart_title": best_match["title"],
        "flipkart_url": best_match.get("url"),
        "match_confidence": round(best_score, 1),
        "price_diff": verdict_info.get("price_diff", 0.0),
        "flipkart_savings": verdict_info.get("flipkart_savings", abs(verdict_info.get("price_diff", 0.0))),
        "diff_pct": verdict_info.get("diff_pct", 0.0),
    }

    # 5. Persist to cache
    await cache.set_flipkart(cache_key, result)
    return result
