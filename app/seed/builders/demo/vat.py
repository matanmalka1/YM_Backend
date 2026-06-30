from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from random import Random

from sqlalchemy import select

from app.annual_reports.models.annual_report_enums import SubmissionMethod
from app.businesses.models.business import BusinessStatus
from app.common.enums import ObligationType, VatType
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.users.models.user import UserRole
from app.vat.models.vat_enums import (
    CounterpartyIdType,
    DocumentType,
    ExpenseCategory,
    InvoiceType,
    VatRateType,
    VatWorkItemStatus,
)
from app.vat.models.vat_invoice import VatInvoice
from app.vat.models.vat_work_item import VatWorkItem

from ...data.demo_catalog import VAT_COUNTERPARTIES
from ...data.random_utils import generate_valid_israeli_id
from ...data.realistic_seed_text import (
    VAT_COUNTERPARTY_DETAILS,
    VAT_INCOME_COUNTERPARTIES,
)
from ..shared.client_refs import (
    attach_seed_client_context,
    get_seed_client_record,
    get_seed_client_record_id,
)

DEDUCTION_RATES: dict[ExpenseCategory, Decimal] = {
    ExpenseCategory.TRAVEL: Decimal("0.6667"),
    ExpenseCategory.VEHICLE: Decimal("0.6667"),
    ExpenseCategory.FUEL: Decimal("0.6667"),
    ExpenseCategory.VEHICLE_MAINTENANCE: Decimal("0.6667"),
    ExpenseCategory.VEHICLE_LEASING: Decimal("0.6667"),
    ExpenseCategory.TOLLS_AND_PARKING: Decimal("0.6667"),
    ExpenseCategory.COMMUNICATION: Decimal("0.6667"),
    ExpenseCategory.MIXED_EXPENSE: Decimal("0.6667"),
    ExpenseCategory.SALARY: Decimal("0.0000"),
    ExpenseCategory.INSURANCE: Decimal("0.0000"),
    ExpenseCategory.ENTERTAINMENT: Decimal("0.0000"),
    ExpenseCategory.GIFTS: Decimal("0.0000"),
    ExpenseCategory.MUNICIPAL_TAX: Decimal("0.0000"),
}

_VAT_PERIOD_MONTHS_COUNT = {VatType.MONTHLY: 1, VatType.BIMONTHLY: 2}


def _group_by_client(businesses) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for b in businesses:
        grouped.setdefault(get_seed_client_record_id(b), []).append(b)
    return grouped


def _choose_periods(
    db,
    rng: Random,
    count: int,
    reference_date: date,
    vat_type: VatType,
) -> list[str]:
    today = datetime.combine(reference_date, datetime.min.time(), tzinfo=UTC)
    periods: list[str] = []
    for i in range(1, count * 2 + 1):
        candidate = (today - timedelta(days=30 * i)).strftime("%Y-%m")
        if vat_type == VatType.BIMONTHLY and int(candidate.split("-")[1]) % 2 == 0:
            continue
        if _vat_due_date(db, candidate, vat_type) >= reference_date:
            continue
        if candidate not in periods:
            periods.append(candidate)
        if len(periods) >= count:
            break
    return periods[:count]


def _vat_due_date(db, period: str, vat_type: VatType) -> date:
    period_months_count = _VAT_PERIOD_MONTHS_COUNT[vat_type]
    entry = TaxCalendarMaterializationService(db).ensure_periodic_entry(
        ObligationType.VAT,
        period,
        period_months_count,
    )
    return entry.due_date


def _status_for_period(
    rng: Random, period: str, reference_date: date
) -> VatWorkItemStatus:
    period_year = int(period.split("-")[0])
    if period_year <= reference_date.year - 2:
        return VatWorkItemStatus.FILED

    period_start = datetime.strptime(f"{period}-01", "%Y-%m-%d").date()
    age_days = (reference_date - period_start).days
    if age_days > 90:
        return rng.choices(
            [
                VatWorkItemStatus.FILED,
                VatWorkItemStatus.READY_FOR_REVIEW,
                VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
            ],
            weights=[75, 15, 10],
            k=1,
        )[0]
    if age_days > 30:
        return rng.choice(
            [
                VatWorkItemStatus.PENDING_MATERIALS,
                VatWorkItemStatus.MATERIAL_RECEIVED,
                VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
                VatWorkItemStatus.READY_FOR_REVIEW,
                VatWorkItemStatus.FILED,
            ]
        )
    return rng.choices(
        [
            VatWorkItemStatus.PENDING_MATERIALS,
            VatWorkItemStatus.MATERIAL_RECEIVED,
            VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
            VatWorkItemStatus.READY_FOR_REVIEW,
        ],
        weights=[45, 25, 20, 10],
        k=1,
    )[0]


