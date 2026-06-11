from pydantic import BaseModel

from app.clients.schemas.client_conflicts import (
    ActiveClientSummary,
    ClientConflictInfo,
    DeletedClientSummary,
)
from app.clients.schemas.client_requests import (
    ClientCreateRequest,
    ClientImpactPreviewClientRequest,
    ClientImpactPreviewRequest,
    ClientOnboardingRequest,
    ClientUpdateRequest,
)


class ClientImportError(BaseModel):
    row: int
    error: str


class ClientImportResponse(BaseModel):
    created: int
    total_rows: int
    errors: list[ClientImportError]


__all__ = [
    "ActiveClientSummary",
    "ClientConflictInfo",
    "ClientCreateRequest",
    "ClientImpactPreviewClientRequest",
    "ClientImpactPreviewRequest",
    "ClientImportError",
    "ClientImportResponse",
    "ClientOnboardingRequest",
    "ClientUpdateRequest",
    "DeletedClientSummary",
]
