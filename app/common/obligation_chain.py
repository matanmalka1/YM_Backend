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

from sqlalchemy import ForeignKey, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column

from app.common.enums import ObligationStatus
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.utils.time_utils import utcnow

AMEND_REQUIRES_CLOSED_MESSAGE = "רק רשומה סגורה ניתנת לתיקון"
ALREADY_AMENDED_MESSAGE = "לרשומה זו כבר קיים תיקון"


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
    """
    return (
        select_obligations(model, include_superseded=True)
        .where(model.client_record_id == client_record_id, period_column == period_value)
        .order_by(model.id.asc())
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