def _promote_to_filed(rng: Random, item: VatWorkItem, cfg) -> None:
    item.status = VatWorkItemStatus.FILED
    item.submission_method = rng.choice(list(SubmissionMethod))
    period_dt = datetime.strptime(f"{item.period}-01", "%Y-%m-%d").replace(tzinfo=UTC)
    filed_at = period_dt + timedelta(days=rng.randint(15, 45))
    reference_now = datetime.combine(
        cfg.reference_date, datetime.min.time(), tzinfo=UTC
    )
    item.filed_at = min(filed_at, reference_now)
    item.filed_by = item.assigned_to or item.created_by
    if not item.submission_reference:
        item.submission_reference = (
            f"VAT-{item.period.replace('-', '')}-{rng.randint(1000, 9999)}"
        )


def _invoice_date_for_period(rng: Random, period: str):
    period_start = datetime.strptime(f"{period}-01", "%Y-%m-%d").replace(tzinfo=UTC)
    return (period_start + timedelta(days=rng.randint(0, 27))).date()


def create_vat_work_items(db, rng: Random, cfg, businesses, users) -> list[VatWorkItem]:
    advisors = [u.id for u in users if u.role == UserRole.ADVISOR]
    fallback_user_id = users[0].id if users else None
    work_items: list[VatWorkItem] = []

    for client_businesses in _group_by_client(businesses).values():
        # Guard: only create VAT items for eligible (non-EXEMPT) clients
        # Use the client's own vat_reporting_frequency via in-memory helper
        eligible_businesses = [
            b
            for b in client_businesses
            if getattr(get_seed_client_record(b), "vat_reporting_frequency", None)
            in (VatType.MONTHLY, VatType.BIMONTHLY)
        ]
        if not eligible_businesses:
            continue
        business = rng.choice(eligible_businesses)
        num_items = rng.randint(
            cfg.min_vat_work_items_per_client, cfg.max_vat_work_items_per_client
        )
        cr = get_seed_client_record(business)
        period_type = getattr(cr, "vat_reporting_frequency", VatType.MONTHLY)
        business_client_record_id = get_seed_client_record_id(business)
        periods = _choose_periods(db, rng, num_items, cfg.reference_date, period_type)

        for period in periods:
            existing_item = db.scalars(
                select(VatWorkItem).where(
                    VatWorkItem.client_record_id == business_client_record_id,
                    VatWorkItem.period == period,
                    VatWorkItem.deleted_at.is_(None),
                )
            ).first()
            if existing_item is not None:
                # If onboarding created this with a non-final status for a pre-current-year
                # period, upgrade it now.
                period_year = int(period.split("-")[0])
                if (
                    period_year < cfg.reference_date.year
                    and existing_item.status != VatWorkItemStatus.FILED
                ):
                    _promote_to_filed(rng, existing_item, cfg)
                    work_items.append(existing_item)
                continue

            period_start = datetime.strptime(f"{period}-01", "%Y-%m-%d").replace(
                tzinfo=UTC
            )
            created_at = max(
                period_start,
                datetime.now(UTC) - timedelta(days=rng.randint(5, 75)),
            )
            if created_at > datetime.now(UTC):
                created_at = datetime.now(UTC)

            if business.status == BusinessStatus.CLOSED:
                status = rng.choice(
                    [VatWorkItemStatus.FILED, VatWorkItemStatus.READY_FOR_REVIEW]
                )
            elif business.status == BusinessStatus.FROZEN:
                status = rng.choice(
                    [
                        VatWorkItemStatus.PENDING_MATERIALS,
                        VatWorkItemStatus.MATERIAL_RECEIVED,
                        VatWorkItemStatus.READY_FOR_REVIEW,
                    ]
                )
            else:
                status = _status_for_period(rng, period, cfg.reference_date)

            period_year = int(period.split("-")[0])
            _FINAL_VAT = (
                VatWorkItemStatus.FILED,
                VatWorkItemStatus.CANCELED,
            )
            if period_year < cfg.reference_date.year and status not in _FINAL_VAT:
                status = VatWorkItemStatus.FILED

            created_by = rng.choice(advisors) if advisors else fallback_user_id
            period_months_count = _VAT_PERIOD_MONTHS_COUNT.get(period_type)
            tax_calendar_entry = TaxCalendarMaterializationService(
                db
            ).ensure_periodic_entry(ObligationType.VAT, period, period_months_count)
            work_item = VatWorkItem(
                client_record_id=business_client_record_id,
                created_by=created_by,
                assigned_to=rng.choice(advisors)
                if advisors and rng.random() < 0.7
                else None,
                period=period,
                period_type=period_type,
                status=status,
                created_at=created_at,
                updated_at=created_at,
                pending_materials_note="ממתינים לחשבוניות מהלקוח"
                if status == VatWorkItemStatus.PENDING_MATERIALS and rng.random() < 0.5
                else None,
                tax_calendar_entry_id=tax_calendar_entry.id,
                due_date_original=tax_calendar_entry.due_date,
                due_date_effective=tax_calendar_entry.due_date,
            )
            if cr is not None:
                attach_seed_client_context(work_item, cr)
            if status == VatWorkItemStatus.FILED:
                work_item.submission_method = rng.choice(list(SubmissionMethod))
                filed_at_candidate = max(
                    created_at, datetime.now(UTC) - timedelta(days=rng.randint(1, 90))
                )
                reference_now = datetime.combine(
                    cfg.reference_date, datetime.min.time(), tzinfo=UTC
                )
                work_item.filed_at = min(reference_now, filed_at_candidate)
                work_item.filed_by = work_item.assigned_to or work_item.created_by
                work_item.submission_reference = (
                    f"VAT-{work_item.period.replace('-', '')}-{rng.randint(1000, 9999)}"
                )

            db.add(work_item)
            work_items.append(work_item)

    db.flush()

    # Add amendments to some filed items
    filed_by_client: dict[int, list[VatWorkItem]] = defaultdict(list)
    for work_item in work_items:
        if work_item.status == VatWorkItemStatus.FILED:
            filed_by_client[get_seed_client_record_id(work_item)].append(work_item)

    for filed_items in filed_by_client.values():
        filed_items.sort(key=lambda item: item.period)
        for index in range(1, len(filed_items)):
            if rng.random() < 0.2:
                filed_items[index].is_amendment = True
                filed_items[index].amends_item_id = filed_items[index - 1].id
                ref = (
                    filed_items[index].submission_reference
                    or f"VAT-{filed_items[index].period.replace('-', '')}-{rng.randint(1000, 9999)}"
                )
                filed_items[index].submission_reference = f"{ref}-AMD"

    # Sweep: fix any onboarding-created items not reached above.
    db.expire_all()
    stragglers = db.scalars(
        select(VatWorkItem).where(
            VatWorkItem.period < f"{cfg.reference_date.year}-01",
            VatWorkItem.status != VatWorkItemStatus.FILED,
            VatWorkItem.deleted_at.is_(None),
        )
    ).all()
    for item in stragglers:
        _promote_to_filed(rng, item, cfg)
    db.flush()

    return work_items


