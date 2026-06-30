"""Phase 7 — one source per timeline category, proven (plan §4).

Two layers of proof:

1. The explicit event-source registry (``timeline_event_sources``) derives the
   change-log suppression set. Asserting that derived set equals the documented
   per-entity set locks the registry as the single source-of-truth that replaced
   the hand-kept ``_DEDUP_ACTIONS`` dict.
2. A client exercising every overlap-prone category produces NO two events that
   share ``(event_type, entity-id, timestamp)`` identity, and the two highest-risk
   facts are single-sourced: ``binder.handed_over`` comes only from the live
   builder (never a lifecycle-change row) and ``annual_report.status_changed``
   comes only from the dedicated builder (never the raw change-log feed).
"""

from datetime import date

from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.audit.audit_constants import (
    ACTION_STATUS_CHANGED,
    ACTION_UPDATED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
    ENTITY_SIGNATURE_REQUEST,
    entity_action,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.timeline.services.timeline_service import TimelineService
from app.timeline.timeline_event_sources import (
    AUDIT_AGGREGATOR_ENTITY_TYPES,
    SOURCE_ENTITY_AUDIT,
    SOURCE_LIVE_BUILDER,
    TIMELINE_EVENT_SOURCES,
    suppressed_actions_for,
)
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import create_tax_calendar_entry_for_annual

# --- Layer 1: registry derives the same suppression set the old dict hard-coded ---

# The literal set the retired ``_DEDUP_ACTIONS`` dict enforced, per aggregator entity.
_LEGACY_DEDUP = {
    ENTITY_CLIENT: {entity_action(ENTITY_CLIENT, "created")},
    ENTITY_BUSINESS: set(),
    ENTITY_CHARGE: {
        entity_action(ENTITY_CHARGE, "created"),
        entity_action(ENTITY_CHARGE, "issued"),
        entity_action(ENTITY_CHARGE, "paid"),
    },
    ENTITY_ANNUAL_REPORT: {entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED)},
}


def test_registry_suppression_matches_legacy_dedup_set():
    for entity_type, expected in _LEGACY_DEDUP.items():
        assert suppressed_actions_for(entity_type) == frozenset(expected), entity_type


def test_registry_each_category_has_exactly_one_source():
    categories = [s.category for s in TIMELINE_EVENT_SOURCES]
    assert len(categories) == len(set(categories)), "duplicate category in registry"
    for source in TIMELINE_EVENT_SOURCES:
        assert source.source in (SOURCE_LIVE_BUILDER, SOURCE_ENTITY_AUDIT)
        if source.source == SOURCE_ENTITY_AUDIT:
            assert source.audit_entity_type is not None
        else:
            # A live builder never declares its own audit-action source.
            assert not source.audit_actions


def test_aggregator_never_suppresses_outside_its_scope():
    # binder / signature reach the timeline via their own readers, not the
    # change-log feed, so they contribute nothing to the aggregator suppression.
    for entity_type in (ENTITY_BUSINESS,):
        assert suppressed_actions_for(entity_type) == frozenset()
    assert "binder" not in AUDIT_AGGREGATOR_ENTITY_TYPES
    assert ENTITY_SIGNATURE_REQUEST not in AUDIT_AGGREGATOR_ENTITY_TYPES


# --- Layer 2: a real client timeline has no duplicate events ---


def _full_binder_lifecycle(db, client_id: int, user_id: int) -> int:
    binder = BinderRepository(db).create(
        client_record_id=client_id,
        binder_number="SS-1",
        period_start=date(2026, 1, 1),
        created_by=user_id,
    )
    lifecycle = BinderLifecycleService(db)
    lifecycle.receive_material_by_id(binder.id, changed_by_user_id=user_id)
    lifecycle.mark_full(binder.id, changed_by_user_id=user_id)
    lifecycle.reopen_capacity(binder.id, changed_by_user_id=user_id)
    lifecycle.mark_full(binder.id, changed_by_user_id=user_id)
    lifecycle.mark_ready_for_handover(binder.id, changed_by_user_id=user_id)
    lifecycle.revert_ready_for_handover(binder.id, changed_by_user_id=user_id)
    lifecycle.mark_ready_for_handover(binder.id, changed_by_user_id=user_id)
    lifecycle.handover_to_client(binder.id, changed_by_user_id=user_id)
    db.flush()
    return binder.id


