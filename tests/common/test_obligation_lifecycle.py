"""The shared transition graph, which all three tax domains now run.

Each rule here replaced something: VAT and annual reports had their own
``VALID_TRANSITIONS`` tables (neither of which contained a cancel edge at all), and
advance payments had no graph — their status was derived from money.
"""

import pytest

from app.common.enums import ObligationStatus
from app.common.obligation_lifecycle import (
    ORDERED_STAGES,
    allowed_transitions,
    assert_transition_allowed,
    is_backward,
    is_locked,
    is_terminal,
    next_stage,
    previous_stage,
    stage_index,
    stages_between,
)
from app.core.exceptions import AppError

S = ObligationStatus
UNLOCKED = (S.AWAITING_INPUT, S.INPUT_RECEIVED, S.IN_PROGRESS, S.AWAITING_VERIFICATION)


class TestLadder:
    def test_the_ladder_is_five_stages_and_excludes_canceled(self):
        assert ORDERED_STAGES == (
            S.AWAITING_INPUT,
            S.INPUT_RECEIVED,
            S.IN_PROGRESS,
            S.AWAITING_VERIFICATION,
            S.SUBMITTED,
        )
        assert S.CANCELED not in ORDERED_STAGES

    def test_canceled_has_no_stage_index(self):
        """It is off-ladder, not stage zero — asking is a caller bug."""
        with pytest.raises(ValueError):
            stage_index(S.CANCELED)

    def test_ends_of_the_ladder(self):
        assert previous_stage(S.AWAITING_INPUT) is None
        assert next_stage(S.SUBMITTED) is None
        assert next_stage(S.CANCELED) is None
        assert previous_stage(S.CANCELED) is None


class TestForward:
    @pytest.mark.parametrize(
        ("current", "target"),
        list(zip(ORDERED_STAGES, ORDERED_STAGES[1:], strict=False)),
    )
    def test_one_stage_forward_is_allowed(self, current, target):
        assert_transition_allowed(current, target)

    def test_skipping_a_stage_is_rejected(self):
        with pytest.raises(AppError) as exc:
            assert_transition_allowed(S.AWAITING_INPUT, S.IN_PROGRESS)
        assert exc.value.code == "OBLIGATION.INVALID_TRANSITION"

    def test_jumping_straight_to_submitted_is_rejected(self):
        with pytest.raises(AppError):
            assert_transition_allowed(S.AWAITING_INPUT, S.SUBMITTED)

    def test_a_no_op_transition_is_rejected(self):
        with pytest.raises(AppError):
            assert_transition_allowed(S.IN_PROGRESS, S.IN_PROGRESS)


class TestBackward:
    @pytest.mark.parametrize(
        ("current", "target"),
        list(zip(ORDERED_STAGES[1:], ORDERED_STAGES, strict=False))[:3],
    )
    def test_one_stage_back_with_a_reason_is_allowed(self, current, target):
        assert_transition_allowed(current, target, reason="חסרים מסמכים")

    def test_backward_without_a_reason_is_rejected(self):
        with pytest.raises(AppError) as exc:
            assert_transition_allowed(S.IN_PROGRESS, S.INPUT_RECEIVED)
        assert exc.value.code == "OBLIGATION.TRANSITION_REASON_REQUIRED"

    def test_a_blank_reason_does_not_count(self):
        with pytest.raises(AppError) as exc:
            assert_transition_allowed(S.IN_PROGRESS, S.INPUT_RECEIVED, reason="   ")
        assert exc.value.code == "OBLIGATION.TRANSITION_REASON_REQUIRED"

    def test_multi_stage_jump_back_is_rejected_even_with_a_reason(self):
        """The reason does not buy a skipped stage — history stays readable."""
        with pytest.raises(AppError) as exc:
            assert_transition_allowed(S.AWAITING_VERIFICATION, S.AWAITING_INPUT, reason="למה")
        assert exc.value.code == "OBLIGATION.INVALID_TRANSITION"

    def test_forward_does_not_require_a_reason(self):
        assert_transition_allowed(S.INPUT_RECEIVED, S.IN_PROGRESS)

    def test_is_backward_classifies_direction(self):
        assert is_backward(S.IN_PROGRESS, S.INPUT_RECEIVED)
        assert not is_backward(S.INPUT_RECEIVED, S.IN_PROGRESS)
        assert not is_backward(S.IN_PROGRESS, S.CANCELED)


