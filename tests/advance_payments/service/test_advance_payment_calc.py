"""Tests for _compute_amounts, calculation snapshots, prefill, and update recompute."""

from datetime import date
from decimal import Decimal
from itertools import count

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.businesses.models.business import Business
from app.common.enums import AdvancePaymentFrequency, VatType
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_client_identity

_seq = count(1)


def _business(db, advance_rate=None) -> Business:
    idx = next(_seq)
    client = seed_client_identity(
        db,
        full_name=f"Calc Test Client {idx}",
        id_number=f"888{idx:06d}",
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
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
            status=AdvancePaymentStatus.PAID,
        )
        updated = svc.update_payment_for_client(
            business.client_record_id,
            payment.id,
            turnover_amount=Decimal("80000"),
        )
        assert updated.expected_amount == Decimal("2000.00")
        assert updated.status == AdvancePaymentStatus.PARTIAL


class TestPrefillTurnover:
    def test_prefill_returns_vat_filed(self, test_db, test_user):
        business = _business(test_db)
        item = _vat_item(
            test_db,
            business.client_record_id,
            "2026-07",
            Decimal("55000"),
            test_user.id,
            VatWorkItemStatus.FILED,
        )
        svc = AdvancePaymentService(test_db)
        turnover, vid, source = svc.get_prefill_turnover_for_client(
            business.client_record_id, "2026-07", 1
        )
        assert source == "vat_filed"
        assert turnover == Decimal("55000")
        assert vid == item.id

    def test_prefill_returns_vat_pending_when_no_filed(self, test_db, test_user):
        business = _business(test_db)
        item = _vat_item(
            test_db,
            business.client_record_id,
            "2026-08",
            Decimal("30000"),
            test_user.id,
            VatWorkItemStatus.READY_FOR_REVIEW,
        )
        svc = AdvancePaymentService(test_db)
        turnover, vid, source = svc.get_prefill_turnover_for_client(
            business.client_record_id, "2026-08", 1
        )
        assert source == "vat_pending"
        assert turnover == Decimal("30000")
        assert vid == item.id

    def test_prefill_returns_none_when_no_vat_item(self, test_db):
        business = _business(test_db)
        svc = AdvancePaymentService(test_db)
        turnover, vid, source = svc.get_prefill_turnover_for_client(
            business.client_record_id, "2026-09", 1
        )
        assert source == "none"
        assert turnover is None
        assert vid is None
