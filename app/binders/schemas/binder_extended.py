from datetime import date

from pydantic import BaseModel

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.core.api_types import PaginatedResponse


class BinderDetailResponse(BaseModel):
    """תצוגה מורחבת עם שדות תפעוליים."""

    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str | None = None
    client_id_number: str | None = None
    binder_number: str
    period_start: date | None = None
    period_end: date | None = None
    location_status: BinderLocationStatus
    capacity_status: BinderCapacityStatus
    handed_over_at: date | None = None
    handover_recipient_name: str | None = None
    # days_in_office: ימים שחלפו מתחילת תקופת הקלסר (period_start → היום).
    # מחושב גם על קלסרים שנמסרו ללקוח.
    days_in_office: int | None = None

    model_config = {"from_attributes": True}


class BinderListResponseExtended(PaginatedResponse[BinderDetailResponse]):
    pass
