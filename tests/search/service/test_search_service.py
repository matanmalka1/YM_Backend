from datetime import date

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.search.services.search_service import SearchService


def test_binder_result_uses_client_name_instead_of_business_name(
    test_db, test_user, create_client_with_business
):
    client, _business = create_client_with_business(
        full_name="אבי הראל",
        business_name="אפיק פתרונות - תכנון פנים",
    )
    binder = Binder(
        client_record_id=client.id,
        binder_number="100024/1",
        period_start=date(2026, 1, 1),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
    )
    test_db.add(binder)
    test_db.commit()

    results, total, _documents = SearchService(test_db).search(
        client_record_id=client.id,
    )

    binder_results = [result for result in results if result["result_type"] == "binder"]
    assert total == 2
    assert len(binder_results) == 1
    assert binder_results[0]["client_name"] == "אבי הראל"
