from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random

from sqlalchemy import func, select

from app.audit.audit_constants import (
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_INTAKE_UPDATED,
    ACTION_BINDER_MARKED_FULL,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_BINDER_MATERIAL_RECEIVED,
    ENTITY_BINDER,
    ENTITY_BINDER_INTAKE,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.binders.binder_audit import binder_metadata, intake_metadata, lifecycle_value
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.models.binder_handover import BinderHandover, BinderHandoverBinder
from app.binders.models.binder_intake import BinderIntake
from app.binders.models.binder_intake_material import BinderIntakeMaterial, MaterialType
from app.common.enums import VatType

from ...data.demo_catalog import BUSINESS_NOTES
from ...data.random_utils import full_name
from ...data.realistic_seed_text import MATERIAL_DESCRIPTIONS
from ..shared.client_refs import (
    attach_seed_client_context,
    get_seed_client_record,
    get_seed_client_record_id,
)


def _group_businesses_by_client(businesses) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for b in businesses:
        grouped.setdefault(get_seed_client_record_id(b), []).append(b)
    return grouped


def create_binders(db, rng: Random, cfg, businesses, users) -> list[Binder]:
    """Add historical binders on top of the initial binder created by onboarding."""
    binders: list[Binder] = []
    businesses_by_client: dict[int, list] = {}
    client_office_number: dict[int, int] = {}
    for business in businesses:
        client_record_id = get_seed_client_record_id(business)
        businesses_by_client.setdefault(client_record_id, []).append(business)
        if client_record_id not in client_office_number:
            cr = get_seed_client_record(business)
            client_office_number[client_record_id] = (
                getattr(cr, "office_client_number", None) or client_record_id
            )

    for client_id, client_businesses in businesses_by_client.items():
        office_num = client_office_number.get(client_id, client_id)
        existing_count = db.scalar(
            select(func.count())
            .select_from(Binder)
            .where(
                Binder.client_record_id == client_id,
                Binder.deleted_at.is_(None),
            )
        )
        num = rng.randint(cfg.min_binders_per_client, cfg.max_binders_per_client)
        cursor = cfg.reference_date - timedelta(days=rng.randint(240, 700))
        for seq in range(1, num + 1):
            period_start = cursor
            location_status = rng.choices(
                [BinderLocationStatus.IN_OFFICE, BinderLocationStatus.HANDED_OVER],
                weights=[40, 60],
                k=1,
            )[0]
            capacity_status = (
                rng.choices(
                    [BinderCapacityStatus.OPEN, BinderCapacityStatus.FULL],
                    weights=[35, 65],
                    k=1,
                )[0]
                if location_status == BinderLocationStatus.IN_OFFICE
                else BinderCapacityStatus.FULL
            )
            duration = rng.randint(20, 90)
            period_end = min(
                cfg.reference_date - timedelta(days=1),
                period_start + timedelta(days=duration),
            )
            handed_over_at = (
                period_end if location_status == BinderLocationStatus.HANDED_OVER else None
            )
            cursor = period_end + timedelta(days=rng.randint(1, 14))

            binder = Binder(
                client_record_id=client_id,
                binder_number=f"{office_num}/{existing_count + seq}",
                period_start=period_start,
                period_end=period_end,
                handed_over_at=handed_over_at,
                location_status=location_status,
                capacity_status=capacity_status,
                created_by=rng.choice(users).id,
                handover_recipient_name=(
                    full_name(rng) if location_status == BinderLocationStatus.HANDED_OVER else None
                ),
                notes=rng.choice(BUSINESS_NOTES),
            )
            if client_businesses:
                cr = get_seed_client_record(client_businesses[0])
                if cr is not None:
                    attach_seed_client_context(binder, cr)
            db.add(binder)
            binders.append(binder)
    db.flush()
    return binders


def create_binder_logs(db, rng: Random, binders, users) -> None:
    if not users:
        return
    now = datetime.now(UTC)
    writer = EntityAuditWriter(db)
    for binder in binders:
        logs = []
        intake_time = datetime.combine(
            binder.period_start, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=rng.randint(8, 16))
        logs.append(
            (
                "null",
                BinderLocationStatus.IN_OFFICE.value,
                "קבלת קלסר",
                intake_time,
                "location_status",
            )
        )
        if binder.capacity_status == BinderCapacityStatus.FULL:
            closed_time = intake_time + timedelta(days=rng.randint(2, 14), hours=rng.randint(1, 8))
            if closed_time > now:
                closed_time = now
            logs.append(
                (
                    BinderCapacityStatus.OPEN.value,
                    BinderCapacityStatus.FULL.value,
                    "הקלסר נסגר במשרד",
                    closed_time,
                    "capacity_status",
                )
            )
        if binder.location_status == BinderLocationStatus.HANDED_OVER:
            ready_time = intake_time + timedelta(days=rng.randint(2, 14), hours=rng.randint(1, 8))
            if ready_time > now:
                ready_time = now
            handed_over_base = binder.handed_over_at or binder.period_end or binder.period_start
            handed_over_time = datetime.combine(
                handed_over_base, datetime.min.time(), tzinfo=UTC
            ) + timedelta(hours=rng.randint(9, 18))
            if handed_over_time < ready_time:
                handed_over_time = ready_time + timedelta(hours=1)
            if handed_over_time > now:
                handed_over_time = now
            logs.append(
                (
                    BinderLocationStatus.IN_OFFICE.value,
                    BinderLocationStatus.READY_FOR_HANDOVER.value,
                    "מוכן למסירה",
                    ready_time,
                    "location_status",
                )
            )
            logs.append(
                (
                    BinderLocationStatus.READY_FOR_HANDOVER.value,
                    BinderLocationStatus.HANDED_OVER.value,
                    "נמסר ללקוח",
                    handed_over_time,
                    "location_status",
                )
            )

        for old_value, new_value, note, changed_at, field_name in logs:
            actor = rng.choice(users)
            row = writer.record_action(
                ENTITY_BINDER,
                binder.id,
                actor.id,
                _binder_action_for_seed(field_name, new_value),
                old_value=lifecycle_value(field_name, None if old_value == "null" else old_value),
                new_value=lifecycle_value(field_name, new_value),
                note=note,
                actor_display_name=actor.full_name,
                metadata_json=binder_metadata(binder),
            )
            row.performed_at = changed_at
    db.flush()


def _binder_action_for_seed(field_name: str, new_value: str) -> str:
    if field_name == "capacity_status" and new_value == BinderCapacityStatus.FULL.value:
        return ACTION_BINDER_MARKED_FULL
    if (
        field_name == "location_status"
        and new_value == BinderLocationStatus.READY_FOR_HANDOVER.value
    ):
        return ACTION_BINDER_MARKED_READY_FOR_HANDOVER
    if field_name == "location_status" and new_value == BinderLocationStatus.HANDED_OVER.value:
        return ACTION_BINDER_HANDED_OVER
    return ACTION_BINDER_MATERIAL_RECEIVED


def create_binder_intakes(db, binders) -> list[BinderIntake]:
    intakes: list[BinderIntake] = []
    for binder in binders:
        intake = BinderIntake(
            binder_id=binder.id,
            received_at=binder.period_start,
            received_by=binder.created_by,
            notes=binder.notes,
        )
        db.add(intake)
        intakes.append(intake)
    db.flush()
    return intakes


def create_binder_intake_materials(
    db, rng: Random, binders, businesses, reports, intakes
) -> list[BinderIntakeMaterial]:
    materials: list[BinderIntakeMaterial] = []
    now = datetime.now(UTC)
    businesses_by_client: dict[int, list] = _group_businesses_by_client(businesses)

    reports_by_client: dict[int, list] = {}
    for report in reports:
        reports_by_client.setdefault(get_seed_client_record_id(report), []).append(report)

    intake_by_binder = {intake.binder_id: intake for intake in intakes}

    for binder in binders:
        intake = intake_by_binder.get(binder.id)
        if intake is None:
            continue
        binder_client_record_id = get_seed_client_record_id(binder)
        candidate_businesses = businesses_by_client.get(binder_client_record_id, [])
        for _ in range(rng.randint(1, 4)):
            business = rng.choice(candidate_businesses) if candidate_businesses else None
            report = None
            material_type = rng.choice(list(MaterialType))
            if business and rng.random() < 0.45:
                client_reports = reports_by_client.get(get_seed_client_record_id(business), [])
                if client_reports:
                    report = rng.choice(client_reports)
            period_year = (
                report.tax_year
                if report and material_type == MaterialType.ANNUAL_REPORT
                else binder.period_start.year
            )
            period_month_start = binder.period_start.month
            period_month_end = period_month_start
            if material_type == MaterialType.VAT and business:
                cr = getattr(business, "client", None)
                if getattr(cr, "vat_reporting_frequency", None) == VatType.BIMONTHLY:
                    period_month_end = min(12, period_month_start + 1)
            db.add(
                BinderIntakeMaterial(
                    intake_id=intake.id,
                    business_id=business.id if business else None,
                    material_type=material_type,
                    annual_report_id=report.id if report else None,
                    period_year=period_year,
                    period_month_start=period_month_start,
                    period_month_end=period_month_end,
                    description=MATERIAL_DESCRIPTIONS[material_type],
                    created_at=min(
                        now,
                        datetime.combine(intake.received_at, datetime.min.time(), tzinfo=UTC)
                        + timedelta(days=rng.randint(0, 14), hours=rng.randint(1, 10)),
                    ),
                )
            )
    db.flush()
    return materials


def create_binder_handovers(db, rng: Random, binders, users) -> list[BinderHandover]:
    handovers: list[BinderHandover] = []
    handed_over_by_client: dict[int, list[Binder]] = {}
    for binder in binders:
        if binder.location_status != BinderLocationStatus.HANDED_OVER:
            continue
        handed_over_by_client.setdefault(get_seed_client_record_id(binder), []).append(binder)

    for client_id, client_binders in handed_over_by_client.items():
        ordered = sorted(
            client_binders,
            key=lambda b: (b.handed_over_at or b.period_end or b.period_start, b.id),
        )
        index = 0
        while index < len(ordered):
            group_size = min(rng.randint(1, 3), len(ordered) - index)
            group = ordered[index : index + group_size]
            index += group_size
            handed_over_at = max(
                (b.handed_over_at or b.period_end or b.period_start) for b in group
            )
            handover = BinderHandover(
                client_record_id=client_id,
                received_by_name=group[-1].handover_recipient_name or full_name(rng),
                handed_over_at=handed_over_at,
                until_period_year=handed_over_at.year,
                until_period_month=handed_over_at.month,
                notes=rng.choice(
                    [
                        None,
                        "המסירה בוצעה במשרד הלקוח",
                        "הלקוח קיבל את כל החומר עד למועד זה",
                        "המסירה בוצעה לאחר תיאום טלפוני",
                    ]
                ),
                created_by=rng.choice(users).id,
                created_at=datetime.combine(handed_over_at, datetime.min.time(), tzinfo=UTC)
                + timedelta(hours=rng.randint(9, 18)),
            )
            db.add(handover)
            db.flush()
            handovers.append(handover)
            for b in group:
                db.add(BinderHandoverBinder(handover_id=handover.id, binder_id=b.id))

    db.flush()
    return handovers


def create_binder_intake_audit_logs(db, rng: Random, intakes, users) -> None:
    if not intakes or not users:
        return
    writer = EntityAuditWriter(db)
    sample_size = min(len(intakes), max(1, len(intakes) // 3))
    for intake in rng.sample(intakes, sample_size):
        binder = db.get(Binder, intake.binder_id)
        if binder is None:
            continue
        edit_time = datetime.combine(
            intake.received_at, datetime.min.time(), tzinfo=UTC
        ) + timedelta(days=rng.randint(0, 10), hours=rng.randint(9, 18))
        note_suffix = rng.choice(
            [
                "הושלם לאחר שיחת הבהרה עם הלקוח",
                "עודכן לאחר קליטת החומר במשרד",
                "נוספה הערה לאחר בדיקת מסמכים",
            ]
        )
        old_notes = intake.notes or None
        new_notes = note_suffix if not intake.notes else f"{intake.notes}. {note_suffix}"
        actor = rng.choice(users)
        row = writer.record_action(
            ENTITY_BINDER_INTAKE,
            intake.id,
            actor.id,
            ACTION_BINDER_INTAKE_UPDATED,
            old_value=old_notes,
            new_value=new_notes,
            actor_display_name=actor.full_name,
            metadata_json=intake_metadata(
                client_record_id=binder.client_record_id,
                binder_id=binder.id,
                intake_id=intake.id,
                field_name="notes",
            ),
        )
        row.performed_at = edit_time
        intake.notes = new_notes

        if rng.random() < 0.4:
            shifted_date = intake.received_at + timedelta(days=1)
            actor = rng.choice(users)
            row = writer.record_action(
                ENTITY_BINDER_INTAKE,
                intake.id,
                actor.id,
                ACTION_BINDER_INTAKE_UPDATED,
                old_value=str(intake.received_at),
                new_value=str(shifted_date),
                actor_display_name=actor.full_name,
                metadata_json=intake_metadata(
                    client_record_id=binder.client_record_id,
                    binder_id=binder.id,
                    intake_id=intake.id,
                    field_name="received_at",
                ),
            )
            row.performed_at = edit_time + timedelta(minutes=15)
            intake.received_at = shifted_date

    db.flush()
