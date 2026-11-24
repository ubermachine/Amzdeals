from fastapi import Query
from pydantic import BaseModel

class QuerySearchDto(BaseModel):
    query: str = Query(..., min_length=1, description="Search term (e.g., Perfume)"),
    min_discount: int = Query(10, ge=0, le=99, description="Minimum discount %"),
    max_discount: int = Query(99, ge=1, le=100, description="Maximum discount %"),
    page: int = Query(1, ge=1, le=100, description="Page number"),
    min_price: int = Query(1000, ge=0, le=100000, description="Minimum price"),
    max_price: int = Query(100000, ge=0, le=100000, description="Maximum price"),
    min_rating: float = Query(3, ge=0, le=5, description="Min rating"),
    sort_by: str = Query("bestsellers", description="Sort order: bestsellers, popularity, reviews, featured"),