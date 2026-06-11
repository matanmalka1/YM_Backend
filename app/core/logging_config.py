"""
Structured logging for production observability.

Provides consistent log format with:
- Timestamp
- Level
- Message
- Request ID (when available)
- Stack traces for errors
"""

import json
import logging
import sys
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Context variable for request tracking
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
request_log_stats_ctx: ContextVar["RequestLogStats | None"] = ContextVar(
    "request_log_stats",
    default=None,
)


@dataclass
class RequestLogStats:
    """Runtime log counters for one request."""

    request_method: str | None = None
    request_path: str | None = None
    request_route: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    response_content_length: int | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    summary_logged: bool = False
    actor_user_id: int | None = None
    actor_business_id: int | None = None
    actor_role: str | None = None
    idempotency_key: str | None = None
    idempotency_replayed: bool = False
    error_type: str | None = None
    error_message: str | None = None
    sql_queries: int = 0
    sql_by_operation: dict[str, int] = field(default_factory=dict)
    sql_transactions: dict[str, int] = field(default_factory=dict)
    sql_total_ms: float = 0
    slowest_sql_ms: float = 0
    app_warnings: int = 0
    app_errors: int = 0

    def record_sql_query(self, statement: str, duration_ms: float) -> None:
        operation = _sql_operation(statement)
        self.sql_queries += 1
        self.sql_by_operation[operation] = self.sql_by_operation.get(operation, 0) + 1
        self.sql_total_ms += duration_ms
        self.slowest_sql_ms = max(self.slowest_sql_ms, duration_ms)

    def record_transaction(self, transaction: str) -> None:
        self.sql_transactions[transaction] = self.sql_transactions.get(transaction, 0) + 1


def _sql_operation(statement: str) -> str:
    stripped = statement.lstrip()
    if not stripped:
        return "OTHER"
    return stripped.split(None, 1)[0].upper()


def begin_request_log_stats() -> None:
    """Start log counters for the current request."""
    request_log_stats_ctx.set(RequestLogStats())


def clear_request_log_stats() -> None:
    """Clear request log counters from current context."""
    request_log_stats_ctx.set(None)


def get_request_log_stats() -> RequestLogStats | None:
    """Return current request log counters, when available."""
    return request_log_stats_ctx.get()


def record_sql_query(statement: str, duration_ms: float) -> None:
    """Record SQL query metrics for the current request."""
    stats = request_log_stats_ctx.get()
    if stats is not None:
        stats.record_sql_query(statement, duration_ms)


def set_request_summary_context(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    *,
    route: str | None = None,
    response_content_length: int | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    referer: str | None = None,
) -> None:
    """Store request metadata used by the summary log."""
    stats = request_log_stats_ctx.get()
    if stats is None:
        return

    stats.request_method = method
    stats.request_path = path
    stats.request_route = route
    stats.status_code = status_code
    stats.duration_ms = duration_ms
    stats.response_content_length = response_content_length
    stats.client_ip = client_ip
    stats.user_agent = user_agent
    stats.referer = referer


def set_actor_context(
    *,
    user_id: int,
    role: str,
    business_id: int | None = None,
) -> None:
    """Store authenticated actor metadata for the current request."""
    stats = request_log_stats_ctx.get()
    if stats is None:
        return

    stats.actor_user_id = user_id
    stats.actor_role = role
    stats.actor_business_id = business_id


def set_idempotency_context(key: str, *, replayed: bool = False) -> None:
    """Store idempotency metadata for the current request."""
    stats = request_log_stats_ctx.get()
    if stats is None:
        return

    stats.idempotency_key = key
    stats.idempotency_replayed = replayed


def set_request_error(exc: BaseException, *, error_type: str | None = None) -> None:
    """Store exception metadata for the current request summary."""
    stats = request_log_stats_ctx.get()
    if stats is None:
        return

    stats.error_type = error_type or exc.__class__.__name__
    stats.error_message = str(exc)


def has_request_db_activity() -> bool:
    """Return whether the current request has emitted DB logs."""
    stats = request_log_stats_ctx.get()
    if stats is None:
        return False
    return stats.sql_queries > 0 or bool(stats.sql_transactions)


