"""OpenAPI regression: LIST endpoints must reference thin list DTOs and
DETAIL endpoints must keep the full response DTOs.

Guards the list/detail DTO split for the VAT, clients, charges, and
notifications domains so a future change cannot silently revert a list
endpoint back to the fat double-duty schema.
"""

from __future__ import annotations

from app.main import app


def _ref_name(schema: dict) -> str | None:
    """Resolve the component schema name a response/array schema points at."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    # Paginated wrappers expose the row schema via items.$ref on the `items` prop.
    props = schema.get("properties", {})
    items = props.get("items", {})
    if items.get("type") == "array" and "$ref" in items.get("items", {}):
        return items["items"]["$ref"].rsplit("/", 1)[-1]
    return None


def _success_schema(spec: dict, path: str, method: str) -> dict:
    operation = spec["paths"][path][method]
    content = operation["responses"]["200"]["content"]["application/json"]
    return content["schema"]


def _referenced_schema_names(spec: dict, path: str, method: str) -> set[str]:
    """All component schema names transitively reachable from the 200 response.

    For wrapper responses (e.g. ``items`` arrays) we resolve the row schema, so
    a single membership check works for both bare and paginated responses.
    """
    schema = _success_schema(spec, path, method)
    names: set[str] = set()
    direct = _ref_name(schema)
    if direct:
        names.add(direct)
    # Resolve the wrapper component's own `items` row ref one level deeper.
    if "$ref" in schema:
        wrapper = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
        row = _ref_name(wrapper)
        if row:
            names.add(row)
    return names


def test_vat_list_endpoints_use_thin_dto():
    spec = app.openapi()

    for path in (
        "/api/v1/vat/work-items",
        "/api/v1/vat/work-items/groups/{group_key}/items",
        "/api/v1/vat/clients/{client_record_id}/work-items",
    ):
        names = _referenced_schema_names(spec, path, "get")
        assert "VatWorkItemListItem" in names, (path, names)
        assert "VatWorkItemResponse" not in names, (path, names)


def test_vat_detail_endpoint_uses_full_dto():
    spec = app.openapi()
    names = _referenced_schema_names(spec, "/api/v1/vat/work-items/{item_id}", "get")
    assert "VatWorkItemResponse" in names


def test_clients_list_endpoint_uses_thin_dto():
    spec = app.openapi()
    names = _referenced_schema_names(spec, "/api/v1/clients", "get")
    assert "ClientRecordListItem" in names, names
    assert "ClientRecordResponse" not in names, names


def test_clients_detail_endpoint_uses_full_dto():
    spec = app.openapi()
    names = _referenced_schema_names(spec, "/api/v1/clients/{client_id}", "get")
    assert "ClientRecordResponse" in names


def test_charges_list_endpoint_uses_thin_dto():
    spec = app.openapi()
    names = _referenced_schema_names(spec, "/api/v1/charges", "get")
    assert "ChargeListItem" in names, names
    assert "ChargeResponse" not in names, names


def test_charges_detail_endpoint_uses_full_dto():
    spec = app.openapi()
    names = _referenced_schema_names(spec, "/api/v1/charges/{charge_id}", "get")
    assert "ChargeResponse" in names


def test_notifications_list_endpoint_uses_thin_dto():
    spec = app.openapi()
    names = _referenced_schema_names(spec, "/api/v1/notifications", "get")
    assert "NotificationListItem" in names, names
    assert "NotificationResponse" not in names, names


def test_notifications_detail_endpoint_exists_and_uses_full_dto():
    spec = app.openapi()
    path = "/api/v1/notifications/{notification_id}"
    assert path in spec["paths"], "GET /notifications/{notification_id} must exist"
    names = _referenced_schema_names(spec, path, "get")
    assert "NotificationResponse" in names, names
