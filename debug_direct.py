"""Direct test of the scraper engine bypassing cache and server."""
import asyncio
import httpx
from scraper.stealth import get_stealth_headers
from scraper.parser import parse_search_results


async def main():
    url = "https://www.amazon.in/s?k=Perfume&pct-off=40-90&page=1"
    headers = get_stealth_headers()
    print(f"URL: {url}")
    print(f"UA: {headers.get('User-Agent', 'curl_cffi_default')[:70]}...")
    print()

    from curl_cffi import requests
    async with requests.AsyncSession(impersonate="chrome", timeout=15) as client:
        try:
            r = await client.get(url, headers=headers)
            print(f"HTTP Status: {r.status_code}")
            text = r.text
            print(f"Response size: {len(text)} bytes")
        except Exception as e:
            print("Request failed:", e)
            return

        # Check for CAPTCHA indicators
        has_captcha_form = "Type the characters you see" in text
        has_validate_captcha = "/errors/validateCaptcha" in text
        has_robot_meta = '<meta name="robots"' in text.lower()
        has_search_results = "s-search-result" in text

        print(f"Has CAPTCHA form: {has_captcha_form}")
        print(f"Has validateCaptcha: {has_validate_captcha}")
        print(f"Has robot meta tag (normal): {has_robot_meta}")
        print(f"Has s-search-result: {has_search_results}")
        print(f"Count of s-search-result: {text.count('s-search-result')}")
        print()

        # Parse products
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
            # Dump a snippet to debug the HTML structure
            # Find data-asin attributes
            import re
            asins = re.findall(r'data-asin="([^"]+)"', text)
            print(f"data-asin values found: {len(asins)}")
            print(f"First 10: {asins[:10]}")
            
            # Find data-component-type
            components = re.findall(r'data-component-type="([^"]+)"', text)
            print(f"data-component-type values: {set(components)}")


asyncio.run(main())
