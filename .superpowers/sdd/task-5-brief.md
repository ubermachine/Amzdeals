### Task 5: Frontend — Tab Bar, Category Pills & Top Deals UI

**Files:**
- Modify: `static/index.html` (restructure with tabs)
- Modify: `static/style.css` (add tab bar, pill bar, deal-score badge, skeleton styles)
- Modify: `static/app.js` (add tab switching, lazy fetching, AbortController, deal-score rendering)

**Interfaces:**
- Consumes:
  - `GET /api/categories` → `[{"name": str, "node": str}, ...]` (Task 4)
  - `GET /api/top-deals?category=<node>` → `{category, node, products: [{...deal_score}], ...}` (Task 4)
- Produces: Complete frontend UI with two tabs and lazy-loaded category deals

- [ ] **Step 1: Rewrite `static/index.html` with tab structure**

Replace entire contents of `static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amazon Deal Finder — Best Deals & Top Category Deals</title>
    <meta name="description" content="Discover the best discounts and top deals across Amazon India categories. Find verified deals with price history.">
    <!-- Google Fonts: Inter -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="app-container">
        <header class="glass-header">
            <h1><span class="accent">Amazon</span> Deal Finder</h1>
            <p class="subtitle">Discover the best discounts across Amazon India</p>
        </header>

        <nav class="tab-bar glass-panel" id="tab-bar">
            <button class="tab-btn active" data-tab="tab-search" id="tab-btn-search">
                <span class="tab-icon">🔍</span> Search Deals
            </button>
            <button class="tab-btn" data-tab="tab-top-deals" id="tab-btn-top-deals">
                <span class="tab-icon">🏆</span> Top Deals
            </button>
            <div class="tab-indicator" id="tab-indicator"></div>
        </nav>

        <main>
            <!-- Tab 1: Search Deals (existing) -->
            <div class="tab-pane active" id="tab-search">
                <section class="search-section glass-panel">
                    <form id="search-form">
                        <div class="input-group">
                            <label for="query">Search Query</label>
                            <input type="text" id="query" name="query" placeholder="e.g. Laptops" required>
                        </div>
                        <div class="input-group">
                            <label for="min_discount">Min Discount (%)</label>
                            <input type="number" id="min_discount" name="min_discount" min="0" max="100" value="40" step="5">
                        </div>
                        <div class="input-group">
                            <label for="max_discount">Max Discount (%)</label>
                            <input type="number" id="max_discount" name="max_discount" min="0" max="100" placeholder="100" step="5">
                        </div>
                        <div class="button-container">
                            <button type="submit" id="search-btn">Find Deals</button>
                        </div>
                    </form>
                </section>

                <section id="results-section" class="hidden">
                    <div class="results-header">
                        <h2>Found Deals</h2>
                        <span id="cache-status" class="badge hidden"></span>
                    </div>
                    <div id="loading-spinner" class="spinner-container hidden">
                        <div class="spinner"></div>
                        <p>Scraping deals, this might take a moment...</p>
                    </div>
                    <div id="error-message" class="error hidden"></div>
                    <div id="product-grid" class="product-grid">
                        <!-- Products will be injected here -->
                    </div>
                </section>
            </div>

            <!-- Tab 2: Top Deals by Category -->
            <div class="tab-pane" id="tab-top-deals">
                <div class="category-pill-bar" id="category-pill-bar">
                    <!-- Category pills injected by JS -->
                </div>
                <div id="top-deals-error" class="error hidden"></div>
                <div id="top-deals-skeleton" class="product-grid hidden">
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                    <div class="skeleton-card"><div class="skeleton-img"></div><div class="skeleton-text"></div><div class="skeleton-text short"></div></div>
                </div>
                <div id="top-deals-grid" class="product-grid">
                    <!-- Top deal products injected by JS -->
                </div>
            </div>
        </main>
    </div>
    <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Add new styles to `static/style.css`**

Append the following to the end of `static/style.css` (after line 448):

```css

/* ───────────── Tab Bar ───────────── */
.tab-bar {
    display: flex;
    position: relative;
    gap: 0;
    padding: 0.5rem;
    margin-bottom: 2rem;
    overflow: hidden;
}

.tab-btn {
    flex: 1;
    background: transparent;
    color: var(--text-secondary);
    border: none;
    border-radius: var(--radius-sm);
    padding: 1rem 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    font-family: var(--font-family);
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
}

.tab-btn:hover {
    color: var(--text-primary);
    transform: none;
    box-shadow: none;
}

