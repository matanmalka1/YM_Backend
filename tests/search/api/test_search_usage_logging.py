import json
import logging

from app.core.logging_config import StructuredFormatter
from app.search.schemas.search import SearchMatchType
from app.search.services import search_service as search_service_module
from app.tasks.models.task import Task


def _usage_record(caplog):
    records = [
        record
        for record in caplog.records
        if getattr(record, "structured_event", {}).get("event") == "global_search_phase1_usage"
    ]
    assert len(records) == 1
    return records[0]


def test_authenticated_search_logs_phase_one_usage_without_the_term(
    client,
    advisor_headers,
    test_db,
    test_user,
    create_client_with_business,
    caplog,
):
    sensitive_term = "Private Client 884422"
    crm_client, _ = create_client_with_business(full_name=sensitive_term)
    test_db.add(
        Task(
            title=sensitive_term,
            client_record_id=crm_client.id,
            created_by_user_id=test_user.id,
        )
    )
    test_db.commit()

    with caplog.at_level(logging.INFO, logger=search_service_module.__name__):
        response = client.get(
            "/api/v1/search",
            params={"search": sensitive_term},
            headers=advisor_headers,
        )

    record = _usage_record(caplog)
    result_totals = {result_type.value: 0 for result_type in SearchMatchType}
    result_totals[SearchMatchType.TASK.value] = 1
    assert response.status_code == 200
    assert response.json()["clients"]["total"] == 1
    assert record.structured_event == {
        "event": "global_search_phase1_usage",
        "term_length": len(sensitive_term),
        "term_classification": "text",
        "client_total": 1,
        "result_totals": result_totals,
        "zero_result": False,
    }

    formatted = StructuredFormatter(log_format="json").format(record)
    payload = json.loads(formatted)
    assert payload["result_totals"] == result_totals
    assert sensitive_term not in record.getMessage()
    assert sensitive_term not in formatted


def test_authenticated_search_logs_zero_result_from_existing_totals(
    client,
    advisor_headers,
    caplog,
):
    sensitive_term = "No Such Private Client 991177"

    with caplog.at_level(logging.INFO, logger=search_service_module.__name__):
        response = client.get(
            "/api/v1/search",
            params={"search": sensitive_term},
            headers=advisor_headers,
        )

    record = _usage_record(caplog)
    assert response.status_code == 200
    assert record.structured_event["client_total"] == 0
    assert set(record.structured_event["result_totals"]) == {
        result_type.value for result_type in SearchMatchType
    }
    assert all(total == 0 for total in record.structured_event["result_totals"].values())
    assert record.structured_event["zero_result"] is True
    assert sensitive_term not in record.getMessage()