def create_vat_invoices(db, rng: Random, cfg, work_items, users) -> list[VatInvoice]:
    invoices: list[VatInvoice] = []
    totals = defaultdict(lambda: {"output": Decimal("0.00"), "input": Decimal("0.00")})
    invoice_counters: dict[int, int] = defaultdict(int)

    for work_item in work_items:
        num_invoices = rng.randint(
            cfg.min_vat_invoices_per_work_item, cfg.max_vat_invoices_per_work_item
        )
        for _ in range(num_invoices):
            invoice_type = rng.choice(list(InvoiceType))
            if invoice_type == InvoiceType.EXPENSE:
                category_pool = list(VAT_COUNTERPARTY_DETAILS)
                if rng.random() < 0.2:
                    category_pool = list(ExpenseCategory)
                expense_category = rng.choice(category_pool)
                counterparty_name, min_amount, max_amount = (
                    VAT_COUNTERPARTY_DETAILS.get(
                        expense_category,
                        (rng.choice(VAT_COUNTERPARTIES), 250, 12000),
                    )
                )
                base_amount = Decimal(
                    str(round(rng.uniform(min_amount, max_amount), 2))
                )
                document_type = rng.choice(
                    [
                        DocumentType.TAX_INVOICE,
                        DocumentType.TRANSACTION_INVOICE,
                        DocumentType.RECEIPT,
                        DocumentType.CONSOLIDATED,
                        DocumentType.SELF_INVOICE,
                    ]
                )
                deduction_rate = DEDUCTION_RATES.get(
                    expense_category, Decimal("1.0000")
                )
            else:
                expense_category = None
                counterparty_name, min_amount, max_amount = rng.choice(
                    VAT_INCOME_COUNTERPARTIES
                )
                base_amount = Decimal(
                    str(round(rng.uniform(min_amount, max_amount), 2))
                )
                document_type = rng.choice(
                    [
                        DocumentType.TAX_INVOICE,
                        DocumentType.TRANSACTION_INVOICE,
                        DocumentType.RECEIPT,
                        DocumentType.CREDIT_NOTE,
                    ]
                )
                deduction_rate = Decimal("1.0000")

            rate_type = rng.choice(
                [
                    VatRateType.STANDARD,
                    VatRateType.STANDARD,
                    VatRateType.ZERO_RATE,
                    VatRateType.EXEMPT,
                ]
            )
            vat_amount = (
                Decimal("0.00")
                if rate_type in (VatRateType.ZERO_RATE, VatRateType.EXEMPT)
                else (base_amount * Decimal("0.18")).quantize(Decimal("0.01"))
            )

            invoice_counters[work_item.id] += 1
            invoice_number = f"{work_item.period.replace('-', '')}-{invoice_counters[work_item.id]:03d}"
            counterparty_id_type = (
                CounterpartyIdType.IL_BUSINESS
                if document_type == DocumentType.TAX_INVOICE
                else rng.choice(
                    [
                        CounterpartyIdType.IL_BUSINESS,
                        CounterpartyIdType.IL_PERSONAL,
                        CounterpartyIdType.FOREIGN,
                    ]
                )
            )
            if counterparty_id_type == CounterpartyIdType.IL_BUSINESS:
                counterparty_id = generate_valid_israeli_id(
                    work_item.id * 1000 + invoice_counters[work_item.id], prefix="5"
                )
            elif counterparty_id_type == CounterpartyIdType.IL_PERSONAL:
                counterparty_id = generate_valid_israeli_id(
                    work_item.id * 1000 + invoice_counters[work_item.id],
                    prefix=str(rng.choice([0, 1, 2, 3])),
                )
            else:
                counterparty_id = f"F{rng.randint(1000000, 9999999)}"

            invoice = VatInvoice(
                work_item_id=work_item.id,
                created_by=work_item.created_by or rng.choice(users).id,
                invoice_type=invoice_type,
                document_type=document_type,
                invoice_number=invoice_number,
                invoice_date=_invoice_date_for_period(rng, work_item.period),
                counterparty_name=counterparty_name,
                counterparty_id=counterparty_id,
                counterparty_id_type=counterparty_id_type,
                net_amount=base_amount,
                vat_amount=vat_amount,
                expense_category=expense_category,
                rate_type=rate_type,
                deduction_rate=deduction_rate,
                is_exceptional=base_amount > Decimal("25000"),
            )
            db.add(invoice)
            invoices.append(invoice)

            if invoice_type == InvoiceType.INCOME:
                totals[work_item.id]["output"] += vat_amount
            else:
                totals[work_item.id]["input"] += (vat_amount * deduction_rate).quantize(
                    Decimal("0.01")
                )

    db.flush()

    for work_item in work_items:
        output_vat = totals[work_item.id]["output"]
        input_vat = totals[work_item.id]["input"]
        work_item.total_output_vat = output_vat
        work_item.total_input_vat = input_vat
        work_item.net_vat = output_vat - input_vat
        work_item.total_output_net = Decimal("0.00")
        work_item.total_input_net = Decimal("0.00")
        for invoice in invoices:
            if invoice.work_item_id != work_item.id:
                continue
            if invoice.invoice_type == InvoiceType.INCOME:
                work_item.total_output_net += Decimal(invoice.net_amount)
            else:
                work_item.total_input_net += Decimal(invoice.net_amount)
        if work_item.status == VatWorkItemStatus.FILED:
            work_item.final_vat_amount = work_item.net_vat
            work_item.is_overridden = rng.random() < 0.1
            if work_item.is_overridden:
                work_item.override_justification = "התאמה ידנית לעיגול"

    db.flush()
    return invoices


# VAT audit rows are no longer seeded: VAT mutations write to the generic
# EntityAuditLog via EntityAuditWriter at runtime (Phase 3 audit refactor). The
# demo seed creates work items/invoices directly (no service-layer mutations), so
# there are no seeded VAT audit rows; the legacy create_vat_audit_logs builder was
# removed with VatAuditLog's read path.
