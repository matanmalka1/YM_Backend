import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging_config import set_idempotency_context
from app.database import get_db
from app.infrastructure.idempotency.model import IdempotencyStatus
from app.infrastructure.idempotency.repository import IdempotencyKeyRepository
from app.users.api.deps import get_current_user
from app.users.repositories.user_repository import AuthSubject


@dataclass
class IdempotencyGuard:
    key: str
    route: str
    user_id: int
    db: Session

    def execute(
        self,
        *,
        payload: bytes,
        fn: Callable[[], Any],
    ) -> Any:
        request_hash = hashlib.sha256(payload).hexdigest()
        repo = IdempotencyKeyRepository(self.db)

        # Reserve the key BEFORE running fn so concurrent requests collide on
        # the PK. Wrap the INSERT in a SAVEPOINT so the conflict rolls back ONLY
        # the failed insert — not unrelated state in the outer transaction.
        try:
            with self.db.begin_nested():
                row = repo.reserve(
                    key=self.key,
                    route=self.route,
                    user_id=self.user_id,
                    request_hash=request_hash,
                )
        except IntegrityError as exc:
            existing = repo.get(self.key, self.route, self.user_id)
            if existing is None:
                # Shouldn't happen — PK conflict but no row found. Surface as 409.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="מפתח אידמפוטנטיות בשימוש",
                ) from exc
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="מפתח אידמפוטנטיות כבר נוצל עם בקשה אחרת",
                ) from exc
            if existing.status == IdempotencyStatus.IN_PROGRESS:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="בקשה זהה כבר בעיבוד",
                ) from exc
            set_idempotency_context(self.key, replayed=True)
            return JSONResponse(
                content=existing.response_body,
                status_code=existing.response_status,
            )

        try:
            result = fn()
        except Exception:
            # Release the reservation so legitimate retries are not blocked,
            # but preserve outer-transaction state from before fn ran.
            try:
                repo.release(row)
            except Exception:
                self.db.rollback()
            raise

        body = jsonable_encoder(result)
        repo.complete(
            row,
            response_status=status.HTTP_200_OK,
            response_body=body,
        )
        return result


def require_idempotency_key(
    request: Request,
    user: AuthSubject = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_idempotency_key: str = Header(alias="X-Idempotency-Key"),
) -> IdempotencyGuard:
    set_idempotency_context(x_idempotency_key)
    return IdempotencyGuard(
        key=x_idempotency_key,
        route=request.url.path,
        user_id=user.id,
        db=db,
    )
