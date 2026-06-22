## Scope
This file owns only:
- Implemented backend HTTP middleware behavior.
- Current request middleware ownership boundaries.

This file must not contain:
- Product/domain behavior.
- Route-specific business rules.
- Cross-project architecture rules.

Source of truth: mandatory

# Middleware Module

> Last audited: 2026-03-17 (domain-by-domain backend sync).


Provides application middleware components for HTTP request lifecycle concerns.

## Scope

This module provides:
- Request ID generation/extraction middleware
- Request ID propagation into logging context
- Response header propagation (`X-Request-ID`)
- Request summary logging for application routes
- Login rate limiting setup and key helpers
- Per-request context cleanup after response

## Domain Model

This module does not define persistent database models.

It defines middleware components:
- `RequestIDMiddleware`
- `rate_limiting.limiter`

Implementation references:
- Middleware package: `app/middleware/__init__.py`
- Request ID middleware: `app/middleware/request_id.py`
- Rate limiting: `app/middleware/rate_limiting.py`

## API

There is currently no standalone HTTP router under `app/middleware`.

Behavior is applied globally through app middleware registration in `app/main.py`:
- `app.add_middleware(RequestIDMiddleware)`
- `setup_rate_limiting(app)`

### Request ID header behavior

For every HTTP request:
- If incoming `X-Request-ID` exists, it is reused.
- Otherwise a UUID is generated.
- The request id is added to logging context.
- Response includes `X-Request-ID` with the same value.
- Logging context is restored at request end.

## Behavior Notes

- Middleware is implemented with `BaseHTTPMiddleware`.
- Request ID context operations use `set_request_id` / `reset_request_id` from `app.core.logging_config`.
- Request summary logging is skipped for noisy platform/browser paths:
  `/`, `/health`, `/ready`, `/docs`, `/openapi.json`, `/favicon.ico`.
- Skipped paths still receive request ID propagation and the `X-Request-ID` response header.
- Rate limiting uses SlowAPI and currently protects `POST /api/v1/auth/login`.
- Login rate limiting keys by normalized email when available, falling back to client IP.
- The middleware is non-domain-specific and applies across all routes.
- `RequestIDMiddleware` is registered after CORS middleware in `app/main.py`, so it runs first on the request path and can propagate `X-Request-ID` across CORS-handled responses.

## Error Envelope

- Rate limit responses use the canonical error envelope with `rate_limit_exceeded`.
- Exceptions continue through global exception handlers configured in `app/main.py` via `app/core/exceptions.py`.

## Cross-Domain Integration

- Integrates with `app/core/logging_config.py` to enrich logs with request correlation id.
- Integrates with `app/config.py` for `AUTH_LOGIN_RATE_LIMIT`.
- Applies uniformly to all domain routers included in `app/main.py`.

## Tests

Middleware behavior is covered by middleware unit tests and API/integration tests.

```bash
JWT_SECRET=test-secret ./.venv/bin/python -m pytest -q tests/middleware tests/<relevant_api_suite>
```
