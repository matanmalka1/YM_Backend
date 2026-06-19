"""
Health check endpoint for production readiness.

Provides:
- Unauthenticated health status
- Database connectivity verification
- Read-only operation
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.health.health_schemas import HealthCheckResponse
from app.health.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthCheckResponse}},
    status_code=status.HTTP_200_OK,
)
def health_check(db: Session = Depends(get_db)) -> HealthCheckResponse | JSONResponse:
    """
    Health check endpoint.

    Verifies:
    - Application is running
    - Database connection is available

    Returns 200 if healthy, 503 if unhealthy.
    """
    result = HealthService(db).check()
    if result["status"] != "healthy":
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=result)
    return HealthCheckResponse(**result)


@router.get(
    "/ready",
    response_model=HealthCheckResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthCheckResponse}},
    status_code=status.HTTP_200_OK,
)
def readiness_check(db: Session = Depends(get_db)) -> HealthCheckResponse | JSONResponse:
    """Return readiness status for platform health checks."""
    result = HealthService(db).check()
    if result["status"] != "healthy":
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=result)
    return HealthCheckResponse(**result)
