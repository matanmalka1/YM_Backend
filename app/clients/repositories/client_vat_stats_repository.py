from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clients.enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from app.common.enums import EntityType, VatType
from app.common.repositories.base_repository import BaseRepository


class ClientVatStatsRepository(BaseRepository[ClientRecord]):
    def __init__(self, db: Session):
        self.db = db

    def _active_base_stmt(self):
        return (
            select(func.count(ClientRecord.id))
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(
                ClientRecord.deleted_at.is_(None),
                ClientRecord.status == ClientStatus.ACTIVE,
            )
        )

    def count_active_by_vat_type(self, vat_type: VatType) -> int:
        return self.db.scalar(
            self._active_base_stmt().where(LegalEntity.vat_reporting_frequency == vat_type)
        )

    def count_active_by_vat_types(self, vat_types: list[VatType]) -> dict[VatType, int]:
        if not vat_types:
            return {}
        stmt = self._active_base_stmt().with_only_columns(
            LegalEntity.vat_reporting_frequency,
            func.count(ClientRecord.id),
        )
        stmt = stmt.where(LegalEntity.vat_reporting_frequency.in_(vat_types)).group_by(
            LegalEntity.vat_reporting_frequency
        )
        counts = {vat_type: 0 for vat_type in vat_types}
        for vat_type, count in self.db.execute(stmt).all():
            counts[vat_type] = int(count)
        return counts

    def count_active_by_entity_and_vat_type(
        self, entity_type: EntityType, vat_type: VatType
    ) -> int:
        return self.db.scalar(
            self._active_base_stmt().where(
                LegalEntity.entity_type == entity_type,
                LegalEntity.vat_reporting_frequency == vat_type,
            )
        )

    def count_active_exempt(self) -> int:
        return self.db.scalar(
            self._active_base_stmt().where(LegalEntity.vat_reporting_frequency == VatType.EXEMPT)
        )
