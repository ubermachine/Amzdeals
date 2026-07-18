import asyncio
import httpx
from scraper.stealth import get_stealth_headers
from scraper.parser import parse_search_results


async def test():
    url = "https://www.amazon.in/s?k=Perfume&pct-off=40-90&page=1"
    headers = get_stealth_headers()
    print(f"Using UA: {headers['User-Agent'][:60]}...")

    async with httpx.AsyncClient(http2=True, timeout=15, follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        print(f"Status: {r.status_code}")
        print(f"Content length: {len(r.text)}")

        text_lower = r.text.lower()
        if "captcha" in text_lower:
            print("CAPTCHA DETECTED!")
        if "robot" in text_lower:
            print("ROBOT CHECK DETECTED!")

        if "s-search-result" in r.text:
            count = r.text.count("s-search-result")
            print(f"Found {count} s-search-result elements")
        else:
            print("NO s-search-result elements found!")

        # Try parsing
        products = parse_search_results(r.text)
        print(f"Parsed {len(products)} products")
        for p in products[:3]:
            print(f"  - {p['title'][:50]} | ₹{p['current_price']} (was ₹{p['original_price']}) | {p['discount_pct']}% off")

        # Save HTML for inspection
        with open("debug_response.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print("Full response saved to debug_response.html")


asyncio.run(test())
