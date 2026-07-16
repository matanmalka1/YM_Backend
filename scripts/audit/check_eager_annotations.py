#!/usr/bin/env python3
"""Find annotations that raise NameError on Render's Python 3.13 runtime.

Render runs Python 3.13, which evaluates annotations eagerly as each `def` and
class body executes. Local dev runs 3.14, where PEP 649 defers evaluation, so an
unresolvable annotation raises nothing locally and only crash-loops after deploy.

Two failure modes are detected, both of which have taken production down:

  1. TYPE_CHECKING-only import — the name exists for type checkers but never at
     runtime, so eager evaluation raises NameError.
  2. Forward reference — the annotation names a class defined later in the same
     module. It resolves on 3.14 (evaluated lazily, or via model_rebuild() for
     Pydantic), but on 3.13 the name does not exist yet when the body executes.

The fix for both is `from __future__ import annotations`, which turns annotations
into strings that are never eagerly evaluated. Files that already have it are
skipped: they cannot fail either way.

This is a static AST check on purpose. An earlier version imported the app and
force-evaluated annotations, but that only sees the module *after* it finished
loading — when forward references already resolve — so it reported a crashing app
as safe. Definition order is only visible in the source.

Usage:
    ./.venv/bin/python scripts/audit/check_eager_annotations.py
    ./.venv/bin/python scripts/audit/check_eager_annotations.py --json
    ./.venv/bin/python scripts/audit/check_eager_annotations.py --fail-on-findings
"""

from __future__ import annotations

import argparse
import ast
import builtins
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_AUDIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SCRIPTS_AUDIT_DIR))

from audit_utils import (  # noqa: E402  # type: ignore[import]
    add_common_args,
    err,
    header,
    ok,
    print_findings,
)

SCAN_DIRS = ("app",)
_BUILTINS = frozenset(dir(builtins))

FIX_HINT = "Add 'from __future__ import annotations' to the top of this file."


class ModuleBindings:
    """Where each module-level name becomes available at runtime."""

    def __init__(self, tree: ast.Module) -> None:
        self.defined_at: dict[str, int] = {}
        self.type_checking_only: set[str] = set()
        self._collect(tree.body, type_checking=False)

    def _collect(self, body: list[ast.stmt], *, type_checking: bool) -> None:
        for node in body:
            if isinstance(node, ast.If) and self._is_type_checking_test(node.test):
                # Names bound here exist for type checkers only, never at runtime.
                self._collect(node.body, type_checking=True)
                self._collect(node.orelse, type_checking=False)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if type_checking:
                        self.type_checking_only.add(name)
                    else:
                        self.defined_at.setdefault(name, node.lineno)
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                self.defined_at.setdefault(node.name, node.lineno)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                for target in ast.walk(node):
                    if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
                        self.defined_at.setdefault(target.id, node.lineno)
            elif isinstance(node, ast.Try):
                # e.g. try: import x / except ImportError: x = None
                for sub in (node.body, node.handlers, node.orelse, node.finalbody):
                    self._collect([n for n in sub if isinstance(n, ast.stmt)], type_checking=False)

    @staticmethod
    def _is_type_checking_test(test: ast.expr) -> bool:
        if isinstance(test, ast.Name):
            return test.id == "TYPE_CHECKING"
        if isinstance(test, ast.Attribute):
            return test.attr == "TYPE_CHECKING"
        return False


def _annotation_names(annotation: ast.expr | None) -> list[ast.Name]:
    """Names a 3.13 interpreter would look up. String annotations are never evaluated."""
    if annotation is None or isinstance(annotation, ast.Constant):
        return []
    return [n for n in ast.walk(annotation) if isinstance(n, ast.Name)]


def _eager_annotations(tree: ast.Module) -> list[tuple[int, str, ast.expr]]:
    """Annotations evaluated during module import, as (lineno, label, annotation).

    Only module-level defs and class bodies run at import. A nested def inside a
    function body is not evaluated until that function is called, by which point
    every module-level name exists — so it cannot fail this way.
    """
    found: list[tuple[int, str, ast.expr]] = []

    def add_signature(fn: ast.FunctionDef | ast.AsyncFunctionDef, label: str) -> None:
        args = fn.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if arg is not None and arg.annotation is not None:
                found.append((arg.lineno, f"{label}({arg.arg})", arg.annotation))
        if fn.returns is not None:
            found.append((fn.returns.lineno, f"{label}() -> ...", fn.returns))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_signature(node, node.name)
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and stmt.annotation is not None:
                    target = getattr(stmt.target, "id", "?")
                    found.append((stmt.lineno, f"{node.name}.{target}", stmt.annotation))
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_signature(stmt, f"{node.name}.{stmt.name}")
    return found


def check_file(path: Path) -> list[dict[str, str]]:
    src = path.read_text(encoding="utf-8")
    if "from __future__ import annotations" in src:
        return []  # annotations become strings; never eagerly evaluated

    rel = path.relative_to(ROOT_DIR)
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [{"location": str(rel), "message": f"SyntaxError: {exc}"}]

    bindings = ModuleBindings(tree)
    findings: list[dict[str, str]] = []

    for lineno, label, annotation in _eager_annotations(tree):
        for name in _annotation_names(annotation):
            if name.id in _BUILTINS:
                continue
            if name.id in bindings.type_checking_only:
                findings.append(
                    {
                        "location": f"{rel}:{lineno}",
                        "message": f"{label}: '{name.id}' is imported only under TYPE_CHECKING, "
                        f"so it does not exist at runtime and raises NameError on "
                        f"Python 3.13. {FIX_HINT}",
                    }
                )
                continue
            defined = bindings.defined_at.get(name.id)
            if defined is not None and defined > lineno:
                findings.append(
                    {
                        "location": f"{rel}:{lineno}",
                        "message": f"{label}: '{name.id}' is not defined until line {defined}, "
                        f"so it raises NameError on Python 3.13 when this body "
                        f"executes. {FIX_HINT}",
                    }
                )
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Check annotations resolve on Python 3.13")
    add_common_args(parser)
    args = parser.parse_args()

    header("Eager Annotation Check (Python 3.13 compatibility)")

    findings: list[dict[str, str]] = []
    checked = 0
    for scan_dir in SCAN_DIRS:
        for path in sorted((ROOT_DIR / scan_dir).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            checked += 1
            findings.extend(check_file(path))

    if not args.json:
        if findings:
            for f in findings:
                err(f"{f['location']}: {f['message']}")
        else:
            ok(f"Scanned {checked} files. No annotations that would fail on Python 3.13.")

    print_findings(findings, as_json=args.json, label="unresolvable annotations")

    if findings and args.fail_on_findings:
        sys.exit(1)


if __name__ == "__main__":
    main()
