import requests
r = requests.get('http://127.0.0.1:8000/api/search?query=Perfume&min_discount=40')
data = r.json()
products = data.get('products', [])
true_deals = [p for p in products if p.get('is_true_deal')]
if true_deals:
    p = true_deals[0]
    print(f"Title: {p['title'][:65]}... \nPrice: Rs {p['current_price']} \nOriginal: Rs {p['original_price']} \nDiscount: {p['discount_pct']}% \nVerified True Deal: Yes")
else:
    print('No true deals found right now. Found items:', len(products))
