"""Explicit event-source registry for the client timeline (plan §4).

Every logical timeline category has exactly ONE source: either a dedicated
*live builder* (reads the live row and emits a rich, domain-specific event) or a
generic *EntityAuditLog action* (the change-log feed). This module is the single
readable source-of-truth for that mapping; it replaces the implicit
``_DEDUP_ACTIONS`` heuristic that ``timeline_audit_aggregator`` used to hand-keep.

The change-log feed (``build_entity_audit_events``) emits raw audit rows for the
client / business / charge / annual_report entities. Any action that a dedicated
builder already owns must NOT be re-emitted as a raw change-log row, or the same
fact would appear twice. ``AUDIT_AGGREGATOR_SUPPRESSED_ACTIONS`` is DERIVED from
this registry for exactly that purpose — it is not maintained by hand.

Binder and signature audit reach the timeline through their own dedicated
readers (``timeline_service._append_lifecycle_change_events`` and
``timeline_repository.list_signature_lifecycle_events``); the change-log feed
does not fetch those entity types, so they do not participate in the aggregator
suppression set. They are still listed here so the registry documents every
category's single source in one place.
"""

from app.audit.audit_constants import (
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_MARKED_FULL,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_BINDER_MATERIAL_RECEIVED,
    ACTION_BINDER_REOPENED,
    ACTION_BINDER_REVERTED_READY,
    ACTION_CHARGE_ISSUED,
    ACTION_CHARGE_PAID,
    ACTION_CREATED,
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
    ACTION_SIGNATURE_REQUEST_SENT,
    ACTION_SIGNATURE_REQUEST_SIGNED,
    ACTION_SIGNATURE_REQUEST_VIEWED,
    ACTION_STATUS_CHANGED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BINDER,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
    ENTITY_SIGNATURE_REQUEST,
    entity_action,
)

# How a category reaches the timeline.
#   LIVE_BUILDER       — a dedicated builder reads the live row and emits the event.
#   ENTITY_AUDIT       — the event comes from an EntityAuditLog action.
SOURCE_LIVE_BUILDER = "live_builder"
SOURCE_ENTITY_AUDIT = "entity_audit"


class TimelineEventSource:
    """One plan-§4 category and the single source that produces its events.

    ``audit_entity_type`` / ``audit_actions`` are populated only when the source
    is ``SOURCE_ENTITY_AUDIT``. ``owns_audit_actions`` lists the EntityAuditLog
    actions a *live builder* already represents on its own entity — these are the
    actions the change-log feed must suppress for that entity type.
    """

    __slots__ = (
        "category",
        "source",
        "audit_entity_type",
        "audit_actions",
        "owns_audit_actions",
    )

    def __init__(
        self,
        category: str,
        source: str,
        *,
        audit_entity_type: str | None = None,
        audit_actions: frozenset[str] = frozenset(),
        owns_audit_actions: frozenset[str] = frozenset(),
    ) -> None:
        self.category = category
        self.source = source
        self.audit_entity_type = audit_entity_type
        self.audit_actions = audit_actions
        self.owns_audit_actions = owns_audit_actions


