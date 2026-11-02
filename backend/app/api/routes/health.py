"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return a simple payload confirming the backend is running."""
    return {"status": "ok", "service": "backend"}
