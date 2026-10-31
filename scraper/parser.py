"""Parse Amazon.in search result HTML into structured product data."""

import json
import re
import ollama
import statistics
import math
from bs4 import BeautifulSoup
import numpy as np
from ollama import Client

def _parse_price(text: str | None) -> float | None:
    """Extract numeric price from text like '₹239' or '₹1,999.00'."""
    if not text:
        return None
    # match ₹ or Rs. followed by price, ignoring other text like duplicated prices
    match = re.search(r"(?:₹|Rs\.?)\s*([0-9,]+(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"([0-9,]+(?:\.[0-9]{1,2})?)", text)
    if match:
        cleaned = match.group(1).replace(",", "")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    return None


def _parse_rating(text: str | None) -> float | None:
    """Extract rating from text like '4.2 out of 5 stars' or '4.2 stars'."""
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)\s*(?:out of 5|stars|star)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d+\.?\d*)\s*out of", text, re.IGNORECASE)
    if match:
        try:
            val = float(match.group(1))
            if 0 <= val <= 5.0:
                return val
        except (ValueError, TypeError):
            return None
    return None


def _parse_review_count(text: str | None) -> int | None:
    """Extract review count from text like '1,543', '(42.8K)', '12K', '1.2M', or '42,864 ratings'."""
    if not text:
        return None
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*([kKmM])?", text.strip())
    if not match:
        return None
    num_str = match.group(1).replace(",", "")
    suffix = match.group(2)
    try:
        val = float(num_str)
        if suffix:
            suffix_lower = suffix.lower()
            if suffix_lower == "k":
                val *= 1000
            elif suffix_lower == "m":
                val *= 1000000
        return int(round(val))
    except (ValueError, TypeError):
        return None
    return None


def _parse_discount(text: str | None) -> int | None:
    """Extract discount from text like '76% off'."""
    if not text:
        return None
    match = re.search(r"(\d+)%", text)
    if match:
        return int(match.group(1))
    return None


def parse_coupon_discount(coupon_text: str | None, current_price: float | None) -> float:
    """Parse numeric discount amount from Amazon coupon text.

    Examples:
        'Save ₹500 with coupon' -> 500.0
        'Apply ₹1,500 coupon' -> 1500.0
        'Extra 5% off with coupon' (with current_price 2000) -> 100.0
        'You pay ₹1,200' (with current_price 1500) -> 300.0
    """
    if not coupon_text:
        return 0.0

    lower = coupon_text.lower()

    # If it says "you pay ₹X", the discount is current_price - X (if current_price > X)
    if "you pay" in lower:
        rupee_match = re.search(r"(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)", coupon_text, re.IGNORECASE)
        if rupee_match and current_price:
            try:
                you_pay = float(rupee_match.group(1).replace(",", ""))
                if 0 < you_pay < current_price:
                    return round(current_price - you_pay, 2)
            except (ValueError, TypeError):
                pass
        return 0.0

    # Search for absolute rupee amount: ₹500, ₹1,500, Rs. 500, etc.
    rupee_match = re.search(r"(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)", coupon_text, re.IGNORECASE)
    if rupee_match:
        try:
            return float(rupee_match.group(1).replace(",", ""))
        except (ValueError, TypeError):
            pass

    # Search for percentage: 5%, 10% off
    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", coupon_text)
    if pct_match and current_price and current_price > 0:
        try:
            pct = float(pct_match.group(1))
            return round((pct / 100.0) * current_price, 2)
        except (ValueError, TypeError):
            pass

    return 0.0


def is_refurbished_title(title: str | None) -> bool:
    """Check if title indicates a refurbished, renewed, or pre-owned product."""
    if not title:
        return False
    lower = title.lower()
    return any(kw in lower for kw in ["(renewed)", "(refurbished)", "refurbished", "pre-owned", "certified renewed"])


def is_accessory_title(title: str | None) -> bool:
    """Check if title indicates a phone/laptop accessory (cases, tempered glass, cables)."""
    if not title:
        return False
    lower = title.lower()
    accessory_triggers = [
        "case for", "cover for", "tempered glass", "screen protector",
        "laptop sleeve", "keyboard skin", "silicone case", "back cover",
        "charging cable", "cable protector", "wall mount", "protective case",
        "stylus pen", "pouch for", "camera lens protector", "watch box", "watch organizer", "watch roll", "case for watch"
    ]
    return any(trig in lower for trig in accessory_triggers)


