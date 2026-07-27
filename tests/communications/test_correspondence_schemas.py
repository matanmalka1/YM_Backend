from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.communications.models.correspondence import CorrespondenceType
from app.communications.schemas.correspondence import (
    CorrespondenceCreateRequest,
    CorrespondenceListResponse,
    CorrespondenceResponse,
    CorrespondenceUpdateRequest,
)


def test_create_schema_rejects_future_occurred_at():
    with pytest.raises(ValidationError):
        CorrespondenceCreateRequest(
            correspondence_type=CorrespondenceType.CALL,
            subject="future",
            occurred_at=datetime.now(UTC) + timedelta(minutes=1),
        )


def test_update_schema_rejects_explicit_null_occurred_at():
    # occurred_at is a required, non-nullable field; explicit null is invalid.
    with pytest.raises(ValidationError):
        CorrespondenceUpdateRequest(occurred_at=None)


def test_update_schema_omitting_occurred_at_is_partial():
    req = CorrespondenceUpdateRequest(subject="updated")
    assert "occurred_at" not in req.model_fields_set
    assert req.model_dump(exclude_unset=True) == {"subject": "updated"}


def test_update_schema_rejects_future_occurred_at():
    with pytest.raises(ValidationError):
        CorrespondenceUpdateRequest(
            occurred_at=datetime.now(UTC) + timedelta(minutes=1),
        )


def test_list_response_build_uses_standard_envelope_without_total_pages(actor_user):
    item = CorrespondenceResponse(
        id=1,
        client_record_id=1,
        business_id=1,
        contact_id=None,
        correspondence_type=CorrespondenceType.EMAIL,
        subject="s",
        notes=None,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_by=actor_user.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    resp = CorrespondenceListResponse.build(items=[item], page=1, page_size=20, total=41)
    assert resp.page == 1
    assert resp.page_size == 20
    assert resp.total == 41
    # #42: total_pages removed — derived client-side, not part of the contract.
    assert not hasattr(resp, "total_pages")
    assert "total_pages" not in resp.model_dump()
