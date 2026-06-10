from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from random import Random

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.invoices.models.invoice import Invoice

from ...data.demo_catalog import INVOICE_BASE_URL
from ...data.realistic_seed_text import CHARGE_TYPE_DETAILS
from ..shared.client_refs import get_seed_client_record_id


def _group_by_client(businesses) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for b in businesses:
        grouped.setdefault(get_seed_client_record_id(b), []).append(b)
    return grouped


def _pick_businesses(rng: Random, client_businesses: list, count: int) -> list:
    if count <= 0 or not client_businesses:
        return []
    return [rng.choice(client_businesses) for _ in range(count)]


def create_charges(db, rng: Random, cfg, businesses, users=None) -> list[Charge]:
    charges: list[Charge] = []
    current_year = cfg.reference_date.year
    for client_businesses in _group_by_client(businesses).values():
        num = rng.randint(cfg.min_charges_per_client, cfg.max_charges_per_client)
        for business in _pick_businesses(rng, client_businesses, num):
            created_at = datetime.now(UTC) - timedelta(days=rng.randint(0, 240))
            is_old = created_at.year < current_year
            if is_old:
                status = rng.choices(
                    [ChargeStatus.PAID, ChargeStatus.CANCELED],
                    weights=[85, 15],
                    k=1,
                )[0]
            else:
                status = rng.choices(
                    [
                        ChargeStatus.DRAFT,
                        ChargeStatus.ISSUED,
                        ChargeStatus.PAID,
                        ChargeStatus.CANCELED,
                    ],
                    weights=[20, 30, 40, 10],
                    k=1,
                )[0]
            issued_at = None
            issued_by = None
            paid_at = None
            paid_by = None
            if status in (ChargeStatus.ISSUED, ChargeStatus.PAID):
                issued_at = created_at + timedelta(days=rng.randint(0, 6))
                issued_by = rng.choice(users).id if users else None
            if status == ChargeStatus.PAID:
                paid_at = issued_at + timedelta(days=rng.randint(0, 20))
                paid_by = rng.choice(users).id if users else None

            charge_type = rng.choices(
                list(ChargeType), weights=[35, 20, 18, 8, 12, 7], k=1
            )[0]
            period = None
            months_covered = 1
            if charge_type == ChargeType.MONTHLY_RETAINER:
                month = rng.randint(1, 12)
                year = date.today().year - rng.randint(0, 1)
                period = f"{year}-{month:02d}"
                months_covered = rng.choice([1, 1, 1, 2])
            elif charge_type == ChargeType.ANNUAL_REPORT_FEE:
                period = f"{date.today().year - rng.randint(1, 3)}-12"
            elif (
                charge_type in (ChargeType.VAT_FILING_FEE, ChargeType.OTHER)
                and rng.random() < 0.4
            ):
                month = rng.randint(1, 12)
                year = date.today().year - rng.randint(0, 1)
                period = f"{year}-{month:02d}"
                months_covered = rng.choice([1, 2])

            base_description, min_amount, max_amount = CHARGE_TYPE_DETAILS[charge_type]
            amount = Decimal(str(round(rng.uniform(min_amount, max_amount), 2)))
            canceled_at = None
            canceled_by = None
            cancellation_reason = None
            if status == ChargeStatus.CANCELED:
                canceled_at = created_at + timedelta(days=rng.randint(1, 8))
                canceled_by = rng.choice(users).id if users else None
                cancellation_reason = rng.choice(
                    [
                        "החיוב בוטל לאחר זיכוי הלקוח",
                        "החיוב נפתח בטעות ונסגר לפני הפקה",
                    ]
                )

            charge = Charge(
                client_record_id=get_seed_client_record_id(business),
                business_id=business.id,
                amount=amount,
                charge_type=charge_type,
                period=period,
                months_covered=months_covered,
                status=status,
                description=" | ".join(
                    filter(
                        None,
                        [
                            base_description,
                            business.business_name,
                            f"תקופה {period}" if period else None,
                        ],
                    )
                ),
                created_at=created_at,
                created_by=rng.choice(users).id if users else None,
                issued_at=issued_at,
                issued_by=issued_by,
                paid_at=paid_at,
                paid_by=paid_by,
                canceled_at=canceled_at,
                canceled_by=canceled_by,
                cancellation_reason=cancellation_reason,
            )
            db.add(charge)
            charges.append(charge)
    db.flush()
    return charges


def create_invoices(db, charges) -> None:
    invoice_serial = 70000
    for charge in charges:
        if charge.status not in (ChargeStatus.ISSUED, ChargeStatus.PAID):
            continue
        invoice_id = f"חשבונית-{invoice_serial}"
        db.add(
            Invoice(
                charge_id=charge.id,
                provider="מערכת הנהלת חשבונות פנימית",
                external_invoice_id=invoice_id,
                document_url=f"{INVOICE_BASE_URL}/{invoice_id}.pdf",
                issued_at=charge.issued_at or charge.created_at,
                created_at=charge.created_at,
            )
        )
        invoice_serial += 1
    db.flush()