def format_request_summary(stats: RequestLogStats) -> str:
    """Format the current request summary."""
    request_method = stats.request_method or "UNKNOWN"
    request_path = stats.request_path or "unknown"
    status_code = stats.status_code if stats.status_code is not None else 500
    duration_ms = stats.duration_ms if stats.duration_ms is not None else 0

    lines = [
        "SUMMARY",
        f"  request: {request_method} {request_path} {status_code}",
    ]
    if stats.request_route:
        lines.append(f"  route: {stats.request_route}")
    if stats.actor_user_id is not None:
        actor = f"user={stats.actor_user_id}"
        if stats.actor_business_id is not None:
            actor = f"{actor} business={stats.actor_business_id}"
        if stats.actor_role is not None:
            actor = f"{actor} role={stats.actor_role}"
        lines.append(f"  actor: {actor}")

    lines.extend(
        [
            f"  duration: {duration_ms:.1f}ms",
            f"  SQL queries: {stats.sql_queries}",
        ]
    )

    for operation, count in sorted(stats.sql_by_operation.items()):
        lines.append(f"  {operation}: {count}")

    for transaction, count in sorted(stats.sql_transactions.items()):
        lines.append(f"  {transaction}: {count}")

    lines.extend(
        [
            f"  SQL total: {stats.sql_total_ms:.1f}ms",
            f"  slowest query: {stats.slowest_sql_ms:.1f}ms",
            f"  app warnings: {stats.app_warnings}",
            f"  errors: {stats.app_errors}",
        ]
    )
    if stats.error_type:
        lines.append(f"  error: {stats.error_type}")

    return "\n".join(lines)


def _request_flags(
    stats: RequestLogStats,
    *,
    slow_request_ms: int,
    slow_query_ms: int,
    high_query_count: int,
) -> dict[str, bool]:
    duration_ms = stats.duration_ms or 0
    return {
        "slow_request": duration_ms >= slow_request_ms,
        "slow_query": stats.slowest_sql_ms >= slow_query_ms,
        "high_query_count": stats.sql_queries >= high_query_count,
    }


def request_summary_level(
    stats: RequestLogStats,
    *,
    slow_request_ms: int,
    slow_query_ms: int,
    high_query_count: int,
) -> int:
    """Choose log level from request outcome and thresholds."""
    status_code = stats.status_code if stats.status_code is not None else 500
    if status_code >= 500 or stats.error_type is not None:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    flags = _request_flags(
        stats,
        slow_request_ms=slow_request_ms,
        slow_query_ms=slow_query_ms,
        high_query_count=high_query_count,
    )
    if any(flags.values()) or stats.app_warnings or stats.app_errors:
        return logging.WARNING
    return logging.INFO


def build_request_summary_event(
    stats: RequestLogStats,
    *,
    service: str,
    env: str,
    slow_request_ms: int,
    slow_query_ms: int,
    high_query_count: int,
) -> dict[str, Any]:
    """Build the structured request summary payload."""
    flags = _request_flags(
        stats,
        slow_request_ms=slow_request_ms,
        slow_query_ms=slow_query_ms,
        high_query_count=high_query_count,
    )
    possible_n_plus_one = (
        stats.sql_queries >= high_query_count
        and stats.sql_by_operation.get("SELECT", 0) >= high_query_count
    )
    status_code = stats.status_code if stats.status_code is not None else 500
    diagnostic = any(flags.values()) or status_code >= 400 or stats.error_type is not None
    payload: dict[str, Any] = {
        "event": "http_request_completed",
        "service": service,
        "env": env,
        "http": {
            "method": stats.request_method or "UNKNOWN",
            "path": stats.request_path or "unknown",
            "route": stats.request_route,
            "status": status_code,
            "duration_ms": round(stats.duration_ms or 0, 1),
        },
        "db": {
            "queries": stats.sql_queries,
            "total_ms": round(stats.sql_total_ms, 1),
        },
        "app": {
            "warnings": stats.app_warnings,
            "errors": stats.app_errors,
        },
    }
    if stats.actor_user_id is not None:
        payload["actor"] = {
            "user_id": stats.actor_user_id,
            "business_id": stats.actor_business_id,
            "role": stats.actor_role,
        }
    if any(flags.values()):
        payload["flags"] = flags
        payload["thresholds"] = {
            "slow_request_ms": slow_request_ms,
            "slow_query_ms": slow_query_ms,
            "high_query_count": high_query_count,
        }
    if diagnostic:
        payload["db"].update(
            {
                "slowest_ms": round(stats.slowest_sql_ms, 1),
                "by_operation": stats.sql_by_operation,
                "possible_n_plus_one": possible_n_plus_one,
            }
        )
        if stats.client_ip:
            payload["http"]["client_ip"] = stats.client_ip
        if stats.user_agent:
            payload["http"]["user_agent"] = stats.user_agent
        if stats.referer:
            payload["http"]["referer"] = stats.referer
    if diagnostic and stats.response_content_length is not None:
        payload["response"] = {"content_length": stats.response_content_length}
    if stats.idempotency_key is not None:
        payload["idempotency"] = {
            "key": stats.idempotency_key,
            "replayed": stats.idempotency_replayed,
        }
    if stats.error_type is not None:
        payload["error"] = {
            "type": stats.error_type,
            "message": stats.error_message,
        }
    return payload


