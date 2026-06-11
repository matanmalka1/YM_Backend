from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date

from app.utils.time_utils import israel_today


@dataclass
class SeedConfig:
    users: int
    clients: int
    min_binders_per_client: int
    max_binders_per_client: int
    min_charges_per_client: int
    max_charges_per_client: int
    annual_reports_per_client: int
    min_vat_work_items_per_client: int
    max_vat_work_items_per_client: int
    min_vat_invoices_per_work_item: int
    max_vat_invoices_per_work_item: int
    signature_requests_per_client: int
    min_authority_contacts_per_client: int
    max_authority_contacts_per_client: int
    seed: int
    reference_date: date
    reset: bool
    preserve_users: bool
    users_only: bool
    onboarding_only: bool
    skip_validation: bool


def parse_args() -> SeedConfig:
    parser = argparse.ArgumentParser(description="Seed local DB with fake demo data")
    parser.add_argument("--users", type=int, default=8)
    parser.add_argument("--clients", type=int, default=60)
    parser.add_argument("--min-binders-per-client", type=int, default=1)
    parser.add_argument("--max-binders-per-client", type=int, default=3)
    parser.add_argument("--min-charges-per-client", type=int, default=3)
    parser.add_argument("--max-charges-per-client", type=int, default=8)
    parser.add_argument("--annual-reports-per-client", type=int, default=3)
    parser.add_argument("--min-vat-work-items-per-client", type=int, default=6)
    parser.add_argument("--max-vat-work-items-per-client", type=int, default=12)
    parser.add_argument("--min-vat-invoices-per-work-item", type=int, default=3)
    parser.add_argument("--max-vat-invoices-per-work-item", type=int, default=12)
    parser.add_argument("--signature-requests-per-client", type=int, default=2)
    parser.add_argument("--min-authority-contacts-per-client", type=int, default=1)
    parser.add_argument("--max-authority-contacts-per-client", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        default=israel_today(),
    )
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--preserve-users", action="store_true")
    parser.add_argument("--users-only", action="store_true")
    parser.add_argument("--onboarding-only", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")

    args = parser.parse_args()
    if args.users < 1:
        raise ValueError("חובה להגדיר לפחות משתמש אחד")
    if not args.users_only and args.clients < 1:
        raise ValueError("חובה להגדיר לפחות לקוח אחד")

    return SeedConfig(
        users=args.users,
        clients=args.clients,
        min_binders_per_client=args.min_binders_per_client,
        max_binders_per_client=args.max_binders_per_client,
        min_charges_per_client=args.min_charges_per_client,
        max_charges_per_client=args.max_charges_per_client,
        annual_reports_per_client=args.annual_reports_per_client,
        min_vat_work_items_per_client=args.min_vat_work_items_per_client,
        max_vat_work_items_per_client=args.max_vat_work_items_per_client,
        min_vat_invoices_per_work_item=args.min_vat_invoices_per_work_item,
        max_vat_invoices_per_work_item=args.max_vat_invoices_per_work_item,
        signature_requests_per_client=args.signature_requests_per_client,
        min_authority_contacts_per_client=args.min_authority_contacts_per_client,
        max_authority_contacts_per_client=args.max_authority_contacts_per_client,
        seed=args.seed,
        reference_date=args.reference_date,
        reset=args.reset,
        preserve_users=args.preserve_users,
        users_only=args.users_only,
        onboarding_only=args.onboarding_only,
        skip_validation=args.skip_validation,
    )
