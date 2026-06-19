from datetime import date

from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.advance_payments.services.advance_payment_service import AdvancePaymentService


def generate_annual_schedule(
    client_record_id: int,
    year: int,
    db: Session,
    period_months_count: int | None = None,
    reference_date: date | None = None,
) -> tuple[list[AdvancePayment], int]:
    return AdvancePaymentService(db).generate_annual_schedule(
        client_record_id,
        year,
        period_months_count=period_months_count,
        reference_date=reference_date,
    )
