from pydantic import BaseModel

from app.core.api_types import ApiDecimal


class CreationImpactItem(BaseModel):
    label: str
    count: int


class ClientCreationImpactResponse(BaseModel):
    items: list[CreationImpactItem]
    years_scope: int
    note: str | None = None
    vat_exempt_ceiling: ApiDecimal | None = None
