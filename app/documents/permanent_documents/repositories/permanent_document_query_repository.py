from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.documents.permanent_documents.models.permanent_document import PermanentDocument


class PermanentDocumentQueryRepository(BaseRepository[PermanentDocument]):
    """Read-only query repository for advanced document lookups."""

    def __init__(self, db: Session):
        self.db = db

    def get_latest_version(
        self,
        client_record_id: int,
        document_type: str,
        tax_year: int | None = None,
        business_id: int | None = None,
    ) -> PermanentDocument | None:
        stmt = select(PermanentDocument).where(
            PermanentDocument.client_record_id == client_record_id,
            PermanentDocument.document_type == document_type,
            PermanentDocument.is_deleted == False,  # noqa: E712
            PermanentDocument.superseded_by == None,  # noqa: E711
        )
        if business_id is None:
            stmt = stmt.where(PermanentDocument.business_id == None)  # noqa: E711
        else:
            stmt = stmt.where(PermanentDocument.business_id == business_id)
        if tax_year is not None:
            stmt = stmt.where(PermanentDocument.tax_year == tax_year)
        return self.db.scalars(stmt.order_by(PermanentDocument.version.desc())).first()

    def get_all_versions(
        self, business_id: int, document_type: str, tax_year: int | None = None
    ) -> list[PermanentDocument]:
        stmt = select(PermanentDocument).where(
            PermanentDocument.business_id == business_id,
            PermanentDocument.document_type == document_type,
            PermanentDocument.is_deleted == False,  # noqa: E712
        )
        if tax_year is not None:
            stmt = stmt.where(PermanentDocument.tax_year == tax_year)
        return list(self.db.scalars(stmt.order_by(PermanentDocument.version.desc())).all())

    def get_all_versions_by_client(
        self, client_record_id: int, document_type: str, tax_year: int | None = None
    ) -> list[PermanentDocument]:
        stmt = select(PermanentDocument).where(
            PermanentDocument.client_record_id == client_record_id,
            PermanentDocument.document_type == document_type,
            PermanentDocument.is_deleted == False,  # noqa: E712
        )
        if tax_year is not None:
            stmt = stmt.where(PermanentDocument.tax_year == tax_year)
        return list(self.db.scalars(stmt.order_by(PermanentDocument.version.desc())).all())

    def get_all_versions_by_client_record(
        self,
        client_record_id: int,
        document_type: str,
        tax_year: int | None = None,
        limit: int = 10,
    ) -> tuple[list[PermanentDocument], bool]:
        """Return (versions, has_more) — fetches limit+1 to detect overflow."""
        stmt = select(PermanentDocument).where(
            PermanentDocument.client_record_id == client_record_id,
            PermanentDocument.document_type == document_type,
            PermanentDocument.is_deleted.is_(False),
        )
        if tax_year is not None:
            stmt = stmt.where(PermanentDocument.tax_year == tax_year)
        rows = list(
            self.db.scalars(
                stmt.order_by(PermanentDocument.version.desc()).limit(limit + 1)
            ).all()
        )
        has_more = len(rows) > limit
        return rows[:limit], has_more

    def list_by_annual_report(self, annual_report_id: int) -> list[PermanentDocument]:
        return list(
            self.db.scalars(
                select(PermanentDocument)
                .where(
                    PermanentDocument.annual_report_id == annual_report_id,
                    PermanentDocument.is_deleted == False,  # noqa: E712
                )
                .order_by(PermanentDocument.uploaded_at.desc())
            ).all()
        )

    def missing_by_type(
        self, business_id: int, client_record_id: int, required_types: list[str]
    ) -> list[str]:
        existing = self.db.execute(
            select(PermanentDocument.document_type)
            .where(
                (
                    (PermanentDocument.business_id == business_id)
                    | (PermanentDocument.client_record_id == client_record_id)
                ),
                PermanentDocument.is_deleted == False,  # noqa: E712
                PermanentDocument.superseded_by == None,  # noqa: E711
            )
            .distinct()
        ).all()
        existing_types = {row[0] for row in existing}
        return [t for t in required_types if t not in existing_types]

    def missing_by_client_type(self, client_record_id: int, required_types: list[str]) -> list[str]:
        existing = self.db.execute(
            select(PermanentDocument.document_type)
            .where(
                PermanentDocument.client_record_id == client_record_id,
                PermanentDocument.is_deleted == False,  # noqa: E712
                PermanentDocument.superseded_by == None,  # noqa: E711
            )
            .distinct()
        ).all()
        existing_types = {row[0] for row in existing}
        return [t for t in required_types if t not in existing_types]
