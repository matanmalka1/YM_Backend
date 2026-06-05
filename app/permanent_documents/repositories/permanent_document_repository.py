from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.permanent_documents.models.permanent_document import (
    DocumentScope,
    DocumentStatus,
    PermanentDocument,
)


class PermanentDocumentRepository(BaseRepository[PermanentDocument]):
    """Data access layer for PermanentDocument entities."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        client_record_id: int,
        business_id: int | None,
        scope: DocumentScope,
        document_type: str,
        storage_key: str,
        uploaded_by: int,
        tax_year: int | None = None,
        version: int = 1,
        status: DocumentStatus = DocumentStatus.PENDING,
        annual_report_id: int | None = None,
        original_filename: str | None = None,
        file_size_bytes: int | None = None,
        mime_type: str | None = None,
    ) -> PermanentDocument:
        document = PermanentDocument(
            client_record_id=client_record_id,
            business_id=business_id,
            scope=scope,
            document_type=document_type,
            storage_key=storage_key,
            uploaded_by=uploaded_by,
            tax_year=tax_year,
            is_present=True,
            version=version,
            status=status,
            annual_report_id=annual_report_id,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
        )
        self.db.add(document)
        self.db.flush()
        return document

    def get_by_id(self, document_id: int) -> PermanentDocument | None:
        return self.db.scalars(
            select(PermanentDocument).where(
                PermanentDocument.id == document_id,
                PermanentDocument.is_deleted == False,  # noqa: E712
            )
        ).first()

    def list_by_business(
        self,
        business_id: int,
        tax_year: int | None = None,
        document_type: str | None = None,
        status: DocumentStatus | None = None,
        include_superseded: bool = False,
    ) -> list[PermanentDocument]:
        stmt = select(PermanentDocument).where(
            PermanentDocument.business_id == business_id,
            PermanentDocument.is_deleted == False,  # noqa: E712
        )
        if not include_superseded:
            stmt = stmt.where(PermanentDocument.superseded_by == None)  # noqa: E711
        if tax_year is not None:
            stmt = stmt.where(PermanentDocument.tax_year == tax_year)
        if document_type is not None:
            stmt = stmt.where(PermanentDocument.document_type == document_type)
        if status is not None:
            stmt = stmt.where(PermanentDocument.status == status)
        return self.db.scalars(stmt.order_by(PermanentDocument.uploaded_at.desc())).all()

    def list_by_client(
        self,
        client_record_id: int,
        tax_year: int | None = None,
        document_type: str | None = None,
        status: DocumentStatus | None = None,
        include_superseded: bool = False,
    ) -> list[PermanentDocument]:
        stmt = select(PermanentDocument).where(
            PermanentDocument.client_record_id == client_record_id,
            PermanentDocument.is_deleted == False,  # noqa: E712
        )
        if not include_superseded:
            stmt = stmt.where(PermanentDocument.superseded_by == None)  # noqa: E711
        if tax_year is not None:
            stmt = stmt.where(PermanentDocument.tax_year == tax_year)
        if document_type is not None:
            stmt = stmt.where(PermanentDocument.document_type == document_type)
        if status is not None:
            stmt = stmt.where(PermanentDocument.status == status)
        return self.db.scalars(stmt.order_by(PermanentDocument.uploaded_at.desc())).all()

    def list_by_client_record(
        self,
        client_record_id: int,
        scope: DocumentScope | None = None,
        tax_year: int | None = None,
        document_type: str | None = None,
        status: DocumentStatus | None = None,
        include_superseded: bool = False,
    ) -> list[PermanentDocument]:
        stmt = select(PermanentDocument).where(
            PermanentDocument.client_record_id == client_record_id,
            PermanentDocument.is_deleted == False,  # noqa: E712
        )
        if scope is not None:
            stmt = stmt.where(PermanentDocument.scope == scope)
        if not include_superseded:
            stmt = stmt.where(PermanentDocument.superseded_by == None)  # noqa: E711
        if tax_year is not None:
            stmt = stmt.where(PermanentDocument.tax_year == tax_year)
        if document_type is not None:
            stmt = stmt.where(PermanentDocument.document_type == document_type)
        if status is not None:
            stmt = stmt.where(PermanentDocument.status == status)
        return self.db.scalars(stmt.order_by(PermanentDocument.uploaded_at.desc())).all()

    def count_by_client_record(self, client_record_id: int) -> int:
        return self.db.scalar(
            select(func.count(PermanentDocument.id)).where(
                PermanentDocument.client_record_id == client_record_id,
                PermanentDocument.is_deleted == False,  # noqa: E712
            )
        )

    def get_by_id_and_client_record(
        self, document_id: int, client_record_id: int
    ) -> PermanentDocument | None:
        return self.db.scalars(
            select(PermanentDocument).where(
                PermanentDocument.id == document_id,
                PermanentDocument.client_record_id == client_record_id,
                PermanentDocument.is_deleted.is_(False),
            )
        ).first()

    def count_by_business(self, business_id: int) -> int:
        return self.db.scalar(
            select(func.count(PermanentDocument.id)).where(
                PermanentDocument.business_id == business_id,
                PermanentDocument.is_deleted == False,  # noqa: E712
            )
        )

    def search_by_filename(self, filename: str, limit: int = 50) -> list[PermanentDocument]:
        term = f"%{filename.strip()}%"
        return self.db.scalars(
            select(PermanentDocument)
            .where(
                PermanentDocument.is_deleted == False,  # noqa: E712
                PermanentDocument.superseded_by == None,  # noqa: E711
                PermanentDocument.original_filename.ilike(term),
            )
            .order_by(PermanentDocument.uploaded_at.desc())
            .limit(limit)
        ).all()

    def search_by_query(self, query: str, limit: int = 50) -> list[PermanentDocument]:
        term = f"%{query.strip()}%"
        return self.db.scalars(
            select(PermanentDocument)
            .where(
                PermanentDocument.is_deleted == False,  # noqa: E712
                PermanentDocument.superseded_by == None,  # noqa: E711
                (
                    PermanentDocument.original_filename.ilike(term)
                    | cast(PermanentDocument.document_type, String).ilike(term)
                ),
            )
            .order_by(PermanentDocument.uploaded_at.desc())
            .limit(limit)
        ).all()
