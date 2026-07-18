"""Dump the raw response to see what Amazon is returning."""
import asyncio
import httpx
from scraper.stealth import get_stealth_headers


async def main():
    url = "https://www.amazon.in/s?k=Perfume&pct-off=40-90&page=1"
    headers = get_stealth_headers()

    async with httpx.AsyncClient(http2=True, timeout=15, follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        print(f"Status: {r.status_code}")
        print(f"Final URL: {r.url}")
        
        with open("amazon_dump.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print("Saved raw HTML to amazon_dump.html")

asyncio.run(main())
