from typing import Any

from pydantic import BaseModel

from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.core.api_types import ApiDateTime, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin


class AnnexDataLineResponse(BaseModel):
    id: int
    annual_report_id: int
    schedule: AnnualReportSchedule
    line_number: int
    data: dict[str, Any]
    data_version: int  # נוסף — קיים במודל
    notes: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


class AnnexDataLineListResponse(PaginatedResponse[AnnexDataLineResponse]):
    pass


class AnnexDataAddRequest(BaseModel):
    data: dict[str, Any]
    notes: str | None = None


class AnnexDataUpdateRequest(NonEmptyUpdateMixin):
    # `data` is the payload of the update; it stays required (single-payload
    # update exception — omitting it would be a no-op). `notes` is nullable.
    data: dict[str, Any]
    notes: str | None = None
