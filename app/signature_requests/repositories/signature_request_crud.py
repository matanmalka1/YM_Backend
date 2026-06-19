import datetime
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clients.repositories.client_active_scope import scope_to_active_clients_stmt
from app.common.repositories.base_repository import BaseRepository
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.utils.time_utils import start_of_day, start_of_next_day, utcnow


class SignatureRequestCrudMixin:
    db: Session

    def create_pending(
        self,
        client_record_id: int,
        created_by: int,
        request_type: SignatureRequestType,
        title: str,
        signer_name: str,
        signing_token: str,
        sent_at: datetime.datetime,
        expires_at: datetime.datetime,
        expiry_days: int,
        business_id: int | None = None,  # OPTIONAL context
        description: str | None = None,
        signer_email: str | None = None,
        signer_phone: str | None = None,
        annual_report_id: int | None = None,
        document_id: int | None = None,
        storage_key: str | None = None,
        content_hash: str | None = None,
    ) -> SignatureRequest:
        if not signing_token or sent_at is None or expires_at is None:
            raise ValueError(
                "pending signature requests require signing_token, sent_at, and expires_at"
            )
        req = SignatureRequest(
            client_record_id=client_record_id,
            business_id=business_id,
            created_by=created_by,
            request_type=request_type,
            title=title,
            description=description,
            signer_name=signer_name,
            signer_email=signer_email,
            signer_phone=signer_phone,
            annual_report_id=annual_report_id,
            document_id=document_id,
            storage_key=storage_key,
            content_hash=content_hash,
            status=SignatureRequestStatus.PENDING_SIGNATURE,
            signing_token=signing_token,
            sent_at=sent_at,
            expires_at=expires_at,
            expiry_days=expiry_days,
        )
        self.db.add(req)
        self.db.flush()
        return req

    def get_by_id(self, request_id: int) -> SignatureRequest | None:
        stmt = select(SignatureRequest).where(
            SignatureRequest.id == request_id,
            SignatureRequest.deleted_at.is_(None),
        )
        return self.db.scalars(stmt).first()

    def get_by_token(self, token: str) -> SignatureRequest | None:
        stmt = select(SignatureRequest).where(
            SignatureRequest.signing_token == token,
            SignatureRequest.deleted_at.is_(None),
        )
        return self.db.scalars(stmt).first()

    def get_pending_by_client_and_id_for_update(
        self, client_record_id: int, request_id: int
    ) -> SignatureRequest | None:
        """Fetch a client-scoped pending request with a row-level lock."""
        stmt = (
            select(SignatureRequest)
            .where(
                SignatureRequest.id == request_id,
                SignatureRequest.client_record_id == client_record_id,
                SignatureRequest.status == SignatureRequestStatus.PENDING_SIGNATURE,
                SignatureRequest.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return self.db.scalars(stmt).first()

    def get_by_token_for_update(self, token: str) -> SignatureRequest | None:
        """Fetch by signing token with a row-level lock for signer actions."""
        stmt = (
            select(SignatureRequest)
            .where(
                SignatureRequest.signing_token == token,
                SignatureRequest.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return self.db.scalars(stmt).first()

    # ── List by client (primary) ──────────────────────────────────────────────

    def list_by_client_record(
        self,
        client_record_id: int,
        status: SignatureRequestStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SignatureRequest]:
        """All requests for a legal entity, regardless of business."""
        stmt = scope_to_active_clients_stmt(select(SignatureRequest), SignatureRequest).where(
            SignatureRequest.client_record_id == client_record_id,
            SignatureRequest.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(SignatureRequest.status == status)
        stmt = BaseRepository.apply_pagination(
            stmt.order_by(SignatureRequest.created_at.desc()), page, page_size
        )
        return self.db.scalars(stmt).all()

    def count_by_client_record(
        self,
        client_record_id: int,
        status: SignatureRequestStatus | None = None,
    ) -> int:
        stmt = scope_to_active_clients_stmt(
            select(func.count(SignatureRequest.id)), SignatureRequest
        ).where(
            SignatureRequest.client_record_id == client_record_id,
            SignatureRequest.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(SignatureRequest.status == status)
        return self.db.scalar(stmt)

    # ── List by business (scoped view) ────────────────────────────────────────

    def list_by_business(
        self,
        business_id: int,
        status: SignatureRequestStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SignatureRequest]:
        stmt = select(SignatureRequest).where(
            SignatureRequest.business_id == business_id,
            SignatureRequest.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(SignatureRequest.status == status)
        stmt = BaseRepository.apply_pagination(
            stmt.order_by(SignatureRequest.created_at.desc()), page, page_size
        )
        return self.db.scalars(stmt).all()

    def count_by_business(
        self,
        business_id: int,
        status: SignatureRequestStatus | None = None,
    ) -> int:
        stmt = select(func.count(SignatureRequest.id)).where(
            SignatureRequest.business_id == business_id,
            SignatureRequest.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(SignatureRequest.status == status)
        return self.db.scalar(stmt)

    # ── Pending (global advisor view) ─────────────────────────────────────────

    @staticmethod
    def _pending_filters(
        *,
        client_record_id: int | None = None,
        request_type: SignatureRequestType | None = None,
        signer_email: str | None = None,
        created_after: date | None = None,
        created_before: date | None = None,
        expires_before: date | None = None,
    ) -> list:
        """Filter set shared by ``list_pending`` and ``count_pending``.

        Always pins the query to the pending, not-deleted subset; optional
        operational filters narrow it further.
        """
        filters = [
            SignatureRequest.status == SignatureRequestStatus.PENDING_SIGNATURE,
            SignatureRequest.deleted_at.is_(None),
        ]
        if client_record_id is not None:
            filters.append(SignatureRequest.client_record_id == client_record_id)
        if request_type is not None:
            filters.append(SignatureRequest.request_type == request_type)
        if signer_email:
            filters.append(SignatureRequest.signer_email.ilike(f"%{signer_email.strip()}%"))
        if created_after is not None:
            filters.append(SignatureRequest.created_at >= start_of_day(created_after))
        if created_before is not None:
            filters.append(SignatureRequest.created_at < start_of_next_day(created_before))
        if expires_before is not None:
            filters.append(SignatureRequest.expires_at < start_of_next_day(expires_before))
        return filters

    def list_pending(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        client_record_id: int | None = None,
        request_type: SignatureRequestType | None = None,
        signer_email: str | None = None,
        created_after: date | None = None,
        created_before: date | None = None,
        expires_before: date | None = None,
    ) -> list[SignatureRequest]:
        filters = self._pending_filters(
            client_record_id=client_record_id,
            request_type=request_type,
            signer_email=signer_email,
            created_after=created_after,
            created_before=created_before,
            expires_before=expires_before,
        )
        stmt = (
            select(SignatureRequest)
            .where(*filters)
            .order_by(
                SignatureRequest.sent_at.asc().nulls_last(),
                SignatureRequest.id.asc(),
            )
        )
        stmt = BaseRepository.apply_pagination(stmt, page, page_size)
        return self.db.scalars(stmt).all()

    def count_pending(
        self,
        *,
        client_record_id: int | None = None,
        request_type: SignatureRequestType | None = None,
        signer_email: str | None = None,
        created_after: date | None = None,
        created_before: date | None = None,
        expires_before: date | None = None,
    ) -> int:
        filters = self._pending_filters(
            client_record_id=client_record_id,
            request_type=request_type,
            signer_email=signer_email,
            created_after=created_after,
            created_before=created_before,
            expires_before=expires_before,
        )
        stmt = select(func.count(SignatureRequest.id)).where(*filters)
        return self.db.scalar(stmt)

    def update(
        self,
        request_id: int,
        req: SignatureRequest | None = None,
        **fields,
    ) -> SignatureRequest | None:
        """Update fields on a signature request.

        Pass a pre-fetched (optionally locked) ``req`` entity to avoid a second
        SELECT and keep the lock from a scoped transition lookup alive.
        """
        entity = req or self.get_by_id(request_id)
        if entity is None:
            return None
        for key, value in fields.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        self.db.flush()
        return entity

    def list_pending_by_annual_report(self, annual_report_id: int) -> list[SignatureRequest]:
        """Return all PENDING_SIGNATURE requests linked to the given annual report."""
        stmt = select(SignatureRequest).where(
            SignatureRequest.annual_report_id == annual_report_id,
            SignatureRequest.status == SignatureRequestStatus.PENDING_SIGNATURE,
            SignatureRequest.deleted_at.is_(None),
        )
        return self.db.scalars(stmt).all()

    def list_expired_pending(self) -> list[SignatureRequest]:
        """Find PENDING_SIGNATURE requests whose expires_at has passed."""
        now = utcnow()
        stmt = select(SignatureRequest).where(
            SignatureRequest.status == SignatureRequestStatus.PENDING_SIGNATURE,
            SignatureRequest.expires_at < now,
            SignatureRequest.expires_at.isnot(None),
            SignatureRequest.deleted_at.is_(None),
        )
        return self.db.scalars(stmt).all()
