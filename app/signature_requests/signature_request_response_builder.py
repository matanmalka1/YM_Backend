"""Response assembly for advisor-facing signature request routes."""

from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.signature_requests.schemas.signature_request import (
    SignatureRequestAuditItemResponse,
    SignatureRequestCreatedResponse,
    SignatureRequestListResponse,
    SignatureRequestResponse,
    SignatureRequestWithAuditResponse,
)


class SignatureRequestResponseBuilder:
    def __init__(self, db):
        self.business_repo = BusinessRepository(db)
        self.client_repo = ClientRecordRepository(db)

    def build(self, request) -> SignatureRequestResponse:
        response = SignatureRequestResponse.model_validate(request)
        self._enrich(response)
        return response

    def build_list(
        self, items, total: int, *, page: int, page_size: int
    ) -> SignatureRequestListResponse:
        business_map = self._business_name_map(items)
        office_number_map = self._office_number_map(items)
        responses = []
        for request in items:
            response = SignatureRequestResponse.model_validate(request)
            self._enrich_from_maps(response, business_map, office_number_map)
            responses.append(response)
        return SignatureRequestListResponse(
            items=responses,
            page=page,
            page_size=page_size,
            total=total,
        )

    def build_with_audit(self, request, audit_events) -> SignatureRequestWithAuditResponse:
        response = SignatureRequestWithAuditResponse.model_validate(request)
        self._enrich(response)
        response.audit_trail = [self._map_audit_item(event) for event in audit_events]
        return response

    def build_created(self, request) -> SignatureRequestCreatedResponse:
        response = self.build(request)
        return SignatureRequestCreatedResponse(
            **response.model_dump(),
            signing_token=request.signing_token,
            signing_url_hint=f"/sign/{request.signing_token}",
        )

    def _enrich(self, response: SignatureRequestResponse) -> None:
        office_number_map = self._office_number_map([response])
        business_map = self._business_name_map([response])
        self._enrich_from_maps(response, business_map, office_number_map)

    def _enrich_from_maps(
        self,
        response: SignatureRequestResponse,
        business_map: dict[int, str],
        office_number_map: dict[int, int],
    ) -> None:
        response.office_client_number = office_number_map.get(response.client_record_id)
        if response.business_id:
            response.business_name = business_map.get(response.business_id)

    def _business_name_map(self, items) -> dict[int, str]:
        business_ids = sorted({item.business_id for item in items if item.business_id is not None})
        return {
            business.id: business.business_name
            for business in self.business_repo.list_by_ids(business_ids)
        }

    def _office_number_map(self, items) -> dict[int, int]:
        client_ids = sorted({item.client_record_id for item in items})
        return {
            record.id: record.office_client_number
            for record in self.client_repo.list_by_ids(client_ids)
        }

    def _map_audit_item(self, event) -> SignatureRequestAuditItemResponse:
        metadata = event.metadata_json if isinstance(event.metadata_json, dict) else {}
        return SignatureRequestAuditItemResponse(
            id=event.id,
            action=event.action,
            actor_type=event.actor_type,
            actor_display_name=event.actor_display_name or event.performed_by_name,
            performed_at=event.performed_at,
            note=event.note,
            client_record_id=metadata.get("client_record_id"),
            signer_name=metadata.get("signer_name"),
            signer_email=metadata.get("signer_email"),
            business_id=metadata.get("business_id"),
            document_id=metadata.get("document_id"),
            ip_address=metadata.get("ip_address"),
            user_agent=metadata.get("user_agent"),
            content_hash=metadata.get("content_hash"),
            content_hash_missing=metadata.get("content_hash_missing"),
            signed_document_key=metadata.get("signed_document_key"),
            reason=metadata.get("reason"),
        )
