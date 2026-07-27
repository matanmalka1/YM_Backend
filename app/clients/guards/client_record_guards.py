"""The single client-eligibility rule every domain blocks on.

One rule, one implementation. Before this was consolidated, VAT, advance payments,
and annual reports each decided "may I act on this client?" separately, raising
three different exception types with three different error codes for the same
underlying condition — so no caller could detect "client not eligible" generically.

The block is a fact about the resource's state, not about the caller's permissions,
so it is a 409 (``ConflictError``), not a 403. The error code is uniform; only the
message distinguishes closed from frozen, because a frozen client can be thawed and
a closed one generally cannot, and the advisor needs to know which they are facing.

The SQL twin of this rule is
``app.clients.repositories.client_active_scope.eligible_client_status_expr``. The two
forms must change together: a client this guard rejects must be a client that
predicate excludes.
"""

from app.clients.client_enums import ClientStatus
from app.clients.client_messages import (
    CLIENT_RECORD_CLOSED_ACTION,
    CLIENT_RECORD_FROZEN_ACTION,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import ConflictError

_BLOCKED_STATUS_MESSAGES = {
    ClientStatus.CLOSED: CLIENT_RECORD_CLOSED_ACTION,
    ClientStatus.FROZEN: CLIENT_RECORD_FROZEN_ACTION,
}


def assert_client_record_is_active(client_record) -> None:
    """Raise when the client record may not be acted on.

    Allowlist, not blocklist, per ``docs/agent/decision-making.md``: anything that
    is not ACTIVE is blocked, so a status added later fails closed instead of
    becoming silently eligible. Only the *message* is looked up per status.

    A missing record is not this guard's concern — callers that need it to exist
    raise their own domain's NOT_FOUND first.
    """
    if client_record is None:
        return
    status = getattr(client_record, "status", None)
    if status == ClientStatus.ACTIVE:
        return
    raise ConflictError(
        _BLOCKED_STATUS_MESSAGES.get(status, CLIENT_RECORD_CLOSED_ACTION),
        ErrorCode.CLIENT_RECORD_CLOSED,
    )
