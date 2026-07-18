import urllib.request
import json

url = "http://localhost:8006/api/search?query=Perfume&min_discount=40&max_discount=90"
r = urllib.request.urlopen(url)
d = json.loads(r.read())
print("Total:", d.get("total_results"))
print("Error:", d.get("error"))
print("Cached:", d.get("cached"))
print("Products count:", len(d.get("products", [])))
for p in d.get("products", [])[:3]:
    print(f"  ASIN={p['asin']}  price={p['current_price']}  discount={p['discount_pct']}%  title={p['title'][:50]}")

# Save full response
with open("debug_api_response.json", "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("\nFull response saved to debug_api_response.json")
