import json
from scraper.parser import parse_search_results

with open('amazon_dump.html', 'r', encoding='utf-8') as f:
    html = f.read()

products = parse_search_results(html)
for p in products:
    print(f"Title: {p['title'][:30]}...")
    print(f"Current: {p['current_price']} Original: {p['original_price']} Discount: {p['discount_pct']}%")
    print("-" * 40)
