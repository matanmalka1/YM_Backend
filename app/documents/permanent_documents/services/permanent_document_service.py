import io
import mimetypes
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_DOCUMENT_DELETED,
    ACTION_DOCUMENT_REPLACED,
    ACTION_DOCUMENT_UPDATED,
    ACTION_DOCUMENT_UPLOADED,
    ENTITY_DOCUMENT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.binders.binder_messages import BINDER_NOT_FOUND
from app.binders.repositories.binder_repository import BinderRepository
from app.businesses.business_guards import (
    assert_business_belongs_to_legal_entity,
    get_business_or_raise,
)
from app.businesses.services.business_signals_service import SignalsService
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.services.client_service import get_client_or_raise
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.documents.permanent_documents.models.permanent_document import (
    CLIENT_SCOPE_TYPES,
    DocumentScope,
    DocumentStatus,
    PermanentDocument,
    PermanentDocumentType,
)
from app.documents.permanent_documents.permanent_document_constants import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
)
from app.documents.permanent_documents.permanent_document_messages import (
    BUSINESS_NOT_FOUND_ERROR,
    CLIENT_SCOPE_VIOLATION_ERROR,
    DOCUMENT_NOT_FOUND_ERROR,
    FILE_TOO_LARGE_ERROR,
    INVALID_FILE_TYPE_ERROR,
    UPLOAD_FAILED_ERROR,
    VERSION_CONFLICT_ERROR,
)
from app.documents.permanent_documents.repositories.permanent_document_query_repository import (
    PermanentDocumentQueryRepository,
)
from app.documents.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)
from app.infrastructure.storage import StorageProvider, get_storage_provider
from app.utils.time_utils import utcnow

_DEFAULT_REQUIRED_TYPES = [
    PermanentDocumentType.ID_COPY.value,
    PermanentDocumentType.POWER_OF_ATTORNEY.value,
    PermanentDocumentType.ENGAGEMENT_AGREEMENT.value,
]

_UPDATABLE_METADATA_FIELDS = {"document_type", "original_filename", "tax_year"}
_SYSTEM_ACTOR_DISPLAY = "מערכת"


