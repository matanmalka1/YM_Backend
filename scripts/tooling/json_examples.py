from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402

FORMAT_EXAMPLES = {
    "date-time": "2026-01-15T10:30:00Z",
    "date": "2026-01-15",
    "email": "user@example.com",
    "uuid": "123e4567-e89b-12d3-a456-426614174000",
    "uri": "https://example.com/resource",
}

MANUAL_BINARY_SUCCESS_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    (
        "GET",
        "/api/v1/annual-reports/{report_id}/export/pdf",
    ): {
        "status": "200",
        "variants": [
            {
                "when": "always",
                "content_type": "application/pdf",
                "content_disposition": 'attachment; filename="annual_report_123_2026.pdf"',
            }
        ],
    },
    ("GET", "/api/v1/clients/export"): {
        "status": "200",
        "variants": [
            {
                "when": "always",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_disposition": 'attachment; filename="clients_export_20260323_120000.xlsx"',
            }
        ],
    },
    ("GET", "/api/v1/clients/template"): {
        "status": "200",
        "variants": [
            {
                "when": "always",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_disposition": 'attachment; filename="clients_template_20260323_120000.xlsx"',
            }
        ],
    },
    ("GET", "/api/v1/reports/aging/export"): {
        "status": "200",
        "variants": [
            {
                "when": "format=pdf",
                "content_type": "application/pdf",
                "content_disposition": 'attachment; filename="aging_report_20260323_120000.pdf"',
            },
            {
                "when": "format=excel",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_disposition": 'attachment; filename="aging_report_20260323_120000.xlsx"',
            },
        ],
    },
    ("GET", "/api/v1/vat/businesses/{business_id}/export"): {
        "status": "200",
        "variants": [
            {
                "when": "format=pdf",
                "content_type": "application/pdf",
                "content_disposition": 'attachment; filename="vat_business_42_2026.pdf"',
            },
            {
                "when": "format=excel",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_disposition": 'attachment; filename="vat_business_42_2026.xlsx"',
            },
        ],
    },
}

MANUAL_SUCCESS_OVERRIDES: dict[tuple[str, str], Any] = {
    ("GET", "/"): {"service": "YM Tax CRM", "status": "running"},
    ("GET", "/info"): {"app": "YM Tax CRM", "env": "development"},
    ("GET", "/health"): {"status": "healthy", "database": "connected"},
    ("POST", "/api/v1/clients/import"): {
        "created": 3,
        "total_rows": 5,
        "errors": [
            {
                "row": 4,
                "error": "שם מלא ומספר מזהה הם שדות חובה",
            },
            {
                "row": 5,
                "error": "Client with this id number already exists",
            },
        ],
    },
    ("GET", "/api/v1/reports/vat-compliance"): {
        "year": 2026,
        "total_clients": 2,
        "items": [
            {
                "client_id": 1,
                "client_name": "string",
                "periods_expected": 12,
                "periods_filed": 10,
                "periods_open": 2,
                "on_time_count": 9,
                "late_count": 1,
                "compliance_rate": 83.33,
            }
        ],
        "stale_pending": [
            {
                "client_id": 1,
                "client_name": "string",
                "period": "2026-01",
                "days_pending": 45,
            }
        ],
    },
    ("GET", "/api/v1/reports/advance-payments"): {
        "year": 2026,
        "month": 3,
        "total_expected": 25000.0,
        "total_paid": 20000.0,
        "collection_rate": 80.0,
        "total_gap": 5000.0,
        "items": [
            {
                "business_id": 1,
                "client_id": 1,
                "business_name": "string",
                "client_name": "string",
                "total_expected": 12000.0,
                "total_paid": 9000.0,
                "overdue_count": 1,
                "gap": 3000.0,
            }
        ],
    },
    ("GET", "/api/v1/reports/annual-reports"): {
        "tax_year": 2026,
        "total": 2,
        "statuses": [
            {
                "status": "collecting_docs",
                "count": 1,
                "clients": [
                    {
                        "client_id": 1,
                        "client_name": "string",
                        "form_type": "1301",
                        "filing_deadline": "2026-04-30",
                        "days_until_deadline": 38,
                    }
                ],
            }
        ],
    },
    ("GET", "/api/v1/reports/aging"): {
        "report_date": "2026-03-23",
        "total_outstanding": 15250.0,
        "items": [
            {
                "client_id": 1,
                "client_name": "string",
                "total_outstanding": 15250.0,
                "current": 5000.0,
                "days_30": 4000.0,
                "days_60": 3000.0,
                "days_90_plus": 3250.0,
                "oldest_invoice_date": "2025-11-20",
                "oldest_invoice_days": 123,
            }
        ],
        "summary": {
            "total_clients": 1,
            "total_current": 5000.0,
            "total_30_days": 4000.0,
            "total_60_days": 3000.0,
            "total_90_plus": 3250.0,
        },
        "capped": False,
        "cap_limit": 2000,
    },
}


