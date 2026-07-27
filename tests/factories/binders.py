from __future__ import annotations

from datetime import date, datetime
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.models.binder_intake import BinderIntake
from app.binders.models.binder_intake_material import BinderIntakeMaterial, MaterialType
from app.businesses.models.business import Business
from app.users.models.user import User
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.factory_utils import (
    TEST_DATE,
    TEST_TAX_YEAR,
    ClientRef,
    resolve_exclusive,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory


class BinderFactory:
    """Model-level Binder factory: no BinderService side effects (audit/timeline)."""

    def __init__(self, db: Session, client_factory: ClientFactory, actor_user: User) -> None:
        self.db = db
        self.client_factory = client_factory
        self.actor_user = actor_user
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        actor: User | None = None,
        created_by: int | None = None,
        binder_number: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        location_status: BinderLocationStatus = BinderLocationStatus.IN_OFFICE,
        capacity_status: BinderCapacityStatus = BinderCapacityStatus.OPEN,
        ready_for_handover_at: datetime | None = None,
        handed_over_at: date | None = None,
        handover_recipient_name: str | None = None,
        notes: str | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> Binder:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        resolve_exclusive(actor, created_by, names="actor or created_by")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        if created_by is None:
            created_by = actor.id if actor is not None else self.actor_user.id
        binder = Binder(
            client_record_id=resolved_client_id,
            binder_number=binder_number or f"BIN-{sequence:04d}",
            period_start=period_start,
            period_end=period_end,
            location_status=location_status,
            capacity_status=capacity_status,
            ready_for_handover_at=ready_for_handover_at,
            handed_over_at=handed_over_at,
            handover_recipient_name=handover_recipient_name,
            notes=notes,
            created_by=created_by,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
        )
        self.db.add(binder)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(binder)
        return binder


class BinderIntakeFactory:
    """Model-level BinderIntake factory."""

    def __init__(self, db: Session, binder_factory: BinderFactory, actor_user: User) -> None:
        self.db = db
        self.binder_factory = binder_factory
        self.actor_user = actor_user

    def __call__(
        self,
        *,
        binder: Binder | None = None,
        binder_id: int | None = None,
        received_by_user: User | None = None,
        received_by: int | None = None,
        received_at: date = TEST_DATE,
        notes: str | None = None,
        created_at: datetime | None = None,
        commit: bool = False,
    ) -> BinderIntake:
        resolve_exclusive(binder, binder_id, names="binder or binder_id")
        resolve_exclusive(received_by_user, received_by, names="received_by_user or received_by")
        if binder is None and binder_id is None:
            binder = self.binder_factory()
        if received_by is None:
            received_by = (
                received_by_user.id if received_by_user is not None else self.actor_user.id
            )
        fields: dict[str, Any] = {
            "binder_id": binder_id if binder_id is not None else binder.id,
            "received_at": received_at,
            "received_by": received_by,
            "notes": notes,
        }
        if created_at is not None:
            fields["created_at"] = created_at
        intake = BinderIntake(**fields)
        self.db.add(intake)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(intake)
        return intake


class BinderIntakeMaterialFactory:
    """Model-level BinderIntakeMaterial factory."""

    def __init__(self, db: Session, binder_intake_factory: BinderIntakeFactory) -> None:
        self.db = db
        self.binder_intake_factory = binder_intake_factory

    def __call__(
        self,
        *,
        intake: BinderIntake | None = None,
        intake_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        annual_report: AnnualReport | None = None,
        annual_report_id: int | None = None,
        vat_work_item: VatWorkItem | None = None,
        vat_report_id: int | None = None,
        material_type: MaterialType = MaterialType.OTHER,
        period_year: int = TEST_TAX_YEAR,
        period_month_start: int = 1,
        period_month_end: int | None = None,
        description: str | None = None,
        created_at: datetime | None = None,
        commit: bool = False,
    ) -> BinderIntakeMaterial:
        resolve_exclusive(intake, intake_id, names="intake or intake_id")
        resolve_exclusive(business, business_id, names="business or business_id")
        resolve_exclusive(
            annual_report, annual_report_id, names="annual_report or annual_report_id"
        )
        resolve_exclusive(vat_work_item, vat_report_id, names="vat_work_item or vat_report_id")
        if intake is None and intake_id is None:
            intake = self.binder_intake_factory()
        fields: dict[str, Any] = {
            "intake_id": intake_id if intake_id is not None else intake.id,
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "annual_report_id": annual_report_id
            if annual_report_id is not None
            else getattr(annual_report, "id", None),
            "vat_report_id": vat_report_id
            if vat_report_id is not None
            else getattr(vat_work_item, "id", None),
            "material_type": material_type,
            "period_year": period_year,
            "period_month_start": period_month_start,
            "period_month_end": (
                period_month_start if period_month_end is None else period_month_end
            ),
            "description": description,
        }
        if created_at is not None:
            fields["created_at"] = created_at
        material = BinderIntakeMaterial(**fields)
        self.db.add(material)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(material)
        return material