.tab-btn.active {
    color: var(--text-primary);
}

.tab-icon {
    font-size: 1.2rem;
}

.tab-indicator {
    position: absolute;
    bottom: 0.5rem;
    left: 0.5rem;
    height: calc(100% - 1rem);
    width: calc(50% - 0.5rem);
    background: rgba(123, 44, 191, 0.15);
    border: 1px solid rgba(123, 44, 191, 0.3);
    border-radius: var(--radius-sm);
    transition: transform 0.35s cubic-bezier(0.25, 0.8, 0.25, 1);
    z-index: 0;
}

.tab-indicator.pos-1 {
    transform: translateX(calc(100% + 0.5rem));
}

/* ───────────── Tab Panes ───────────── */
.tab-pane {
    display: none;
    animation: fadeIn 0.3s ease;
}

.tab-pane.active {
    display: block;
}

/* ───────────── Category Pill Bar ───────────── */
.category-pill-bar {
    display: flex;
    gap: 0.75rem;
    overflow-x: auto;
    padding: 0.5rem 0 1.5rem 0;
    scrollbar-width: thin;
    scrollbar-color: rgba(123, 44, 191, 0.3) transparent;
    -webkit-overflow-scrolling: touch;
}

.category-pill-bar::-webkit-scrollbar {
    height: 4px;
}

.category-pill-bar::-webkit-scrollbar-track {
    background: transparent;
}

.category-pill-bar::-webkit-scrollbar-thumb {
    background: rgba(123, 44, 191, 0.3);
    border-radius: 4px;
}

.category-pill {
    flex-shrink: 0;
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--panel-border);
    border-radius: 24px;
    padding: 0.6rem 1.4rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: var(--transition);
    font-family: var(--font-family);
    white-space: nowrap;
}

.category-pill:hover {
    color: var(--text-primary);
    border-color: var(--accent-color);
    transform: none;
    box-shadow: none;
}

.category-pill.active {
    background: var(--accent-color);
    color: white;
    border-color: var(--accent-color);
    box-shadow: 0 0 20px var(--accent-glow);
}

.category-pill.loading {
    animation: pillPulse 1.2s ease-in-out infinite;
}

@keyframes pillPulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ───────────── Deal Score Badge ───────────── */
.deal-score-badge {
    position: absolute;
    top: 1rem;
    left: 1rem;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    color: white;
    z-index: 2;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
}

