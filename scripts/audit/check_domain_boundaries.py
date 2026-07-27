#!/usr/bin/env python3
"""Enforce the cross-domain import rules that docs/backend/architecture.md already states.

Two rules are checked, both quoted from that doc:

- "Repositories must not import models from other business domains by default."
  (Line-level exception in the doc: join clauses needed for scoping or typed read
  projections. That exception cannot be recognised statically, so a genuine scoping
  join must be added to ALLOWED_REPOSITORY_MODEL_IMPORTS with a reason.)

- "Cross-domain writes must be orchestrated in services" and "Routers must not contain
  business branching, orchestration, ...". A router importing another domain's service
  is orchestration in the wrong layer.

These rules were written down long before this check existed and were violated anyway,
because nothing mechanical could see a violation. The allowlist is the point: an entry
is a visible, reviewable admission, not a silent exemption.

Usage:
    ./.venv/bin/python scripts/audit/check_domain_boundaries.py
    ./.venv/bin/python scripts/audit/check_domain_boundaries.py --json
    ./.venv/bin/python scripts/audit/check_domain_boundaries.py --fail-on-findings
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# Infrastructure and cross-cutting packages every domain may import from freely.
# These are not business workflow domains; they own no workflow state of their own.
# `clients`/`legal_entities`/`users` are here because every workflow object anchors on
# ClientRecord, and architecture.md mandates the active-client scoping join.
SHARED_PACKAGES = frozenset(
    {
        "auth",
        "clients",
        "common",
        "core",
        "legal_entities",
        "users",
        "utils",
    }
)

# Domains whose whole purpose is cross-domain read aggregation. architecture.md:
# "Cross-domain read aggregation must live only in explicit read-model/query domains
# or dedicated query services." Their repositories necessarily join foreign models;
# flagging them would make this check noise instead of signal.
#
# This set is deliberately narrow. A domain that owns workflow state of its own does
# not belong here just because it happens to read a sibling.
READ_MODEL_DOMAINS = frozenset(
    {
        "alerts",
        "audit",
        "dashboard",
        "reports",
        "search",
        "tasks",
        "tax_calendar",
        "timeline",
        "work_queue",
    }
)

# Repository -> other-domain-model imports that are accepted scoping/projection joins,
# each with the reason it is legitimate. Anything not listed is a finding.
ALLOWED_REPOSITORY_MODEL_IMPORTS: dict[str, str] = {
    # ClientRecord/LegalEntity are the shared anchor every workflow object scopes by;
    # active-client scoping is mandated by architecture.md and cannot avoid the join.
    "*:app.clients.models": "active-client scoping join (mandated by architecture.md)",
    "*:app.legal_entities.models": "legal-entity scoping join through ClientRecord",
    # KNOWN VIOLATION, tracked for removal. This repository owns VAT's filing semantics
    # (which statuses resolve a turnover) from inside advance_payments. Removing it means
    # VAT publishing that rule as a service contract. See the tax-lifecycle plan.
    "advance_payments/repositories/advance_payment_turnover_lookup_repository.py:app.vat.models": (
        "TRACKED VIOLATION: VAT turnover-resolution rule owned by the wrong domain"
    ),
    # TRACKED VIOLATION: signature_requests owns workflow state of its own, so it is not
    # a read-model domain, yet its repository reads annual-report status directly.
    "signature_requests/repositories/signature_request_crud.py:app.annual_reports.models": (
        "TRACKED VIOLATION: reads annual-report status without a published contract"
    ),
}

# Router -> other-domain-service imports accepted for now, each with the reason.
ALLOWED_ROUTER_SERVICE_IMPORTS: dict[str, str] = {
    # TRACKED VIOLATION: available-action assembly is domain logic sitting in the
    # serializer layer. Belongs behind a VAT service method.
    "vat/api/vat_serializers.py:app.actions.services": (
        "TRACKED VIOLATION: action assembly orchestrated from the serializer layer"
    ),
}


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    imported: str
    detail: str


def _domain_of(path: Path) -> str:
    return path.relative_to(APP_ROOT).parts[0]


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
    return found


def _target_domain(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "app":
        return None
    return parts[1]


def _allowlisted(table: dict[str, str], rel_path: str, module_prefix: str) -> bool:
    return f"*:{module_prefix}" in table or f"{rel_path}:{module_prefix}" in table


def _check_file(path: Path, layer: str) -> list[Finding]:
    rel_path = str(path.relative_to(APP_ROOT.parent / "app"))
    own_domain = _domain_of(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:  # pragma: no cover - a parse failure is a real problem
        return [Finding("parse-error", rel_path, exc.lineno or 0, "", str(exc))]

    findings: list[Finding] = []
    for module, lineno in _imported_modules(tree):
        target = _target_domain(module)
        if target is None or target == own_domain or target in SHARED_PACKAGES:
            continue
        if own_domain in READ_MODEL_DOMAINS:
            continue

        if layer == "repositories" and f"app.{target}.models" in module:
            prefix = f"app.{target}.models"
            if not _allowlisted(ALLOWED_REPOSITORY_MODEL_IMPORTS, rel_path, prefix):
                findings.append(
                    Finding(
                        "repository-imports-foreign-model",
                        rel_path,
                        lineno,
                        module,
                        "architecture.md: repositories must not import other domains' models",
                    )
                )
        elif layer == "api" and f"app.{target}.services" in module:
            prefix = f"app.{target}.services"
            if not _allowlisted(ALLOWED_ROUTER_SERVICE_IMPORTS, rel_path, prefix):
                findings.append(
                    Finding(
                        "router-orchestrates-foreign-service",
                        rel_path,
                        lineno,
                        module,
                        "architecture.md: cross-domain writes are orchestrated in services",
                    )
                )
    return findings


def collect_findings() -> list[Finding]:
    findings: list[Finding] = []
    for layer in ("repositories", "api"):
        for path in sorted(APP_ROOT.glob(f"*/{layer}/*.py")):
            if path.name == "__init__.py":
                continue
            findings.extend(_check_file(path, layer))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="exit non-zero when any finding is reported (use in CI)",
    )
    args = parser.parse_args()

    findings = collect_findings()

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2, ensure_ascii=False))
    elif not findings:
        print("check_domain_boundaries: no cross-domain boundary violations found.")
    else:
        print(f"check_domain_boundaries: {len(findings)} finding(s)\n")
        for f in findings:
            print(f"  {f.path}:{f.line}")
            print(f"    rule     : {f.rule}")
            print(f"    imports  : {f.imported}")
            print(f"    detail   : {f.detail}\n")
        print(
            "If an import is a legitimate scoping join or an accepted temporary\n"
            "exception, add it to the matching allowlist in this script with a reason."
        )

    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
