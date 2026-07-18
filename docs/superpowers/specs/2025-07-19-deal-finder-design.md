# Amazon.in Deal Finder — Design Spec

## Purpose

A web app that finds the best deals on Amazon.in for any user-supplied search term (e.g. "Perfume", "Gaming Mouse"). Deals are filtered by discount percentage using Amazon's `pct-off` URL parameter, sorted by highest discount first, and displayed in a premium dark-themed UI with price charts and deal cards.

## Core Concept

Power users find Amazon deals by constructing URLs with the `pct-off` parameter:
```
https://www.amazon.in/s?k={search_term}&pct-off={min}-{max}
```
This app automates and beautifies that workflow, adding caching, stealth request handling, and a polished web interface.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Browser (User)                  │
│         HTML/CSS/JS Frontend (Vanilla)           │
└──────────────────┬──────────────────────────────┘
                   │  HTTP (REST JSON API)
                   ▼
┌─────────────────────────────────────────────────┐
│              Python Backend (FastAPI)            │
│                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐│
│  │ /api/search  │  │ /api/trending│  │ /api/   ││
│  │              │  │              │  │ categories│
│  └──────┬──────┘  └──────┬───────┘  └─────────┘│
│         │                │                       │
│         ▼                ▼                       │
│  ┌──────────────────────────────────────────┐   │
│  │          Scraper Engine (httpx)           │   │
│  │  • Stealth headers + UA rotation         │   │
│  │  • Request throttling (2-5s random)      │   │
│  │  • BeautifulSoup HTML parsing            │   │
│  └──────────────┬───────────────────────────┘   │
│                 │                                │
│                 ▼                                │
│  ┌──────────────────────────────────────────┐   │
│  │          Cache Layer (SQLite)             │   │
│  │  • 30-minute TTL per search query        │   │
│  │  • Keyed by (search_term, pct_off_range) │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Technology Stack

| Layer      | Technology                    | Rationale                                              |
|------------|-------------------------------|--------------------------------------------------------|
| Frontend   | HTML + Vanilla CSS + JS       | No framework overhead, maximum control, premium design |
| Backend    | Python 3.12+ with FastAPI     | Async-native, fast, great for API servers              |
| HTTP Client| httpx (async)                 | Modern async HTTP, supports HTTP/2, stealth-friendly   |
| Parser     | BeautifulSoup4 + lxml         | Robust HTML parsing, handles malformed Amazon HTML     |
| Cache      | SQLite via aiosqlite          | Zero-config, file-based, perfect for single-server     |
| Server     | Uvicorn                       | ASGI server for FastAPI                                |

---

## Backend Design

### Scraper Engine

The scraper constructs Amazon.in search URLs and extracts product data from the HTML response.

**URL Construction:**
```python
base_url = "https://www.amazon.in/s"
params = {
    "k": search_term,          # User's search query
    "pct-off": f"{min_discount}-{max_discount}",  # e.g. "50-90"
    "s": "discount-percent-rank",  # Sort by highest discount
    "page": page_number,
}
```

**Stealth Measures:**
1. **User-Agent Rotation**: Pool of 20+ real browser UA strings (Chrome, Firefox, Edge on Windows/Mac/Linux), randomly selected per request
2. **Request Throttling**: Random delay between 2-5 seconds between requests to Amazon
3. **Session Cookies**: Fresh session per request batch (no persistent fingerprint)
4. **Accept Headers**: Full realistic browser Accept, Accept-Language, Accept-Encoding headers
5. **No Referer Leak**: Omit or randomize Referer header
6. **HTTP/2**: Use httpx with HTTP/2 to match modern browser behavior

**Data Extraction (BeautifulSoup):**

For each search result item, extract:
- **Title**: Product name
- **ASIN**: Amazon Standard Identification Number (from `data-asin` attribute)
- **Current Price**: The deal price (₹)
- **Original Price (MRP)**: The strikethrough price
- **Discount Percentage**: Computed from current vs. original, or from Amazon's displayed badge
- **Rating**: Star rating (1-5)
- **Review Count**: Number of reviews
- **Image URL**: Product thumbnail
- **Product URL**: Direct link to the product page on Amazon.in
- **Prime Badge**: Whether the product is Prime-eligible
- **Coupon**: Any additional coupon discount shown

### API Endpoints

#### `GET /api/search`
Search for deals on Amazon.in.

**Query Parameters:**
| Param          | Type   | Default | Description                          |
|----------------|--------|---------|--------------------------------------|
| `q`            | string | required| Search query (e.g. "Perfume")        |
| `min_discount` | int    | 40      | Minimum discount percentage          |
| `max_discount` | int    | 90      | Maximum discount percentage          |
| `page`         | int    | 1       | Page number for pagination           |