.deal-score-badge.score-high {
    background: linear-gradient(135deg, #06d6a0, #00b894);
}

.deal-score-badge.score-mid {
    background: linear-gradient(135deg, #ffd166, #f4a261);
}

.deal-score-badge.score-low {
    background: linear-gradient(135deg, #ef476f, #e63946);
}

/* ───────────── Skeleton Loading ───────────── */
.skeleton-card {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: var(--radius-md);
    overflow: hidden;
    min-height: 360px;
}

.skeleton-img {
    width: 100%;
    height: 200px;
    background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
}

.skeleton-text {
    height: 16px;
    margin: 1rem 1.5rem 0;
    border-radius: 4px;
    background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
}

.skeleton-text.short {
    width: 60%;
    margin-top: 0.75rem;
}

@keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}
```

- [ ] **Step 3: Rewrite `static/app.js` with tab logic and category fetching**

Replace entire contents of `static/app.js`:

```javascript
document.addEventListener('DOMContentLoaded', () => {
    // ─── Existing Search Tab Elements ───
    const searchForm = document.getElementById('search-form');
    const resultsSection = document.getElementById('results-section');
    const loadingSpinner = document.getElementById('loading-spinner');
    const productGrid = document.getElementById('product-grid');
    const errorMessage = document.getElementById('error-message');
    const cacheStatus = document.getElementById('cache-status');

    // ─── Tab Elements ───
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const tabIndicator = document.getElementById('tab-indicator');

    // ─── Top Deals Elements ───
    const categoryPillBar = document.getElementById('category-pill-bar');
    const topDealsGrid = document.getElementById('top-deals-grid');
    const topDealsSkeleton = document.getElementById('top-deals-skeleton');
    const topDealsError = document.getElementById('top-deals-error');

    let topDealsInitialized = false;
    let currentAbortController = null;

    // ─── Tab Switching ───
    tabBtns.forEach((btn, index) => {
        btn.addEventListener('click', () => {
            // Update active tab button
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Move indicator
            tabIndicator.className = 'tab-indicator';
            if (index > 0) {
                tabIndicator.classList.add(`pos-${index}`);
            }

            // Show corresponding pane
            const targetId = btn.getAttribute('data-tab');
            tabPanes.forEach(pane => pane.classList.remove('active'));
            document.getElementById(targetId).classList.add('active');

            // Initialize top deals on first visit
            if (targetId === 'tab-top-deals' && !topDealsInitialized) {
                topDealsInitialized = true;
                loadCategories();
            }
        });
    });

    // ─── Load Categories ───
    async function loadCategories() {
        try {
            const resp = await fetch('/api/categories');
            const categories = await resp.json();
            renderCategoryPills(categories);

            // Auto-load first category
            if (categories.length > 0) {
                fetchCategoryDeals(categories[0].node, categories[0].name);
            }
        } catch (err) {
            topDealsError.textContent = 'Failed to load categories.';
            topDealsError.classList.remove('hidden');
        }
    }

    function renderCategoryPills(categories) {
        categoryPillBar.innerHTML = '';
        categories.forEach((cat, idx) => {
            const pill = document.createElement('button');
            pill.className = 'category-pill' + (idx === 0 ? ' active' : '');
            pill.textContent = cat.name;
            pill.setAttribute('data-node', cat.node);
            pill.setAttribute('data-name', cat.name);
            pill.addEventListener('click', () => {
                // Update active pill
                document.querySelectorAll('.category-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                fetchCategoryDeals(cat.node, cat.name);
            });
            categoryPillBar.appendChild(pill);
        });
    }

    // ─── Fetch Category Deals ───
    async function fetchCategoryDeals(node, name) {
        // Abort previous request
        if (currentAbortController) {
            currentAbortController.abort();
        }
        currentAbortController = new AbortController();

        // Show skeleton, hide grid and error
        topDealsSkeleton.classList.remove('hidden');
        topDealsGrid.innerHTML = '';
        topDealsError.classList.add('hidden');

        // Mark pill as loading
        const activePill = document.querySelector(`.category-pill[data-node="${node}"]`);
        if (activePill) activePill.classList.add('loading');

        try {
            const resp = await fetch(
                `/api/top-deals?category=${encodeURIComponent(node)}`,
                { signal: currentAbortController.signal }
            );

            if (!resp.ok) {
                const errData = await resp.json();
                throw new Error(errData.detail || 'Failed to fetch top deals');
            }

            const data = await resp.json();

            if (data.error) {
                topDealsError.textContent = data.error;
                topDealsError.classList.remove('hidden');
            } else {
                renderProducts(data.products, topDealsGrid, true);
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                topDealsError.textContent = err.message || 'Failed to load deals for this category.';
                topDealsError.classList.remove('hidden');
            }
        } finally {
            topDealsSkeleton.classList.add('hidden');
            if (activePill) activePill.classList.remove('loading');
        }
    }

    // ─── Existing Search Form Handler ───
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const query = document.getElementById('query').value.trim();
        const minDiscount = document.getElementById('min_discount').value;
        const maxDiscount = document.getElementById('max_discount').value;

        if (!query) return;

        let url = `/api/search?query=${encodeURIComponent(query)}`;
        if (minDiscount) url += `&min_discount=${minDiscount}`;
        if (maxDiscount) url += `&max_discount=${maxDiscount}`;

        resultsSection.classList.remove('hidden');
        loadingSpinner.classList.remove('hidden');
        productGrid.innerHTML = '';
        errorMessage.classList.add('hidden');
        cacheStatus.classList.add('hidden');
        cacheStatus.textContent = '';
        cacheStatus.className = 'badge hidden';

        try {
            const response = await fetch(url);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to fetch deals');
            }

            const data = await response.json();

            if (data.metadata && data.metadata.source) {
                cacheStatus.classList.remove('hidden');
                if (data.metadata.source === 'cache') {
                    cacheStatus.textContent = 'Served from Cache';
                    cacheStatus.classList.add('cached');
                } else {
                    cacheStatus.textContent = 'Live Fetch';
                    cacheStatus.classList.add('live');
                }
            }

            renderProducts(data.products, productGrid, false);

        } catch (error) {
            errorMessage.textContent = error.message;
            errorMessage.classList.remove('hidden');
        } finally {
            loadingSpinner.classList.add('hidden');
        }
    });

    // ─── Shared Product Renderer ───
    function renderProducts(products, targetGrid, showDealScore) {
        if (!products || products.length === 0) {
            const errorEl = targetGrid === productGrid ? errorMessage : topDealsError;
            errorEl.textContent = 'No deals found matching your criteria.';
            errorEl.classList.remove('hidden');
            return;
        }

        targetGrid.innerHTML = '';

        products.forEach(product => {
            const card = document.createElement('div');
            card.className = 'product-card';

            const imgUrl = product.image_url || 'https://via.placeholder.com/200x200?text=No+Image';

            const formatPrice = (price) => {
                if (price === null || price === undefined) return 'N/A';
                return `₹${price.toLocaleString('en-IN')}`;
            };

            const currentPriceText = formatPrice(product.current_price);
            const originalPriceText = product.original_price ? formatPrice(product.original_price) : '';

            let discountBadge = '';
            if (product.discount_pct) {
                discountBadge = `<div class="discount-badge">${product.discount_pct}% OFF</div>`;
            }

            let verifiedBadge = '';
            if (product.is_true_deal) {
                verifiedBadge = `<div class="verified-badge">✓ Verified Deal</div>`;
                card.classList.add('true-deal');
            }

            // Deal score badge (only in Top Deals tab)
            let dealScoreBadge = '';
            if (showDealScore && product.deal_score != null) {
                const score = product.deal_score;
                let scoreClass = 'score-low';
                if (score >= 80) scoreClass = 'score-high';
                else if (score >= 60) scoreClass = 'score-mid';
                dealScoreBadge = `<div class="deal-score-badge ${scoreClass}">${score}</div>`;
            }

            const ratingHtml = product.rating ?
                `<span class="star-icon">★</span> <span class="rating-text">${product.rating}</span>` :
                `<span class="rating-text">No rating</span>`;

            card.innerHTML = `
                ${discountBadge}
                ${showDealScore ? dealScoreBadge : verifiedBadge}
                <div class="image-container">
                    <img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(product.title)}" class="product-image" loading="lazy">
                </div>
                <div class="product-info">
                    <h3 class="product-title" title="${escapeHtml(product.title)}">${escapeHtml(product.title)}</h3>
                    <div class="product-rating">
                        ${ratingHtml}
                    </div>
                    <div class="price-container">
                        <span class="current-price">${currentPriceText}</span>
                        ${originalPriceText ? `<span class="original-price">${originalPriceText}</span>` : ''}
                    </div>
                    <a href="${escapeHtml(product.product_url)}" target="_blank" rel="noopener noreferrer" class="view-btn">View on Amazon</a>
                    ${product.asin ? `<button class="keepa-btn" data-asin="${escapeHtml(product.asin)}">View Price History</button>` : ''}
                    <div class="keepa-graph-container">
                        <div class="keepa-loading">Loading graph...</div>
                        <img alt="Price History Graph" class="keepa-img" style="display:none;" />
                    </div>
                </div>
            `;

            // Keepa button handler
            const keepaBtn = card.querySelector('.keepa-btn');
            if (keepaBtn) {
                keepaBtn.addEventListener('click', () => {
                    const container = card.querySelector('.keepa-graph-container');
                    const img = container.querySelector('.keepa-img');
                    const loading = container.querySelector('.keepa-loading');

                    if (container.classList.contains('active')) {
                        container.classList.remove('active');
                        keepaBtn.textContent = 'View Price History';
                    } else {
                        container.classList.add('active');
                        keepaBtn.textContent = 'Hide Price History';

                        if (!img.getAttribute('src')) {
                            const asin = keepaBtn.getAttribute('data-asin');
                            img.setAttribute('src', `https://graph.keepa.com/pricehistory?asin=${asin}&domain=10&range=365`);
                            img.onload = () => {
                                loading.style.display = 'none';
                                img.style.display = 'block';
                            };
                            img.onerror = () => {
                                loading.textContent = 'Failed to load graph';
                                loading.style.color = '#ef233c';
                            };
                        }
                    }
                });
            }

            targetGrid.appendChild(card);
        });
    }

    // ─── XSS Prevention Helper ───
    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
             .toString()
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }
});
```

- [ ] **Step 4: Manual verification — start the server and test both tabs**

Run: `python main.py`
Then open `http://localhost:8000` in the browser and verify:
1. Tab bar renders with "Search Deals" and "Top Deals" tabs
2. Search tab works identically to before
3. Clicking "Top Deals" tab shows category pills and auto-loads Electronics
4. Clicking a category pill shows skeleton loading then product cards with deal scores
5. Deal score badges show correct color tiers (green/amber/red)
6. Rapid pill switching doesn't cause stale data

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/style.css static/app.js
git commit -m "feat: add Top Deals tab with category pills, deal scores, and skeleton loading"
```

---

