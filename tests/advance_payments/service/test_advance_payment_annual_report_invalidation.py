"""Cross-domain: advance-payment writes must invalidate an open annual report's tax.

The annual report's ``advances_paid`` comes from an aggregate that sums ``paid_amount``
*and* filters on ``status == PAID``, so any advance-payment write that can move either
one makes a previously saved ``tax_due``/``refund_due`` stale.

Invalidation used to live in the single-record PATCH route, so bulk settle, turnover
refresh, and bulk repricing all skipped it. These tests pin every path to the service.
"""

from decimal import Decimal

from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.annual_reports.services.annual_report_tax_service import AnnualReportTaxService
from app.common.enums import AdvancePaymentFrequency

TAX_YEAR = 2026


def _client(client_factory):
    return client_factory(
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        advance_rate=Decimal("10"),
    )


def _payment(db, client_record, period, *, paid=None, turnover=Decimal("50000")):
    payment = AdvancePaymentService(db).create_payment_for_client(
        client_record_id=client_record.id,
        period=period,
        period_months_count=1,
        turnover_amount=turnover,
        paid_amount=paid,
    )
    db.commit()
    return payment


def _report_with_saved_tax(db, annual_report_service_factory, client_record):
    report = annual_report_service_factory(client_record_id=client_record.id, tax_year=TAX_YEAR)
    AnnualReportTaxService(db).save_tax_calculation(
        report.id, tax_due=Decimal("1234.00"), refund_due=None
    )
    db.commit()
    db.expire_all()
    return report


def _tax_due(db, report_id):
    from app.annual_reports.repositories.annual_report_report_repository import (
        AnnualReportRootRepository,
    )

    db.expire_all()
    return AnnualReportRootRepository(db).get_by_id(report_id).tax_due


def test_single_update_marking_paid_invalidates_saved_tax(
    test_db, client_factory, annual_report_service_factory
):
    record = _client(client_factory)
    report = _report_with_saved_tax(test_db, annual_report_service_factory, record)
    payment = _payment(test_db, record, f"{TAX_YEAR}-03")

    AdvancePaymentService(test_db).update_payment_for_client(
        client_record_id=record.id,
        payment_id=payment.id,
        paid_amount=payment.expected_amount,
    )
    test_db.commit()

    assert _tax_due(test_db, report.id) is None


def test_bulk_mark_paid_invalidates_saved_tax(
    test_db, client_factory, annual_report_service_factory
):
    """The regression this suite exists for: bulk settle skipped invalidation entirely."""
    record = _client(client_factory)
    report = _report_with_saved_tax(test_db, annual_report_service_factory, record)
    first = _payment(test_db, record, f"{TAX_YEAR}-03")
    second = _payment(test_db, record, f"{TAX_YEAR}-04")

    updated, skipped = AdvancePaymentService(test_db).bulk_mark_paid([first.id, second.id])
    test_db.commit()

    assert sorted(updated) == sorted([first.id, second.id])
    assert skipped == []
    assert _tax_due(test_db, report.id) is None


def test_bulk_mark_paid_invalidates_each_client_separately(
    test_db, client_factory, annual_report_service_factory
):
    """bulk_mark_paid is cross-client; every affected client's report must be cleared."""
    first_record = _client(client_factory)
    second_record = _client(client_factory)
    first_report = _report_with_saved_tax(test_db, annual_report_service_factory, first_record)
    second_report = _report_with_saved_tax(test_db, annual_report_service_factory, second_record)
    first_payment = _payment(test_db, first_record, f"{TAX_YEAR}-03")
    second_payment = _payment(test_db, second_record, f"{TAX_YEAR}-03")

    AdvancePaymentService(test_db).bulk_mark_paid([first_payment.id, second_payment.id])
    test_db.commit()

    assert _tax_due(test_db, first_report.id) is None
    assert _tax_due(test_db, second_report.id) is None


def test_submitted_report_tax_is_not_invalidated(
    test_db, client_factory, annual_report_service_factory
):
    """Invalidation is scoped to open pre-submission reports; a filed one stays put."""
    from app.annual_reports.models.annual_report_enums import AnnualReportStatus
    from app.annual_reports.repositories.annual_report_report_repository import (
        AnnualReportRootRepository,
    )

    record = _client(client_factory)
    report = _report_with_saved_tax(test_db, annual_report_service_factory, record)
    AnnualReportRootRepository(test_db).update(report.id, status=AnnualReportStatus.SUBMITTED)
    test_db.commit()
    payment = _payment(test_db, record, f"{TAX_YEAR}-03")

    AdvancePaymentService(test_db).bulk_mark_paid([payment.id])
    test_db.commit()

    assert _tax_due(test_db, report.id) == Decimal("1234.00")
