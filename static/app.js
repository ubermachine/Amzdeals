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
    const topDealsSort = document.getElementById('top-deals-sort');
    const topDealsCount = document.getElementById('top-deals-count');

    let topDealsInitialized = false;
    let currentAbortController = null;
    let currentCategoryNode = null;
    let currentCategoryName = null;
    let currentSortBy = 'popularity';
    let currentPriceMin = 0;
    let currentPriceMax = Infinity;
    let currentLoadedProducts = [];

    // ─── In-memory Filter & Sort Helper ───
    function applyFiltersAndSorting(products, sortBy, minPrice = currentPriceMin, maxPrice = currentPriceMax) {
        if (!products || products.length === 0) return [];

        // 1. In-memory Budget / Price filtering
        const filtered = products.filter(p => {
            const price = p.current_price;
            if (price == null) return true; // keep if price unparsed
            return price >= minPrice && price <= maxPrice;
        });

        // 2. Sorting
        const sorted = [...filtered];
        if (sortBy === 'deal_score') {
            sorted.sort((a, b) => (b.deal_score ?? -1) - (a.deal_score ?? -1));
        } else if (sortBy === 'discount') {
            sorted.sort((a, b) => (b.discount_pct ?? -1) - (a.discount_pct ?? -1));
        } else if (sortBy === 'reviews') {
            sorted.sort((a, b) => (b.review_count ?? -1) - (a.review_count ?? -1));
        } else if (sortBy === 'popularity' || sortBy === 'bestsellers') {
            sorted.sort((a, b) => (a._original_rank ?? 9999) - (b._original_rank ?? 9999));
        }
        return sorted;
    }

    function updateTopDealsView() {
        if (!currentLoadedProducts || currentLoadedProducts.length === 0) return;

        const visibleProducts = applyFiltersAndSorting(currentLoadedProducts, currentSortBy, currentPriceMin, currentPriceMax);

        if (visibleProducts.length === 0) {
            topDealsGrid.innerHTML = '';
            topDealsError.innerHTML = `<span>No deals match the selected budget filter. Try choosing "All Prices" or another range.</span>`;
            topDealsError.classList.remove('hidden');
            if (topDealsCount) {
                topDealsCount.textContent = '0 Deals';
                topDealsCount.classList.remove('hidden');
            }
        } else {
            topDealsError.classList.add('hidden');
            renderProducts(visibleProducts, topDealsGrid, true, currentSortBy);
            if (topDealsCount) {
                if (currentPriceMin > 0 || currentPriceMax < Infinity) {
                    topDealsCount.textContent = `Showing ${visibleProducts.length} of ${currentLoadedProducts.length} Deals`;
                } else {
                    topDealsCount.textContent = `Showing ${visibleProducts.length} Deals`;
                }
                topDealsCount.classList.remove('hidden');
            }
        }
    }

    function resetPriceFilter() {
        currentPriceMin = 0;
        currentPriceMax = Infinity;
        document.querySelectorAll('.price-pill').forEach(btn => {
            const min = parseFloat(btn.getAttribute('data-min'));
            const max = parseFloat(btn.getAttribute('data-max'));
            if (min === 0 && max === Infinity) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    function handleSortChange(newSortBy) {
        currentSortBy = newSortBy;

        // Sync Sort Pills
        document.querySelectorAll('.sort-pill').forEach(btn => {
            if (btn.getAttribute('data-sort') === newSortBy) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Sync Select Dropdown
        if (topDealsSort && topDealsSort.value !== newSortBy) {
            topDealsSort.value = newSortBy;
        }

        // Instant 0ms In-Memory Re-sort and filter
        updateTopDealsView();

        // Server-side fetch in background without wiping grid with skeleton
        if (currentCategoryNode) {
            fetchCategoryDeals(currentCategoryNode, currentCategoryName, newSortBy, false);
        }
    }

    function handlePriceChange(min, max) {
        currentPriceMin = min;
        currentPriceMax = max;

        // Sync Price Pills
        document.querySelectorAll('.price-pill').forEach(btn => {
            const btnMin = parseFloat(btn.getAttribute('data-min'));
            const btnMax = parseFloat(btn.getAttribute('data-max'));
            if (btnMin === min && btnMax === max) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Instant 0ms In-Memory Filter update
        updateTopDealsView();
    }

    // Attach click listeners to Sort Pills
    document.querySelectorAll('.sort-pill').forEach(pill => {
        pill.addEventListener('click', (e) => {
            e.preventDefault();
            const sortBy = pill.getAttribute('data-sort');
            handleSortChange(sortBy);
        });
    });

    // Attach click listeners to Price Pills
    document.querySelectorAll('.price-pill').forEach(pill => {
        pill.addEventListener('click', (e) => {
            e.preventDefault();
            const min = parseFloat(pill.getAttribute('data-min'));
            const max = parseFloat(pill.getAttribute('data-max'));
            handlePriceChange(min, max);
        });
    });

    if (topDealsSort) {
        topDealsSort.addEventListener('change', (e) => {
            handleSortChange(e.target.value);
        });
    }

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
            pill.textContent = cat.icon ? `${cat.icon} ${cat.name}` : cat.name;
            pill.setAttribute('data-node', cat.node);
            pill.setAttribute('data-name', cat.name);
            pill.addEventListener('click', () => {
                // Update active pill
                document.querySelectorAll('.category-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                resetPriceFilter();
                fetchCategoryDeals(cat.node, cat.name);
            });
            categoryPillBar.appendChild(pill);
        });
    }

    function showTopDealsError(msg) {
        topDealsError.innerHTML = `
            <div class="error-content">
                <span>${escapeHtml(msg)}</span>
                <button type="button" class="retry-btn" id="retry-deals-btn">🔄 Retry</button>
            </div>
        `;
        topDealsError.classList.remove('hidden');
        const retryBtn = document.getElementById('retry-deals-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => {
                if (currentCategoryNode) {
                    fetchCategoryDeals(currentCategoryNode, currentCategoryName, currentSortBy, true);
                }
            });
        }
    }

    // ─── Fetch Category Deals ───
    async function fetchCategoryDeals(node, name, sortBy = currentSortBy, showSkeleton = true) {
        currentCategoryNode = node;
        currentCategoryName = name;
        currentSortBy = sortBy;

        // Abort previous request
        if (currentAbortController) {
            currentAbortController.abort();
        }
        currentAbortController = new AbortController();
        const controller = currentAbortController;

        if (showSkeleton) {
            topDealsSkeleton.classList.remove('hidden');
            topDealsGrid.innerHTML = '';
            topDealsError.classList.add('hidden');
            if (topDealsCount) topDealsCount.classList.add('hidden');
        }

        // Mark category pill as loading
        document.querySelectorAll('.category-pill').forEach(p => p.classList.remove('loading'));
        const activePill = document.querySelector(`.category-pill[data-node="${node}"]`);
        if (activePill) activePill.classList.add('loading');

        try {
            const resp = await fetch(
                `/api/top-deals?category=${encodeURIComponent(node)}&sort_by=${encodeURIComponent(sortBy)}`,
                { signal: currentAbortController.signal }
            );

            if (!resp.ok) {
                const errData = await resp.json();
                throw new Error(errData.detail || 'Failed to fetch top deals');
            }

            const data = await resp.json();

            if (data.error) {
                showTopDealsError(data.error);
            } else if (data.products) {
                // Preserve original rank order from Amazon
                data.products.forEach((p, idx) => {
                    p._original_rank = idx + 1;
                });
                currentLoadedProducts = data.products;
                updateTopDealsView();
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                showTopDealsError(err.message || 'Failed to load deals for this category.');
            }
        } finally {
            if (currentAbortController === controller) {
                topDealsSkeleton.classList.add('hidden');
                if (activePill) activePill.classList.remove('loading');
            }
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
    function renderProducts(products, targetGrid, showDealScore, sortBy = null) {
        if (!products || products.length === 0) {
            const errorEl = targetGrid === productGrid ? errorMessage : topDealsError;
            errorEl.textContent = 'No deals found matching your criteria.';
            errorEl.classList.remove('hidden');
            return;
        }

        targetGrid.innerHTML = '';

        products.forEach((product, idx) => {
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

            let rankBadge = '';
            if (sortBy === 'popularity' || sortBy === 'bestsellers') {
                rankBadge = `<div class="rank-badge" title="Popularity Rank #${idx + 1}">#${idx + 1}</div>`;
            }

            let amazonBadge = '';
            if (product.badge) {
                const isChoice = product.badge.toLowerCase().includes('choice');
                const badgeClass = isChoice ? 'badge-choice' : 'badge-bestseller';
                const badgeIcon = isChoice ? '✨' : '🔥';
                amazonBadge = `<span class="amazon-badge ${badgeClass}">${badgeIcon} ${escapeHtml(product.badge)}</span>`;
            }

            let verifiedBadge = '';
            let trueDealTag = '';
            if (product.is_true_deal) {
                verifiedBadge = `<div class="verified-badge">✓ Verified Deal</div>`;
                trueDealTag = `<span class="verified-tag">✓ Verified Deal</span>`;
                card.classList.add('true-deal');
            }

            // Cross-market Flipkart badge
            let flipkartBadge = '';
            if (product.cross_market && product.cross_market.match_found) {
                const cm = product.cross_market;
                const fkPriceFormatted = cm.flipkart_price ? `₹${Math.round(cm.flipkart_price).toLocaleString('en-IN')}` : '';
                const diffFormatted = cm.price_diff ? `₹${Math.round(cm.price_diff).toLocaleString('en-IN')}` : '';
                const savingsFormatted = cm.flipkart_savings ? `₹${Math.round(cm.flipkart_savings).toLocaleString('en-IN')}` : '';
                const fkUrl = cm.flipkart_url || '#';

                if (cm.verdict === 'true_deal') {
                    flipkartBadge = `
                        <a href="${escapeHtml(fkUrl)}" target="_blank" rel="noopener noreferrer" class="flipkart-badge fk-deal" title="Flipkart price: ${fkPriceFormatted} (Confidence: ${cm.match_confidence}%)">
                            <span class="fk-icon">⚡</span> Best Price: ${diffFormatted} cheaper than Flipkart ↗
                        </a>
                    `;
                } else if (cm.verdict === 'market_parity') {
                    flipkartBadge = `
                        <a href="${escapeHtml(fkUrl)}" target="_blank" rel="noopener noreferrer" class="flipkart-badge fk-parity" title="Flipkart price: ${fkPriceFormatted} (Within ±5% market parity)">
                            <span class="fk-icon">⚖️</span> Market Parity (${fkPriceFormatted} on Flipkart) ↗
                        </a>
                    `;
                } else if (cm.verdict === 'cheaper_on_flipkart') {
                    flipkartBadge = `
                        <a href="${escapeHtml(fkUrl)}" target="_blank" rel="noopener noreferrer" class="flipkart-badge fk-cheaper" title="Amazon price is higher than Flipkart">
                            <span class="fk-icon">⚠️</span> Cheaper on Flipkart: Save ${savingsFormatted} (${fkPriceFormatted}) ↗
                        </a>
                    `;
                }
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

            // Ratings and review count
            let ratingHtml = '<span class="rating-text">No rating</span>';
            if (product.rating) {
                const revCountText = product.review_count != null ?
                    `<span class="review-count">(${product.review_count.toLocaleString('en-IN')})</span>` : '';
                ratingHtml = `<span class="star-icon">★</span> <span class="rating-text">${product.rating}</span> ${revCountText}`;
            }

            card.innerHTML = `
                ${discountBadge}
                ${rankBadge}
                ${showDealScore ? dealScoreBadge : verifiedBadge}
                <div class="image-container">
                    <img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(product.title)}" class="product-image" loading="lazy">
                </div>
                <div class="product-info">
                    <div class="product-badges-row">
                        ${amazonBadge}
                        ${trueDealTag}
                    </div>
                    <h3 class="product-title" title="${escapeHtml(product.title)}">${escapeHtml(product.title)}</h3>
                    <div class="product-rating">
                        ${ratingHtml}
                    </div>
                    <div class="price-container">
                        <span class="current-price">${currentPriceText}</span>
                        ${originalPriceText ? `<span class="original-price">${originalPriceText}</span>` : ''}
                    </div>
                    ${flipkartBadge}
                    <a href="${escapeHtml(product.product_url)}" target="_blank" rel="noopener noreferrer" class="view-btn">View on Amazon</a>
                    ${product.asin ? `<button class="keepa-btn" data-asin="${escapeHtml(product.asin)}">View Price History</button>` : ''}
                    <div class="keepa-graph-container">
                        <div class="keepa-loading">Loading graph...</div>
                        <img alt="Price History Graph" class="keepa-img" referrerpolicy="no-referrer" style="display:none;" />
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
                            const proxyUrl = `/api/keepa-graph?asin=${encodeURIComponent(asin)}&range=365`;
                            const directUrl = `https://graph.keepa.com/pricehistory?asin=${encodeURIComponent(asin)}&domain=10&range=365`;

                            img.referrerPolicy = 'no-referrer';
                            let hasFallbackRun = false;

                            img.onload = () => {
                                loading.style.display = 'none';
                                img.style.display = 'block';
                            };

                            img.onerror = () => {
                                if (!hasFallbackRun) {
                                    hasFallbackRun = true;
                                    img.setAttribute('src', directUrl);
                                } else {
                                    loading.textContent = 'Price history unavailable for this product';
                                    loading.style.color = '#ef233c';
                                }
                            };

                            img.setAttribute('src', proxyUrl);
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
