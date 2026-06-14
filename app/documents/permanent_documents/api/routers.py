"""Permanent documents API router aggregating sub-routers."""

from fastapi import APIRouter

from app.documents.permanent_documents.api.permanent_document_actions import (
    router as permanent_document_actions_router,
)
from app.documents.permanent_documents.api.permanent_documents import (
    router as permanent_documents_router,
)

router = APIRouter()
router.include_router(permanent_document_actions_router)
router.include_router(permanent_documents_router)

__all__ = ["router"]
