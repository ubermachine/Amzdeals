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

# Categories (popular Amazon.in browse nodes)
CATEGORIES = [
    {"name": "Electronics", "node": "976419031"},
    {"name": "Fashion", "node": "1571271031"},
    {"name": "Beauty", "node": "1355016031"},
    {"name": "Home & Kitchen", "node": "976442031"},
    {"name": "Books", "node": "976389031"},
    {"name": "Sports", "node": "1984443031"},
    {"name": "Toys", "node": "1350380031"},
    {"name": "Computers", "node": "976392031"},
    {"name": "Mobile Phones", "node": "1389401031"},
    {"name": "Grocery", "node": "2454178031"},
]

# Top Deals
TOP_DEALS_PAGES = 3       # pages to scrape per category
TOP_DEALS_LIMIT = 50      # max products per category
