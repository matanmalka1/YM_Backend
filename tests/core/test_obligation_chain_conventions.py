"""There is exactly one way to query an obligation table (D-12).

Correcting a closed obligation creates a second row for the same period
(``app/common/obligation_chain.py``). Every list, count and sum must therefore
see only the chain tip — and a query that forgets the predicate does not fail:
it returns the amended period twice and quietly reports a wrong number. No
exception is raised and no behavioural test goes red on a total merely being
too large.

That is why this is a source-level guard rather than a runtime one. The rule it
enforces is not "remember the filter" but "there is only one way to write the
query": ``select_obligations``, which applies both the soft-delete and chain-tip
scopes, and takes an explicit ``include_superseded=True`` for the few reads that
genuinely want every link in a chain.
"""

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

#: The three tables where a period can be more than one row.
OBLIGATION_MODELS = frozenset({"VatWorkItem", "AnnualReport", "AdvancePayment"})

#: Files allowed to name an obligation model inside ``select()``.
#:
#: ``obligation_chain`` is where the one way lives. ``base_repository`` builds
#: ``select(self.model)`` generically for *every* model in the application, and
#: every call it serves is qualified by primary key, so the chain-tip predicate
#: could not change an answer there — it is carved out deliberately rather than
#: left to fail the day someone reads this test. ``seed`` builds fixture data
#: and legitimately reaches for rows a business query would hide.
ALLOWED = (
    APP_ROOT / "common" / "obligation_chain.py",
    APP_ROOT / "common" / "repositories" / "base_repository.py",
    APP_ROOT / "seed",
)


def _is_allowed(path: Path) -> bool:
    return any(path == allowed or allowed in path.parents for allowed in ALLOWED)


def _named_model(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id if node.id in OBLIGATION_MODELS else None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.value.id if node.value.id in OBLIGATION_MODELS else None
    return None


def _is_rooted_in_select_obligations(node: ast.AST) -> bool:
    """Whether ``node`` is a ``select_obligations(...)`` call, chained or not.

    Follows the method chain back to its root, so ``select_obligations(M).where(
    M.x == 1)`` is recognised as compliant — the model named in ``.where`` belongs
    to a statement that already carries both scopes.
    """
    while isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id == "select_obligations"
        if isinstance(node.func, ast.Attribute):
            node = node.func.value
            continue
        return False
    return False


def _mentions_obligation(node: ast.AST) -> str | None:
    """An obligation model named in ``node``, ignoring nested compliant calls.

    ``select(exists(select_obligations(AdvancePayment, ...).where(...)))`` is
    correct — the inner query carries both scopes and the outer ``select`` merely
    wraps it. A naive walk sees the model name through the wrapper and reports the
    compliant call as the violation, which would push the reader to "fix" working
    code.
    """
    if _is_rooted_in_select_obligations(node):
        return None
    named = _named_model(node)
    if named is not None:
        return named
    for child in ast.iter_child_nodes(node):
        found = _mentions_obligation(child)
        if found is not None:
            return found
    return None


def _select_calls_naming_an_obligation(tree: ast.AST) -> list[tuple[int, str]]:
    """Every ``select(...)`` whose own arguments name an obligation model."""
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "select"):
            continue
        for argument in node.args:
            found = _mentions_obligation(argument)
            if found is not None:
                offenders.append((node.lineno, found))
                break
    return offenders


@pytest.mark.parametrize(
    "path",
    [p for p in sorted(APP_ROOT.rglob("*.py")) if not _is_allowed(p)],
    ids=lambda p: str(p.relative_to(APP_ROOT)),
)
def test_obligation_tables_are_queried_only_through_select_obligations(path: Path):
    offenders = _select_calls_naming_an_obligation(ast.parse(path.read_text(encoding="utf-8")))
    assert not offenders, (
        f"{path.relative_to(APP_ROOT)} builds select() over "
        + ", ".join(f"{model} (line {line})" for line, model in offenders)
        + ". Use select_obligations(Model, ...) from app.common.obligation_chain — it applies "
        "the soft-delete and chain-tip scopes together. If this read genuinely wants every "
        "link in a chain, pass include_superseded=True and say why."
    )