class TestCancel:
    @pytest.mark.parametrize("current", UNLOCKED)
    def test_cancel_from_any_unlocked_stage(self, current):
        assert_transition_allowed(current, S.CANCELED)

    def test_cancel_needs_no_reason_from_the_graph(self):
        """Cancelling is not a backward move; the advisor-only guard is elsewhere."""
        assert_transition_allowed(S.AWAITING_INPUT, S.CANCELED)

    def test_a_submitted_obligation_cannot_be_cancelled(self):
        with pytest.raises(AppError) as exc:
            assert_transition_allowed(S.SUBMITTED, S.CANCELED)
        assert exc.value.code == "OBLIGATION.LOCKED"


class TestTerminal:
    def test_submitted_is_locked_and_terminal(self):
        assert is_locked(S.SUBMITTED)
        assert is_terminal(S.SUBMITTED)
        assert allowed_transitions(S.SUBMITTED) == frozenset()

    def test_canceled_is_terminal_but_not_locked(self):
        """Different facts: locked means "submitted, amend it"; cancelled means
        "this stopped being ours". Only the first is a filing record."""
        assert is_terminal(S.CANCELED)
        assert not is_locked(S.CANCELED)
        assert allowed_transitions(S.CANCELED) == frozenset()

    @pytest.mark.parametrize("target", list(ObligationStatus))
    def test_nothing_leaves_submitted(self, target):
        if target == S.SUBMITTED:
            return
        with pytest.raises(AppError):
            assert_transition_allowed(S.SUBMITTED, target, reason="למה")

    @pytest.mark.parametrize("current", UNLOCKED)
    def test_unlocked_stages_are_not_terminal(self, current):
        assert not is_terminal(current)
        assert not is_locked(current)


class TestAllowedTransitions:
    def test_a_middle_stage_can_go_forward_back_or_cancel(self):
        assert allowed_transitions(S.IN_PROGRESS) == frozenset(
            {S.INPUT_RECEIVED, S.AWAITING_VERIFICATION, S.CANCELED}
        )

    def test_the_first_stage_has_no_backward(self):
        assert allowed_transitions(S.AWAITING_INPUT) == frozenset({S.INPUT_RECEIVED, S.CANCELED})

    def test_every_allowed_transition_actually_passes_the_assertion(self):
        for current in ObligationStatus:
            for target in allowed_transitions(current):
                assert_transition_allowed(current, target, reason="סיבה")


class TestStagesBetween:
    def test_one_event_may_perform_consecutive_transitions(self):
        """Recording a payment on an advance still awaiting turnover moves it
        1 -> 2 -> 3. Two real transitions, both recorded — not a skipped stage."""
        assert stages_between(S.AWAITING_INPUT, S.IN_PROGRESS) == (
            S.INPUT_RECEIVED,
            S.IN_PROGRESS,
        )

    def test_a_single_step_returns_one_stage(self):
        assert stages_between(S.INPUT_RECEIVED, S.IN_PROGRESS) == (S.IN_PROGRESS,)

    def test_no_steps_when_already_there_or_beyond(self):
        assert stages_between(S.IN_PROGRESS, S.IN_PROGRESS) == ()
        assert stages_between(S.AWAITING_VERIFICATION, S.INPUT_RECEIVED) == ()

    def test_no_steps_out_of_a_terminal_status(self):
        assert stages_between(S.SUBMITTED, S.SUBMITTED) == ()
        assert stages_between(S.CANCELED, S.IN_PROGRESS) == ()

    def test_every_returned_stage_is_a_legal_single_step(self):
        current = S.AWAITING_INPUT
        for stage in stages_between(S.AWAITING_INPUT, S.SUBMITTED):
            assert_transition_allowed(current, stage)
            current = stage
        assert current == S.SUBMITTED


class TestResolved:
    def test_submitted_and_canceled_need_no_further_work(self):
        from app.common.enums import RESOLVED_OBLIGATION_STATUSES, is_obligation_resolved

        assert RESOLVED_OBLIGATION_STATUSES == frozenset({S.SUBMITTED, S.CANCELED})
        for status in ObligationStatus:
            assert is_obligation_resolved(status) is (status in RESOLVED_OBLIGATION_STATUSES)

    def test_resolved_matches_terminal(self):
        """The two questions coincide by construction; if they ever diverge, that is
        a decision someone made, not an accident."""
        for status in ObligationStatus:
            from app.common.enums import is_obligation_resolved

            assert is_obligation_resolved(status) is is_terminal(status)
