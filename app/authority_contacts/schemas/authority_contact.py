from pydantic import BaseModel, EmailStr

from app.authority_contacts.models.authority_contact import ContactType
from app.core.api_types import ApiDateTime, PaginatedResponse


class AuthorityContactCreateRequest(BaseModel):
    contact_type: ContactType
    name: str
    office: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    notes: str | None = None


class AuthorityContactUpdateRequest(BaseModel):
    contact_type: ContactType | None = None
    name: str | None = None
    office: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    notes: str | None = None


class AuthorityContactResponse(BaseModel):
    id: int
    client_record_id: int
    contact_type: ContactType
    name: str
    office: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


AuthorityContactListResponse = PaginatedResponse[AuthorityContactResponse]
