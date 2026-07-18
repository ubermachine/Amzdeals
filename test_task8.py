import statistics
from scraper.parser import parse_search_results

def test_true_deal():
    with open("amazon_dump.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    products = parse_search_results(html)
    valid_discounts = [p["discount_pct"] for p in products if p["discount_pct"] is not None]
    median_discount = statistics.median(valid_discounts) if valid_discounts else 0
    print(f"Total products: {len(products)}")
    print(f"Products with discount: {len(valid_discounts)}")
    print(f"Median discount: {median_discount}")
    
    true_deals = [p for p in products if p.get("is_true_deal")]
    print(f"Found {len(true_deals)} true deals")
    for p in true_deals:
        print(f" - {p['title'][:40]}... (Discount: {p['discount_pct']}%, Price: {p['current_price']})")
        
if __name__ == "__main__":
    test_true_deal()