class PermanentDocumentService:
    """Permanent document management service."""

    def __init__(self, db: Session, storage: StorageProvider | None = None):
        self.db = db
        self.document_repo = PermanentDocumentRepository(db)
        self.query_repo = PermanentDocumentQueryRepository(db)
        self.storage = storage or get_storage_provider()
        self.client_repo = ClientRecordRepository(db)
        self._audit = EntityAuditWriter(db)

    def _actor_kwargs(self, actor_id: int | None, actor_display_name: str | None) -> dict:
        if actor_id is None:
            return {
                "actor_type": "system",
                "actor_display_name": actor_display_name or _SYSTEM_ACTOR_DISPLAY,
            }
        return {"actor_display_name": actor_display_name}

    def _audit_metadata(self, doc: PermanentDocument) -> dict:
        meta = {
            "client_record_id": doc.client_record_id,
            "document_type": doc.document_type,
            "tax_year": doc.tax_year,
            "version": doc.version,
            "mime_type": doc.mime_type,
            "file_size_bytes": doc.file_size_bytes,
        }
        if doc.business_id is not None:
            meta["business_id"] = doc.business_id
        if doc.annual_report_id is not None:
            meta["annual_report_id"] = doc.annual_report_id
        return meta

    def _audit_snapshot(self, doc: PermanentDocument) -> dict:
        return {
            "document_type": doc.document_type,
            "original_filename": doc.original_filename,
            "tax_year": doc.tax_year,
            "status": doc.status,
            "version": doc.version,
            "file_size_bytes": doc.file_size_bytes,
            "mime_type": doc.mime_type,
            "is_deleted": doc.is_deleted,
        }

    def _resolve_mime(self, mime_type: str | None, filename: str) -> str:
        resolved = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if resolved not in ALLOWED_MIME_TYPES:
            raise AppError(
                INVALID_FILE_TYPE_ERROR,
                ErrorCode.DOCUMENT_INVALID_FILE_TYPE,
                status_code=422,
            )
        return resolved

    def _build_storage_key(
        self,
        *,
        client_record_id: int,
        document_type: str,
        tax_year: int | None,
        version: int,
        filename: str,
        business_id: int | None = None,
    ) -> str:
        tax_year_str = str(tax_year) if tax_year else "permanent"
        owner_segment = (
            f"businesses/{business_id}"
            if business_id is not None
            else f"clients/{client_record_id}"
        )
        return f"{owner_segment}/{document_type}/{tax_year_str}/v{version}_{filename}"

    def upload_document(
        self,
        client_record_id: int,
        document_type: str,
        file_data: BinaryIO,
        filename: str,
        uploaded_by: int,
        business_id: int | None = None,
        tax_year: int | None = None,
        annual_report_id: int | None = None,
        mime_type: str | None = None,
        legal_entity_id: int | None = None,
        actor_display_name: str | None = None,
    ) -> PermanentDocument:
        get_client_or_raise(self.db, client_record_id)
        client_record = self.client_repo.get_by_id(client_record_id)
        if not client_record:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה", ErrorCode.CLIENT_RECORD_NOT_FOUND
            )
        if business_id is not None:
            try:
                business = get_business_or_raise(self.db, business_id)
            except NotFoundError as exc:
                raise NotFoundError(
                    BUSINESS_NOT_FOUND_ERROR, ErrorCode.PERMANENT_DOCUMENTS_BUSINESS_NOT_FOUND
                ) from exc
            assert_business_belongs_to_legal_entity(
                business,
                legal_entity_id if legal_entity_id is not None else client_record.legal_entity_id,
            )

        scope = DocumentScope.BUSINESS if business_id is not None else DocumentScope.CLIENT
        doc_type_enum = PermanentDocumentType(document_type)
        if doc_type_enum in CLIENT_SCOPE_TYPES and business_id is not None:
            raise AppError(
                CLIENT_SCOPE_VIOLATION_ERROR,
                ErrorCode.PERMANENT_DOCUMENTS_CLIENT_SCOPE_VIOLATION,
                status_code=422,
            )

        file_bytes = file_data.read()
        file_size = len(file_bytes)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise AppError(
                FILE_TOO_LARGE_ERROR.format(max_size_mb=MAX_FILE_SIZE_BYTES // (1024 * 1024)),
                ErrorCode.DOCUMENT_FILE_TOO_LARGE,
                status_code=422,
            )
        resolved_mime = self._resolve_mime(mime_type, filename)

        existing = self.query_repo.get_latest_version(
            client_record_id=client_record_id,
            business_id=business_id,
            document_type=document_type,
            tax_year=tax_year,
        )
        next_version = (existing.version + 1) if existing else 1
        storage_key = self._build_storage_key(
            client_record_id=client_record_id,
            business_id=business_id,
            document_type=document_type,
            tax_year=tax_year,
            version=next_version,
            filename=filename,
        )

        # Flush DB record first; upload to storage only if flush succeeds.
        # Single commit at the end keeps record + superseded_by atomic.
        document = self.document_repo.create(
            client_record_id=client_record.id,
            business_id=business_id,
            scope=scope,
            document_type=document_type,
            storage_key=storage_key,
            uploaded_by=uploaded_by,
            tax_year=tax_year,
            version=next_version,
            status=DocumentStatus.APPROVED,
            annual_report_id=annual_report_id,
            original_filename=filename,
            file_size_bytes=file_size,
            mime_type=resolved_mime,
        )
        document.approved_by = uploaded_by
        document.approved_at = utcnow()
        try:
            self.storage.upload(storage_key, io.BytesIO(file_bytes), resolved_mime)
        except Exception as exc:
            self.db.rollback()
            raise AppError(
                UPLOAD_FAILED_ERROR, ErrorCode.DOCUMENT_UPLOAD_FAILED, status_code=500
            ) from exc

        if existing:
            existing.superseded_by = document.id
        self._audit.record_action(
            ENTITY_DOCUMENT,
            document.id,
            uploaded_by,
            ACTION_DOCUMENT_UPLOADED,
            new_value=self._audit_snapshot(document),
            actor_display_name=actor_display_name,
            metadata_json=self._audit_metadata(document),
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                VERSION_CONFLICT_ERROR,
                ErrorCode.DOCUMENT_VERSION_CONFLICT,
                status_code=409,
            ) from exc
        self.db.refresh(document)
        return document

    def get_document(self, client_record_id: int, document_id: int) -> PermanentDocument:
        doc = self.document_repo.get_by_id_and_client_record(document_id, client_record_id)
        if not doc:
            raise NotFoundError(DOCUMENT_NOT_FOUND_ERROR, ErrorCode.PERMANENT_DOCUMENTS_NOT_FOUND)
        return doc

    def update_document_metadata(
        self,
        client_record_id: int,
        document_id: int,
        actor_id: int | None = None,
        actor_display_name: str | None = None,
        **fields,
    ) -> PermanentDocument:
        doc = self.document_repo.get_by_id_and_client_record(document_id, client_record_id)
        if not doc:
            raise NotFoundError(DOCUMENT_NOT_FOUND_ERROR, ErrorCode.PERMANENT_DOCUMENTS_NOT_FOUND)
        old_snapshot = self._audit_snapshot(doc)
        for key, value in fields.items():
            if key not in _UPDATABLE_METADATA_FIELDS:
                raise ValueError(f"Unsupported document metadata field: {key}")
            setattr(doc, key, value)
        self.db.flush()
        self._audit.record_action(
            ENTITY_DOCUMENT,
            doc.id,
            actor_id,
            ACTION_DOCUMENT_UPDATED,
            old_value=old_snapshot,
            new_value=self._audit_snapshot(doc),
            metadata_json=self._audit_metadata(doc),
            **self._actor_kwargs(actor_id, actor_display_name),
        )
        return doc

    def list_binder_documents(
        self,
        binder_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PermanentDocument], int]:
        if not BinderRepository(self.db).get_by_id(binder_id):
            raise NotFoundError(
                BINDER_NOT_FOUND.format(binder_id=binder_id), ErrorCode.BINDER_NOT_FOUND
            )
        return self.document_repo.list_by_binder_page(binder_id, page=page, page_size=page_size)

    def get_download_url(
        self, client_record_id: int, document_id: int, expires_in: int = 3600
    ) -> str:
        doc = self.document_repo.get_by_id_and_client_record(document_id, client_record_id)
        if not doc:
            raise NotFoundError(DOCUMENT_NOT_FOUND_ERROR, ErrorCode.PERMANENT_DOCUMENTS_NOT_FOUND)
        return self.storage.get_presigned_url(doc.storage_key, expires_in=expires_in)

    def list_business_documents(
        self,
        business_id: int,
        tax_year: int | None = None,
        document_type: str | None = None,
        status: DocumentStatus | None = None,
    ) -> list[PermanentDocument]:
        return self.document_repo.list_by_business(
            business_id,
            tax_year=tax_year,
            document_type=document_type,
            status=status,
        )

    def list_client_documents(
        self,
        client_record_id: int,
        page: int = 1,
        page_size: int = 20,
        tax_year: int | None = None,
        document_type: PermanentDocumentType | None = None,
        status: DocumentStatus | None = None,
    ) -> tuple[list[PermanentDocument], int]:
        get_client_or_raise(self.db, client_record_id)
        return self.document_repo.list_by_client_record_page(
            client_record_id,
            page=page,
            page_size=page_size,
            tax_year=tax_year,
            document_type=document_type.value if document_type is not None else None,
            status=status,
        )

    def get_missing_document_types(
        self, business_id: int, required: list[str] | None = None
    ) -> list[str]:
        business = get_business_or_raise(self.db, business_id)
        client_record = self.client_repo.get_by_legal_entity_id(business.legal_entity_id)
        if not client_record:
            raise NotFoundError(
                f"רשומת לקוח לעסק {business_id} לא נמצאה",
                ErrorCode.PERMANENT_DOCUMENTS_CLIENT_RECORD_NOT_FOUND,
            )
        required_types = required if required is not None else _DEFAULT_REQUIRED_TYPES
        return self.query_repo.missing_by_type(business_id, client_record.id, required_types)

    def get_operational_signals(self, business_id: int) -> dict:
        return SignalsService(self.db).compute_business_operational_signals(business_id)

    def get_client_operational_signals(self, client_record_id: int) -> dict:
        get_client_or_raise(self.db, client_record_id)
        return {
            "client_record_id": client_record_id,
            "missing_documents": self.query_repo.missing_by_client_type(
                client_record_id, _DEFAULT_REQUIRED_TYPES
            ),
        }

    def delete_document(
        self,
        client_record_id: int,
        document_id: int,
        *,
        actor_id: int,
        actor_display_name: str | None = None,
    ) -> None:
        doc = self.document_repo.get_by_id_and_client_record(document_id, client_record_id)
        if not doc:
            raise NotFoundError(DOCUMENT_NOT_FOUND_ERROR, ErrorCode.PERMANENT_DOCUMENTS_NOT_FOUND)
        old_snapshot = self._audit_snapshot(doc)
        doc.is_deleted = True
        self.db.flush()
        self._audit.record_action(
            ENTITY_DOCUMENT,
            doc.id,
            actor_id,
            ACTION_DOCUMENT_DELETED,
            old_value=old_snapshot,
            actor_display_name=actor_display_name,
            metadata_json=self._audit_metadata(doc),
        )

    def replace_document(
        self,
        client_record_id: int,
        document_id: int,
        file_data: BinaryIO,
        filename: str,
        uploaded_by: int,
        mime_type: str | None = None,
        actor_display_name: str | None = None,
    ) -> PermanentDocument:
        doc = self.document_repo.get_by_id_and_client_record(document_id, client_record_id)
        if not doc:
            raise NotFoundError(DOCUMENT_NOT_FOUND_ERROR, ErrorCode.PERMANENT_DOCUMENTS_NOT_FOUND)
        old_snapshot = self._audit_snapshot(doc)

        file_bytes = file_data.read()
        file_size = len(file_bytes)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise AppError(
                FILE_TOO_LARGE_ERROR.format(max_size_mb=MAX_FILE_SIZE_BYTES // (1024 * 1024)),
                ErrorCode.DOCUMENT_FILE_TOO_LARGE,
                status_code=422,
            )
        resolved_mime = self._resolve_mime(mime_type, filename)

        next_version = doc.version + 1
        storage_key = self._build_storage_key(
            client_record_id=doc.client_record_id,
            business_id=doc.business_id,
            document_type=doc.document_type,
            tax_year=doc.tax_year,
            version=next_version,
            filename=filename,
        )
        self.storage.upload(storage_key, io.BytesIO(file_bytes), resolved_mime)
        doc.storage_key = storage_key
        doc.mime_type = resolved_mime
        doc.file_size_bytes = file_size
        doc.original_filename = filename
        doc.uploaded_at = utcnow()
        doc.uploaded_by = uploaded_by
        doc.is_present = True
        doc.version = next_version
        self._audit.record_action(
            ENTITY_DOCUMENT,
            doc.id,
            uploaded_by,
            ACTION_DOCUMENT_REPLACED,
            old_value=old_snapshot,
            new_value=self._audit_snapshot(doc),
            actor_display_name=actor_display_name,
            metadata_json=self._audit_metadata(doc),
        )
        # explicit commit: storage upload already succeeded above
        self.db.commit()
        return doc