def extract_pack_count(title: str | None) -> int:
    """Extract pack or set count from title (e.g. 'Pack of 3', 'Set of 5')."""
    if not title:
        return 1
    match = re.search(r"\b(?:pack|set|lot)\s+of\s+(\d+)\b", title, re.IGNORECASE)
    if match:
        try:
            return max(1, int(match.group(1)))
        except (ValueError, TypeError):
            return 1
    match2 = re.search(r"\b(\d+)\s*[-]?\s*(?:pack|pcs|pieces)\b", title, re.IGNORECASE)
    if match2:
        try:
            return max(1, int(match2.group(1)))
        except (ValueError, TypeError):
            return 1
    return 1

def calculate_score(product, score):

    rating = product.get("rating") or 0
    review_count = product.get("review_count") or 0
    discount_pct = product.get("discount_pct") or 0

    rating_score = (
        rating *
        min(review_count / 1000, 1)
    ) / 5

    review_score = min(
        math.log10(review_count + 1) / 5,
        1.0
    )

    discount_score = discount_pct / 100

    final_score = (
        score * 0.50 +
        rating_score * 0.25 +
        review_score * 0.10 +
        discount_score * 0.15
    )
    
    print(final_score)

    return round(final_score, 4)

def parse_search_results(html: str, query: str) -> list[dict]:
    """Parse Amazon.in search results HTML and return structured product data.

    Args:
        html: Raw HTML string from an Amazon.in search results page.

    Returns:
        List of product dicts with keys: asin, title, current_price,
        original_price, discount_pct, rating, review_count, image_url,
        product_url, is_prime, coupon.
    """
    
    
    
    
    soup = BeautifulSoup(html, "lxml")
    products = []

    result_items = soup.select('[data-component-type="s-search-result"][data-asin]')

    for item in result_items:
        asin = item.get("data-asin", "").strip()
        if not asin:
            continue

        # Title extraction:
        # On Amazon search result cards, full title can be in div.s-title-instructions-style a,
        # h2 a.a-text-normal, or h2 with brand prefix
        title_link = item.select_one(
            "div.s-title-instructions-style a.a-text-normal, "
            "div[data-cy='title-recipe'] a.a-text-normal, "
            "h2 a.a-text-normal, "
            "h2 a span.a-text-normal, "
            "h2 a span, "
            "h2 .a-size-medium.a-color-base.a-text-normal, "
            "h2 .a-size-base-plus.a-color-base.a-text-normal, "
            "h2 .a-text-normal"
        )
        h2 = item.select_one("h2")
        h2_text = h2.get_text(strip=True) if h2 else ""

        if title_link:
            sub_title = title_link.get_text(strip=True)
            if h2_text and not sub_title.lower().startswith(h2_text.lower()) and len(h2_text) < 30:
                title = f"{h2_text} {sub_title}"
            else:
                title = sub_title
        else:
            title = h2_text or "Unknown Product"

        # Image
        img_tag = item.select_one("img.s-image")
        image_url = img_tag.get("src") if img_tag else None

        # Current price
        price_tag = item.select_one('span.a-price[data-a-color="base"] .a-offscreen')
        if not price_tag:
            price_tag = item.select_one("span.a-price .a-offscreen")
        current_price = _parse_price(price_tag.get_text() if price_tag else None)

        # Original price (strikethrough)
        orig_tag = item.select_one(
            'span.a-price[data-a-strike="true"] .a-offscreen, '
            'span.a-text-price[data-a-strike="true"] .a-offscreen'
        )
        original_price = _parse_price(orig_tag.get_text() if orig_tag else None)

        # Discount percentage
        discount_tag = item.select_one("span.a-badge-text, span.savingsPercentage")
        discount_pct = _parse_discount(
            discount_tag.get_text() if discount_tag else None
        )
        # Compute from prices if badge not found
        if discount_pct is None and current_price and original_price and original_price > 0:
            discount_pct = round((1 - current_price / original_price) * 100)
        if discount_pct is not None:
            discount_pct = max(0, min(99, discount_pct))

        # Rating
        rating_tag = item.select_one("span.a-icon-alt")
        rating = _parse_rating(rating_tag.get_text() if rating_tag else None)

        # Review count
        review_count = None
        rev_link = item.select_one('a[aria-label*="rating"], a[aria-label*="review"]')
        if rev_link:
            aria = rev_link.get("aria-label", "")
            if "out of" not in aria.lower():
                review_count = _parse_review_count(aria)

        if review_count is None:
            candidates = item.select(
                "span.s-underline-text, span.puis-normal-weight-text, "
                "a[href*='#customerReviews'] span, span.a-size-mini, span.a-size-base"
            )
            for ct in candidates:
                txt = ct.get_text(strip=True)
                if not txt or "bought" in txt.lower():
                    continue
                if re.search(r"\(?\s*[\d,]+(?:\.\d+)?\s*[kKmM]?\s*\)?", txt):
                    cnt = _parse_review_count(txt)
                    if cnt is not None and cnt > 0:
                        review_count = cnt
                        break

        # Product URL
        link_tag = item.select_one("h2 a.a-link-normal")
        href = link_tag.get("href", "") if link_tag else ""
        if href.startswith("/"):
            product_url = f"https://www.amazon.in{href}"
        elif href.startswith("http"):
            product_url = href
        else:
            product_url = f"https://www.amazon.in/dp/{asin}"

        # Prime badge
        prime_tag = item.select_one('i.a-icon-prime, [aria-label*="Prime"]')
        is_prime = prime_tag is not None

        # Coupon
        coupon_tag = item.select_one("span.s-coupon-highlight-color, .s-coupon-unclipped")
        coupon = coupon_tag.get_text(strip=True) if coupon_tag else None

        # Badge extraction (Best Seller / Amazon's Choice)
        badge = None
        for b_tag in item.select("span.a-badge-text, span.a-badge-label, .a-badge"):
            b_text = b_tag.get_text(strip=True)
            if not b_text:
                continue
            lower_b = b_text.lower()
            if "best seller" in lower_b or "bestseller" in lower_b:
                badge = "Best Seller"
                break
            elif "amazon's choice" in lower_b or "choice" in lower_b:
                badge = "Amazon's Choice"
                break
        if not badge:
            if item.select_one('[aria-label*="Best Seller"]'):
                badge = "Best Seller"
            elif item.select_one('[aria-label*="Choice"]'):
                badge = "Amazon's Choice"

        coupon_discount = parse_coupon_discount(coupon, current_price)
        effective_price = max(0.0, round(current_price - coupon_discount, 2)) if current_price is not None else None

        # Recalculate effective discount if coupon provides additional savings
        effective_discount_pct = discount_pct
        if effective_price is not None and original_price and original_price > 0:
            effective_discount_pct = round((1 - effective_price / original_price) * 100)
            effective_discount_pct = max(0, min(99, effective_discount_pct))

        is_refurbished = is_refurbished_title(title)
        is_accessory = is_accessory_title(title)
        pack_count = extract_pack_count(title)

        products.append(
            {
                "asin": asin,
                "title": title,
                "current_price": current_price,
                "original_price": original_price,
                "discount_pct": discount_pct,
                "coupon_discount": coupon_discount,
                "effective_price": effective_price,
                "effective_discount_pct": effective_discount_pct,
                "is_refurbished": is_refurbished,
                "is_accessory": is_accessory,
                "pack_count": pack_count,
                "rating": rating,
                "review_count": review_count,
                "image_url": image_url,
                "product_url": product_url,
                "is_prime": is_prime,
                "coupon": coupon,
                "badge": badge,
            }
        )

    # Calculate median discount
    valid_discounts = [
        p.get("effective_discount_pct") or p.get("discount_pct")
        for p in products
        if (p.get("effective_discount_pct") or p.get("discount_pct")) is not None
    ]
    median_discount = statistics.median(valid_discounts) if valid_discounts else 0

    for p in products:
        d = p.get("effective_discount_pct") if p.get("effective_discount_pct") is not None else p.get("discount_pct")
        if d is not None and d >= 40 and d >= median_discount + 10:
            p["is_true_deal"] = True
        else:
            p["is_true_deal"] = False
    
    product_texts = [
        f"""{p['asin']} 
            Name {p['title']} 
            Current Price {p['current_price']} 
            Original Price {p['original_price']} 
            Rating {p['rating']}
            Discount percent {p['discount_pct']}
            Review Count {p['review_count']},
            Image url {p['image_url']},
            Product url {p['product_url']},
            Is prime {p['is_prime']},
            Coupon {p['coupon']},
            Badge {p['badge']}"""
        for p in products
    ]
    
    response1 = ollama.embed(
    model="nomic-embed-text",
    input=product_texts
   )
        
    response2 = ollama.embed(
        model="nomic-embed-text",
        input=query
       )
    
    product_embeddings = response1["embeddings"]
    query_embedding = response2["embeddings"]
     
    scores = []

    for i, embedding in enumerate(product_embeddings):

        similarity = np.dot(query_embedding,embedding) / (np.linalg.norm(query_embedding) * np.linalg.norm(embedding))

        scores.append(
            {
                "product": products[i],
                "score": similarity.item()
            }
        )
        
    scores.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    top_products = scores[:10]
    
    avg_score = statistics.mean([
    calculate_score(p["product"], p["score"])
    for p in top_products
])
    
    filtered_products = list(filter(lambda w: w["score"] >= avg_score, top_products))
    
    filtered_asins = {
    item["product"]["asin"]
    for item in filtered_products
    }

    matched_products = [
    item for item in products
    if item["asin"] in filtered_asins
  ]

    return matched_products
