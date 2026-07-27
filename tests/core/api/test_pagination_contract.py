import pytest

from app.core.pagination import MAX_PAGE_SIZE

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _resolve_ref(openapi: dict, value: dict) -> dict:
    ref = value.get("$ref")
    if not ref:
        return value

    resolved = openapi
    for part in ref.removeprefix("#/").split("/"):
        resolved = resolved[part]
    return resolved


def _get_operation_parameters(
    openapi: dict,
    path_item: dict,
    operation: dict,
) -> list[dict]:
    parameters = [
        *path_item.get("parameters", []),
        *operation.get("parameters", []),
    ]
    return [_resolve_ref(openapi, parameter) for parameter in parameters]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/clients",
        "/api/v1/annual-reports",
        "/api/v1/clients/1/annual-reports",
        "/api/v1/notifications",
    ],
)
def test_page_size_above_global_max_returns_422(client, advisor_headers, path):
    response = client.get(
        f"{path}?page_size={MAX_PAGE_SIZE + 1}",
        headers=advisor_headers,
    )

    assert response.status_code == 422


def test_notification_page_size_at_global_max_is_accepted(client, advisor_headers):
    response = client.get(
        f"/api/v1/notifications?page_size={MAX_PAGE_SIZE}",
        headers=advisor_headers,
    )

    assert response.status_code == 200


def test_all_openapi_page_size_parameters_use_global_bounds(client):
    openapi = client.app.openapi()
    violations = []
    for path, path_item in openapi["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            parameters = _get_operation_parameters(openapi, path_item, operation)
            for parameter in parameters:
                if parameter.get("name") != "page_size" or parameter.get("in") != "query":
                    continue
                schema = _resolve_ref(openapi, parameter["schema"])
                if schema.get("minimum") != 1 or schema.get("maximum") != MAX_PAGE_SIZE:
                    violations.append(
                        {
                            "method": method.upper(),
                            "path": path,
                            "minimum": schema.get("minimum"),
                            "maximum": schema.get("maximum"),
                        }
                    )

    assert not violations, (
        f"All page_size query parameters must use bounds 1..{MAX_PAGE_SIZE}: {violations}"
    )
