from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random

from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    DocumentStatus,
    PermanentDocumentType,
    PermanentDocument,
)

from ...data.realistic_seed_text import DOCUMENT_TYPE_DETAILS
from ..shared.client_refs import attach_seed_client_context, get_seed_client_record_id


def _doc_timestamps(rng: Random, now: datetime):
    uploaded_at = now - timedelta(days=rng.randint(0, 500))
    status = rng.choices(
        [
            DocumentStatus.PENDING,
            DocumentStatus.RECEIVED,
            DocumentStatus.APPROVED,
            DocumentStatus.REJECTED,
        ],
        weights=[10, 20, 60, 10],
        k=1,
    )[0]
    is_present = rng.random() > 0.05
    if not is_present and status in (DocumentStatus.APPROVED, DocumentStatus.RECEIVED):
        status = DocumentStatus.PENDING
    age_days = (now - uploaded_at).days
    if age_days > 90 and status == DocumentStatus.PENDING:
        status = rng.choices(
            [DocumentStatus.APPROVED, DocumentStatus.REJECTED],
            weights=[80, 20],
            k=1,
        )[0]
        is_present = True
    approved_at = rejected_at = None
    if status == DocumentStatus.APPROVED and is_present and rng.random() < 0.7:
        approved_at = min(now, uploaded_at + timedelta(days=rng.randint(1, 30)))
    if status == DocumentStatus.REJECTED:
        rejected_at = min(now, uploaded_at + timedelta(days=rng.randint(1, 10)))
    return status, is_present, uploaded_at, approved_at, rejected_at


def create_documents(db, rng: Random, clients, businesses, users):
    documents = []
    now = datetime.now(UTC)
    businesses_by_client: dict[int, list] = {}
    for business in businesses:
        businesses_by_client.setdefault(get_seed_client_record_id(business), []).append(
            business
        )

    for client in clients:
        doc_types = [PermanentDocumentType.ID_COPY, PermanentDocumentType.POWER_OF_ATTORNEY]
        if rng.random() < 0.8:
            doc_types.append(PermanentDocumentType.ENGAGEMENT_AGREEMENT)
        if rng.random() < 0.55:
            doc_types.append(PermanentDocumentType.BANK_APPROVAL)

        for doc_type in doc_types:
            doc_label, filename = DOCUMENT_TYPE_DETAILS[doc_type]
            status, is_present, uploaded_at, approved_at, rejected_at = _doc_timestamps(
                rng, now
            )
            approved_by = (
                rng.choice(users).id
                if status == DocumentStatus.APPROVED and approved_at
                else None
            )
            rejected_by = (
                rng.choice(users).id if status == DocumentStatus.REJECTED else None
            )
            doc = PermanentDocument(
                client_record_id=client.id,
                business_id=None,
                scope=DocumentScope.CLIENT,
                document_type=doc_type,
                storage_key=f"clients/{client.id}/{doc_type.value}_{rng.randint(1000, 9999)}.pdf",
                original_filename=filename,
                file_size_bytes=rng.randint(50000, 500000),
                mime_type="application/pdf",
                tax_year=None,
                status=status,
                is_present=is_present,
                uploaded_by=rng.choice(users).id,
                uploaded_at=uploaded_at,
                approved_by=approved_by,
                approved_at=approved_at,
                rejected_by=rejected_by,
                rejected_at=rejected_at,
            )
            attach_seed_client_context(doc, client)
            db.add(doc)
            documents.append(doc)

        client_businesses = businesses_by_client.get(client.id, [])
        for business in rng.sample(
            client_businesses, k=min(max(0, 4 - len(doc_types)), len(client_businesses))
        ):
            status, is_present, uploaded_at, approved_at, rejected_at = _doc_timestamps(
                rng, now
            )
            approved_by = (
                rng.choice(users).id
                if status == DocumentStatus.APPROVED and approved_at
                else None
            )
            rejected_by = (
                rng.choice(users).id if status == DocumentStatus.REJECTED else None
            )
            doc_type = rng.choice(
                [
                    PermanentDocumentType.INVOICE_DOC,
                    PermanentDocumentType.RECEIPT,
                    PermanentDocumentType.TAX_FORM,
                    PermanentDocumentType.WITHHOLDING_CERTIFICATE,
                    PermanentDocumentType.NII_APPROVAL,
                ]
            )
            doc_label, filename = DOCUMENT_TYPE_DETAILS[doc_type]
            doc = PermanentDocument(
                client_record_id=client.id,
                business_id=business.id,
                scope=DocumentScope.BUSINESS,
                document_type=doc_type,
                storage_key=f"clients/{client.id}/businesses/{business.id}/doc_{rng.randint(1000, 9999)}.pdf",
                original_filename=f"{business.business_name}_{filename}",
                file_size_bytes=rng.randint(50000, 500000),
                mime_type="application/pdf",
                tax_year=rng.choice([uploaded_at.year, uploaded_at.year - 1, None]),
                status=status,
                is_present=is_present,
                uploaded_by=rng.choice(users).id,
                uploaded_at=uploaded_at,
                approved_by=approved_by,
                approved_at=approved_at,
                rejected_by=rejected_by,
                rejected_at=rejected_at,
            )
            attach_seed_client_context(doc, client)
            db.add(doc)
            documents.append(doc)

    db.flush()
    return documents
