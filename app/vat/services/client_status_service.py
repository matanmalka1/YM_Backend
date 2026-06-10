from sqlalchemy.orm import Session

from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository,
)


class VatWorkItemClientStatusService:
    def __init__(self, db: Session):
        self.repo = VatWorkItemWriteRepository(db)

    def cancel_open_by_client_record(self, client_record_id: int) -> int:
        return self.repo.cancel_open_by_client_record(client_record_id)
