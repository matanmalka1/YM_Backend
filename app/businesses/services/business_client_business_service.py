"""Service layer for client-scoped business routes."""

from sqlalchemy.orm import Session

from app.businesses.business_guards import (
    assert_business_belongs_to_legal_entity,
)
from app.businesses.models.business import Business
from app.businesses.repositories.business_repository import BusinessRepository
from app.businesses.schemas.business_schemas import (
    BusinessResponse,
    ClientBusinessesResponse,
)
from app.businesses.services.business_service import BusinessService
from app.clients.services.client_service import get_client_or_raise
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.users.models.user import UserRole


class ClientBusinessService:
    def __init__(self, db: Session):
        self.db = db
        self.business_service = BusinessService(db)
        self.business_repo = BusinessRepository(db)

    def to_response(self, business: Business, client_id: int | None = None) -> BusinessResponse:
        response = BusinessResponse.model_validate(business)
        if client_id is not None:
            response.client_id = client_id
        return response

    def list_for_client(
        self,
        client_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> ClientBusinessesResponse:
        items, total = self.business_service.list_businesses_for_client(
            client_id,
            page=page,
            page_size=page_size,
        )
        return ClientBusinessesResponse(
            client_id=client_id,
            items=[self.to_response(business, client_id=client_id) for business in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_for_client(self, client_id: int, business_id: int) -> Business:
        business = self.business_service.get_business_or_raise(business_id)
        self._assert_business_belongs_to_client(business, client_id)
        return business

    def delete_for_client(self, client_id: int, business_id: int, actor_id: int) -> None:
        self.get_for_client(client_id, business_id)
        self.business_service.delete_business(business_id, actor_id=actor_id)

    def restore_for_client(
        self,
        client_id: int,
        business_id: int,
        *,
        actor_id: int,
        actor_role: UserRole,
    ) -> Business:
        business = self.business_repo.get_by_id_including_deleted(business_id)
        if not business:
            raise NotFoundError(f"עסק {business_id} לא נמצא", ErrorCode.BUSINESS_NOT_FOUND)
        self._assert_business_belongs_to_client(business, client_id)
        return self.business_service.restore_business(
            business_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )

    def _assert_business_belongs_to_client(self, business: Business, client_id: int) -> None:
        client_record = get_client_or_raise(self.db, client_id)
        assert_business_belongs_to_legal_entity(business, client_record.legal_entity_id)
