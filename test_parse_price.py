import re

def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    # match ₹ or Rs. followed by price
    match = re.search(r"(?:₹|Rs\.?)\s*([0-9,]+(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)
    if not match:
        # fallback to just numbers with optional decimals
        match = re.search(r"([0-9,]+(?:\.[0-9]{1,2})?)", text)
    if match:
        cleaned = match.group(1).replace(",", "")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    return None

print(_parse_price("₹1,280 ₹1,280"))
print(_parse_price("₹1.28"))
print(_parse_price("₹239"))
print(_parse_price("₹1,999.00"))
