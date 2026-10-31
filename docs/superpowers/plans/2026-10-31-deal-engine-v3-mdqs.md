# Implementation Plan: Deal Engine v3.0 (MDQS - Multi-Dimensional Deal Quality Score)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul DealFinder's scoring, parsing, anti-scam defense, and cross-market arbitrage into a high-precision, fraud-resistant engine that values real cash savings and stops catalog manipulation.

**Architecture:**
- Modernized Bayesian + CLT log-reviews + absolute rupee cash utility formula.
- Amazon coupon extraction with effective price deduction ($P_{\text{eff}} = P_{\text{curr}} - C$).
- Catalog anti-scam safeguards: refurbished relic detection, accessory smuggling filters, and multi-pack unit price checks.
- Adaptive Flipkart parity band $\tau(P) = \max(50, \min(0.035P, 1500))$ and asymmetric multiplicative score crush ($S \times 0.15 \le 12$) for fake deals.

**Tech Stack:** Python 3.14, FastAPI, BeautifulSoup4, curl_cffi, SQLite3, Vanilla JS / CSS.

## Global Constraints
- Strictly follow `user_global`: NO screenshots during automated testing or MCP verification; inspect DOM, console logs, and network responses only.
- Universal category coverage: All 18 categories must remain functional.
- Zero test regressions: 100% test pass rate on pytest.
- Strict concurrency guard and fail-fast timeouts on external network requests.

---

### Task 1: Parser & Anti-Scam Upgrades (`scraper/parser.py`, `config.py`)
- Extract numeric coupon discounts (e.g. "Save ₹500 with coupon", "Apply 10% coupon").
- Compute `coupon_discount` and `effective_price`.
- Extract `is_refurbished` (detect "(Renewed)", "(Refurbished)", "Pre-owned").
- Extract `is_accessory` for device categories.
- Extract `pack_count` for multi-packs.

### Task 2: Multi-Dimensional Deal Quality Score v3.0 (`scraper/engine.py`)
- Implement $U_{\text{relative}}$, $U_{\text{cash}}(\Delta \text{INR})$, shifted Bayesian $U_{\text{rating}}$, and logarithmic $U_{\text{reviews}}$.
- Apply trust adjustments: Prime (+6), Best Seller (+4), unreviewed dropshipper (-15), Refurbished (-20).
- Filter accessory smuggling and filter multi-pack price inflation in `search_category_deals()`.

### Task 3: Adaptive Flipkart Parity & Arbitrage Crush (`scraper/flipkart.py`, `scraper/engine.py`)
- Implement `adaptive_parity_band(price)` in `scraper/flipkart.py`.
- Pass `effective_price` to Flipkart search & scoring.
- Add refurbished conflict check in `has_chipset_or_series_conflict()`.
- Upgrade Flipkart verdict penalty in `scraper/engine.py` with multiplicative score crush.

### Task 4: Frontend UI Badging & Polish (`static/app.js`, `static/style.css`, `static/index.html`)
- Render coupon badge with effective price on deal cards.
- Render cash savings badge (`💰 Save ₹X,XXX`).
- Render refurbished badge (`♻️ Renewed`).
- Bump version to `v2.2.0` across `config.py`, `main.py`, and `index.html`.

### Task 5: Comprehensive Unit & Integration Tests
- Write unit tests for coupon parsing, effective price, cash utility, adaptive parity, and refurbished penalties.
- Run pytest suite and ensure 100% pass rate.

### Task 6: 3-Super-Agent Speed & Optimization Summit
- Dispatch 3 parallel subagents to analyze caching, async pooling, latency bottlenecks, and memory footprint.
- Synthesize actionable optimizations.

### Task 7: Full End-to-End MCP Verification
- Run live test on `http://127.0.0.1:8000` via Chrome DevTools MCP.
- Verify search deals, top category deals, coupon rendering, budget filters, and Flipkart parity badges.