def log_request_summary(
    logger: logging.Logger,
    *,
    service: str = "binder-billing-crm",
    env: str = "development",
    slow_request_ms: int = 500,
    slow_query_ms: int = 250,
    high_query_count: int = 20,
) -> None:
    """Log the current request summary once."""
    stats = request_log_stats_ctx.get()
    if stats is None or stats.summary_logged:
        return

    stats.summary_logged = True
    level = request_summary_level(
        stats,
        slow_request_ms=slow_request_ms,
        slow_query_ms=slow_query_ms,
        high_query_count=high_query_count,
    )
    logger.log(
        level,
        format_request_summary(stats),
        extra={
            "structured_event": build_request_summary_event(
                stats,
                service=service,
                env=env,
                slow_request_ms=slow_request_ms,
                slow_query_ms=slow_query_ms,
                high_query_count=high_query_count,
            )
        },
    )


class StructuredFormatter(logging.Formatter):
    """Structured log formatter."""

    def __init__(self, *, log_format: str = "text"):
        super().__init__()
        self.log_format = log_format

    def _timestamp(self, record: logging.LogRecord) -> str:
        return datetime.fromtimestamp(record.created, tz=UTC).isoformat(
            timespec="milliseconds"
        )

    def _format_json(self, record: logging.LogRecord) -> str:
        request_id = request_id_ctx.get()
        payload = getattr(record, "structured_event", None)
        if isinstance(payload, dict):
            event = dict(payload)
        else:
            event = {
                "event": "app_log",
                "message": record.getMessage(),
            }

        event.setdefault("ts", self._timestamp(record))
        event.setdefault("level", record.levelname)
        event.setdefault("logger", record.name)
        if request_id:
            event.setdefault("request_id", request_id)
        if record.exc_info and "error" not in event:
            event["error"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stack": self.formatException(record.exc_info),
            }
        return json.dumps(event, ensure_ascii=False, separators=(",", ":"))

    def _format_prefix(self, record: logging.LogRecord) -> str:
        request_id = request_id_ctx.get()
        parts = [
            f"[{self.formatTime(record)}]",
            record.levelname,
        ]
        if request_id:
            parts.append(f"request_id={request_id}")
        return " ".join(parts)

    def _indent(self, text: str) -> str:
        return "\n".join(f"  {line}" if line else "" for line in text.splitlines())

    def _format_sqlalchemy(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        prefix = f"{self._format_prefix(record)} SQL"
        stats = request_log_stats_ctx.get()

        if stats is not None:
            if message.startswith("BEGIN"):
                stats.record_transaction("BEGIN")
            elif message == "COMMIT":
                stats.record_transaction("COMMIT")
            elif message == "ROLLBACK":
                stats.record_transaction("ROLLBACK")

        if message.startswith("["):
            return f"{prefix}\n  {message}"

        return f"{prefix}\n{self._indent(message)}"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with structured fields."""
        stats = request_log_stats_ctx.get()
        if stats is not None and not isinstance(getattr(record, "structured_event", None), dict):
            if record.levelno >= logging.ERROR:
                stats.app_errors += 1
            elif record.levelno >= logging.WARNING:
                stats.app_warnings += 1

        if self.log_format == "json":
            return self._format_json(record)

        if record.name.startswith("sqlalchemy.engine"):
            return self._format_sqlalchemy(record)

        prefix = self._format_prefix(record)
        record_message = record.getMessage()
        if record_message.startswith("SUMMARY\n"):
            summary_body = record_message.removeprefix("SUMMARY\n")
            message = f"{prefix} SUMMARY\n{summary_body}"
        else:
            message = f"{prefix} {record.name} | {record_message}"

        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            message = f"{message}\nexception:\n{self._indent(exc_text)}"

        return message


def setup_logging(level: str = "INFO", *, log_format: str = "text") -> None:
    """
    Setup structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter(log_format=log_format))
    logger.addHandler(handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def set_request_id(request_id: str) -> Token[str | None]:
    """Set request ID for current context."""
    return request_id_ctx.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the previous request ID context."""
    request_id_ctx.reset(token)


def clear_request_id() -> None:
    """Clear request ID from current context."""
    request_id_ctx.set(None)


def get_request_id() -> str | None:
    """Return current request ID, or None if not set."""
    return request_id_ctx.get()


def get_logger(name: str) -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)
