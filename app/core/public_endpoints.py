"""Single source of truth for endpoints that are intentionally unauthenticated.

OpenAPI ``security`` is documentation only and does not enforce auth at runtime;
real enforcement is the ``get_current_user`` dependency. This allowlist is reused
by:

- ``app/core/openapi.py`` — to set ``security: []`` on these operations while the
  rest of the spec inherits the global ``HTTPBearer`` default.
- ``tests/core/test_endpoint_auth_guard.py`` — to fail if any non-listed endpoint
  lacks a real auth dependency.

Keys are ``(HTTP_METHOD, path)`` pairs. Method is upper-case; path is the route
template as registered with FastAPI.
"""

PUBLIC_ENDPOINTS: set[tuple[str, str]] = {
    ("GET", "/"),
    ("GET", "/info"),
    ("GET", "/health"),
    ("GET", "/ready"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/reset-password"),
    ("GET", "/sign/{token}"),
    ("POST", "/sign/{token}/approve"),
    ("POST", "/sign/{token}/decline"),
}
