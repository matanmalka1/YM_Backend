from app.businesses.models.business import BusinessStatus
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


def test_annual_report_factory_accepts_an_actor_and_custom_fields(
    annual_report_factory,
    user_factory,
):
    actor = user_factory(full_name="Annual Report Creator")

    report = annual_report_factory(
        actor=actor,
        tax_year=2025,
        deadline_type="custom",
        notes="Factory report",
    )

    assert report.tax_year == 2025
    assert report.created_by == actor.id
    assert report.deadline_type.value == "custom"
    assert report.notes == "Factory report"
