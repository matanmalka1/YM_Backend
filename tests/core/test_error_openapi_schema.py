from app.core.exceptions import (
    ErrorEnvelope,
    bad_request_response,
    conflict_response,
    forbidden_response,
    internal_server_error_response,
    not_found_response,
    unauthorized_response,
)
from app.main import app


def test_openapi_contains_error_envelope_schema():
    spec = app.openapi()
    schemas = spec["components"]["schemas"]

    assert "ErrorEnvelope" in schemas
    assert "ErrorBody" in schemas
    assert schemas["ErrorEnvelope"]["properties"]["error"]["$ref"] == "#/components/schemas/ErrorBody"


def test_error_response_helpers_document_error_envelope_model():
    helpers = [
        (400, bad_request_response()),
        (401, unauthorized_response()),
        (403, forbidden_response()),
        (404, not_found_response()),
        (409, conflict_response()),
        (500, internal_server_error_response()),
    ]

    for status_code, response in helpers:
        assert response[status_code]["model"] is ErrorEnvelope
        assert response[status_code]["description"]


def test_documented_error_responses_use_error_envelope_schema():
    spec = app.openapi()
    mismatches: list[tuple[str, str, str]] = []

    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status_code in ("400", "401", "403", "404", "409", "500"):
                response = (operation.get("responses") or {}).get(status_code)
                if not response:
                    continue
                schema = (
                    response.get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
                )
                if schema.get("$ref") != "#/components/schemas/ErrorEnvelope":
                    mismatches.append((method.upper(), path, status_code))

    assert not mismatches


def test_openapi_documents_common_business_error_statuses():
    spec = app.openapi()
    found: set[str] = set()

    for path_item in spec["paths"].values():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            responses = operation.get("responses") or {}
            for status_code in ("400", "401", "403", "409", "500"):
                if status_code in responses:
                    found.add(status_code)

    assert {"400", "401", "403", "409", "500"}.issubset(found)


def test_annual_report_charges_openapi_response_schema_is_typed():
    spec = app.openapi()
    response_schema = spec["paths"]["/api/v1/annual-reports/{report_id}/charges"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

    assert response_schema
    assert response_schema != {}
    assert response_schema["$ref"].startswith("#/components/schemas/PaginatedResponse_ChargeResponse_")
