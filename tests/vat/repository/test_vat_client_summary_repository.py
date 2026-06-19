from datetime import date
from decimal import Decimal
from itertools import count

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType, VatType
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService
from app.utils.time_utils import utcnow
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_client_summary_repository import (
    VatClientSummaryRepository,
)
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.tax_calendar_links import create_linked_vat_work_item

_seq = count(1)


def _user(test_db) -> User:
    user = User(
        full_name="VAT Summary Repo User",
        email="vat.summary.repo@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db) -> tuple[Business, int]:
    idx = next(_seq)
    legal_entity = LegalEntity(
        official_name=f"VAT Summary Client {idx}",
        id_number=f"VAT-SUM-{idx}",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    test_db.add(legal_entity)
    test_db.commit()
    test_db.refresh(legal_entity)

    client_record = ClientRecord(legal_entity_id=legal_entity.id)
    test_db.add(client_record)
    test_db.commit()
    test_db.refresh(client_record)

    business = Business(
        legal_entity_id=legal_entity.id,
        business_name=legal_entity.official_name,
        opened_at=date(2026, 1, 1),
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    return business, client_record.id


def test_vat_client_summary_repository_periods_and_annual_aggregates(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)
    work_repo = VatWorkItemRepository(test_db)
    summary_repo = VatClientSummaryRepository(test_db)

    i1 = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=client_record_id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        created_by=user.id,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
    )
    i2 = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=client_record_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )

    work_repo.update_vat_totals(
        i1.id,
        total_output_vat=170.0,
        total_input_vat=20.0,
        total_output_net=1000.0,
        total_input_net=200.0,
    )
    work_repo.update_vat_totals(
        i2.id,
        total_output_vat=85.0,
        total_input_vat=10.0,
        total_output_net=500.0,
        total_input_net=100.0,
    )

    periods = summary_repo.get_periods_for_client(client_record_id)
    assert [work_item.period for work_item, _output_net, _input_net in periods] == [
        "2026-02",
        "2026-01",
    ]

    annual = summary_repo.get_annual_aggregates(client_record_id)
    assert len(annual) == 1
    assert annual[0]["year"] == 2026
    assert float(annual[0]["total_output_vat"]) == 255.0
    assert float(annual[0]["total_input_vat"]) == 30.0
    assert float(annual[0]["net_vat"]) == 225.0
    assert annual[0]["periods_count"] == 2
    assert annual[0]["filed_count"] == 1


def test_get_annual_turnover_by_client_ids_groups_clients_and_bounds_year(test_db):
    user = _user(test_db)
    _, first_client_id = _business(test_db)
    _, second_client_id = _business(test_db)
    _, unused_client_id = _business(test_db)
    work_repo = VatWorkItemRepository(test_db)
    summary_repo = VatClientSummaryRepository(test_db)

    first_jan = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=first_client_id,
        period="2026-01",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )
    first_dec = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=first_client_id,
        period="2026-12",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )
    ignored_previous_year = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=first_client_id,
        period="2025-12",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )
    ignored_unfiled = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=first_client_id,
        period="2026-02",
        created_by=user.id,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
    )
    ignored_deleted = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=second_client_id,
        period="2026-03",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )
    second = create_linked_vat_work_item(
        test_db,
        repo=work_repo,
        client_record_id=second_client_id,
        period="2026-04",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )

    for item, amount in (
        (first_jan, Decimal("100.00")),
        (first_dec, Decimal("200.00")),
        (ignored_previous_year, Decimal("300.00")),
        (ignored_unfiled, Decimal("400.00")),
        (ignored_deleted, Decimal("500.00")),
        (second, Decimal("600.00")),
    ):
        work_repo.update_vat_totals(
            item.id,
            total_output_vat=amount,
            total_input_vat=Decimal("0.00"),
            total_output_net=amount,
            total_input_net=Decimal("0.00"),
        )
    ignored_deleted.deleted_at = utcnow()
    test_db.flush()

    result = summary_repo.get_annual_turnover_by_client_ids(
        [first_client_id, second_client_id, unused_client_id],
        2026,
    )

    assert result == {
        first_client_id: Decimal("300.00"),
        second_client_id: Decimal("600.00"),
    }


def test_vat_work_item_repository_list_by_business(test_db):
    user = _user(test_db)
    _, cr_id_1 = _business(test_db)
    _, cr_id_2 = _business(test_db)

    repo = VatWorkItemRepository(test_db)
    a = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=cr_id_1,
        period="2026-03",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    b = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=cr_id_1,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=cr_id_2,
        period="2026-02",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    rows = repo.list_by_client_record(cr_id_1)
    assert [r.id for r in rows] == [a.id, b.id]


def test_vat_work_item_repository_list_by_business_applies_limit(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)
    repo = VatWorkItemRepository(test_db)

    for month in range(1, 301):
        year = 2026 + (month - 1) // 12
        month_in_year = ((month - 1) % 12) + 1
        create_linked_vat_work_item(
            test_db,
            repo=repo,
            client_record_id=client_record_id,
            period=f"{year:04d}-{month_in_year:02d}",
            period_type=VatType.MONTHLY,
            created_by=user.id,
        )

    rows = repo.list_by_client_record(client_record_id)

    assert len(rows) == 200
    assert rows[0].period == "2050-12"
    assert rows[-1].period == "2034-05"
