#!/usr/bin/env python3
"""Verify the Alembic migration chain is linear and complete.

Checks:
  - Exactly one root migration (down_revision = None)
  - Exactly one head migration (no other migration points to it)
  - No duplicate revision IDs
  - No broken references (down_revision points to non-existent revision)
  - No merge points (down_revision is a tuple/list)

Usage:
    ./.venv/bin/python scripts/audit/check_migration_chain.py
    ./.venv/bin/python scripts/audit/check_migration_chain.py --json
    ./.venv/bin/python scripts/audit/check_migration_chain.py --fail-on-findings
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
VERSIONS_DIR = ROOT_DIR / "alembic" / "versions"
SCRIPTS_AUDIT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SCRIPTS_AUDIT_DIR))

from audit_utils import add_common_args, err, header, ok, print_findings  # noqa: E402


def _parse_migration(path: Path) -> dict:
    """Extract revision, down_revision, branch_labels from a migration file."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    result: dict = {"file": str(path.relative_to(ROOT_DIR))}

    def _extract_val(val: ast.expr, name: str) -> None:
        if isinstance(val, ast.Constant):
            result[name] = val.value
        elif isinstance(val, (ast.Tuple, ast.List)):
            elts = [e.value for e in val.elts if isinstance(e, ast.Constant)]
            result[name] = tuple(elts)
        else:
            result[name] = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "revision",
                    "down_revision",
                    "branch_labels",
                ):
                    _extract_val(node.value, target.id)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id in (
                "revision",
                "down_revision",
                "branch_labels",
            ):
                if node.value is not None:
                    _extract_val(node.value, target.id)

    return result


def _load_migrations() -> list[dict]:
    migrations = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        migrations.append(_parse_migration(path))
    return migrations


def _check(migrations: list[dict]) -> list[dict]:
    findings = []

    revisions = {}
    for m in migrations:
        rev = m.get("revision")
        if rev is None:
            findings.append(
                {
                    "location": m["file"],
                    "message": "Could not parse revision ID",
                }
            )
            continue
        if rev in revisions:
            findings.append(
                {
                    "location": m["file"],
                    "message": f"Duplicate revision ID: {rev!r} (also in {revisions[rev]['file']})",
                }
            )
        revisions[rev] = m

    all_revisions = set(revisions.keys())
    roots = []
    heads = set(all_revisions)

    for m in migrations:
        rev = m.get("revision")
        down = m.get("down_revision")

        if isinstance(down, tuple):
            findings.append(
                {
                    "location": m["file"],
                    "message": f"Merge point detected — down_revision is a tuple: {down}. "
                    "This project does not use merge migrations.",
                }
            )
            for d in down:
                heads.discard(d)
            continue

        if down is None:
            roots.append(m)
        else:
            if down not in all_revisions:
                findings.append(
                    {
                        "location": m["file"],
                        "message": f"Broken reference: down_revision={down!r} does not exist",
                    }
                )
            heads.discard(down)

    if len(roots) == 0:
        findings.append(
            {
                "location": "alembic/versions/",
                "message": "No root migration found (down_revision=None)",
            }
        )
    elif len(roots) > 1:
        for r in roots:
            findings.append(
                {
                    "location": r["file"],
                    "message": "Multiple root migrations — only one migration may have down_revision=None",
                }
            )

    if len(heads) > 1:
        for h in heads:
            m = revisions.get(h, {})
            findings.append(
                {
                    "location": m.get("file", h),
                    "message": f"Multiple head migrations — revision {h!r} has no child. "
                    "Run 'alembic merge heads' or check for stale files.",
                }
            )

    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Alembic migration chain integrity")
    add_common_args(parser)
    args = parser.parse_args()

    header("Migration Chain Check")
    migrations = _load_migrations()
    print(f"  Found {len(migrations)} migration file(s) in alembic/versions/\n")

    findings = _check(migrations)

    if not args.json:
        if findings:
            for f in findings:
                err(f"{f['location']}: {f['message']}")
        else:
            ok("Migration chain is linear and complete.")

    print_findings(findings, as_json=args.json, label="chain issues")

    if findings and args.fail_on_findings:
        sys.exit(1)


# Alias used by audit_utils color helpers
green = "\033[32m"

if __name__ == "__main__":
    main()
