import pytest

from app.core.exceptions import NotFoundError
from app.timeline.services.timeline_service import TimelineService


def test_get_client_timeline_raises_for_missing_client(test_db):
    service = TimelineService(test_db)

    with pytest.raises(NotFoundError) as exc:
        service.get_client_timeline(client_record_id=99999)

    assert exc.value.code == "TIMELINE.CLIENT_NOT_FOUND"
