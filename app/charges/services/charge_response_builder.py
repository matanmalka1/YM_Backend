from app.actions.services.charge_actions import get_charge_actions
from app.charges.models.charge import Charge
from app.charges.schemas.charge import ChargeResponse
from app.charges.services.charge_query_service import ChargeQueryService
from app.users.models.user import UserRole


class ChargeResponseBuilder:
    def __init__(self, query_service: ChargeQueryService):
        self.query_service = query_service

    def build(self, charge: Charge, user_role: UserRole | None = None) -> ChargeResponse:
        data = ChargeResponse.model_validate(charge).model_dump()
        client_name, business_name, office_client_number = self.query_service.enrich_charge_context(
            charge
        )
        data["client_name"] = client_name
        data["business_name"] = business_name
        data["office_client_number"] = office_client_number
        data["available_actions"] = get_charge_actions(charge, user_role=user_role)
        return ChargeResponse(**data)
