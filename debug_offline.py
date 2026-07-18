"""Test parser offline using dumped HTML."""
from scraper.parser import parse_search_results


with open("amazon_dump.html", "r", encoding="utf-8") as f:
    text = f.read()

products = parse_search_results(text)
print(f"Parsed products: {len(products)}")
print()

if products:
    for i, p in enumerate(products[:5]):
        title = p["title"][:60] if p["title"] else "N/A"
        print(f"Product {i+1}:")
        print(f"  ASIN: {p['asin']}")
        print(f"  Title: {title}")
        print(f"  Price: {p['current_price']}")
        print(f"  Original: {p['original_price']}")
        print(f"  Discount: {p['discount_pct']}%")
        print(f"  Prime: {p['is_prime']}")
        print()
else:
    print("NO PRODUCTS PARSED!")
