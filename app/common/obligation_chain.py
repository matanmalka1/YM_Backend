"""Amendment chains, shared by all three tax domains (D-10, D-12, D-21).

A closed obligation is never reopened. Correcting one creates a **second row**
for the same period, linked to the row it corrects (§4.1.6). The original stays
closed forever, so what the office originally filed remains readable.

That makes a period more than one row, and every list, count and sum in the
system then has to answer the same question: *which row do I mean?* D-12
answers it once — **a chain is one row everywhere**: the latest record, marked
as amended. Earlier records are reachable only by asking for them explicitly.

Two facts carry this, and they are deliberately not the same fact:

``amends_id``
    Points backwards, at the row this one corrects. It is the chain itself, and
    it is what the uniqueness rule excludes (§4.1.13) — an amendment does not
    occupy the period's slot.

``superseded_at``
    Stamped **on the row being corrected**, at the moment its amendment is born.
    It points forwards, and it is the only thing every read filters on. Without
    it, "am I the latest?" is a correlated subquery repeated at forty call
    sites; with it, it is one indexable predicate that reads the same
    everywhere.

There is no ``is_amendment`` column. It would be exactly ``amends_id IS NOT
NULL`` — one truth stored twice, which is the duplication W0 spent a wave
deleting. Read :attr:`AmendableMixin.is_amendment` instead; it derives.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, case, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column

from app.common.enums import ObligationStatus
from app.common.obligation_lifecycle import LOCKED_MESSAGE
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.utils.time_utils import utcnow

AMEND_REQUIRES_CLOSED_MESSAGE = "רק רשומה סגורה ניתנת לתיקון"
ALREADY_AMENDED_MESSAGE = "לרשומה זו כבר קיים תיקון"
AMENDMENT_NOT_DELETABLE_MESSAGE = "רשומת תיקון אינה נמחקת — יש לבטל אותה"
NOT_AN_AMENDMENT_MESSAGE = "רק רשומת תיקון ניתנת לביטול"


@declarative_mixin
class AmendableMixin:
    """The two chain columns, identical in all three obligation tables."""

    @declared_attr
    def amends_id(cls) -> Mapped[int | None]:
        return mapped_column(
            ForeignKey(f"{cls.__tablename__}.id", ondelete="RESTRICT"),
            nullable=True,
        )

    @declared_attr
    def superseded_at(cls) -> Mapped[datetime | None]:
        return mapped_column(nullable=True)

    @declared_attr
    def chain_closed_late(cls) -> Mapped[bool | None]:
        """Was the *period* closed late — the whole chain's answer (D-34).

        Distinct from ``closed_late``, which answers "was **this row's** closing
        act late". An amendment has no due date (D-14), so its own answer is
        always NULL; but the period it corrects may well have been filed late,
        and D-20 exists to preserve exactly that. Without this column, amending
        a period **hides that it was late** — the plan raises it as EC-2.

        Carried forward once, at birth, so no read has to walk the chain.
        """
        return mapped_column(nullable=True)

    @property
    def is_amendment(self) -> bool:
        return self.amends_id is not None

    @property
    def is_withdrawn(self) -> bool:
        """Was this correction taken back (:func:`withdraw_amendment`).

        Derived for the same reason ``is_amendment`` is: the state is already
        stored, as a link that exists and a soft-delete that also exists. It is
        exposed because the chain view is the one read that shows withdrawn links,
        and it needs to mark them as such — every other read filters them out and
        never sees this at all.
        """
        return self.is_amendment and self.deleted_at is not None

    @classmethod
    def chain_tip_clause(cls):
        """The one predicate every list, count and sum applies (D-12).

        Consumed two ways: through :func:`scope_to_chain_tip_stmt` for an
        ordinary ``WHERE``, and directly inside a ``case()`` or a filtered
        aggregate, where there is no ``WHERE`` to hang it on. Both must exist —
        the aggregate form is exactly the call site that gets forgotten.
        """
        return cls.superseded_at.is_(None)


def scope_to_chain_tip_stmt(stmt, model):
    """Restrict a statement to the latest record of every amendment chain."""
    return stmt.where(model.chain_tip_clause())


def select_obligations(
    model, *entities, include_deleted: bool = False, include_superseded: bool = False
):
    """Build a ``SELECT`` over an obligation table with both scopes applied.

    **The only place ``select()`` may name one of the three obligation models.**
    An ``arch`` test enforces that, because the failure this prevents is silent:
    a query that forgets the chain-tip predicate returns an amended period twice
    and every sum built on it is wrong by the amount of the correction. Nothing
    raises, and no test fails on the number being wrong — so correctness has to
    come from there being one way to write the query, not from remembering.

    Pass column expressions to project instead of loading whole rows:
    ``select_obligations(VatWorkItem, VatWorkItem.period, func.count())``.

    Both escapes are explicit and both are narrow. ``include_deleted`` is the
    existing soft-delete escape. ``include_superseded`` is for the one legitimate
    case: showing a chain's own history, where every link is the point.
    """
    stmt = select(*(entities or (model,)))
    if not include_deleted:
        stmt = stmt.where(model.deleted_at.is_(None))
    if not include_superseded:
        stmt = scope_to_chain_tip_stmt(stmt, model)
    return stmt


def select_chain(model, *, client_record_id: int, period_column, period_value):
    """Every link of one period's chain, oldest first.

    Fetched by period rather than by walking ``amends_id``: the uniqueness rule
    already guarantees a period holds at most one original, and a chain cannot
    fork, so the rows for a client and period *are* the chain. One query instead
    of one per link.

    ``include_superseded`` is the whole point here — this is the one read that
    wants the corrected records, not the correction.

    ``include_deleted`` is on for one row only: a **withdrawn** amendment
    (:func:`withdraw_amendment`). A correction that was opened and taken back is
    part of what happened to the period, and this is the only read that shows
    what happened rather than what counts. Rows deleted for any other reason are
    filtered back out — a row soft-deleted before any correction existed was
    never a link in this chain, and showing it here would turn the history view
    into a recycle bin.
    """
    return (
        select_obligations(model, include_superseded=True, include_deleted=True)
        .where(
            model.client_record_id == client_record_id,
            period_column == period_value,
            or_(model.deleted_at.is_(None), model.amends_id.is_not(None)),
        )
        .order_by(model.id.asc())
    )


def select_slot_occupant(model, *, client_record_id: int, period_column, period_value):
    """The row holding a period's slot, by the unique index's own predicate.

    **The only query a creation gate may ask.** "Does this period already exist?"
    and "which row does this period show?" read like the same question and are
    not: the first is answered by the partial unique index in §4.1.13, the second
    by the chain-tip scope in :func:`select_obligations`. Asking the second in
    place of the first is wrong in both directions, and each direction fails
    differently:

    - A **cancelled** row is hidden from the index and visible to the chain-tip
      scope. Using the tip query rejects the creation with a 409 for a slot the
      database would have accepted — which is D-23 exactly: the returning client
      whose period can never be reopened.
    - A **superseded** original is visible to the index and hidden from the
      chain-tip scope. Using the tip query lets the creation through to an
      ``IntegrityError``, surfacing as a 500 rather than a conflict.

    So the predicate here is the index's, restated in SQLAlchemy and nothing
    else: not deleted, not an amendment, not cancelled. It is deliberately *not*
    built on the chain-tip scope — ``include_superseded=True`` is what lets a
    superseded original be seen holding its slot, which is the point.

    At most one row can match, because the index says so; callers may take the
    first without ordering.
    """
    return select_obligations(model, include_superseded=True).where(
        model.client_record_id == client_record_id,
        period_column == period_value,
        model.amends_id.is_(None),
        model.status != ObligationStatus.CANCELED,
    )


def select_current_obligation(model, *, client_record_id: int, period_column, period_value):
    """The period's one operational row: what it shows and what work acts on.

    The counterpart to :func:`select_slot_occupant`, and the reason both exist.
    Once D-23 lets a cancelled period be created fresh, a period legitimately
    holds more than one visible row — every cancelled attempt, plus the live one
    — and a bare ``.first()`` over the chain-tip scope picks between them by
    whatever order the plan happened to produce. That is not a theoretical
    ordering nit: with a sequential scan the cancelled row is returned, so the
    same lookup answers differently depending on the query plan.

    Ordered rather than filtered. Cancelled rows stay reachable here because a
    period whose only row is cancelled must still display as cancelled; they are
    merely never preferred over a live one. Ties among them break on ``id``
    descending, so the most recent attempt wins and the answer is stable.
    """
    return (
        select_obligations(model)
        .where(
            model.client_record_id == client_record_id,
            period_column == period_value,
        )
        .order_by(
            case((model.status == ObligationStatus.CANCELED, 1), else_=0),
            model.id.desc(),
        )
    )


def assert_amendable(original) -> None:
    """Raise unless ``original`` may be corrected by a new record right now.

    Two conditions, and neither is domain-specific:

    - **It must be closed.** An open obligation is corrected by editing it; the
      amendment mechanism exists only because a closed one cannot be touched.
    - **It must not already have an amendment.** A chain is a line, not a tree —
      two corrections of the same record would give the period two "latest"
      rows and put every aggregate back where D-12 found it.

    Ownership is *not* checked here: the caller already resolved the record
    through its own client scope, and re-deriving that here would fork the
    scoping rule. Cycle detection is not checked either, and cannot be needed —
    ``amends_id`` is written once, at birth, pointing at a row that already
    exists, so the chain only ever grows forward.
    """
    if original.status != ObligationStatus.SUBMITTED:
        raise AppError(AMEND_REQUIRES_CLOSED_MESSAGE, ErrorCode.OBLIGATION_NOT_CLOSED)
    if original.superseded_at is not None:
        # 409, not 400: the request is well formed and the caller is permitted —
        # the record simply already has the one amendment a chain may hold.
        raise AppError(
            ALREADY_AMENDED_MESSAGE,
            ErrorCode.OBLIGATION_ALREADY_AMENDED,
            status_code=409,
        )


def assert_deletable(record) -> None:
    """Raise if ``record`` is a link in a chain rather than a standalone record.

    Deleting an amendment is not the local act it looks like. The stamp that made
    it the tip lives on the *other* row, so soft-deleting the amendment alone
    performs half of :func:`link_amendment` in reverse: the original keeps its
    ``superseded_at`` and its claim on the period, and the period ends up with no
    visible row at all — the original hidden as superseded, the amendment hidden
    as deleted — while the unique index still counts the original as occupying
    the slot. Every list, sum and count then reports the period as absent, and it
    can be neither corrected again (``ALREADY_AMENDED``) nor recreated (unique
    violation).

    Taking a correction back is :func:`withdraw_amendment`, which performs both
    halves. This gate exists so the plain ``DELETE`` route cannot perform one.
    """
    if record.is_amendment:
        # 409 for the same reason as ALREADY_AMENDED: the request is well formed
        # and the caller is permitted; the record's place in a chain forbids it.
        raise AppError(
            AMENDMENT_NOT_DELETABLE_MESSAGE,
            ErrorCode.OBLIGATION_AMENDMENT_NOT_DELETABLE,
            status_code=409,
        )


def assert_withdrawable(amendment) -> None:
    """Raise unless ``amendment`` may be taken back right now.

    Three conditions, none domain-specific:

    - **It must be an amendment.** Withdrawing is defined as undoing a link; a
      standalone record has none, and deleting one is a different act entirely.
    - **It must not be closed.** Once a correction has been filed it is the
      record of a filing, and D-13 puts it beyond change like any other closed
      obligation. A wrong correction that was filed is corrected by amending
      *it* — the chain grows, it does not shrink.
    - **It must be the tip.** On ``original ← A ← B``, taking back ``A`` would
      revive the original while ``B`` still points at ``A``: two rows with no
      ``superseded_at`` for one period, which is the double count D-12 exists to
      prevent. Withdrawing walks a chain back from its end, one link at a time.

    ``CANCELED`` is deliberately **not** refused, and the condition above is
    "closed", not "open": cancelling is terminal but it is not a filing, so there
    is no filed record to protect. It also has to be allowed, because a cancelled
    correction is otherwise a dead end — it keeps ``superseded_at IS NULL`` for
    ever, so it stays its period's tip while the record it corrected stays hidden
    as superseded, and the period can be neither corrected again nor recreated.
    Withdrawing is the only way out of that state, and refusing it here would
    leave the office with a period it cannot touch.
    """
    if not amendment.is_amendment:
        raise AppError(NOT_AN_AMENDMENT_MESSAGE, ErrorCode.OBLIGATION_NOT_AN_AMENDMENT)
    if amendment.status == ObligationStatus.SUBMITTED:
        raise AppError(LOCKED_MESSAGE, ErrorCode.OBLIGATION_LOCKED)
    if amendment.superseded_at is not None:
        raise AppError(
            ALREADY_AMENDED_MESSAGE,
            ErrorCode.OBLIGATION_ALREADY_AMENDED,
            status_code=409,
        )


def withdraw_amendment(amendment, original, *, actor_id: int) -> None:
    """Take back an open correction: the exact inverse of :func:`link_amendment`.

    Both writes belong to one act for the same reason the two writes at birth do
    — a row carrying only one of them is either invisible to every read or
    counted twice by all of them. Here that means the original returns to being
    its period's one visible row in the same statement that removes the
    correction.

    The amendment is **soft-deleted** rather than moved to ``CANCELED``, and that
    is the whole reason this needs no migration: ``deleted_at IS NULL`` is already
    carried by the chain-tip reads *and* by the unique index on ``amends_id``, so
    one write both stops the withdrawn row counting as a tip and frees the
    original to be corrected again. A ``CANCELED`` amendment would keep
    ``superseded_at IS NULL`` for ever — a permanent second tip for the period —
    and would keep the ``amends_id`` slot, which its index does not exclude by
    status.

    ``chain_closed_late`` is deliberately not touched: it was copied *onto* the
    amendment and the original's own answer never changed, so the period's
    lateness (D-34) survives the round trip untouched.
    """
    amendment.deleted_at = utcnow()
    amendment.deleted_by = actor_id
    original.superseded_at = None


def record_closing_lateness(record, closed_late: bool | None) -> None:
    """Write both lateness facts at a close (D-20, D-34).

    ``closed_late`` is this row's own act. ``chain_closed_late`` is the period's,
    and on a record that corrects nothing they are the same answer — so it is
    written here rather than left NULL, or every display site would have to
    coalesce the two and the one that forgot would report a late period as
    on time. An amendment overwrites it from its original in
    :func:`link_amendment`.
    """
    record.closed_late = closed_late
    record.chain_closed_late = closed_late


def link_amendment(amendment, original) -> None:
    """Join a newborn amendment to the record it corrects.

    Both writes belong to one act and must not be separable: the link points
    backwards and the stamp points forwards, and a row carrying only one of them
    is either invisible to every read or counted twice by all of them.
    """
    amendment.amends_id = original.id
    original.superseded_at = utcnow()
    # The period's lateness is a fixed historical fact and survives every
    # correction (D-34). Read the original's chain answer first: on a chain
    # three links long, the second link already carries the first's.
    amendment.chain_closed_late = (
        original.chain_closed_late
        if original.chain_closed_late is not None
        else original.closed_late
    )


#: Columns an amendment never inherits, whatever the domain.
#:
#: Identity, the chain columns and the soft-delete state are mechanical. The two
#: that carry a decision:
#:
#: - **The closing facts.** An amendment is born open (D-21), so it has not been
#:   closed, by anyone, at any time. Copying ``closed_at``/``closed_by`` would
#:   assert that a person closed a record they have not yet worked on.
#: - **The due dates.** An amendment has no deadline of its own (D-14) — a
#:   correction is not a new obligation. It keeps the original's
#:   ``tax_calendar_entry_id``, because the regulatory period is shared; only
#:   the per-record snapshot is absent.
NEVER_COPIED_INTO_AMENDMENT: frozenset[str] = frozenset(
    {
        "id",
        "created_at",
        "created_by",
        "updated_at",
        "amends_id",
        "superseded_at",
        "deleted_at",
        "deleted_by",
        "restored_at",
        "restored_by",
        "status",
        "closed_at",
        "closed_by",
        "closed_late",
        "chain_closed_late",
        "due_date",
        "due_date_original",
        "due_date_effective",
    }
)


#: Columns a copied child row never inherits: its own identity and its own
#: timestamps. Its parent key is always overridden, so it is excluded by
#: :func:`copy_child` rather than listed here.
CHILD_NEVER_COPIED: frozenset[str] = frozenset({"id", "created_at", "updated_at"})


def copy_child(source, *, parent_fk: str, parent_id: int, overrides: dict | None = None):
    """A child row of the original, re-parented onto the amendment.

    An amendment is a full copy — every invoice, line and figure (D-21) — so the
    children come across with it. Same mapper-driven reasoning as
    :func:`copy_for_amendment`: the risk is a column added later that a
    hand-written list silently drops.

    ``overrides`` is for the few fields the copy must not inherit, typically
    ``created_by``: the copy was made by whoever pressed "amend", not by whoever
    entered the original line.
    """
    overrides = overrides or {}
    excluded = CHILD_NEVER_COPIED | {parent_fk} | set(overrides)
    mapper = sa_inspect(type(source)).mapper
    values = {
        attr.key: getattr(source, attr.key)
        for attr in mapper.column_attrs
        if attr.key not in excluded
    }
    return type(source)(**values, **{parent_fk: parent_id}, **overrides)


def copy_for_amendment(original, *, also_exclude: frozenset[str] = frozenset()) -> dict:
    """The original's columns, as keyword arguments for its amendment.

    Driven by the mapper rather than a hand-written field list: an amendment is
    "the same record with different figures" (D-21), so a column added later
    should be carried by default. A hand-written list silently drops it, and
    what it drops is a figure nobody notices is missing.

    ``also_exclude`` is for the per-domain closing facts — the submission
    method, the authority reference, an override and its justification — which
    are as much closing facts as ``closed_at`` but are named differently in each
    domain.
    """
    excluded = NEVER_COPIED_INTO_AMENDMENT | also_exclude
    mapper = sa_inspect(type(original)).mapper
    return {
        attr.key: getattr(original, attr.key)
        for attr in mapper.column_attrs
        if attr.key not in excluded
    }
