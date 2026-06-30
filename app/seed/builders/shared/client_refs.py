from __future__ import annotations

from typing import Any


def attach_seed_client_context(row: Any, client_record: Any) -> None:
    """Attach seed-only client context to ORM rows that do not store it directly."""
    row._seed_client_record_id = client_record.id
    row._seed_client_record = client_record


def get_seed_client_record_id(row: Any) -> int:
    client_record_id = getattr(row, "client_record_id", None)
    if client_record_id is not None:
        return int(client_record_id)

    seed_client_record_id = getattr(row, "_seed_client_record_id", None)
    if seed_client_record_id is not None:
        return int(seed_client_record_id)

    raise AttributeError(f"{type(row).__name__} has no client_record_id or seed client context")


def get_seed_client_record(row: Any) -> Any | None:
    return getattr(row, "_seed_client_record", None)
