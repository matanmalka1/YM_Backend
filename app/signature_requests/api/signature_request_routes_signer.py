from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.path_params import SigningTokenPath
from app.signature_requests.schemas.signature_request import (
    SignerDeclineRequest,
    SignerViewResponse,
)
from app.signature_requests.services.signature_request_service import (
    SignatureRequestService,
)
from app.users.api.user_deps import DBSession

signer_router = APIRouter(
    prefix="/sign",
    tags=["public-signing"],
)


def _to_signer_view(req) -> SignerViewResponse:
    return SignerViewResponse(
        request_id=req.id,
        title=req.title,
        description=req.description,
        signer_name=req.signer_name,
        status=req.status.value,
        content_hash=req.content_hash,
        expires_at=req.expires_at,
    )


@signer_router.get("/{token}", response_model=SignerViewResponse)
def signer_view(token: SigningTokenPath, raw_request: Request, db: DBSession):
    service = SignatureRequestService(db)
    req = service.record_view(
        token=token,
        ip_address=raw_request.client.host if raw_request.client else None,
        user_agent=raw_request.headers.get("user-agent"),
    )
    return _to_signer_view(req)


@signer_router.post("/{token}/approve", response_model=SignerViewResponse)
def signer_approve(token: SigningTokenPath, raw_request: Request, db: DBSession):
    service = SignatureRequestService(db)
    req = service.sign_request(
        token=token,
        ip_address=raw_request.client.host if raw_request.client else None,
        user_agent=raw_request.headers.get("user-agent"),
    )
    return _to_signer_view(req)


@signer_router.post("/{token}/decline", response_model=SignerViewResponse)
def signer_decline(
    token: SigningTokenPath, body: SignerDeclineRequest, raw_request: Request, db: DBSession
):
    service = SignatureRequestService(db)
    req = service.decline_request(
        token=token,
        reason=body.reason,
        ip_address=raw_request.client.host if raw_request.client else None,
        user_agent=raw_request.headers.get("user-agent"),
    )
    return _to_signer_view(req)
