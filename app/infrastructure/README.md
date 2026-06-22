## Scope
This file owns only:
- Implemented backend infrastructure adapter behavior.
- Current storage, outbound notification, and infrastructure service boundaries.

This file must not contain:
- Product notification rules.
- Deployment secrets inventory.
- Cross-project architecture rules.

Source of truth: mandatory

# Infrastructure Module

> Last audited: 2026-03-17 (domain-by-domain backend sync).


Provides infrastructure adapters used by domain services for external integrations (storage and outbound notifications).

## Scope

This module provides:
- Storage provider abstraction (`StorageProvider`)
- Local filesystem storage adapter for development/testing
- S3-compatible cloud storage adapter (AWS S3 / Cloudflare R2)
- Notification channel adapters for Email (SendGrid) and WhatsApp (360dialog)
- Environment-based provider/channel configuration behavior

## Domain Model

This module does not define persistent database models.

It defines infrastructure abstractions/adapters:
- `StorageProvider` (abstract interface)
- `LocalStorageProvider`
- `S3StorageProvider`
- `get_storage_provider()` factory
- `EmailChannel`
- `WhatsAppChannel`

Implementation references:
- Package init: `app/infrastructure/__init__.py`
- Storage adapters: `app/infrastructure/storage.py`
- Notification adapters: `app/infrastructure/notifications.py`

## API

There is currently no standalone HTTP router under `app/infrastructure`.

This module is consumed internally by service layers:
- Storage: used by `PermanentDocumentService`
- Notifications: used by `NotificationService`

## Behavior Notes

- Storage factory behavior (`get_storage_provider`):
  - `APP_ENV in {development, test}` -> `LocalStorageProvider`
  - otherwise -> `S3StorageProvider` (requires R2/S3 env variables)
- `LocalStorageProvider`:
  - Writes files under local `./storage` path by default
  - Returns `/local-storage/{key}` pseudo-url for download
- `S3StorageProvider`:
  - Requires `boto3`
  - Supports upload/delete/presigned URL
  - Works with AWS S3 and Cloudflare R2 via endpoint configuration
- Email channel (`EmailChannel`):
  - When notifications are disabled (`NOTIFICATIONS_ENABLED=false`), logs and returns success without sending
  - When enabled, sends through SendGrid API using configured sender identity
- WhatsApp channel (`WhatsAppChannel`):
  - Enabled only when API key + from-number are configured
  - Returns `(False, "not configured")` when disabled so caller can fall back to email
- Helper `_to_html` generates minimal RTL HTML from plain text content for email payloads.

## Error Envelope

Errors raised by callers still flow through the global app format in `app/core/exceptions.py`, including:
- `error.code`
- `error.message`
- `error.details` (null or domain-specific object)
- `error.request_id` (when available)

Infrastructure-specific runtime failures may include:
- Missing storage configuration (runtime error from `get_storage_provider`)
- Missing `boto3` dependency for `S3StorageProvider`
- Channel-level send failures returned as `(False, error_message)` by notification adapters

## Cross-Domain Integration

- `permanent_documents` integration:
  - `PermanentDocumentService` injects/uses `StorageProvider` for upload + presigned download URLs.
- `notification` integration:
  - `NotificationService` uses `EmailChannel` + `WhatsAppChannel` to deliver notifications and fallback across channels.
- `config` integration:
  - Provider/channel behavior is driven by environment variables loaded via `app/config.py`.

## Tests

There is no dedicated infrastructure-only test suite currently.

Infrastructure behavior is covered indirectly through domain tests, including:
- Notification domain tests:
  - `tests/notifications/service/test_notification.py`
  - `tests/notifications/repository/test_notification_repository.py`
- Permanent-documents domain tests:
  - `tests/permanent_documents/api/test_permanent_documents.py`
  - `tests/permanent_documents/service/test_permanent_document.py`
  - `tests/permanent_documents/service/test_permanent_document_list_delete.py`

Run related integration tests:

```bash
./.venv/bin/python -m pytest tests/notifications tests/permanent_documents -q
```
