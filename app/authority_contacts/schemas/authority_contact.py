from pydantic import BaseModel, EmailStr, model_validator

from app.authority_contacts.models.authority_contact import ContactType
from app.core.api_types import ApiDateTime, NonBlankStr, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin


class AuthorityContactCreateRequest(BaseModel):
    contact_type: ContactType
    name: str
    office: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    notes: str | None = None


class AuthorityContactUpdateRequest(NonEmptyUpdateMixin):
    contact_type: ContactType | None = None
    name: NonBlankStr | None = None
    office: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> AuthorityContactUpdateRequest:
        for field in ("contact_type", "name"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


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


class AuthorityContactListResponse(PaginatedResponse[AuthorityContactResponse]):
    pass
