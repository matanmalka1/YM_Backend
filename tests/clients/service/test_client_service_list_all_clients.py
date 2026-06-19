from app.clients.services.client_create_service import create_client_identity_only
from app.clients.services.client_lifecycle_service import ClientLifecycleService
from app.clients.services.client_query_service import ClientQueryService
from app.common.enums import EntityType, IdNumberType


def test_list_all_clients_returns_only_active_sorted(test_db):
    b = create_client_identity_only(
        test_db,
        full_name="B Client",
        id_number="680000007",
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.COMPANY_LTD,
        actor_id=1,
    )
    a = create_client_identity_only(
        test_db,
        full_name="A Client",
        id_number="680000015",
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.COMPANY_LTD,
        actor_id=1,
    )
    d = create_client_identity_only(
        test_db,
        full_name="D Client",
        id_number="680000023",
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.COMPANY_LTD,
        actor_id=1,
    )

    ClientLifecycleService(test_db).delete_client(d.id, actor_id=1)

    items = ClientQueryService(test_db).list_all_clients()

    assert [c.id for c in items] == [a.id, b.id]
