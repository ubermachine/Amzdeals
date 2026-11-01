import pytest
from fastapi.testclient import TestClient

import config
from main import app

# Use TestClient with context manager to trigger lifespan events (cache init/close)
@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_api_search_missing_query(client):
    response = client.get("/api/search")
    assert response.status_code == 422  # Validation error for missing 'query'


def test_api_search_valid(client, monkeypatch):
    # Mock the search_deals function to avoid hitting Amazon in tests
    import main
    
    async def mock_search(*args, **kwargs):
        return {
            "query": "Perfume",
            "page": 1,
            "products": [{"asin": "123", "title": "Test Product"}],
            "total_results": 1,
            "cached": False
        }
        
    monkeypatch.setattr(main, "search_deals", mock_search)
    
    response = client.get("/api/search?query=Perfume&min_discount=40&max_discount=90&page=1")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Perfume"
    assert data["total_results"] == 1
    assert data["products"][0]["asin"] == "123"


def test_static_files_served(client):
    # Depending on how the static file is mounted, this should return a 200 or 404 (if empty)
    # but the server itself should not 500 or crash.
    response = client.get("/")
    assert response.status_code in (200, 404)


def test_api_version_endpoint(client):
    """Verify /api/version returns release metadata."""
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == config.APP_VERSION
    assert data["release"] == f"v{config.APP_VERSION}"
    assert data["status"] == "healthy"


def test_api_snapshot_endpoints(client):
    """Verify daily snapshot REST API endpoints."""
    # 1. Dates endpoint
    res_dates = client.get("/api/snapshots/dates")
    assert res_dates.status_code == 200
    assert isinstance(res_dates.json(), list)

    # 2. Dump endpoint
    res_dump = client.post("/api/snapshots/dump?date=2026-11-01")
    assert res_dump.status_code == 200
    dump_data = res_dump.json()
    assert dump_data["status"] == "success"

    # 3. Deals endpoint
    res_deals = client.get("/api/snapshots/deals?date=2026-11-01")
    assert res_deals.status_code == 200
    deals_data = res_deals.json()
    assert deals_data["snapshot_date"] == "2026-11-01"
    assert "deals" in deals_data

    # 4. Compare endpoint
    res_comp = client.get("/api/snapshots/compare?date1=2026-11-01&date2=2026-11-01")
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert "summary" in comp_data
    assert "price_drops" in comp_data
    assert "new_deals" in comp_data
