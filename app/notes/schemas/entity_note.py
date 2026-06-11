from pydantic import BaseModel

from app.core.api_types import ApiDateTime, NonBlankStr, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin


class EntityNoteResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    note: str
    created_by: int | None = None
    created_by_name: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


EntityNoteListResponse = PaginatedResponse[EntityNoteResponse]


class EntityNoteCreateRequest(BaseModel):
    note: str


class EntityNoteUpdateRequest(NonEmptyUpdateMixin):
    # `note` is the payload; it stays required (single-payload update exception)
    # and must be non-blank.
    note: NonBlankStr
