from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from random import Random
from typing import Any, Iterable

from sqlalchemy import select


from app.annual_reports.models.annual_report_annex_data import AnnualReportAnnexData
from app.annual_reports.models.annual_report_credit_point_reason import (
    AnnualReportCreditPoint,
    CreditPointReason,
)
from app.annual_reports.models.annual_report_detail import AnnualReportDetail
from app.annual_reports.models.annual_report_enums import (
    PrimaryAnnualReportForm,
    AnnualReportSchedule,
    AnnualReportStatus,
    ClientAnnualFilingType,
    ExtensionReason,
    FilingDeadlineType as DeadlineType,
    SubmissionMethod,
)
from app.annual_reports.models.annual_report_expense_line import (
    AnnualReportExpenseLine,
    ExpenseCategoryType,
)
from app.annual_reports.models.annual_report_income_line import (
    AnnualReportIncomeLine,
    IncomeSourceType,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.models.annual_report_schedule_entry import (
    AnnualReportScheduleEntry,
)
from app.annual_reports.models.annual_report_status_history import (
    AnnualReportStatusHistory,
)
from app.annual_reports.domain.expense_rules import default_recognition_rate
from app.annual_reports.annual_report_constants import VALID_TRANSITIONS
from app.annual_reports.services.annual_report_deadlines import extended_deadline, standard_deadline
from app.common.enums import EntityType
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.users.models.user import UserRole

from ...data.realistic_seed_text import EXPENSE_DESCRIPTIONS, INCOME_DESCRIPTIONS
from ..shared.client_refs import (
    attach_seed_client_context,
    get_seed_client_record,
    get_seed_client_record_id,
)


SEEDABLE_STATUSES = [
    AnnualReportStatus.NOT_STARTED,
    AnnualReportStatus.COLLECTING_DOCS,
    AnnualReportStatus.IN_PREPARATION,
    AnnualReportStatus.PENDING_CLIENT,
    AnnualReportStatus.SUBMITTED,
    AnnualReportStatus.CLOSED,
    AnnualReportStatus.CANCELED,
]

FINAL_STATUSES = [
    AnnualReportStatus.SUBMITTED,
    AnnualReportStatus.CLOSED,
    AnnualReportStatus.CANCELED,
]

COUNTRIES = ["ארצות הברית", "בריטניה", "גרמניה", "צרפת", "קפריסין", "פורטוגל"]
PROPERTY_CITIES = ["תל אביב", "ירושלים", "חיפה", "נתניה", "הרצליה"]
SECURITIES = ["מניית בנק לאומי", "מדד S&P 500", 'קרן סל ת"א 125', 'אג"ח ממשלתי']


def _group_by_client(businesses) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for b in businesses:
        grouped.setdefault(get_seed_client_record_id(b), []).append(b)
    return grouped


def _random_decimal(rng: Random, minimum: float, maximum: float) -> Decimal:
    return Decimal(str(round(rng.uniform(minimum, maximum), 2)))


def _as_plain_decimal(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _property_address(rng: Random) -> str:
    return f"{rng.choice(['הרצל', 'ביאליק', 'ויצמן', 'דיזנגוף'])} {rng.randint(1, 120)}, {rng.choice(PROPERTY_CITIES)}"


def _build_annex_payload(
    rng: Random, report: AnnualReport, schedule: AnnualReportSchedule
) -> dict[str, Any]:
    if schedule == AnnualReportSchedule.SCHEDULE_A:
        gross = _random_decimal(rng, 80_000, 520_000)
        cogs = _random_decimal(rng, 10_000, float(gross * Decimal("0.65")))
        gp = gross - cogs
        opex = _random_decimal(rng, 15_000, float(gp * Decimal("0.85")))
        return {
            "gross_income": _as_plain_decimal(gross),
            "cost_of_goods": _as_plain_decimal(cogs),
            "gross_profit": _as_plain_decimal(gp),
            "operating_expenses": _as_plain_decimal(opex),
            "net_income": _as_plain_decimal(gp - opex),
        }
    if schedule == AnnualReportSchedule.SCHEDULE_B:
        ri = _random_decimal(rng, 24_000, 96_000)
        maint = _random_decimal(rng, 1_500, 12_000)
        dep = _random_decimal(rng, 0, 8_000)
        return {
            "property_address": _property_address(rng),
            "rental_income": _as_plain_decimal(ri),
            "depreciation_claimed": _as_plain_decimal(dep),
            "maintenance_expenses": _as_plain_decimal(maint),
            "net_rental_income": _as_plain_decimal(ri - maint - dep),
        }
    if schedule == AnnualReportSchedule.FORM_1399:
        pp = _random_decimal(rng, 25_000, 220_000)
        sp = pp + _random_decimal(rng, 5_000, 90_000)
        return {
            "asset_description": rng.choice(["מכירת דירה להשקעה", "מכירת ציוד עסקי"]),
            "purchase_date": f"{report.tax_year - rng.randint(1, 6)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "sale_date": f"{report.tax_year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "purchase_price": _as_plain_decimal(pp),
            "sale_price": _as_plain_decimal(sp),
            "capital_gain": _as_plain_decimal(sp - pp),
            "tax_rate": _as_plain_decimal(_random_decimal(rng, 20, 30)),
        }
    if schedule == AnnualReportSchedule.SCHEDULE_DALET:
        gi = _random_decimal(rng, 8_000, 85_000)
        ft = _random_decimal(rng, 0, float(gi * Decimal("0.22")))
        return {
            "country": rng.choice(COUNTRIES),
            "income_type": rng.choice(["משכורת", "דיבידנד", "ריבית"]),
            "gross_income": _as_plain_decimal(gi),
            "foreign_tax_paid": _as_plain_decimal(ft),
            "net_income": _as_plain_decimal(gi - ft),
        }
    if schedule == AnnualReportSchedule.FORM_1342:
        ac = _random_decimal(rng, 6_000, 80_000)
        ad = _random_decimal(rng, 1_000, float(ac * Decimal("0.25")))
        acc = ad + _random_decimal(rng, 500, float(ac * Decimal("0.35")))
        return {
            "asset_description": rng.choice(["מחשב נייד", "ריהוט משרדי"]),
            "asset_cost": _as_plain_decimal(ac),
            "depreciation_rate": _as_plain_decimal(_random_decimal(rng, 7, 20)),
            "accumulated_depreciation": _as_plain_decimal(acc),
            "annual_depreciation": _as_plain_decimal(ad),
            "book_value": _as_plain_decimal(max(ac - acc, Decimal("0.00"))),
        }
    if schedule == AnnualReportSchedule.SCHEDULE_GIMMEL:
        pp = _random_decimal(rng, 8_000, 70_000)
        sp = pp + rng.choice(
            [_random_decimal(rng, 1_500, 20_000), -_random_decimal(rng, 500, 12_000)]
        )
        return {
            "security_name": rng.choice(SECURITIES),
            "quantity": _as_plain_decimal(_random_decimal(rng, 10, 600)),
            "purchase_price": _as_plain_decimal(pp),
            "sale_price": _as_plain_decimal(sp),
            "gain_loss": _as_plain_decimal(sp - pp),
        }
    if schedule == AnnualReportSchedule.FORM_150:
        ga = _random_decimal(rng, 6_000, 60_000)
        wh = _random_decimal(rng, 0, float(ga * Decimal("0.25")))
        return {
            "country": rng.choice(COUNTRIES),
            "income_description": rng.choice(["הכנסות ייעוץ", "דיבידנד"]),
            "gross_amount": _as_plain_decimal(ga),
            "withholding_tax": _as_plain_decimal(wh),
            "treaty_rate": _as_plain_decimal(_random_decimal(rng, 5, 25)),
        }
    if schedule == AnnualReportSchedule.FORM_1343:
        return {
            "bank_name": rng.choice(["בנק הפועלים", "בנק לאומי", "מזרחי טפחות"]),
            "account_number": f"{rng.randint(10000, 99999)}-{rng.randint(1000000, 9999999)}",
            "interest_income": _as_plain_decimal(_random_decimal(rng, 300, 8_000)),
            "dividend_income": _as_plain_decimal(_random_decimal(rng, 0, 12_000)),
            "withholding_tax": _as_plain_decimal(_random_decimal(rng, 0, 2_500)),
        }
    return {}


def _annex_schedules_for_report(
    report: AnnualReport, rng: Random
) -> list[AnnualReportSchedule]:
    schedules: list[AnnualReportSchedule] = []
    if report.client_type in (
        ClientAnnualFilingType.SELF_EMPLOYED,
        ClientAnnualFilingType.CORPORATION,
    ):
        schedules.append(AnnualReportSchedule.SCHEDULE_A)
    if report.has_rental_income:
        schedules.append(AnnualReportSchedule.SCHEDULE_B)
    if report.has_capital_gains:
        schedules.extend(
            [AnnualReportSchedule.FORM_1399, AnnualReportSchedule.SCHEDULE_GIMMEL]
        )
    if report.has_foreign_income:
        schedules.extend(
            [AnnualReportSchedule.SCHEDULE_DALET, AnnualReportSchedule.FORM_150]
        )
    if report.has_depreciation:
        schedules.append(AnnualReportSchedule.FORM_1342)
    if rng.random() < 0.35:
        schedules.append(AnnualReportSchedule.FORM_1343)
    return list(dict.fromkeys(schedules)) or [rng.choice(list(AnnualReportSchedule))]


def _status_path_to(target: AnnualReportStatus) -> list[AnnualReportStatus]:
    if target in (AnnualReportStatus.CANCELED, AnnualReportStatus.NOT_STARTED):
        return [target]
    frontier: list[list[AnnualReportStatus]] = [[AnnualReportStatus.NOT_STARTED]]
    while frontier:
        path = frontier.pop(0)
        current = path[-1]
        for nxt in VALID_TRANSITIONS.get(current, set()):
            if nxt in path:
                continue
            new_path = [*path, nxt]
            if nxt == target:
                return new_path
            frontier.append(new_path)
    raise RuntimeError(
        f"Cannot build legal annual-report status path to {target.value}"
    )


def create_annual_reports(
    db, rng: Random, cfg, businesses, users
) -> list[AnnualReport]:
    """
    Creates historical annual report shells for years prior to current year.
    The current year's shell is already created by the onboarding orchestrator.
    """
    reports: list[AnnualReport] = []
    current_year = cfg.reference_date.year
    # Only historical years — onboarding already created current year shell
    available_years = list(
        range(current_year - cfg.annual_reports_per_client, current_year)
    )
    advisors = [u.id for u in users if u.role == UserRole.ADVISOR]
    fallback_user_id = users[0].id if users else None
    status_cycle = list(SEEDABLE_STATUSES)
    status_cycle_idx = 0

    for client_businesses in _group_by_client(businesses).values():
        years = rng.sample(
            available_years,
            k=min(cfg.annual_reports_per_client, len(available_years)),
        )
        for year in years:
            business = rng.choice(client_businesses)
            cr = get_seed_client_record(business)
            entity_type = getattr(cr, "entity_type", None)
            business_client_record_id = get_seed_client_record_id(business)

            if entity_type == EntityType.COMPANY_LTD:
                client_type_for_report = ClientAnnualFilingType.CORPORATION
                form_type = PrimaryAnnualReportForm.FORM_1214
            elif entity_type in (EntityType.OSEK_PATUR, EntityType.OSEK_MURSHE):
                client_type_for_report = ClientAnnualFilingType.SELF_EMPLOYED
                form_type = PrimaryAnnualReportForm.FORM_1301
            else:
                client_type_for_report = ClientAnnualFilingType.INDIVIDUAL
                form_type = PrimaryAnnualReportForm.FORM_1301

            # Skip if report already exists for this client/year
            existing = db.scalars(
                select(AnnualReport).where(
                    AnnualReport.client_record_id == business_client_record_id,
                    AnnualReport.tax_year == year,
                    AnnualReport.deleted_at.is_(None),
                )
            ).first()
            if existing:
                if (
                    existing.tax_year < current_year
                    and existing.status not in FINAL_STATUSES
                ):
                    existing.status = rng.choice(FINAL_STATUSES)
                reports.append(existing)
                continue

            # All historical years must be in a final (closed) state
            if year < current_year:
                status = rng.choice(FINAL_STATUSES)
            elif status_cycle_idx < len(status_cycle):
                status = status_cycle[status_cycle_idx]
                status_cycle_idx += 1
            else:
                status = rng.choice(SEEDABLE_STATUSES)

            deadline_type = rng.choice(list(DeadlineType))
            submission_method = (
                rng.choice(list(SubmissionMethod))
                if status
                in (
                    AnnualReportStatus.SUBMITTED,
                    AnnualReportStatus.CLOSED,
                )
                else None
            )
            if deadline_type == DeadlineType.STANDARD:
                filing_deadline = standard_deadline(
                    year,
                    client_type=client_type_for_report,
                    submission_method=submission_method,
                )
            elif deadline_type == DeadlineType.EXTENDED:
                filing_deadline = extended_deadline(year)
            else:
                filing_deadline = None

            extension_reason = (
                rng.choice(list(ExtensionReason))
                if deadline_type == DeadlineType.EXTENDED
                else None
            )
            created_at = datetime.now(UTC) - timedelta(days=rng.randint(0, 400))
            updated_at = min(
                datetime.now(UTC), created_at + timedelta(days=rng.randint(0, 60))
            )
            submitted_at = None
            if status in (
                AnnualReportStatus.SUBMITTED,
                AnnualReportStatus.CLOSED,
            ):
                submitted_at = min(
                    datetime.now(UTC), created_at + timedelta(days=rng.randint(1, 180))
                )
                if updated_at < submitted_at:
                    updated_at = submitted_at

            tax_calendar_entry = TaxCalendarMaterializationService(
                db
            ).ensure_annual_entry(year)
            report = AnnualReport(
                client_record_id=business_client_record_id,
                tax_year=year,
                tax_calendar_entry_id=tax_calendar_entry.id,
                client_type=client_type_for_report,
                form_type=form_type,
                status=status,
                deadline_type=deadline_type,
                filing_deadline=filing_deadline,
                custom_deadline_note="המועד עודכן בהתאם לאישור ארכה"
                if deadline_type == DeadlineType.CUSTOM
                else None,
                submitted_at=submitted_at,
                has_rental_income=rng.random() < 0.3,
                has_capital_gains=rng.random() < 0.25,
                has_foreign_income=rng.random() < 0.2,
                has_depreciation=rng.random() < 0.2,
                submission_method=submission_method,
                extension_reason=extension_reason,
                notes=rng.choice(["", "דורש בדיקה", "ממתין לחתימת לקוח"]),
                created_at=created_at,
                updated_at=updated_at,
                created_by=rng.choice(advisors) if advisors else fallback_user_id,
                assigned_to=rng.choice(advisors) if advisors else None,
            )
            if cr is not None:
                attach_seed_client_context(report, cr)
            db.add(report)
            reports.append(report)

    db.flush()
    return reports


def create_annual_report_details(db, rng: Random, reports) -> None:
    for report in reports:
        # Skip if detail already exists
        from app.annual_reports.models.annual_report_detail import (
            AnnualReportDetail as ARD,
        )

        if db.scalars(select(ARD).where(ARD.report_id == report.id)).first():
            continue
        client_approved_at = None
        if report.status in (
            AnnualReportStatus.SUBMITTED,
            AnnualReportStatus.CLOSED,
        ):
            upper = report.submitted_at or report.updated_at or datetime.now(UTC)
            candidate = report.created_at + timedelta(days=rng.randint(7, 45))
            client_approved_at = min(candidate, upper)
        db.add(
            AnnualReportDetail(
                report_id=report.id,
                pension_contribution=_random_decimal(rng, 0, 15_000),
                donation_amount=_random_decimal(rng, 0, 6_000),
                other_credits=_random_decimal(rng, 0, 3_500),
                client_approved_at=client_approved_at,
                internal_notes=rng.choice(
                    [None, "ממתין לאישור לקוח", "לעדכן נתוני שכר", 'לבדוק קלטי מע"מ']
                ),
                amendment_reason=(
                    rng.choice(["תיקון לפי מסמכים מעודכנים", "תיקון בעקבות שומת מס"])
                    if report.status == AnnualReportStatus.IN_PREPARATION
                    else None
                ),
                created_at=report.created_at,
            )
        )
    db.flush()


def create_annual_report_schedule_entries(db, rng: Random, reports, users=None) -> None:
    advisors = [u.id for u in users] if users else []
    fallback_user_id = users[0].id if users else None
    for report in reports:
        for schedule in list(AnnualReportSchedule):
            if db.scalars(
                select(AnnualReportScheduleEntry).where(
                    AnnualReportScheduleEntry.annual_report_id == report.id,
                    AnnualReportScheduleEntry.schedule == schedule,
                )
            ).first():
                continue
            is_required = rng.random() < 0.4
            is_complete = is_required and rng.random() < 0.5
            completed_at = None
            completed_by = None
            if is_complete:
                completed_at = report.created_at + timedelta(days=rng.randint(5, 60))
                completed_by = rng.choice(advisors) if advisors else fallback_user_id
            db.add(
                AnnualReportScheduleEntry(
                    annual_report_id=report.id,
                    schedule=schedule,
                    is_required=is_required,
                    is_complete=is_complete,
                    notes="נוצר אוטומטית" if is_required else None,
                    created_at=report.created_at,
                    completed_at=completed_at,
                    completed_by=completed_by,
                )
            )
    db.flush()


def create_annual_report_income_lines(db, rng: Random, reports) -> None:
    for report in reports:
        source_candidates = [IncomeSourceType.SALARY]
        if report.client_type in (
            ClientAnnualFilingType.SELF_EMPLOYED,
            ClientAnnualFilingType.CORPORATION,
        ):
            source_candidates.extend(
                [
                    IncomeSourceType.BUSINESS,
                    IncomeSourceType.INTEREST,
                    IncomeSourceType.DIVIDENDS,
                ]
            )
        if report.has_rental_income:
            source_candidates.append(IncomeSourceType.RENTAL)
        if report.has_capital_gains:
            source_candidates.append(IncomeSourceType.CAPITAL_GAINS)
        if report.has_foreign_income:
            source_candidates.append(IncomeSourceType.FOREIGN)
        unique_sources = list(dict.fromkeys(source_candidates))
        for source_type in rng.sample(
            unique_sources, k=min(len(unique_sources), rng.randint(1, 3))
        ):
            db.add(
                AnnualReportIncomeLine(
                    annual_report_id=report.id,
                    source_type=source_type,
                    amount=Decimal(str(round(rng.uniform(2_500, 120_000), 2))),
                    description=INCOME_DESCRIPTIONS.get(
                        source_type.value, "הכנסה נוספת לפי מסמכי הלקוח"
                    ),
                    created_at=report.created_at,
                )
            )
    db.flush()


def create_annual_report_expense_lines(
    db, rng: Random, reports, seeded_documents: Iterable | None = None
) -> None:
    base_categories = [
        ExpenseCategoryType.PROFESSIONAL_SERVICES,
        ExpenseCategoryType.BANK_FEES,
        ExpenseCategoryType.INSURANCE,
    ]
    documents_by_client: dict[int, list] = {}
    if seeded_documents:
        for doc in seeded_documents:
            documents_by_client.setdefault(get_seed_client_record_id(doc), []).append(
                doc
            )

    for report in reports:
        category_candidates = list(base_categories)
        if report.client_type in (
            ClientAnnualFilingType.SELF_EMPLOYED,
            ClientAnnualFilingType.CORPORATION,
        ):
            category_candidates.extend(
                [
                    ExpenseCategoryType.OFFICE_RENT,
                    ExpenseCategoryType.COMMUNICATION,
                    ExpenseCategoryType.VEHICLE,
                    ExpenseCategoryType.MARKETING,
                    ExpenseCategoryType.TRAVEL,
                    ExpenseCategoryType.TRAINING,
                ]
            )
        if report.has_depreciation:
            category_candidates.append(ExpenseCategoryType.DEPRECIATION)
        if rng.random() < 0.45:
            category_candidates.append(ExpenseCategoryType.OTHER)
        unique_categories = list(dict.fromkeys(category_candidates))
        for category in rng.sample(
            unique_categories, k=min(len(unique_categories), rng.randint(1, 4))
        ):
            client_docs = documents_by_client.get(get_seed_client_record_id(report), [])
            linked_doc = (
                rng.choice(client_docs) if client_docs and rng.random() < 0.7 else None
            )
            db.add(
                AnnualReportExpenseLine(
                    annual_report_id=report.id,
                    category=category,
                    amount=_random_decimal(rng, 200, 40_000),
                    recognition_rate=default_recognition_rate(category),
                    external_document_reference=(
                        (
                            linked_doc.original_filename
                            or linked_doc.storage_key.split("/")[-1]
                        )
                        if linked_doc
                        else (
                            f"EXP-{report.tax_year}-{rng.randint(1000, 9999)}"
                            if rng.random() < 0.35
                            else None
                        )
                    ),
                    supporting_document_id=linked_doc.id if linked_doc else None,
                    description=EXPENSE_DESCRIPTIONS.get(
                        category.value, "הוצאה עסקית לפי מסמך תומך"
                    ),
                    created_at=report.created_at,
                )
            )
    db.flush()


def create_annual_report_annex_data(db, rng: Random, reports) -> None:
    for report in reports:
        schedule_entries = {
            entry.schedule: entry
            for entry in db.scalars(
                select(AnnualReportScheduleEntry).where(
                    AnnualReportScheduleEntry.annual_report_id == report.id
                )
            ).all()
        }
        for line_number, schedule in enumerate(
            _annex_schedules_for_report(report, rng), start=1
        ):
            schedule_entry = schedule_entries.get(schedule)
            if schedule_entry is None:
                continue
            db.add(
                AnnualReportAnnexData(
                    schedule_entry_id=schedule_entry.id,
                    line_number=line_number,
                    data=_build_annex_payload(rng, report, schedule),
                    notes=rng.choice([None, "אומת מול טפסי 867", "נדרש מסמך תומך"]),
                    created_at=report.created_at,
                )
            )
    db.flush()


def create_annual_report_credit_points(db, rng: Random, reports) -> None:
    for report in reports:
        reason_candidates = list(CreditPointReason)
        rng.shuffle(reason_candidates)
        for reason in reason_candidates[
            : rng.randint(1, min(3, len(reason_candidates)))
        ]:
            points = (
                Decimal("2.25")
                if reason == CreditPointReason.RESIDENT
                else Decimal(str(rng.choice([0.5, 1.0, 1.5, 2.0])))
            )
            db.add(
                AnnualReportCreditPoint(
                    annual_report_id=report.id,
                    reason=reason,
                    points=points,
                    notes=rng.choice([None, "נקודת זיכוי לפי נתוני לקוח"]),
                )
            )
    db.flush()


def create_annual_report_status_history(db, rng: Random, reports, users) -> None:
    fallback_user = users[0] if users else None
    for report in reports:
        history_statuses = _status_path_to(report.status)
        previous = None
        occurred_at = report.created_at
        for status in history_statuses:
            actor_id = (
                report.created_by
                or report.assigned_to
                or (fallback_user.id if fallback_user else None)
            )
            occurred_at += timedelta(hours=rng.randint(1, 72))
            db.add(
                AnnualReportStatusHistory(
                    annual_report_id=report.id,
                    from_status=previous,
                    to_status=status,
                    changed_by=actor_id,
                    note=rng.choice(
                        [
                            "היסטוריית סטטוסים שנוצרה אוטומטית",
                            "עודכן לאחר בדיקת מסמכים",
                            "הועבר לשלב הבא",
                        ]
                    ),
                    occurred_at=occurred_at,
                )
            )
            previous = status
    db.flush()