def _annual_report(db, client_id: int) -> AnnualReport:
    entry = create_tax_calendar_entry_for_annual(db, 2026)
    report = AnnualReport(
        client_record_id=client_id,
        tax_year=2026,
        client_type=ClientAnnualFilingType.INDIVIDUAL,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        status=AnnualReportStatus.IN_PREPARATION,
        deadline_type=FilingDeadlineType.STANDARD,
        tax_calendar_entry_id=entry.id,
    )
    db.add(report)
    db.flush()
    return report


def test_full_client_timeline_has_no_duplicate_events(test_db, test_user):
    client = seed_client_identity(test_db, full_name="Single Source", id_number="SS-100")
    writer = EntityAuditWriter(test_db)

    _full_binder_lifecycle(test_db, client.id, test_user.id)

    report = _annual_report(test_db, client.id)
    # Dedicated builder source (annual_report_status_changed) — must NOT also appear
    # as a raw change-log row.
    _ar_meta = {"client_record_id": client.id, "tax_year": 2026}
    writer.record_action(
        ENTITY_ANNUAL_REPORT,
        report.id,
        test_user.id,
        entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED),
        old_value={"status": "in_preparation"},
        new_value={"status": "submitted"},
        metadata_json=_ar_meta,
    )
    # A non-suppressed annual_report change — SHOULD surface via the change-log feed.
    writer.record_action(
        ENTITY_ANNUAL_REPORT,
        report.id,
        test_user.id,
        entity_action(ENTITY_ANNUAL_REPORT, ACTION_UPDATED),
        new_value={"internal_notes": "edited"},
        metadata_json=_ar_meta,
    )
    test_db.flush()

    events, _total = TimelineService(test_db).get_client_timeline(client.id, page_size=200)

    # No two events share (event_type, entity-id, timestamp) identity.
    identities = [
        (e["event_type"], e.get("charge_id"), e.get("binder_id"), e["timestamp"]) for e in events
    ]
    assert len(identities) == len(set(identities)), "duplicate timeline event identity"

    event_types = [e["event_type"] for e in events]

    # binder.handed_over is the live builder's territory only — exactly one
    # handover event, and it is the live builder shape (binder_handed_over),
    # never a binder_lifecycle_change row.
    assert event_types.count("binder_handed_over") == 1
    handover_lifecycle = [
        e
        for e in events
        if e["event_type"] == "binder_lifecycle_change"
        and e["metadata"].get("new_value") == "handed_over"
    ]
    assert handover_lifecycle == []

    # annual_report.status_changed is the dedicated builder's territory only.
    assert event_types.count("annual_report_status_changed") == 1
    # The raw change-log feed surfaced the non-suppressed annual_report.updated...
    ar_changed = [
        e
        for e in events
        if e["event_type"] == "annual_report_changed"
        and e["metadata"].get("change_action")
        == entity_action(ENTITY_ANNUAL_REPORT, ACTION_UPDATED)
    ]
    assert len(ar_changed) == 1
    # ...but never re-emitted status_changed as a raw change-log row.
    ar_status_as_changelog = [
        e
        for e in events
        if e["event_type"] == "annual_report_changed"
        and e["metadata"].get("change_action")
        == entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED)
    ]
    assert ar_status_as_changelog == []

    # Binder lifecycle (marked_full/reopened/ready/reverted) appears; reception &
    # handover come from live builders. (Signature lifecycle is single-sourced
    # through its own reader — proven in test_timeline_signature_lifecycle.py — and
    # never reaches the change-log feed, asserted above at the registry level.)
    assert "binder_lifecycle_change" in event_types
    assert "binder_received" in event_types
