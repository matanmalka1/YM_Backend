from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.core.api_types import ApiDateTime, ApiDecimal, PeriodStr
from app.main import app


class _PeriodModel(BaseModel):
    period: PeriodStr


class _OptionalPeriodModel(BaseModel):
    period: PeriodStr | None = None


@pytest.mark.parametrize("value", ["2026-01", "2026-06", "2026-12", "2000-09", "1999-11"])
def test_period_str_accepts_valid_yyyymm(value):
    assert _PeriodModel(period=value).period == value


@pytest.mark.parametrize(
    "value",
    [
        "garbage",
        "01-2026",
        "2026-00",
        "2026-13",
        "2026-1",
        "26-01",
        "2026-01-01",
        "",
    ],
)
def test_period_str_rejects_invalid_format(value):
    with pytest.raises(ValidationError):
        _PeriodModel(period=value)


def test_period_str_optional_none_allowed():
    assert _OptionalPeriodModel(period=None).period is None


def test_period_str_openapi_schema_has_pattern():
    openapi = app.openapi()
    schemas = openapi["components"]["schemas"]
    # VatWorkItemCreateRequest.period must expose the PeriodStr pattern
    vat_period = schemas["VatWorkItemCreateRequest"]["properties"]["period"]
    assert vat_period.get("pattern") == r"^\d{4}-(0[1-9]|1[0-2])$"
    # AdvancePaymentCreateRequest.period
    adv_period = schemas["AdvancePaymentCreateRequest"]["properties"]["period"]
    assert adv_period.get("pattern") == r"^\d{4}-(0[1-9]|1[0-2])$"


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
    invoice_created_at = schema["VatInvoiceResponse"]["properties"]["created_at"]
    attention_id = schema["AttentionBoardItem"]["properties"]["id"]
    attention_amount = schema["AttentionBoardItem"]["properties"]["amount"]
    annual_status_deadline = schema["AnnualReportStatusClientResponse"]["properties"][
        "filing_deadline"
    ]
    annual_card_deadline = schema["AnnualReportCard"]["properties"]["filing_deadline"]
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
    assert invoice_created_at["type"] == "string"
    assert invoice_created_at["format"] == "date-time"
    assert attention_id["pattern"] == "^\\w+:\\d+$"
    assert attention_amount["anyOf"][0]["type"] == "string"
    assert attention_amount["anyOf"][0]["format"] == "decimal"
    assert annual_status_deadline["anyOf"][0]["format"] == "date-time"
    assert annual_card_deadline["anyOf"][0]["format"] == "date-time"
    assert "{source_type}:{source_id}" in work_queue_id["description"]
    assert overdue_response["$ref"] == "#/components/schemas/AnnualReportListResponse"