# Single-source-per-category registry (plan §4 table, in code terms).
TIMELINE_EVENT_SOURCES: tuple[TimelineEventSource, ...] = (
    # client created — live builder (client_created_event). The change-log feed
    # must not re-emit client.created for the client entity.
    TimelineEventSource(
        "client_created",
        SOURCE_LIVE_BUILDER,
        owns_audit_actions=frozenset({entity_action(ENTITY_CLIENT, ACTION_CREATED)}),
    ),
    # business changed — EntityAuditLog business.* via the change-log feed.
    TimelineEventSource(
        "business_changed",
        SOURCE_ENTITY_AUDIT,
        audit_entity_type=ENTITY_BUSINESS,
    ),
    # charge created/issued/paid + invoice attached — live builders. The
    # change-log feed must not re-emit those charge actions for the charge entity.
    TimelineEventSource(
        "charge_lifecycle",
        SOURCE_LIVE_BUILDER,
        owns_audit_actions=frozenset(
            {
                entity_action(ENTITY_CHARGE, ACTION_CREATED),
                ACTION_CHARGE_ISSUED,
                ACTION_CHARGE_PAID,
            }
        ),
    ),
    # annual_report status changed — dedicated builder (annual_report_status_changed_event)
    # reads EntityAuditLog annual_report.status_changed via the timeline repo. The
    # change-log feed must not re-emit status_changed for the annual_report entity.
    TimelineEventSource(
        "annual_report_status_changed",
        SOURCE_ENTITY_AUDIT,
        audit_entity_type=ENTITY_ANNUAL_REPORT,
        audit_actions=frozenset({entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED)}),
        owns_audit_actions=frozenset({entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED)}),
    ),
    # binder received / handed_over — live builders (binder_received / binder_handed_over).
    TimelineEventSource(
        "binder_reception_handover",
        SOURCE_LIVE_BUILDER,
        owns_audit_actions=frozenset({ACTION_BINDER_MATERIAL_RECEIVED, ACTION_BINDER_HANDED_OVER}),
    ),
    # binder lifecycle (marked_full/reopened/ready/reverted) — EntityAuditLog binder.*
    # via the dedicated timeline reader (_append_lifecycle_change_events).
    TimelineEventSource(
        "binder_lifecycle",
        SOURCE_ENTITY_AUDIT,
        audit_entity_type=ENTITY_BINDER,
        audit_actions=frozenset(
            {
                ACTION_BINDER_MARKED_FULL,
                ACTION_BINDER_REOPENED,
                ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
                ACTION_BINDER_REVERTED_READY,
            }
        ),
    ),
    # signature lifecycle (sent/viewed/signed/declined/canceled/expired) —
    # EntityAuditLog signature_request.* via list_signature_lifecycle_events.
    TimelineEventSource(
        "signature_lifecycle",
        SOURCE_ENTITY_AUDIT,
        audit_entity_type=ENTITY_SIGNATURE_REQUEST,
        audit_actions=frozenset(
            {
                ACTION_SIGNATURE_REQUEST_SENT,
                ACTION_SIGNATURE_REQUEST_VIEWED,
                ACTION_SIGNATURE_REQUEST_SIGNED,
                ACTION_SIGNATURE_REQUEST_DECLINED,
                ACTION_SIGNATURE_REQUEST_CANCELED,
                ACTION_SIGNATURE_REQUEST_EXPIRED,
            }
        ),
    ),
    # document uploaded — live PermanentDocument builder (document_uploaded_event).
    TimelineEventSource("document_uploaded", SOURCE_LIVE_BUILDER),
    # notifications sent/failed — live Notification builders.
    TimelineEventSource("notifications", SOURCE_LIVE_BUILDER),
)


# Entity types whose full change log the aggregator surfaces as raw change-log rows.
AUDIT_AGGREGATOR_ENTITY_TYPES: frozenset[str] = frozenset(
    {ENTITY_CLIENT, ENTITY_BUSINESS, ENTITY_CHARGE, ENTITY_ANNUAL_REPORT}
)


def suppressed_actions_for(entity_type: str) -> frozenset[str]:
    """Audit actions the change-log feed must NOT re-emit for ``entity_type``.

    Derived from the registry: an action is suppressed iff a dedicated builder
    already owns it (``owns_audit_actions``) on an entity the aggregator scopes.
    Replaces the hand-kept ``_DEDUP_ACTIONS`` dict — behaviour is identical, only
    the source of the suppression set changes.
    """
    suppressed: set[str] = set()
    for source in TIMELINE_EVENT_SOURCES:
        for action in source.owns_audit_actions:
            # ``client.created`` → entity_type ``client``; suppress on that entity.
            owning_entity = action.split(".", 1)[0]
            if owning_entity == entity_type:
                suppressed.add(action)
    return frozenset(suppressed)
