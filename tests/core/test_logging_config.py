import json
import logging

from app.core.logging_config import (
    RequestLogStats,
    StructuredFormatter,
    build_request_summary_event,
    clear_request_id,
    request_summary_level,
    set_request_id,
)


def test_request_summary_event_keeps_normal_request_compact():
    stats = RequestLogStats(
        request_method="GET",
        request_path="/api/v1/clients",
        request_route="clients.list_clients",
        status_code=200,
        duration_ms=84.7,
        actor_user_id=12,
        actor_role="advisor",
        sql_queries=3,
        sql_by_operation={"SELECT": 3},
        sql_total_ms=18.4,
    )

    event = build_request_summary_event(
        stats,
        service="YM-Tax-CRM",
        env="production",
        slow_request_ms=500,
        slow_query_ms=250,
        high_query_count=20,
    )

    assert event["event"] == "http_request_completed"
    assert event["http"] == {
        "method": "GET",
        "path": "/api/v1/clients",
        "route": "clients.list_clients",
        "status": 200,
        "duration_ms": 84.7,
    }
    assert event["actor"] == {"user_id": 12, "business_id": None, "role": "advisor"}
    assert event["db"] == {"queries": 3, "total_ms": 18.4}
    assert "flags" not in event


def test_request_summary_level_warns_on_threshold_flags():
    stats = RequestLogStats(
        status_code=200,
        duration_ms=501,
        sql_queries=20,
        sql_by_operation={"SELECT": 20},
        slowest_sql_ms=251,
    )

    assert (
        request_summary_level(
            stats,
            slow_request_ms=500,
            slow_query_ms=250,
            high_query_count=20,
        )
        == logging.WARNING
    )


def test_request_summary_event_expands_when_thresholds_trip():
    stats = RequestLogStats(
        request_method="GET",
        request_path="/api/v1/clients",
        request_route="clients.list_clients",
        status_code=200,
        duration_ms=501,
        sql_queries=20,
        sql_by_operation={"SELECT": 20},
        sql_total_ms=300,
        slowest_sql_ms=251,
        client_ip="203.0.113.24",
    )

    event = build_request_summary_event(
        stats,
        service="YM-Tax-CRM-crm",
        env="production",
        slow_request_ms=500,
        slow_query_ms=250,
        high_query_count=20,
    )

    assert event["flags"] == {
        "slow_request": True,
        "slow_query": True,
        "high_query_count": True,
    }
    assert event["db"]["by_operation"] == {"SELECT": 20}
    assert event["db"]["possible_n_plus_one"] is True
    assert event["http"]["client_ip"] == "203.0.113.24"


def test_possible_n_plus_one_tolerates_non_select_queries():
    stats = RequestLogStats(
        status_code=200,
        sql_queries=21,
        sql_by_operation={"SELECT": 20, "UPDATE": 1},
    )

    event = build_request_summary_event(
        stats,
        service="YM-Tax-CRM-crm",
        env="production",
        slow_request_ms=500,
        slow_query_ms=250,
        high_query_count=20,
    )

    assert event["db"]["possible_n_plus_one"] is True


def test_request_summary_level_errors_on_500():
    stats = RequestLogStats(status_code=500)

    assert (
        request_summary_level(
            stats,
            slow_request_ms=500,
            slow_query_ms=250,
            high_query_count=20,
        )
        == logging.ERROR
    )


def test_json_formatter_outputs_single_line_structured_event():
    set_request_id("req-123")
    formatter = StructuredFormatter(log_format="json")
    record = logging.LogRecord(
        name="app.middleware.request_id",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="SUMMARY",
        args=(),
        exc_info=None,
    )
    record.structured_event = {"event": "http_request_completed", "service": "test"}

    try:
        formatted = formatter.format(record)
        payload = json.loads(formatted)
    finally:
        clear_request_id()

    assert payload["event"] == "http_request_completed"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.middleware.request_id"
    assert payload["request_id"] == "req-123"
    assert "\n" not in formatted


def test_request_summary_error_excludes_stack():
    stats = RequestLogStats(
        status_code=500,
        error_type="server_error",
        error_message="boom",
    )

    event = build_request_summary_event(
        stats,
        service="YM-Tax-CRM-crm",
        env="production",
        slow_request_ms=500,
        slow_query_ms=250,
        high_query_count=20,
    )

    assert event["error"] == {"type": "server_error", "message": "boom"}


def test_json_formatter_preserves_structured_error_when_exc_info_exists():
    formatter = StructuredFormatter(log_format="json")
    try:
        raise RuntimeError("raw stack")
    except RuntimeError as exc:
        record = logging.LogRecord(
            name="app.core.exceptions",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Unhandled exception",
            args=(),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    record.structured_event = {
        "event": "http_request_completed",
        "error": {"type": "server_error", "message": "safe"},
    }

    payload = json.loads(formatter.format(record))

    assert payload["error"] == {"type": "server_error", "message": "safe"}
