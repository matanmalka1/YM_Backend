"""Tests for _compute_amounts, calculation snapshots, VAT refresh, and update recompute."""

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.advance_payments.models.advance_payment import AdvancePaymentStatus, TurnoverSource
from app.advance_payments.repositories.advance_payment_turnover_lookup_repository import (
    TurnoverLookupRepository,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.audit.audit_constants import (
    ACTION_ADVANCE_PAYMENT_TURNOVER_REFRESHED,
    ENTITY_ADVANCE_PAYMENT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.businesses.models.business import Business
from app.common.enums import AdvancePaymentFrequency, VatType
from app.core.error_codes import ErrorCode
from app.core.exceptions import ConflictError, NotFoundError
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_client_identity

_seq = count(1)


def _make_business(db, frequency, advance_rate=None) -> Business:
    idx = next(_seq)
    client = seed_client_identity(
        db,
        full_name=f"Calc Test Client {idx}",
        id_number=f"888{idx:06d}",
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=frequency,
        advance_rate=Decimal(str(advance_rate)) if advance_rate is not None else None,
    )
    business = Business(
        legal_entity_id=client.legal_entity_id,
        business_name=f"Calc Test Business {idx}",
        opened_at=date.today(),
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    return business


def _business(db, advance_rate=None) -> Business:
    return _make_business(db, AdvancePaymentFrequency.MONTHLY, advance_rate)


def _bimonthly_business(db, advance_rate=None) -> Business:
    return _make_business(db, AdvancePaymentFrequency.BIMONTHLY, advance_rate)


def _vat_item(db, client_id, period, total_output_net, user_id, status=VatWorkItemStatus.FILED):
    mat = TaxCalendarMaterializationService(db)
    entry = mat.ensure_periodic_entry("vat", period, 1)
    net = Decimal(str(total_output_net))
    item = VatWorkItem(
        client_record_id=client_id,
        created_by=user_id,
        period=period,
        period_type=VatType.MONTHLY,
        status=status,
        total_output_vat=net,
        total_output_net=net,
        total_input_vat=Decimal("0"),
        net_vat=net,
        tax_calendar_entry_id=entry.id,
        due_date_original=entry.due_date,
        due_date_effective=entry.due_date,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


class TestComputeAmounts:
    def test_both_provided(self, test_db):
        svc = AdvancePaymentService(test_db)
        calc, expected = svc._compute_amounts(
            turnover_amount=Decimal("50000"),
            advance_rate=Decimal("2.5"),
            override_amount=None,
        )
        assert calc == Decimal("1250.00")
        assert expected == Decimal("1250.00")

    def test_override_replaces_expected(self, test_db):
        svc = AdvancePaymentService(test_db)
        calc, expected = svc._compute_amounts(
            turnover_amount=Decimal("50000"),
            advance_rate=Decimal("2.5"),
            override_amount=Decimal("1000"),
        )
        assert calc == Decimal("1250.00")
        assert expected == Decimal("1000.00")

    def test_no_rate_no_turnover_falls_back(self, test_db):
        svc = AdvancePaymentService(test_db)
        calc, expected = svc._compute_amounts(
            turnover_amount=None,
            advance_rate=None,
            override_amount=None,
            fallback_expected=Decimal("500"),
        )
        assert calc == Decimal("0.00")
        assert expected == Decimal("500")

    def test_rounding_half_up(self, test_db):
        svc = AdvancePaymentService(test_db)
        calc, _ = svc._compute_amounts(
            turnover_amount=Decimal("33333"),
            advance_rate=Decimal("3"),
            override_amount=None,
        )
        assert calc == Decimal("999.99")

    def test_missing_rate_alone_yields_none_calc(self, test_db):
        svc = AdvancePaymentService(test_db)
        calc, expected = svc._compute_amounts(
            turnover_amount=Decimal("50000"),
            advance_rate=None,
            override_amount=None,
        )
        assert calc == Decimal("0.00")
        assert expected == Decimal("0.00")


class TestCreateSnapshots:
    def test_create_snapshots_advance_rate_from_legal_entity(self, test_db):
        business = _business(test_db, advance_rate=Decimal("3.0"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-01",
            period_months_count=1,
        )
        assert payment.advance_rate == Decimal("3.0")

    def test_create_computes_calculated_amount(self, test_db):
        business = _business(test_db, advance_rate=Decimal("2.5"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-02",
            period_months_count=1,
            turnover_amount=Decimal("40000"),
        )
        assert payment.calculated_amount == Decimal("1000.00")
        assert payment.expected_amount == Decimal("1000.00")

    def test_create_override_sets_expected(self, test_db):
        business = _business(test_db, advance_rate=Decimal("2.5"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-03",
            period_months_count=1,
            turnover_amount=Decimal("40000"),
            override_amount=Decimal("800"),
        )
        assert payment.calculated_amount == Decimal("1000.00")
        assert payment.expected_amount == Decimal("800.00")
        assert payment.override_amount == Decimal("800.00")

    def test_create_explicit_rate_overrides_entity(self, test_db):
        business = _business(test_db, advance_rate=Decimal("5.0"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-04",
            period_months_count=1,
            turnover_amount=Decimal("10000"),
            advance_rate=Decimal("2.0"),
        )
        assert payment.advance_rate == Decimal("2.0")
        assert payment.calculated_amount == Decimal("200.00")

    def test_create_derives_status_from_paid_amount(self, test_db):
        business = _business(test_db, advance_rate=Decimal("2.5"))
        payment = AdvancePaymentService(test_db).create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-10",
            period_months_count=1,
            turnover_amount=Decimal("40000"),
            paid_amount=Decimal("250"),
        )

        assert payment.expected_amount == Decimal("1000.00")
        assert payment.status == AdvancePaymentStatus.PARTIAL


class TestUpdateRecompute:
    def test_patch_turnover_recomputes_amounts(self, test_db):
        business = _business(test_db, advance_rate=Decimal("2.5"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-05",
            period_months_count=1,
            turnover_amount=Decimal("40000"),
        )
        updated = svc.update_payment_for_client(
            business.client_record_id,
            payment.id,
            turnover_amount=Decimal("80000"),
        )
        assert updated.calculated_amount == Decimal("2000.00")
        assert updated.expected_amount == Decimal("2000.00")

    def test_patch_turnover_rederives_status(self, test_db):
        business = _business(test_db, advance_rate=Decimal("2.5"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-06",
            period_months_count=1,
            turnover_amount=Decimal("40000"),
        )
        svc.update_payment_for_client(
            business.client_record_id,
            payment.id,
            paid_amount=Decimal("1000"),
        )
        updated = svc.update_payment_for_client(
            business.client_record_id,
            payment.id,
            turnover_amount=Decimal("80000"),
        )
        assert updated.expected_amount == Decimal("2000.00")
        assert updated.status == AdvancePaymentStatus.PARTIAL

    def test_patch_expected_amount_rederives_status(self, test_db):
        business = _business(test_db, advance_rate=Decimal("2.5"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-11",
            period_months_count=1,
            turnover_amount=Decimal("40000"),
            paid_amount=Decimal("1000"),
        )
        assert payment.status == AdvancePaymentStatus.PAID

        updated = svc.update_payment_for_client(
            business.client_record_id,
            payment.id,
            expected_amount=Decimal("2000"),
        )

        assert updated.status == AdvancePaymentStatus.PARTIAL


class TestResolveTurnover:
    """The coverage/source rule, isolated from the command that applies it.

    Monthly and bi-monthly × filed / pending / missing / partly-covered.
    """

    def _resolve(self, db, business, period, months_count=1):
        return TurnoverLookupRepository(db).resolve_turnover(
            business.client_record_id, period, months_count
        )

    def test_monthly_filed(self, test_db, test_user):
        business = _business(test_db)
        item = _vat_item(
            test_db, business.client_record_id, "2026-01", Decimal("60000"), test_user.id
        )

        resolution = self._resolve(test_db, business, "2026-01")

        assert resolution.is_resolved
        assert resolution.amount == Decimal("60000")
        assert resolution.source == TurnoverSource.VAT_FILED
        assert resolution.vat_work_item_ids == [item.id]

    def test_monthly_pending(self, test_db, test_user):
        business = _business(test_db)
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-02",
            Decimal("30000"),
            test_user.id,
            VatWorkItemStatus.READY_FOR_REVIEW,
        )

        resolution = self._resolve(test_db, business, "2026-02")

        assert resolution.amount == Decimal("30000")
        assert resolution.source == TurnoverSource.VAT_PENDING

    def test_monthly_missing(self, test_db):
        business = _business(test_db)

        resolution = self._resolve(test_db, business, "2026-03")

        assert not resolution.is_resolved
        assert resolution.amount is None
        assert resolution.source is None
        assert resolution.vat_work_item_ids == []

    def test_bimonthly_both_filed_sums(self, test_db, test_user):
        business = _bimonthly_business(test_db)
        first = _vat_item(
            test_db, business.client_record_id, "2026-05", Decimal("60000"), test_user.id
        )
        second = _vat_item(
            test_db, business.client_record_id, "2026-06", Decimal("40000"), test_user.id
        )

        resolution = self._resolve(test_db, business, "2026-05", months_count=2)

        assert resolution.amount == Decimal("100000")
        assert resolution.source == TurnoverSource.VAT_FILED
        assert resolution.vat_work_item_ids == [first.id, second.id]

    def test_bimonthly_half_covered_is_unresolved(self, test_db, test_user):
        """Never report a halved turnover as if it covered the whole period."""
        business = _bimonthly_business(test_db)
        _vat_item(test_db, business.client_record_id, "2026-07", Decimal("60000"), test_user.id)

        resolution = self._resolve(test_db, business, "2026-07", months_count=2)

        assert not resolution.is_resolved

    def test_bimonthly_one_unfiled_month_downgrades_to_pending(self, test_db, test_user):
        business = _bimonthly_business(test_db)
        _vat_item(test_db, business.client_record_id, "2026-09", Decimal("60000"), test_user.id)
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-10",
            Decimal("40000"),
            test_user.id,
            VatWorkItemStatus.READY_FOR_REVIEW,
        )

        resolution = self._resolve(test_db, business, "2026-09", months_count=2)

        assert resolution.amount == Decimal("100000")
        assert resolution.source == TurnoverSource.VAT_PENDING

    def test_bimonthly_spans_year_boundary(self, test_db, test_user):
        business = _bimonthly_business(test_db)
        _vat_item(test_db, business.client_record_id, "2026-11", Decimal("10000"), test_user.id)
        _vat_item(test_db, business.client_record_id, "2026-12", Decimal("20000"), test_user.id)

        resolution = self._resolve(test_db, business, "2026-11", months_count=2)

        assert resolution.amount == Decimal("30000")


class TestRefreshTurnoverBulk:
    def _payment(self, db, business, period):
        return AdvancePaymentService(db).create_payment_for_client(
            client_record_id=business.client_record_id,
            period=period,
            period_months_count=1,
        )

    def test_counts_each_skip_reason_separately(self, test_db, test_user):
        """Chasing a missing return and waiting for a pending one are different jobs."""
        business = _business(test_db, advance_rate=Decimal("10"))
        filed = self._payment(test_db, business, "2026-01")
        pending = self._payment(test_db, business, "2026-02")
        absent = self._payment(test_db, business, "2026-03")
        _vat_item(test_db, business.client_record_id, "2026-01", Decimal("60000"), test_user.id)
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-02",
            Decimal("50000"),
            test_user.id,
            VatWorkItemStatus.READY_FOR_REVIEW,
        )
        svc = AdvancePaymentService(test_db)

        result = svc.refresh_turnover_bulk(
            business.client_record_id, [filed.id, pending.id, absent.id]
        )

        assert (result.refreshed, result.skipped_no_vat, result.skipped_not_filed) == (1, 1, 1)
        assert filed.turnover_amount == Decimal("60000")
        assert pending.turnover_amount is None
        assert absent.turnover_amount is None

    def test_never_snapshots_pending_even_in_bulk(self, test_db, test_user):
        """confirm_pending is a per-period judgement and has no bulk equivalent."""
        business = _business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-04")
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-04",
            Decimal("50000"),
            test_user.id,
            VatWorkItemStatus.READY_FOR_REVIEW,
        )
        svc = AdvancePaymentService(test_db)

        result = svc.refresh_turnover_bulk(business.client_record_id, [payment.id])

        assert result.skipped_not_filed == 1
        assert payment.turnover_source is None

    def test_one_unresolvable_period_does_not_block_its_neighbours(self, test_db, test_user):
        business = _business(test_db, advance_rate=Decimal("10"))
        first = self._payment(test_db, business, "2026-05")
        gap = self._payment(test_db, business, "2026-06")
        last = self._payment(test_db, business, "2026-07")
        _vat_item(test_db, business.client_record_id, "2026-05", Decimal("10000"), test_user.id)
        _vat_item(test_db, business.client_record_id, "2026-07", Decimal("30000"), test_user.id)
        svc = AdvancePaymentService(test_db)

        result = svc.refresh_turnover_bulk(business.client_record_id, [first.id, gap.id, last.id])

        assert result.refreshed == 2
        assert first.turnover_amount == Decimal("10000")
        assert last.turnover_amount == Decimal("30000")
        assert gap.turnover_amount is None

    def test_foreign_payment_id_fails_whole_request_before_writing(self, test_db, test_user):
        """A malformed request is a caller bug, not a skip — and must write nothing."""
        business = _business(test_db, advance_rate=Decimal("10"))
        other = _business(test_db, advance_rate=Decimal("10"))
        mine = self._payment(test_db, business, "2026-08")
        theirs = self._payment(test_db, other, "2026-08")
        _vat_item(test_db, business.client_record_id, "2026-08", Decimal("60000"), test_user.id)
        svc = AdvancePaymentService(test_db)

        with pytest.raises(NotFoundError) as exc:
            svc.refresh_turnover_bulk(business.client_record_id, [mine.id, theirs.id])
        assert exc.value.code == ErrorCode.ADVANCE_PAYMENT_NOT_FOUND
        assert mine.turnover_amount is None

    def test_writes_one_audit_entry_per_refreshed_payment(self, test_db, test_user):
        business = _business(test_db, advance_rate=Decimal("10"))
        first = self._payment(test_db, business, "2026-09")
        second = self._payment(test_db, business, "2026-10")
        _vat_item(test_db, business.client_record_id, "2026-09", Decimal("10000"), test_user.id)
        _vat_item(test_db, business.client_record_id, "2026-10", Decimal("20000"), test_user.id)
        svc = AdvancePaymentService(test_db)

        svc.refresh_turnover_bulk(
            business.client_record_id, [first.id, second.id], actor_id=test_user.id
        )
        test_db.flush()

        logged = test_db.scalars(
            select(EntityAuditLog).where(
                EntityAuditLog.entity_type == ENTITY_ADVANCE_PAYMENT,
                EntityAuditLog.entity_id.in_([first.id, second.id]),
                EntityAuditLog.action == ACTION_ADVANCE_PAYMENT_TURNOVER_REFRESHED,
            )
        ).all()
        assert {log.entity_id for log in logged} == {first.id, second.id}


class TestRefreshTurnoverFromVat:
    def _payment(self, db, business, period, months_count=1):
        return AdvancePaymentService(db).create_payment_for_client(
            client_record_id=business.client_record_id,
            period=period,
            period_months_count=months_count,
        )

    def test_snapshots_filed_turnover_and_recomputes(self, test_db, test_user):
        business = _business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-07")
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-07",
            Decimal("60000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        svc = AdvancePaymentService(test_db)

        updated = svc.refresh_turnover_from_vat(business.client_record_id, payment.id)

        assert updated.turnover_amount == Decimal("60000")
        assert updated.turnover_source == TurnoverSource.VAT_FILED
        assert updated.turnover_snapshot_at is not None
        assert updated.calculated_amount == Decimal("6000.00")
        assert updated.expected_amount == Decimal("6000.00")
        assert updated.status == AdvancePaymentStatus.PENDING

    def test_pending_vat_requires_confirmation(self, test_db, test_user):
        business = _business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-08")
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-08",
            Decimal("30000"),
            test_user.id,
            VatWorkItemStatus.READY_FOR_REVIEW,
        )
        svc = AdvancePaymentService(test_db)

        with pytest.raises(ConflictError) as exc:
            svc.refresh_turnover_from_vat(business.client_record_id, payment.id)
        assert exc.value.code == ErrorCode.ADVANCE_PAYMENT_VAT_NOT_FILED

        updated = svc.refresh_turnover_from_vat(
            business.client_record_id, payment.id, confirm_pending=True
        )
        assert updated.turnover_source == TurnoverSource.VAT_PENDING
        assert updated.turnover_amount == Decimal("30000")

    def test_bimonthly_partly_filed_is_pending(self, test_db, test_user):
        """One filed + one unfiled month is worth only the weaker of the two."""
        business = _bimonthly_business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-03", months_count=2)
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-03",
            Decimal("60000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-04",
            Decimal("40000"),
            test_user.id,
            VatWorkItemStatus.READY_FOR_REVIEW,
        )
        svc = AdvancePaymentService(test_db)

        with pytest.raises(ConflictError) as exc:
            svc.refresh_turnover_from_vat(business.client_record_id, payment.id)
        assert exc.value.code == ErrorCode.ADVANCE_PAYMENT_VAT_NOT_FILED

        updated = svc.refresh_turnover_from_vat(
            business.client_record_id, payment.id, confirm_pending=True
        )
        assert updated.turnover_source == TurnoverSource.VAT_PENDING
        assert updated.turnover_amount == Decimal("100000")

    def test_raises_when_no_vat_item(self, test_db):
        business = _business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-10")
        svc = AdvancePaymentService(test_db)

        with pytest.raises(NotFoundError) as exc:
            svc.refresh_turnover_from_vat(business.client_record_id, payment.id)
        assert exc.value.code == ErrorCode.ADVANCE_PAYMENT_VAT_TURNOVER_NOT_FOUND

    def test_bimonthly_sums_both_months(self, test_db, test_user):
        business = _bimonthly_business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-07", months_count=2)
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-07",
            Decimal("60000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-08",
            Decimal("40000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        svc = AdvancePaymentService(test_db)

        updated = svc.refresh_turnover_from_vat(business.client_record_id, payment.id)

        assert updated.turnover_amount == Decimal("100000")
        assert updated.calculated_amount == Decimal("10000.00")

    def test_bimonthly_rejects_half_covered_period(self, test_db, test_user):
        business = _bimonthly_business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-09", months_count=2)
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-09",
            Decimal("60000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        svc = AdvancePaymentService(test_db)

        with pytest.raises(NotFoundError) as exc:
            svc.refresh_turnover_from_vat(business.client_record_id, payment.id)
        assert exc.value.code == ErrorCode.ADVANCE_PAYMENT_VAT_TURNOVER_NOT_FOUND

    def test_override_survives_refresh(self, test_db, test_user):
        business = _business(test_db, advance_rate=Decimal("10"))
        svc = AdvancePaymentService(test_db)
        payment = svc.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-11",
            period_months_count=1,
            override_amount=Decimal("4500"),
        )
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-11",
            Decimal("60000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )

        updated = svc.refresh_turnover_from_vat(business.client_record_id, payment.id)

        assert updated.calculated_amount == Decimal("6000.00")
        assert updated.expected_amount == Decimal("4500.00")

    def test_manual_patch_clears_vat_provenance(self, test_db, test_user):
        business = _business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-12")
        _vat_item(
            test_db,
            business.client_record_id,
            "2026-12",
            Decimal("60000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        svc = AdvancePaymentService(test_db)
        svc.refresh_turnover_from_vat(business.client_record_id, payment.id)

        updated = svc.update_payment_for_client(
            business.client_record_id,
            payment.id,
            turnover_amount=Decimal("55000"),
        )

        assert updated.turnover_source == TurnoverSource.MANUAL
        assert updated.calculated_amount == Decimal("5500.00")

    def test_writes_turnover_refreshed_audit_entry(self, test_db, test_user):
        business = _business(test_db, advance_rate=Decimal("10"))
        payment = self._payment(test_db, business, "2026-05")
        item = _vat_item(
            test_db,
            business.client_record_id,
            "2026-05",
            Decimal("60000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        svc = AdvancePaymentService(test_db)
        svc.refresh_turnover_from_vat(business.client_record_id, payment.id, actor_id=test_user.id)
        test_db.flush()

        log = test_db.scalars(
            select(EntityAuditLog).where(
                EntityAuditLog.entity_type == ENTITY_ADVANCE_PAYMENT,
                EntityAuditLog.entity_id == payment.id,
                EntityAuditLog.action == ACTION_ADVANCE_PAYMENT_TURNOVER_REFRESHED,
            )
        ).one()
        assert log.metadata_json["source"] == "vat_filed"
        assert log.metadata_json["vat_work_item_ids"] == [item.id]
        assert log.old_value["turnover_amount"] is None
        assert Decimal(str(log.new_value["turnover_amount"])) == Decimal("60000")