def _extract_ref_name(ref: str) -> str:
    return ref.split("/")[-1]


def _extract_explicit_example(payload: dict[str, Any]) -> Any | None:
    if "example" in payload:
        return payload["example"]

    examples = payload.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
        return first
    if isinstance(examples, list) and examples:
        return examples[0]
    return None


def _first_success_status_with_json(
    responses: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    def sort_key(code: str) -> tuple[int, int]:
        if code.isdigit():
            return (0, int(code))
        return (1, 999)

    for status in sorted(responses.keys(), key=sort_key):
        if status.startswith("2"):
            content = responses[status].get("content", {})
            if "application/json" in content:
                return status, content["application/json"]
    return None, None


def _first_success_status(responses: dict[str, Any]) -> str | None:
    def sort_key(code: str) -> tuple[int, int]:
        if code.isdigit():
            return (0, int(code))
        return (1, 999)

    for status in sorted(responses.keys(), key=sort_key):
        if status.startswith("2"):
            return status
    return None


def _pick_non_null_variant(variants: list[dict[str, Any]]) -> dict[str, Any] | None:
    for candidate in variants:
        candidate_type = candidate.get("type")
        if candidate_type == "null":
            continue
        if isinstance(candidate_type, list) and set(candidate_type) == {"null"}:
            continue
        if candidate.get("enum") == [None]:
            continue
        return candidate
    return variants[0] if variants else None


def _is_empty_container(value: Any) -> bool:
    return value == {} or value == []


def get_example_from_schema(
    schema: dict[str, Any],
    all_schemas: dict[str, Any],
    ref_stack: set[str] | None = None,
    depth: int = 0,
) -> Any:
    if ref_stack is None:
        ref_stack = set()
    if depth > 12:
        return {}

    if not schema:
        return {}

    if "$ref" in schema:
        ref_name = _extract_ref_name(schema["$ref"])
        if ref_name in ref_stack:
            return {}
        return get_example_from_schema(
            all_schemas.get(ref_name, {}),
            all_schemas,
            ref_stack | {ref_name},
            depth + 1,
        )

    explicit_example = _extract_explicit_example(schema)
    if explicit_example is not None and not _is_empty_container(explicit_example):
        return explicit_example

    if "default" in schema and not _is_empty_container(schema["default"]):
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema and schema["enum"]:
        for value in schema["enum"]:
            if value is not None:
                return value
        return schema["enum"][0]

    if "allOf" in schema:
        merged: dict[str, Any] = {}
        for part in schema["allOf"]:
            part_example = get_example_from_schema(part, all_schemas, ref_stack, depth + 1)
            if isinstance(part_example, dict):
                merged.update(part_example)
            elif part_example is not None and not merged:
                return part_example
        return merged

    for key in ("oneOf", "anyOf"):
        variants = schema.get(key)
        if isinstance(variants, list) and variants:
            chosen = _pick_non_null_variant(variants)
            if chosen is not None:
                return get_example_from_schema(chosen, all_schemas, ref_stack, depth + 1)

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null = [value for value in schema_type if value != "null"]
        schema_type = non_null[0] if non_null else "null"
    if schema_type is None:
        if "properties" in schema or "additionalProperties" in schema:
            schema_type = "object"
        elif "items" in schema:
            schema_type = "array"

    if schema_type == "object":
        result: dict[str, Any] = {}
        for prop, prop_schema in schema.get("properties", {}).items():
            result[prop] = get_example_from_schema(
                prop_schema,
                all_schemas,
                ref_stack,
                depth + 1,
            )
        additional = schema.get("additionalProperties")
        if not result and additional:
            if additional is True:
                result["key"] = "value"
            elif isinstance(additional, dict):
                result["key"] = get_example_from_schema(
                    additional,
                    all_schemas,
                    ref_stack,
                    depth + 1,
                )
        return result

    if schema_type == "array":
        item_schema = schema.get("items", {})
        item_example = get_example_from_schema(item_schema, all_schemas, ref_stack, depth + 1)
        if item_example is None:
            return []
        return [item_example]

    if schema_type == "string":
        return FORMAT_EXAMPLES.get(schema.get("format"), "string")
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "null":
        return None

    return {}


def _example_from_content(content_obj: dict[str, Any], all_schemas: dict[str, Any]) -> Any:
    explicit = _extract_explicit_example(content_obj)
    if explicit is not None:
        return explicit
    return get_example_from_schema(content_obj.get("schema", {}), all_schemas)


def _write_binary_response_example(file_obj, status: str, metadata: dict[str, Any]) -> None:
    variants = metadata.get("variants", [])
    file_obj.write(f"### 📤 Success Response ({status})\n")
    file_obj.write("```text\n")
    file_obj.write("Binary file response (download stream)\n\n")
    for idx, variant in enumerate(variants, start=1):
        when = variant.get("when", "always")
        content_type = variant.get("content_type", "application/octet-stream")
        content_disposition = variant.get(
            "content_disposition", 'attachment; filename="download.bin"'
        )
        file_obj.write(f"Variant {idx} ({when})\n")
        file_obj.write(f"Content-Type: {content_type}\n")
        file_obj.write(f"Content-Disposition: {content_disposition}\n\n")
    file_obj.write("Body: <binary bytes>\n")
    file_obj.write("```\n\n")


def generate_enhanced_contract(app: FastAPI, filename: str = "JSON_EXAMPLES.md") -> None:
    openapi_data = app.openapi()
    paths = openapi_data.get("paths", {})
    all_schemas = openapi_data.get("components", {}).get("schemas", {})

    with open(filename, "w", encoding="utf-8") as f:
        f.write("# 🚀 API Contract & Documentation\n")
        f.write(f"**Last Updated:** {date.today().isoformat()}\n\n---\n")

        for path, methods in paths.items():
            for method, details in methods.items():
                f.write(f"## {method.upper()} `{path}`\n")
                f.write(f"**Summary:** {details.get('summary', 'N/A')}\n\n")

                request_body = details.get("requestBody", {})
                request_content = request_body.get("content", {}).get("application/json")
                if request_content:
                    request_example = _example_from_content(request_content, all_schemas)
                    f.write("### 📥 Request Body (JSON)\n")
                    f.write(
                        f"```json\n{json.dumps(request_example, indent=2, ensure_ascii=False)}\n```\n\n"
                    )

                responses = details.get("responses", {})
                raw_success_status = _first_success_status(responses)
                binary_override = MANUAL_BINARY_SUCCESS_OVERRIDES.get((method.upper(), path))
                if binary_override is not None:
                    status = binary_override.get("status") or raw_success_status or "200"
                    _write_binary_response_example(f, status, binary_override)
                    f.write("---\n\n")
                    continue

                success_status, success_content = _first_success_status_with_json(responses)
                override_example = MANUAL_SUCCESS_OVERRIDES.get((method.upper(), path))
                if override_example is not None:
                    status = success_status or "200"
                    f.write(f"### 📤 Success Response ({status})\n")
                    f.write(
                        f"```json\n{json.dumps(override_example, indent=2, ensure_ascii=False)}\n```\n\n"
                    )
                elif success_status and success_content:
                    response_example = _example_from_content(success_content, all_schemas)
                    f.write(f"### 📤 Success Response ({success_status})\n")
                    f.write(
                        f"```json\n{json.dumps(response_example, indent=2, ensure_ascii=False)}\n```\n\n"
                    )

                f.write("---\n\n")


if __name__ == "__main__":
    generate_enhanced_contract(app)
    print("✅ JSON_EXAMPLES.md generated with richer JSON examples")
