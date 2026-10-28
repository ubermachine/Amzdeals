"""Central configuration for DealFinderAmazonPy."""

# Amazon
AMAZON_BASE_URL = "https://www.amazon.in/s"
AMAZON_PRODUCT_URL = "https://www.amazon.in/dp/{asin}"

# Cache
CACHE_TTL_SECONDS = 1800  # 30 minutes
CACHE_DB_PATH = "cache.db"

# Request
REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 3
BACKOFF_BASE = 2  # exponential backoff: 2s, 4s, 8s

# Throttle
THROTTLE_MIN = 2.0  # minimum seconds between requests
THROTTLE_MAX = 5.0  # maximum seconds between requests

# Pagination
DEFAULT_MIN_DISCOUNT = 40
DEFAULT_MAX_DISCOUNT = 90
DEFAULT_PAGE = 1

# Categories: Curated high-conversion, specific deal niches with verified Amazon India browse-nodes
CATEGORIES = [
    {"name": "Laptops", "node": "1375424031", "icon": "💻"},
    {"name": "Smartphones", "node": "1805560031", "icon": "📱"},
    {"name": "Headphones & Earbuds", "node": "29561348031", "icon": "🎧"},
    {"name": "Smartwatches", "node": "11599648031", "icon": "⌚"},
    {"name": "Shoes & Sneakers", "node": "1983518031", "icon": "👟"},
    {"name": "Watches", "node": "1350387031", "icon": "⌚"},
    {"name": "Luggage & Backpacks", "node": "2917436031", "icon": "🎒"},
    {"name": "Perfumes & Fragrances", "node": "1374298031", "icon": "🌸"},
    {"name": "Kitchen Appliances", "node": "4951860031", "icon": "🍳"},
    {"name": "Cookware & Dining", "node": "5925789031", "icon": "🍽️"},
    {"name": "Monitors", "node": "1375425031", "icon": "🖥️"},
    {"name": "Tablets & iPads", "node": "1375458031", "icon": "📱"},
    {"name": "TVs & Projectors", "node": "1389375031", "icon": "📺"},
    {"name": "Storage & SSDs", "node": "1375393031", "icon": "💾"},
    {"name": "Furniture", "node": "1380441031", "icon": "🛋️"},
    {"name": "Men's Clothing", "node": "1968024031", "icon": "👕"},
    {"name": "Women's Clothing", "node": "1953602031", "icon": "👗"},
    {"name": "Baby Care & Toys", "node": "1953111031", "icon": "👶"},
]

# Top Deals
TOP_DEALS_PAGES = 5       # pages to scrape per category
TOP_DEALS_LIMIT = 100     # max products per category

# Safety
MAX_CONCURRENT_SCRAPES = 1  # max concurrent HTTP requests to Amazon
