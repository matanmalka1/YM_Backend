from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.legal_entity import LegalEntity


class LegalEntityRepository(BaseRepository[LegalEntity]):
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        id_number: str,
        id_number_type: IdNumberType,
        official_name: str,
        entity_type: EntityType | None = None,
        vat_reporting_frequency: VatType | None = None,
        advance_payment_frequency: AdvancePaymentFrequency | None = None,
        vat_exempt_ceiling=None,
        advance_rate=None,
        vat_liable_from: date | None = None,
        vat_liable_to: date | None = None,
        advance_liable_from: date | None = None,
        advance_liable_to: date | None = None,
        annual_liable_from: date | None = None,
        annual_liable_to: date | None = None,
    ) -> LegalEntity:
        entity = LegalEntity(
            id_number=id_number,
            id_number_type=id_number_type,
            official_name=official_name,
            entity_type=entity_type,
            vat_reporting_frequency=vat_reporting_frequency,
            advance_payment_frequency=advance_payment_frequency,
            vat_exempt_ceiling=vat_exempt_ceiling,
            advance_rate=advance_rate,
            vat_liable_from=vat_liable_from,
            vat_liable_to=vat_liable_to,
            advance_liable_from=advance_liable_from,
            advance_liable_to=advance_liable_to,
            annual_liable_from=annual_liable_from,
            annual_liable_to=annual_liable_to,
        )
        self.db.add(entity)
        self.db.flush()
        return entity

    def get_by_id(self, entity_id: int) -> LegalEntity | None:
        return self.db.scalars(select(LegalEntity).where(LegalEntity.id == entity_id)).first()

    def list_by_ids(self, ids: list[int]) -> list[LegalEntity]:
        if not ids:
            return []
        return self.db.scalars(select(LegalEntity).where(LegalEntity.id.in_(ids))).all()

    def get_by_id_number(self, id_number_type: IdNumberType, id_number: str) -> LegalEntity | None:
        return self.db.scalars(
            select(LegalEntity).where(
                LegalEntity.id_number_type == id_number_type,
                LegalEntity.id_number == id_number,
            )
        ).first()
