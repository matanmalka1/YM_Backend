"""Custom OpenAPI schema builder.

Makes ``HTTPBearer`` the global default security scheme so every operation is
documented as requiring a bearer token unless it explicitly opts out with
``security: []``. Public endpoints (see ``app/core/public_endpoints.py``) are
opted out here.

Note: this is documentation only. Runtime auth is enforced by the
``get_current_user`` dependency, guarded by
``tests/core/test_endpoint_auth_guard.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.openapi.utils import get_openapi

from app.core.public_endpoints import PUBLIC_ENDPOINTS

if TYPE_CHECKING:
    from fastapi import FastAPI


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """Build (and cache) the OpenAPI schema with a global HTTPBearer default."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # Global default: every operation requires a bearer token unless it opts out.
    schema["security"] = [{"HTTPBearer": []}]
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
    }

    http_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            method_upper = method.upper()
            if method_upper not in http_methods:
                continue
            if (method_upper, path) in PUBLIC_ENDPOINTS:
                operation["security"] = []
            elif operation.get("security") == [{"HTTPBearer": []}]:
                operation.pop("security")

    app.openapi_schema = schema
    return schema
