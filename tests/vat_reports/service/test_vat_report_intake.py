import pytest

from app.clients.enums import ClientStatus
from app.common.enums import EntityType, VatType
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.vat_reports.models.vat_enums import VatWorkItemStatus
from app.vat_reports.repositories.vat_work_item_repository import VatWorkItemRepository
from app.vat_reports.services import intake
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.vat_reports import make_item


def _seed(
    db,
    *,
    id_number: str,
    vat_type=None,
    status=ClientStatus.ACTIVE,
    entity_type=EntityType.OSEK_MURSHE,
):
    c = seed_client_identity(
        db,
        full_name="Test",
        id_number=id_number,
        entity_type=entity_type,
        vat_reporting_frequency=vat_type,
        status=status,
    )
    seed_business(db, legal_entity_id=c.legal_entity_id, business_name="Test Biz")
    db.commit()
    return c


class TestCreateWorkItem:
    def test_happy_path_material_received(self, test_db):
        c = _seed(test_db, id_number="100000001")
        repo = VatWorkItemRepository(test_db)
        result = intake.create_work_item(
            repo, test_db, client_record_id=c.id, period="2026-01", created_by=1
        )
        assert result.status == VatWorkItemStatus.MATERIAL_RECEIVED

    def test_client_not_found_raises(self, test_db):
        repo = VatWorkItemRepository(test_db)
        with pytest.raises(NotFoundError) as exc_info:
            intake.create_work_item(
                repo, test_db, client_record_id=99999, period="2026-01", created_by=1
            )
        assert exc_info.value.code == "VAT.NOT_FOUND"

    def test_duplicate_period_raises(self, test_db):
        c = _seed(test_db, id_number="100000002")
        repo = VatWorkItemRepository(test_db)
        intake.create_work_item(
            repo, test_db, client_record_id=c.id, period="2026-01", created_by=1
        )
        with pytest.raises(ConflictError) as exc_info:
            intake.create_work_item(
                repo, test_db, client_record_id=c.id, period="2026-01", created_by=1
            )
        assert exc_info.value.code == "VAT.CONFLICT"

    def test_pending_without_note_raises(self, test_db):
        c = _seed(test_db, id_number="100000003")
        repo = VatWorkItemRepository(test_db)
        with pytest.raises(AppError) as exc_info:
            intake.create_work_item(
                repo,
                test_db,
                client_record_id=c.id,
                period="2026-01",
                created_by=1,
                mark_pending=True,
            )
        assert exc_info.value.code == "VAT.PENDING_NOTE_REQUIRED"

    def test_pending_with_note_creates_item(self, test_db):
        c = _seed(test_db, id_number="100000004")
        repo = VatWorkItemRepository(test_db)
        result = intake.create_work_item(
            repo,
            test_db,
            client_record_id=c.id,
            period="2026-01",
            created_by=1,
            mark_pending=True,
            pending_materials_note="Missing Q4",
        )
        assert result.status == VatWorkItemStatus.PENDING_MATERIALS

    def test_exempt_vat_type_rejected(self, test_db):
        c = _seed(test_db, id_number="100000005", vat_type=VatType.EXEMPT)
        repo = VatWorkItemRepository(test_db)
        with pytest.raises(AppError) as exc_info:
            intake.create_work_item(
                repo, test_db, client_record_id=c.id, period="2026-01", created_by=1
            )
        assert exc_info.value.code == "VAT.CLIENT_EXEMPT"

    def test_bimonthly_rejects_even_month(self, test_db):
        c = _seed(test_db, id_number="100000006", vat_type=VatType.BIMONTHLY)
        repo = VatWorkItemRepository(test_db)
        with pytest.raises(AppError) as exc_info:
            intake.create_work_item(
                repo, test_db, client_record_id=c.id, period="2026-02", created_by=1
            )
        assert exc_info.value.code == "VAT.INVALID_PERIOD_FOR_FREQUENCY"


class TestMarkMaterialsComplete:
    def test_happy_path(self):
        from unittest.mock import MagicMock

        work_item_repo = MagicMock()
        item = make_item(status=VatWorkItemStatus.PENDING_MATERIALS)
        work_item_repo.get_by_id_for_update.return_value = item
        work_item_repo.update_status.return_value = make_item(
            status=VatWorkItemStatus.MATERIAL_RECEIVED
        )

        result = intake.mark_materials_complete(work_item_repo, item_id=1, performed_by=1)
        assert result.status == VatWorkItemStatus.MATERIAL_RECEIVED

    def test_wrong_status_raises(self):
        from unittest.mock import MagicMock

        work_item_repo = MagicMock()
        work_item_repo.get_by_id_for_update.return_value = make_item(
            status=VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS
        )

        with pytest.raises(AppError) as exc_info:
            intake.mark_materials_complete(work_item_repo, item_id=1, performed_by=1)
        assert exc_info.value.code == "VAT.INVALID_TRANSITION"
