from bs4 import BeautifulSoup
from scraper.parser import parse_search_results

text = open('amazon_dump.html', encoding='utf-8').read()
products = parse_search_results(text)

true_deals = [p for p in products if p.get('is_true_deal')]
if true_deals:
    p = true_deals[0]
    print(f"Product: {p['title'][:60]}...")
    print(f"ASIN: {p['asin']}")
    print(f"Current Price: Rs {p['current_price']}")
    print(f"Original MSRP: Rs {p['original_price']}")
    print(f"Discount: {p['discount_pct']}%")
    print("Is True Deal: Yes")
else:
    print("No true deals found.")
