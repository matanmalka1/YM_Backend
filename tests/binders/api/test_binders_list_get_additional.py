from datetime import date

from tests.helpers.identity import SeededClient, seed_client_identity


def _create_client(test_db, suffix: str) -> SeededClient:
    return seed_client_identity(
        test_db,
        full_name=f"Binders List Client {suffix}",
        id_number=f"BDL{suffix}",
        office_client_number=100400 + int(suffix),
    )


def _create_binder_via_api(client, advisor_headers, client_record_id: int, user_id: int) -> int:
    res = client.post(
        "/api/v1/binders/receive",
        headers=advisor_headers,
        json={
            "client_record_id": client_record_id,
            "received_at": date.today().isoformat(),
            "received_by": user_id,
            "materials": [
                {
                    "material_type": "other",
                    "period_year": date.today().year,
                    "period_month_start": date.today().month,
                    "period_month_end": date.today().month,
                    "description": "list get test material",
                }
            ],
        },
    )
    assert res.status_code == 201
    payload = res.json()
    return payload["binder"]["id"] if "binder" in payload else payload["id"]


def test_get_and_delete_binder_paths(client, test_db, advisor_headers, test_user):
    crm_client = _create_client(test_db, "1")
    binder_id = _create_binder_via_api(client, advisor_headers, crm_client.id, test_user.id)

    get_ok = client.get(f"/api/v1/binders/{binder_id}", headers=advisor_headers)
    assert get_ok.status_code == 200
    assert get_ok.json()["id"] == binder_id

    get_missing = client.get("/api/v1/binders/999999", headers=advisor_headers)
    assert get_missing.status_code == 404

    del_ok = client.delete(f"/api/v1/binders/{binder_id}", headers=advisor_headers)
    assert del_ok.status_code == 204

    del_missing = client.delete("/api/v1/binders/999999", headers=advisor_headers)
    assert del_missing.status_code == 404


def test_receive_does_not_reuse_number_after_soft_delete(
    client, test_db, advisor_headers, test_user
):
    crm_client = _create_client(test_db, "2")

    first_id = _create_binder_via_api(client, advisor_headers, crm_client.id, test_user.id)
    del_ok = client.delete(f"/api/v1/binders/{first_id}", headers=advisor_headers)
    assert del_ok.status_code == 204

    second = client.post(
        "/api/v1/binders/receive",
        headers=advisor_headers,
        json={
            "client_record_id": crm_client.id,
            "received_at": date.today().isoformat(),
            "received_by": test_user.id,
            "materials": [
                {
                    "material_type": "other",
                    "period_year": date.today().year,
                    "period_month_start": date.today().month,
                    "period_month_end": date.today().month,
                    "description": "reuse number test material",
                }
            ],
        },
    )
    assert second.status_code == 201
    payload = second.json()
    binder_payload = payload["binder"] if "binder" in payload else payload
    second_id = binder_payload["id"]
    assert second_id != first_id
    assert binder_payload["binder_number"] == "100402/2"


# ── #44: binders `order` param validated (Literal["asc","desc"]) ──


def test_list_binders_accepts_valid_order(client, advisor_headers):
    for value in ("asc", "desc"):
        res = client.get(
            "/api/v1/binders",
            headers=advisor_headers,
            params={"order": value},
        )
        assert res.status_code == 200


def test_list_binders_rejects_invalid_order(client, advisor_headers):
    res = client.get(
        "/api/v1/binders",
        headers=advisor_headers,
        params={"order": "random"},
    )
    assert res.status_code == 422