**Response:**
```json
{
  "query": "Perfume",
  "total_results": 48,
  "page": 1,
  "cached": true,
  "cache_expires_in": 1423,
  "products": [
    {
      "asin": "B0DNTCMFRG",
      "title": "Park Avenue Oud Perfume 100ml",
      "current_price": 239,
      "original_price": 999,
      "discount_pct": 76,
      "rating": 4.2,
      "review_count": 1543,
      "image_url": "https://m.media-amazon.com/images/I/...",
      "product_url": "https://www.amazon.in/dp/B0DNTCMFRG",
      "is_prime": true,
      "coupon": "Extra 5% off with coupon"
    }
  ]
}
```

#### `GET /api/categories`
Returns a curated list of popular Amazon.in browse nodes for quick browsing.

**Response:**
```json
{
  "categories": [
    {"name": "Electronics", "node": "976419031"},
    {"name": "Fashion", "node": "1571271031"},
    {"name": "Beauty", "node": "1355016031"},
    {"name": "Home & Kitchen", "node": "976442031"},
    {"name": "Books", "node": "976389031"},
    {"name": "Sports", "node": "1984443031"},
    {"name": "Toys", "node": "1350380031"}
  ]
}
```

### Cache Layer

- **Storage**: SQLite database (`cache.db`) with a single `search_cache` table
- **Key**: SHA256 hash of `(query, min_discount, max_discount, page)`
- **Value**: JSON-serialized product list + metadata
- **TTL**: 30 minutes — expired entries are purged on read
- **Benefits**: Dramatically reduces Amazon requests; same search by multiple users hits cache

---

## Frontend Design

### Visual Theme
- **Dark mode** with glassmorphism card effects
- **Color palette**: Deep navy (#0a0e27) background, electric blue (#4f46e5) accents, emerald green (#10b981) for deal badges
- **Typography**: Inter (Google Fonts) for clean, modern readability
- **Animations**: Smooth card entrance animations, hover lift effects, shimmer loading skeletons

### Pages / Views

#### 1. Landing / Search View
- Large centered search bar with placeholder "Search for deals... (e.g. Perfume, Laptop)"
- Discount range slider (default 40-90%)
- "Find Deals" button with ripple animation
- Below: Quick category chips (Electronics, Fashion, Beauty, etc.)
- Background: Subtle animated gradient

#### 2. Results View
- Grid of deal cards (responsive: 1 col mobile → 3 col desktop)
- Each card shows:
  - Product image
  - Title (truncated to 2 lines)
  - Current price in large bold ₹ format
  - Original price with strikethrough
  - Discount badge (e.g. "76% OFF") in bright green
  - Star rating with review count
  - Prime badge if applicable
  - Coupon badge if applicable
  - "View on Amazon" button → opens Amazon.in product page
- Top bar: Search query, result count, sort options
- Infinite scroll or "Load More" pagination
- Loading state: Shimmer skeleton cards

#### 3. Error / Empty States
- Friendly illustration + message for no results
- Retry button for network errors
- CAPTCHA detection: Show message "Amazon is temporarily limiting requests. Results will refresh automatically."

### Responsive Design
- Mobile-first approach
- Breakpoints: 640px (sm), 768px (md), 1024px (lg), 1280px (xl)
- Cards stack vertically on mobile, 2-col on tablet, 3-col on desktop

---

## Error Handling

| Scenario                     | Behavior                                                    |
|------------------------------|-------------------------------------------------------------|
| Amazon returns CAPTCHA page  | Return cached data if available; otherwise return error with retry-after hint |
| Amazon returns 503/429       | Exponential backoff (2s, 4s, 8s), max 3 retries            |
| No results found             | Return empty products array; frontend shows friendly empty state |
| Network timeout              | 15-second timeout per request; return error if exceeded     |
| Malformed HTML               | Log warning, skip unparseable products, return partial results |

---

## Project Structure

```
DealFinderAmazonPy/
├── app.py                   # FastAPI application entry point
├── requirements.txt         # Python dependencies
├── config.py                # Configuration (cache TTL, UA pool, etc.)
├── scraper/
│   ├── __init__.py
│   ├── engine.py            # Core scraping logic (httpx + BS4)
│   ├── stealth.py           # UA rotation, header generation
│   └── parser.py            # BeautifulSoup extraction logic
├── cache/
│   ├── __init__.py
│   └── sqlite_cache.py      # SQLite cache layer
├── static/
│   ├── index.html           # Main HTML page
│   ├── css/
│   │   └── style.css        # All styles
│   └── js/
│       └── app.js           # Frontend logic
└── docs/
    └── superpowers/
        └── specs/
            └── 2025-07-19-deal-finder-design.md  # This file
```

---

## Dependencies

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
httpx[http2]>=0.27.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
aiosqlite>=0.20.0
```

---

## Success Criteria

1. User can search for any term and see Amazon.in products sorted by highest discount within 5 seconds
2. Results are accurate — discount percentages match what Amazon shows
3. No Amazon blocks for normal usage patterns (≤10 searches per minute)
4. Cache reduces Amazon requests by 80%+ for repeated searches
5. Frontend is responsive, visually premium, and works on mobile
6. No browser automation required — pure HTTP requests for maximum stealth
