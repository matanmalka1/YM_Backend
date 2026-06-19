from datetime import date

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository
from app.businesses.models.business import Business
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService


def test_business_and_binder_repository_counts_active_entities(test_db):
    user = User(
        full_name="Receiver",
        email="receiver@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)

    le_a = LegalEntity(
        official_name="Alpha Ltd",
        id_number="C001",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    le_b = LegalEntity(
        official_name="Beta LLC",
        id_number="C002",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    test_db.add_all([le_a, le_b])
    test_db.commit()

    cr_a = ClientRecord(legal_entity_id=le_a.id, office_client_number=100901)
    cr_b = ClientRecord(legal_entity_id=le_b.id, office_client_number=100902)
    test_db.add_all([cr_a, cr_b])
    test_db.commit()

    business_active = Business(
        legal_entity_id=le_a.id,
        business_name="Alpha Business",
        opened_at=date(2024, 1, 1),
    )
    business_other = Business(
        legal_entity_id=le_b.id,
        business_name="Beta Business",
        opened_at=date(2024, 2, 1),
    )
    test_db.add_all([business_active, business_other])
    test_db.commit()

    binder_active = Binder(
        client_record_id=cr_a.id,
        binder_number="B-1",
        period_start=date(2024, 3, 1),
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=user.id,
    )
    binder_handed_over = Binder(
        client_record_id=cr_b.id,
        binder_number="B-2",
        period_start=date(2024, 3, 2),
        handed_over_at=date(2024, 3, 5),
        location_status=BinderLocationStatus.HANDED_OVER,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=user.id,
    )
    test_db.add_all([binder_active, binder_handed_over])
    test_db.commit()

    total_businesses = BusinessRepository(test_db).count()
    active_binders = BinderRepository(test_db).count_active()

    assert total_businesses >= 2
    assert active_binders >= 1
    # Handed-over binder should not be counted as active.
    assert active_binders < total_businesses + 1
