import pytest

from app.core import background_jobs


class _FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_run_startup_expiry_commits_expired_requests(monkeypatch):
    session = _FakeSession()

    monkeypatch.setattr(background_jobs, "SessionLocal", lambda: session)
    monkeypatch.setattr(background_jobs, "SignatureRequestRepository", lambda db: db)
    monkeypatch.setattr(background_jobs, "expire_overdue_requests", lambda repo: 3)

    background_jobs.run_startup_expiry()

    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


def test_run_startup_expiry_rolls_back_on_failure(monkeypatch):
    session = _FakeSession()

    def fail(_repo):
        raise RuntimeError("expiry failed")

    monkeypatch.setattr(background_jobs, "SessionLocal", lambda: session)
    monkeypatch.setattr(background_jobs, "SignatureRequestRepository", lambda db: db)
    monkeypatch.setattr(background_jobs, "expire_overdue_requests", fail)

    with pytest.raises(RuntimeError, match="expiry failed"):
        background_jobs.run_startup_expiry()

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True
