"""Each domain's "needs no further work" set must answer the same in Python and SQL.

The two forms are not two implementations — each domain publishes one frozenset,
and both the ``is_*_resolved`` predicate and every SQL query read it. These tests
pin that, and pin the bug that motivated it: VAT's Python set omitted CANCELED
while its SQL side excluded it, so a cancelled period read open on one screen and
closed on another.
"""

import pytest

from app.advance_payments.models.advance_payment import (
    RESOLVED_ADVANCE_PAYMENT_STATUSES,
    AdvancePaymentStatus,
    is_advance_payment_resolved,
)
from app.annual_reports.models.annual_report_enums import (
    RESOLVED_ANNUAL_REPORT_STATUSES,
    AnnualReportStatus,
    is_annual_report_resolved,
)
from app.vat.models.vat_enums import (
    RESOLVED_VAT_WORK_ITEM_STATUSES,
    VatWorkItemStatus,
    is_vat_work_item_resolved,
)


class TestVatResolvedSet:
    def test_cancelled_period_is_resolved(self):
        """The regression. A cancelled period is not outstanding work."""
        assert VatWorkItemStatus.CANCELED in RESOLVED_VAT_WORK_ITEM_STATUSES
        assert is_vat_work_item_resolved(VatWorkItemStatus.CANCELED)

    def test_filed_period_is_resolved(self):
        assert is_vat_work_item_resolved(VatWorkItemStatus.FILED)

    @pytest.mark.parametrize(
        "status",
        [
            VatWorkItemStatus.PENDING_MATERIALS,
            VatWorkItemStatus.MATERIAL_RECEIVED,
            VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
            VatWorkItemStatus.READY_FOR_REVIEW,
        ],
    )
    def test_working_statuses_are_not_resolved(self, status):
        assert not is_vat_work_item_resolved(status)


class TestAnnualReportResolvedSet:
    @pytest.mark.parametrize(
        "status",
        [
            AnnualReportStatus.SUBMITTED,
            AnnualReportStatus.CLOSED,
            AnnualReportStatus.CANCELED,
        ],
    )
    def test_terminal_statuses_are_resolved(self, status):
        assert is_annual_report_resolved(status)

    @pytest.mark.parametrize(
        "status",
        [
            AnnualReportStatus.NOT_STARTED,
            AnnualReportStatus.COLLECTING_DOCS,
            AnnualReportStatus.IN_PREPARATION,
            AnnualReportStatus.PENDING_CLIENT,
        ],
    )
    def test_working_statuses_are_not_resolved(self, status):
        assert not is_annual_report_resolved(status)


class TestAdvancePaymentResolvedSet:
    def test_paid_is_resolved(self):
        assert is_advance_payment_resolved(AdvancePaymentStatus.PAID)

    @pytest.mark.parametrize(
        "status",
        [AdvancePaymentStatus.PENDING, AdvancePaymentStatus.PARTIAL],
    )
    def test_money_still_owed_is_not_resolved(self, status):
        assert not is_advance_payment_resolved(status)


class TestPredicateReadsThePublishedSet:
    """Every status is classified identically by the predicate and the set.

    This is what makes the frozenset a twin rather than a second implementation:
    SQL reads the same object, so it cannot drift from the predicate.
    """

    @pytest.mark.parametrize(
        ("statuses", "resolved_set", "predicate"),
        [
            (VatWorkItemStatus, RESOLVED_VAT_WORK_ITEM_STATUSES, is_vat_work_item_resolved),
            (
                AnnualReportStatus,
                RESOLVED_ANNUAL_REPORT_STATUSES,
                is_annual_report_resolved,
            ),
            (
                AdvancePaymentStatus,
                RESOLVED_ADVANCE_PAYMENT_STATUSES,
                is_advance_payment_resolved,
            ),
        ],
    )
    def test_every_status_agrees(self, statuses, resolved_set, predicate):
        for status in statuses:
            assert predicate(status) is (status in resolved_set), status
