"""Service: client-level VAT summary."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import NotFoundError
from app.vat.repositories.vat_client_summary_repository import (
    VatClientSummaryRepository,
)
from app.vat.schemas.vat_client_summary_schema import (
    VatAnnualSummary,
    VatClientSummaryResponse,
    VatPeriodRow,
)
from app.vat.services.messages import VAT_CLIENT_NOT_FOUND
from app.vat.services.vat_report_queries import get_vat_deadline_fields


def get_client_summary(
    db: Session,
    *,
    client_record_id: int,
    period_year_after: int | None = None,
    period_year_before: int | None = None,
) -> VatClientSummaryResponse:
    summary_repo = VatClientSummaryRepository(db)
    if not ClientRecordRepository(db).get_by_id(client_record_id):
        raise NotFoundError(
            VAT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
            "VAT.NOT_FOUND",
        )

    raw_periods = summary_repo.get_periods_for_client(
        client_record_id, period_year_after=period_year_after, period_year_before=period_year_before
    )
    periods = [
        VatPeriodRow(
            work_item_id=r.id,
            period=r.period,
            period_type=r.period_type.value if r.period_type else None,
            status=r.status,
            total_output_vat=r.total_output_vat,
            total_input_vat=r.total_input_vat,
            net_vat=r.net_vat,
            total_output_net=Decimal(str(output_net)),
            total_input_net=Decimal(str(input_net)),
            final_vat_amount=r.final_vat_amount,
            filed_at=r.filed_at,
            **get_vat_deadline_fields(r, r.submission_method),
        )
        for r, output_net, input_net in raw_periods
    ]

    raw_annual = summary_repo.get_annual_aggregates(
        client_record_id, period_year_after=period_year_after, period_year_before=period_year_before
    )
    annual = [VatAnnualSummary.model_validate(row) for row in raw_annual]

    return VatClientSummaryResponse(
        client_record_id=client_record_id,
        periods=periods,
        annual=annual,
    )
