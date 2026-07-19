# Top Deals by Category — Design Spec

**Date:** 2026-07-19
**Status:** Approved (pending final spec review)

## Overview

Add a "Top Deals" tab to the Amazon Deal Finder that automatically discovers the best 50 products per Amazon.in category using browse-node scraping, ranks them by a weighted deal-quality score, and displays them in a lazy-loaded category-tabbed interface alongside the existing search feature.

## Goals

- Surface the highest-quality deals across 10 Amazon.in categories without requiring the user to type search queries
- Rank deals by a balanced score combining discount depth, rating quality, and review volume
- Minimize Amazon throttle/block risk via lazy per-category loading
- Preserve existing search functionality with zero modifications

## Non-Goals

- Real-time price tracking or alerts
- Cross-category comparison (e.g., "best deal across all categories")
- User accounts or saved preferences

---

## Architecture

### Approach: Dedicated Browse-Node Scraping

Uses Amazon's `rh=n:<node>` browse-node URL parameter to fetch category-scoped results instead of keyword searches. This gives precise, category-relevant products rather than keyword-matched noise.

### New URL Builder

```python
def build_category_url(node: str, min_discount: int, max_discount: int, page: int) -> str:
    params = {
        "rh": f"n:{node}",
        "pct-off": f"{min_discount}-{max_discount}",
        "s": "discount-percent-rank",
        "page": page,
    }
    return f"{AMAZON_BASE_URL}?{urlencode(params)}"
```

Constructs URLs like:
```
https://www.amazon.in/s?rh=n:976419031&pct-off=40-90&s=discount-percent-rank&page=1
```

### Deal Score Algorithm

Each product receives a score from 0–100 using:

| Signal | Weight | Normalization |
|--------|--------|---------------|
| `discount_pct` | 60% | Raw percentage (0–100) |
| `rating` | 25% | `(rating / 5) × 100` → 0–100 scale |
| `review_count` | 15% | `min(reviews, 5000) / 5000 × 100` — capped at 5K |

**Formula:**
```
score = round(discount_pct * 0.6 + (rating / 5 * 100) * 0.25 + min(review_count, 5000) / 5000 * 100 * 0.15)
```

- Products with `null` discount are scored 0
- Products with `null` rating treated as 0 for that component
- Products with `null` review_count treated as 0 for that component

### New API Endpoint

**`GET /api/top-deals`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category` | string (required) | — | Amazon browse-node ID (e.g., `976419031`) |
| `min_discount` | int | 40 | Minimum discount % |
| `max_discount` | int | 90 | Maximum discount % |

**Response:**
```json
{
  "category": "Electronics",
  "node": "976419031",
  "products": [
    {
      "asin": "B0...",
      "title": "...",
      "current_price": 999.0,
      "original_price": 3999.0,
      "discount_pct": 75,
      "rating": 4.2,
      "review_count": 1543,
      "image_url": "...",
      "product_url": "...",
      "is_prime": true,
      "coupon": null,
      "is_true_deal": true,
      "deal_score": 71
    }
  ],
  "total_results": 50,
  "cached": false
}
```

### Aggregation Logic

`search_category_deals(node, category_name, cache)`:
1. Fetch up to 3 pages (configurable via `TOP_DEALS_PAGES`)
2. Parse each page with existing `parse_search_results()`
3. Deduplicate by ASIN (keep first occurrence)
4. Compute `deal_score` for each product
5. Sort descending by `deal_score`
6. Trim to top 50 (configurable via `TOP_DEALS_LIMIT`)
7. Cache result with standard 30-minute TTL

Cache key format: `top-deals:<node>:<min_discount>:<max_discount>` (SHA256 hashed).

### Config Additions

```python
# Top Deals
TOP_DEALS_PAGES = 3       # pages to scrape per category
TOP_DEALS_LIMIT = 50      # max products per category
```

---

## Frontend Design

### Tab Bar

Two-tab glassmorphism tab bar at the top of `<main>`:

- **🔍 Search Deals** (default active) — existing search form & results
- **🏆 Top Deals** — category-based best deals

Animated sliding underline indicator glides between tabs. Tab panes fade in/out with CSS transitions.

### Category Pill Bar

Horizontally scrollable row of 10 category pills inside the Top Deals pane:

```
[ Electronics ] [ Fashion ] [ Beauty ] [ Home & Kitchen ] [ Books ] [ Sports ] [ Toys ] [ Computers ] [ Mobile Phones ] [ Grocery ]
```

- Active pill: filled purple background with neon glow
- Inactive pills: outlined/ghost style
- First category (Electronics) auto-loads when Top Deals tab first opens
- Clicking a pill fetches `/api/top-deals?category=<node>` lazily

### Product Cards

Reuses existing card design with one addition:

- **Deal Score Badge** — circular badge in the top-left corner showing the numeric score (e.g., `92`). Gradient fill:
  - 80–100: green tones
  - 60–79: yellow/amber tones
  - 0–59: red/orange tones
- Positioned opposite the existing discount badge (top-left vs top-right)

### Loading State

While a category is fetching:
- 6 skeleton placeholder cards with shimmer pulse animation
- Category pill shows subtle loading indicator (opacity pulse)

### Layout

Same responsive grid: `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| All 3 pages return CAPTCHA | Return `{ products: [], error: "..." }` — frontend shows error banner |
| Partial page failure | Return products from successful pages, still score and rank |
| Category returns < 50 products | Return all available, no padding |
| Network timeout | Existing 3-attempt exponential backoff retry handles this |

## Edge Cases

- **Duplicate ASINs across pages:** Deduplicate, keep first occurrence
- **Products with no discount/rating:** Scored 0 for missing fields, pushed to bottom
- **Rapid pill switching:** Frontend uses `AbortController` to cancel previous fetch before starting new one

## Isolation

All changes are additive. No modifications to:
- Existing `/api/search` endpoint
- `search_deals()` function
- `parse_search_results()` parser
- `SearchCache` class
- Existing HTML/CSS/JS search functionality

---

## Files Changed

### Backend
- **[MODIFY]** `config.py` — add `TOP_DEALS_PAGES`, `TOP_DEALS_LIMIT`
- **[MODIFY]** `scraper/engine.py` — add `build_category_url()`, `compute_deal_score()`, `search_category_deals()`
- **[MODIFY]** `main.py` — add `GET /api/top-deals` endpoint

### Frontend
- **[MODIFY]** `static/index.html` — add tab bar, tab panes, category pill bar, top-deals product grid
- **[MODIFY]** `static/style.css` — tab bar, category pills, deal score badge, skeleton loading styles
- **[MODIFY]** `static/app.js` — tab switching, lazy category fetching, AbortController, deal score rendering
