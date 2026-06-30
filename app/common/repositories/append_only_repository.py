"""Append-only repository base for immutable audit tables.

Audit rows are append-only by design: a correction is a new row, never an edit
or delete of an existing one. This base therefore exposes ONLY the shared
session handle and the canonical pagination helper — it deliberately does NOT
provide ``update``/``delete``/``soft_delete``/``hard_delete`` (unlike
``BaseRepository``), so an audit repository can never mutate or remove a
persisted row. See docs/backend/architecture.md (append-only audit repositories).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.repositories.base_repository import _apply_pagination


class AppendOnlyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    apply_pagination = staticmethod(_apply_pagination)
