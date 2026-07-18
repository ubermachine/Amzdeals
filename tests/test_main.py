import pytest
from fastapi.testclient import TestClient

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
