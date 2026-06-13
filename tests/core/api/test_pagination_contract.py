import pytest

from app.core.pagination import MAX_PAGE_SIZE


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/clients",
        "/api/v1/annual-reports",
        "/api/v1/clients/1/annual-reports",
        "/api/v1/notifications",
    ],
)
def test_page_size_above_global_max_returns_422(client, advisor_headers, path):
    response = client.get(
        f"{path}?page_size={MAX_PAGE_SIZE + 1}",
        headers=advisor_headers,
    )

    assert response.status_code == 422


def test_notification_page_size_at_global_max_is_accepted(client, advisor_headers):
    response = client.get(
        f"/api/v1/notifications?page_size={MAX_PAGE_SIZE}",
        headers=advisor_headers,
    )

    assert response.status_code != 422
