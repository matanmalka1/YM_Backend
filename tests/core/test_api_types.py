from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pydantic import BaseModel

from app.core.api_types import ApiDateTime, ApiDecimal
from app.main import app


class ExampleSchema(BaseModel):
    amount: ApiDecimal
    happened_at: ApiDateTime


def test_api_scalar_serialization_normalizes_to_string_and_utc():
    payload = ExampleSchema(
        amount=Decimal("123.45"),
        happened_at=datetime(2026, 1, 2, 5, 4, 5, tzinfo=timezone(timedelta(hours=2))),
    )

    assert payload.model_dump(mode="json") == {
        "amount": "123.45",
        "happened_at": "2026-01-02T03:04:05Z",
    }


def test_openapi_uses_string_contract_for_decimal_and_datetime_fields():
    openapi = app.openapi()
    schema = openapi["components"]["schemas"]

    expected_amount = schema["AdvancePaymentCreateRequest"]["properties"]["turnover_amount"]
    created_at = schema["ClientRecordResponse"]["properties"]["created_at"]
    vat_total = schema["VatWorkItemResponse"]["properties"]["total_output_vat"]
    invoice_gross = schema["VatInvoiceResponse"]["properties"]["gross_amount"]
    work_queue_id = schema["WorkQueueItem"]["properties"]["id"]
    overdue_response = openapi["paths"]["/api/v1/annual-reports/overdue"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]

    assert expected_amount["anyOf"][0]["type"] == "string"
    assert expected_amount["anyOf"][0]["format"] == "decimal"
    assert created_at["anyOf"][0]["type"] == "string"
    assert created_at["anyOf"][0]["format"] == "date-time"
    assert created_at["anyOf"][0]["examples"] == ["2026-01-02T03:04:05Z"]
    assert vat_total["type"] == "string"
    assert vat_total["format"] == "decimal"
    assert invoice_gross["type"] == "string"
    assert invoice_gross["format"] == "decimal"
    assert invoice_gross["readOnly"] is True
    assert "{source_type}:{source_id}" in work_queue_id["description"]
    assert overdue_response["$ref"] == "#/components/schemas/PaginatedResponse_AnnualReportResponse_"
