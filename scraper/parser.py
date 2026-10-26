"""Parse Amazon.in search result HTML into structured product data."""

import re
import statistics
from bs4 import BeautifulSoup


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


def _parse_discount(text: str | None) -> int | None:
    """Extract discount from text like '76% off'."""
    if not text:
        return None
    match = re.search(r"(\d+)%", text)
    if match:
        return int(match.group(1))
    return None


def parse_search_results(html: str) -> list[dict]:
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

        # Title
        title_tag = item.select_one(
            "h2 .a-size-medium.a-color-base.a-text-normal, "
            "h2 .a-size-base-plus.a-color-base.a-text-normal, "
            "h2 .a-text-normal"
        )
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            h2 = item.select_one("h2")
            title = h2.get_text(strip=True) if h2 else "Unknown Product"

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

        products.append(
            {
                "asin": asin,
                "title": title,
                "current_price": current_price,
                "original_price": original_price,
                "discount_pct": discount_pct,
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
    valid_discounts = [p["discount_pct"] for p in products if p["discount_pct"] is not None]
    median_discount = statistics.median(valid_discounts) if valid_discounts else 0

    for p in products:
        d = p["discount_pct"]
        if d is not None and d >= 40 and d >= median_discount + 10:
            p["is_true_deal"] = True
        else:
            p["is_true_deal"] = False

    return products
