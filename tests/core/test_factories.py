from datetime import date

import pytest

from app.binders.models.binder_intake_material import MaterialType
from app.businesses.models.business import BusinessStatus
from app.common.enums import ObligationType
from app.users.models.user import UserRole


def test_user_factory_supports_roles_states_and_unique_defaults(user_factory):
    advisor = user_factory()
    secretary = user_factory(role=UserRole.SECRETARY, is_active=False)

    assert advisor.email != secretary.email
    assert advisor.role == UserRole.ADVISOR
    assert secretary.role == UserRole.SECRETARY
    assert secretary.is_active is False


def test_identity_factories_build_complete_client_business_graphs(
    client_factory,
    business_factory,
    create_client_with_business,
):
    standalone_client = client_factory()
    standalone_business = business_factory(
        legal_entity_id=standalone_client.legal_entity_id,
        status=BusinessStatus.FROZEN,
    )
    client, business = create_client_with_business()

    assert standalone_business.legal_entity_id == standalone_client.legal_entity_id
    assert standalone_business.status == BusinessStatus.FROZEN
    assert business.legal_entity_id == client.legal_entity_id
    assert business.client_record_id == client.id


def test_annual_report_service_factory_accepts_an_actor_and_custom_fields(
    annual_report_service_factory,
    user_factory,
):
    actor = user_factory(full_name="Annual Report Creator")

    report = annual_report_service_factory(
        actor=actor,
        tax_year=2025,
        deadline_type="custom",
        notes="Factory report",
    )

    assert report.tax_year == 2025
    assert report.created_by == actor.id
    assert report.deadline_type.value == "custom"
    assert report.notes == "Factory report"


def test_binder_intake_material_factory_preserves_explicit_zero_month_end(
    binder_intake_material_factory,
):
    material = binder_intake_material_factory(
        material_type=MaterialType.OTHER,
        period_month_start=1,
        period_month_end=0,
    )

    assert material.period_month_end == 0


def test_tax_calendar_entry_factory_rejects_zero_period_months_count(
    tax_calendar_entry_factory,
):
    with pytest.raises(ValueError, match="period_months_count must be 1 or 2"):
        tax_calendar_entry_factory(
            obligation_type=ObligationType.VAT,
            period="2026-01",
            period_months_count=0,
        )


def test_tax_calendar_entry_factory_rejects_conflicting_existing_fields(
    tax_calendar_entry_factory,
):
    tax_calendar_entry_factory(
        obligation_type=ObligationType.VAT,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )

    with pytest.raises(ValueError, match="due_date"):
        tax_calendar_entry_factory(
            obligation_type=ObligationType.VAT,
            period="2026-01",
            period_months_count=1,
            due_date=date(2026, 2, 20),
        )
