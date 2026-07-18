document.addEventListener('DOMContentLoaded', () => {
    const searchForm = document.getElementById('search-form');
    const resultsSection = document.getElementById('results-section');
    const loadingSpinner = document.getElementById('loading-spinner');
    const productGrid = document.getElementById('product-grid');
    const errorMessage = document.getElementById('error-message');
    const cacheStatus = document.getElementById('cache-status');

    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Get form values
        const query = document.getElementById('query').value.trim();
        const minDiscount = document.getElementById('min_discount').value;
        const maxDiscount = document.getElementById('max_discount').value;

        if (!query) return;

        // Construct API URL
        let url = `/api/search?query=${encodeURIComponent(query)}`;
        if (minDiscount) url += `&min_discount=${minDiscount}`;
        if (maxDiscount) url += `&max_discount=${maxDiscount}`;

        // Reset UI
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
            
            // Show cache status
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

            renderProducts(data.results);
            
        } catch (error) {
            errorMessage.textContent = error.message;
            errorMessage.classList.remove('hidden');
        } finally {
            loadingSpinner.classList.add('hidden');
        }
    });

    function renderProducts(products) {
        if (!products || products.length === 0) {
            errorMessage.textContent = 'No deals found matching your criteria.';
            errorMessage.classList.remove('hidden');
            return;
        }

        products.forEach(product => {
            const card = document.createElement('div');
            card.className = 'product-card';
            
            // Default image if missing
            const imgUrl = product.image_url || 'https://via.placeholder.com/200x200?text=No+Image';
            
            // Format prices
            const formatPrice = (price) => {
                if (price === null || price === undefined) return 'N/A';
                return `₹${price.toLocaleString('en-IN')}`;
            };
            
            const currentPriceText = formatPrice(product.price);
            const originalPriceText = product.original_price ? formatPrice(product.original_price) : '';
            
            // Calculate and display discount badge if available
            let discountBadge = '';
            if (product.discount_percentage) {
                discountBadge = `<div class="discount-badge">${product.discount_percentage}% OFF</div>`;
            }

            let verifiedBadge = '';
            if (product.is_true_deal) {
                verifiedBadge = `<div class="verified-badge">✓ Verified Deal</div>`;
                card.classList.add('true-deal');
            }

            // Rating display
            const ratingHtml = product.rating ? 
                `<span class="star-icon">★</span> <span class="rating-text">${product.rating}</span>` : 
                `<span class="rating-text">No rating</span>`;

            card.innerHTML = `
                ${discountBadge}
                ${verifiedBadge}
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
                    <a href="${escapeHtml(product.url)}" target="_blank" rel="noopener noreferrer" class="view-btn">View on Amazon</a>
                    ${product.asin ? `<button class="keepa-btn" data-asin="${escapeHtml(product.asin)}">View Price History</button>` : ''}
                    <div class="keepa-graph-container">
                        <div class="keepa-loading">Loading graph...</div>
                        <img alt="Price History Graph" class="keepa-img" style="display:none;" />
                    </div>
                </div>
            `;
            
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
                            img.setAttribute('src', `https://graph.keepa.com/pricehistory?asin=${asin}&domain=11`);
                            img.onload = () => {
                                loading.style.display = 'none';
                                img.style.display = 'block';
                            };
                            img.onerror = () => {
                                loading.textContent = 'Failed to load graph';
                                loading.style.color = '#ef233c'; // error color
                            };
                        }
                    }
                });
            }
            
            productGrid.appendChild(card);
        });
    }

    // Helper to prevent XSS
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
