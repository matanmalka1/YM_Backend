from datetime import date

from app.binders.repositories.binder_repository import BinderRepository


def test_list_client_binders_returns_only_requested_client_binders(
    test_db, user_factory, binder_factory, client_factory
):
    user = user_factory(
        full_name="Timeline Repo User",
        email="timeline.repo@example.com",
        password="pass",
        commit=True,
    )
    client_a = client_factory(full_name="Timeline Repo Client 1", id_number="TLR001")
    client_b = client_factory(full_name="Timeline Repo Client 2", id_number="TLR002")

    binder_repo = BinderRepository(test_db)
    b1 = binder_factory(
        client_record_id=client_a.id,
        binder_number="TL-B-001",
        period_start=date.today(),
        created_by=user.id,
        commit=True,
    )
    b2 = binder_factory(
        client_record_id=client_a.id,
        binder_number="TL-B-002",
        period_start=date.today(),
        created_by=user.id,
        commit=True,
    )
    binder_factory(
        client_record_id=client_b.id,
        binder_number="TL-B-003",
        period_start=date.today(),
        created_by=user.id,
        commit=True,
    )

    result = binder_repo.list_by_client_record(client_a.id)

    assert {binder.id for binder in result} == {b1.id, b2.id}
