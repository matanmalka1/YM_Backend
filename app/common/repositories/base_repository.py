from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.utils.time_utils import utcnow

ModelType = TypeVar("ModelType")


def _has_column(model: type[Any], column_name: str) -> bool:
    return hasattr(model, column_name)


def _apply_not_deleted(stmt, model: type[Any]):
    if not _has_column(model, "deleted_at"):
        return stmt
    return stmt.where(model.deleted_at.is_(None))


def _apply_pagination(stmt, page: int, page_size: int):
    return stmt.offset((page - 1) * page_size).limit(page_size)


class BaseRepository(Generic[ModelType]):
    """
    Generic CRUD base for SQLAlchemy ORM repositories.

    Opt in by setting `model = SomeModel`. Subclasses that do not set `model`
    continue to override methods directly.
    """

    model: ClassVar[type[ModelType]]

    def __init__(self, db: Session):
        self.db = db

    def select_base(self, *, include_deleted: bool = False):
        stmt = select(self.model)
        return stmt if include_deleted else _apply_not_deleted(stmt, self.model)

    def get(self, entity_id: int, /, *, include_deleted: bool = False) -> ModelType | None:
        # Session.get() is identity-map-aware: it emits no SQL when the entity was already
        # loaded earlier in the request. Apply the soft-delete filter in Python so callers
        # that preload an entity do not pay an extra SELECT here.
        entity = self.db.get(self.model, entity_id)
        if entity is None:
            return None
        if not include_deleted and getattr(entity, "deleted_at", None) is not None:
            return None
        return entity

    def get_by_id(self, entity_id: int, /) -> ModelType | None:
        return self.get(entity_id)

    def get_by_ids(
        self, entity_ids: set[int] | list[int], /, *, include_deleted: bool = False
    ) -> dict[int, ModelType]:
        ids = set(entity_ids)
        if not ids:
            return {}
        rows = self.db.scalars(
            self.select_base(include_deleted=include_deleted).where(self.model.id.in_(ids))
        ).all()
        return {row.id: row for row in rows}

    def get_by_id_for_update(self, entity_id: int, /) -> ModelType | None:
        """The row, locked until the transaction ends.

        ``populate_existing`` is not optional here. A plain ``SELECT`` whose row is
        already in the identity map returns the *loaded* object and leaves its
        attributes untouched — so a caller that read the entity before taking the
        lock would re-check its gate against the state it saw beforehand, which is
        exactly the state the lock exists to stop trusting. The lock would be held
        and the decision still stale.
        """
        stmt = (
            self.select_base()
            .where(self.model.id == entity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.db.scalars(stmt).first()

    def add(self, entity: ModelType) -> ModelType:
        self.db.add(entity)
        self.db.flush()
        return entity

    def create(self, *args, **kwargs) -> ModelType:
        if args:
            raise TypeError("BaseRepository.create accepts keyword fields only")
        return self.build_and_add(**kwargs)

    def build_and_add(self, **kwargs) -> ModelType:
        entity = self.model(**kwargs)
        self.db.add(entity)
        self.db.flush()
        return entity

    def update(self, entity_id: int, /, **fields) -> ModelType | None:
        return self._update_entity(self.get(entity_id), **fields)

    def soft_delete(self, entity_id: int, /, deleted_by: int | None = None) -> bool:
        if not _has_column(self.model, "deleted_at"):
            return self.hard_delete(entity_id)
        entity = self.get_by_id(entity_id)
        if not entity:
            return False
        entity.deleted_at = utcnow()
        if deleted_by is not None and hasattr(entity, "deleted_by"):
            entity.deleted_by = deleted_by
        self.db.flush()
        return True

    def _soft_delete_entity(self, entity_id: int, /, deleted_by: int | None = None) -> bool:
        return BaseRepository.soft_delete(self, entity_id, deleted_by)

    def delete(
        self,
        entity_id: int,
        /,
        deleted_by: int | None = None,
        *,
        hard: bool = False,
    ) -> bool:
        if not hard and _has_column(self.model, "deleted_at"):
            return self.soft_delete(entity_id, deleted_by)
        return self.hard_delete(entity_id)

    def hard_delete(self, entity_id: int, /) -> bool:
        entity = self.get(entity_id, include_deleted=True)
        if not entity:
            return False
        self.db.delete(entity)
        self.db.flush()
        return True

    apply_pagination = staticmethod(_apply_pagination)

    def _update_entity(
        self,
        entity,
        *,
        touch_updated_at: bool = False,
        **fields,
    ):
        if not entity:
            return None

        for key, value in fields.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        if touch_updated_at and hasattr(entity, "updated_at"):
            entity.updated_at = utcnow()

        self.db.flush()
        return entity

    def _update_status(
        self,
        entity,
        new_status,
        *,
        touch_updated_at: bool = False,
        **additional_fields,
    ):
        if not entity:
            return None
        entity.status = new_status
        return self._update_entity(
            entity,
            touch_updated_at=touch_updated_at,
            **additional_fields,
        )
