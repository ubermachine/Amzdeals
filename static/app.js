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
