import logging
from datetime import date

from sqlalchemy.orm import Session

from app.binders.binder_messages import (
    BINDER_CLIENT_LOCKED,
    BINDER_RECEIVED,
)
from app.binders.models.binder import Binder, BinderLocationStatus
from app.binders.models.binder_intake import BinderIntake
from app.binders.repositories.binder_intake_material_repository import (
    BinderIntakeMaterialRepository,
)
from app.binders.repositories.binder_intake_repository import BinderIntakeRepository
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.businesses.models.business import BusinessStatus
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.guards.client_record_guards import assert_client_record_is_active
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)

_log = logging.getLogger(__name__)


class BinderIntakeService:
    """Handles the 'find or create' binder intake flow."""

    def __init__(self, db: Session):
        self.db = db
        self.binder_repo = BinderRepository(db)
        self.lifecycle_service = BinderLifecycleService(db)
        self.intake_repo = BinderIntakeRepository(db)
        self.material_repo = BinderIntakeMaterialRepository(db)
        # Used for the "all businesses locked" guard before intake is accepted.
        self.business_repo = BusinessRepository(db)
        self.client_repo = ClientRecordRepository(db)

    def receive(
        self,
        client_record_id: int,
        received_at: date,
        received_by: int,
        open_new_binder: bool = False,
        notes: str | None = None,
        materials: list[dict] | None = None,
    ) -> tuple[Binder, BinderIntake, bool]:
        """
        Find open (IN_OFFICE) binder or create new one, then record the intake.

        materials: list of dicts with keys:
            material_type (str), business_id (int|None),
            annual_report_id (int|None), vat_report_id (int|None),
            period_year (int), period_month_start (int), period_month_end (int),
            description (str|None, optional note only)

        Returns (binder, intake, is_new_binder).
        """
        from app.binders.binder_messages import BINDER_OFFICE_NUMBER_MISSING

        client_record = self.client_repo.get_by_id(client_record_id)
        assert_client_record_is_active(client_record)

        businesses = self.business_repo.list_by_legal_entity(client_record.legal_entity_id)
        has_active = any(b.status == BusinessStatus.ACTIVE for b in businesses)
        if businesses and not has_active:
            raise AppError(BINDER_CLIENT_LOCKED, ErrorCode.BINDER_CLIENT_LOCKED)

        active_binder = self.binder_repo.get_active_by_client_record(client_record_id)
        existing = self._resolve_existing_binder_for_materials(
            client_record_id=client_record_id,
            active_binder=active_binder,
            materials=materials,
        )

        if existing:
            binder = existing
            is_new_binder = False
        elif active_binder and not open_new_binder:
            binder = active_binder
            is_new_binder = False
        else:
            if active_binder and open_new_binder:
                active_binder.period_end = self._resolve_closing_period_structured(
                    active_binder.id, received_at
                )
                self.lifecycle_service.mark_full(
                    active_binder.id,
                    changed_by_user_id=received_by,
                    notes=BINDER_RECEIVED,
                )

            if client_record.office_client_number is None:
                raise AppError(BINDER_OFFICE_NUMBER_MISSING, ErrorCode.BINDER_OFFICE_NUMBER_MISSING)
            seq = self.binder_repo.count_all_by_client(client_record_id) + 1
            binder = self.binder_repo.create(
                client_record_id=client_record_id,
                binder_number=self._build_binder_number(client_record.office_client_number, seq),
                period_start=None,
                created_by=received_by,
            )
            self.lifecycle_service.log_initial_state(
                binder=binder,
                changed_by_user_id=received_by,
                notes=BINDER_RECEIVED,
            )
            is_new_binder = True

        if not is_new_binder:
            self.lifecycle_service.receive_material(
                binder,
                changed_by_user_id=received_by,
                allow_full_in_office=True,
            )

        # Old-period guard: if any material is for a period older than the binder's
        # current period_start, the intake must include a note explaining the mismatch.
        self._validate_old_period_note(binder, materials, notes)

        intake = self.intake_repo.create(
            binder_id=binder.id,
            received_at=received_at,
            received_by=received_by,
            notes=notes,
        )

        for mat in materials or []:
            self.material_repo.create(
                intake_id=intake.id,
                material_type=mat["material_type"],
                business_id=mat.get("business_id"),
                annual_report_id=mat.get("annual_report_id"),
                vat_report_id=mat.get("vat_report_id"),
                period_year=mat.get("period_year"),
                period_month_start=mat.get("period_month_start"),
                period_month_end=mat.get("period_month_end"),
                description=mat.get("description"),
            )

        # Backfill period_start from the first structured material whenever the binder
        # still lacks a derived period window, including legacy existing binders.
        if binder.period_start is None and materials:
            first = materials[0]
            py = first.get("period_year")
            pm = first.get("period_month_start")
            if py and pm:
                from datetime import date as _date

                binder.period_start = _date(py, pm, 1)
                self.db.flush()

        self._auto_advance_vat_work_items(materials, performed_by=received_by)

        return binder, intake, is_new_binder

    def _auto_advance_vat_work_items(
        self,
        materials: list[dict] | None,
        performed_by: int,
    ) -> None:
        """Advance PENDING_MATERIALS → MATERIAL_RECEIVED for linked VAT work items."""
        from app.vat.vat_constants import ACTION_STATUS_CHANGED

        vat_repo = VatWorkItemRepository(self.db)
        seen: set[int] = set()
        for mat in materials or []:
            if mat.get("material_type") != "vat":
                continue
            vat_id = mat.get("vat_report_id")
            if not vat_id or vat_id in seen:
                continue
            seen.add(vat_id)
            item = vat_repo.get_by_id_for_update(vat_id)
            if not item or item.status != VatWorkItemStatus.PENDING_MATERIALS:
                continue
            vat_repo.update_status(
                vat_id,
                VatWorkItemStatus.MATERIAL_RECEIVED,
                item=item,
                pending_materials_note=None,
            )
            vat_repo.append_audit(
                work_item_id=vat_id,
                performed_by=performed_by,
                action=ACTION_STATUS_CHANGED,
                old_value=VatWorkItemStatus.PENDING_MATERIALS.value,
                new_value=VatWorkItemStatus.MATERIAL_RECEIVED.value,
            )

    def _resolve_existing_binder_for_materials(
        self,
        *,
        client_record_id: int,
        active_binder: Binder | None,
        materials: list[dict] | None,
    ) -> Binder | None:
        """
        Pick an existing binder for the intake before any "open new binder" logic runs.

        Rules:
        - If there is no active binder or no structured material periods, fall back to the
          normal active/new-binder flow.
        - If incoming material is older than the active binder's period_start, first try to
          place it in a matching older in-office binder for that period window.
        - If no suitable older binder exists, keep the intake on the current active binder.
          The note requirement is enforced separately by _validate_old_period_note().
        """
        if not active_binder or active_binder.period_start is None:
            return None

        period_window = self._extract_material_period_window(materials)
        if not period_window:
            return None

        min_period_start, max_period_end = period_window
        if min_period_start >= active_binder.period_start:
            return None

        older_binder = self._find_matching_older_binder(
            client_record_id=active_binder.client_record_id,
            active_binder_id=active_binder.id,
            min_period_start=min_period_start,
            max_period_end=max_period_end,
        )
        return older_binder or active_binder

    def _find_matching_older_binder(
        self,
        *,
        client_record_id: int,
        active_binder_id: int,
        min_period_start: date,
        max_period_end: date,
    ) -> Binder | None:
        """
        Return the latest older binder whose stored period window can contain the intake.

        Only binders still physically in the office are eligible. A full binder can
        receive old-period material only when its stored period window contains
        the incoming material period.
        """
        candidates: list[Binder] = []
        binders = self.binder_repo.list_by_client_record(client_record_id)
        for binder in binders:
            if binder.id == active_binder_id:
                continue
            if binder.location_status != BinderLocationStatus.IN_OFFICE:
                continue
            if binder.period_start is None or binder.period_end is None:
                continue
            if binder.period_start <= min_period_start and max_period_end <= binder.period_end:
                candidates.append(binder)

        return candidates[-1] if candidates else None

    @staticmethod
    def _extract_material_period_window(
        materials: list[dict] | None,
    ) -> tuple[date, date] | None:
        periods: list[tuple[date, date]] = []
        for mat in materials or []:
            py = mat.get("period_year")
            month_start = mat.get("period_month_start")
            month_end = mat.get("period_month_end")
            if not py or not month_start or not month_end:
                continue
            period_start = date(py, month_start, 1)
            period_end = date(py, month_end, 1)
            periods.append((period_start, period_end))

        if not periods:
            return None

        return (
            min(period_start for period_start, _period_end in periods),
            max(period_end for _period_start, period_end in periods),
        )

    def _validate_old_period_note(
        self,
        binder: Binder,
        materials: list[dict] | None,
        notes: str | None,
    ) -> None:
        """
        Enforce old-period note requirement.

        If any material row carries a reporting period older than the binder's
        current period_start, a note must be present on the intake to explain
        why old-period material is being inserted into this binder.

        Raises AppError if the condition is violated.
        """
        from app.binders.binder_messages import BINDER_OLD_PERIOD_NOTE_REQUIRED

        if not materials or binder.period_start is None:
            return
        for mat in materials:
            py = mat.get("period_year")
            pm = mat.get("period_month_start")
            if not py or not pm:
                continue
            from datetime import date as _date

            mat_period_start = _date(py, pm, 1)
            if mat_period_start < binder.period_start:
                if not notes or not notes.strip():
                    raise AppError(
                        BINDER_OLD_PERIOD_NOTE_REQUIRED,
                        ErrorCode.BINDER_OLD_PERIOD_NOTE_REQUIRED,
                    )
                break

    def _resolve_closing_period_structured(self, binder_id: int, fallback: date) -> date:
        """Derive period_end from the last material's structured period fields."""
        import calendar as _cal

        last_mat = self.material_repo.get_last_by_binder(binder_id)
        if last_mat and last_mat.period_year and last_mat.period_month_end:
            year, month = last_mat.period_year, last_mat.period_month_end
            day = _cal.monthrange(year, month)[1]
            return date(year, month, day)
        return fallback

    @staticmethod
    def _build_binder_number(office_client_number: int, sequence: int) -> str:
        return f"{office_client_number}/{sequence}"
