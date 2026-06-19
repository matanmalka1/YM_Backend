from __future__ import annotations

from fastapi import APIRouter

from app.signature_requests.api.signature_request_routes_advisor import advisor_router
from app.signature_requests.api.signature_request_routes_client import client_router
from app.signature_requests.api.signature_request_routes_signer import signer_router

router = APIRouter()
router.include_router(advisor_router)
router.include_router(client_router)

__all__ = ["router", "signer_router"]
