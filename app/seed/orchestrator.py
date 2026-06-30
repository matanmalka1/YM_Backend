from __future__ import annotations

import importlib
import random
from pathlib import Path

from sqlalchemy import func, inspect, select, text

from app.clients.repositories.client_record_repository import OFFICE_CLIENT_NUMBER_START
from app.database import Base, SessionLocal, engine
from app.tax_calendar.services.tax_calendar_bootstrap_service import bootstrap_tax_calendar

from .builders import clients as clients_builder
from .builders import users as users_builder
from .builders.demo import advance_payments as advance_payments_builder
from .builders.demo import binders as binders_builder
from .builders.demo import charges as charges_builder
from .builders.demo import contacts as contacts_builder
from .builders.demo import documents as documents_builder
from .builders.demo import notifications as notifications_builder
from .builders.demo import reports as reports_builder
from .builders.demo import signature_requests as sig_builder
from .builders.demo import vat as vat_builder
from .builders.shared.client_refs import attach_seed_client_context
from .config import SeedConfig
from .tax_calendar_range import tax_calendar_year_range_for_seed
from .validator import SeedIntegrityValidator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"


def _import_all_model_modules() -> None:
    for model_file in APP_DIR.glob("*/models/*.py"):
        if model_file.name.startswith("__"):
            continue
        module = ".".join(model_file.relative_to(PROJECT_ROOT).with_suffix("").parts)
        importlib.import_module(module)


def _ensure_schema_ready() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = {table.name for table in Base.metadata.sorted_tables}
    missing = sorted(expected_tables - existing_tables)
    if missing:
        preview = ", ".join(missing[:8])
        suffix = "..." if len(missing) > 8 else ""
        raise RuntimeError(
            f"Database schema is not ready. Missing tables: {preview}{suffix}. "
            "Run `alembic upgrade head` first."
        )

    missing_columns: dict[str, list[str]] = {}
    for table in Base.metadata.sorted_tables:
        existing_cols = {col["name"] for col in inspector.get_columns(table.name)}
        expected_cols = {col.name for col in table.columns}
        gaps = sorted(expected_cols - existing_cols)
        if gaps:
            missing_columns[table.name] = gaps

    if missing_columns:
        preview_items = [f"{t}({', '.join(c[:4])})" for t, c in list(missing_columns.items())[:6]]
        suffix = "..." if len(missing_columns) > 6 else ""
        raise RuntimeError(
            "Database schema is not ready. Missing columns: "
            + "; ".join(preview_items)
            + suffix
            + ". Run `alembic upgrade head` first."
        )


class SeedOrchestrator:
    def __init__(self, cfg: SeedConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)

    def run(self) -> None:
        _import_all_model_modules()
        engine.echo = False
        _ensure_schema_ready()
        db = SessionLocal()
        try:
            if self.cfg.reset:
                self._reset(db)

            seeded_users = self._seed_users(db)
            if self.cfg.users_only:
                db.commit()
                self._print_counts(db)
                return

            start_year, end_year = tax_calendar_year_range_for_seed(self.cfg)
            bootstrap_tax_calendar(
                db,
                start_year=start_year,
                end_year=end_year,
            )

            # ── Onboarding phase ─────────────────────────────────────────────
            # CreateClientService → automatically triggers ClientOnboardingOrchestrator
            # which creates: initial binder, TaxCalendar entries, VAT items (eligible only),
            # advance payments, annual report shell.
            client_pairs = clients_builder.create_clients(db, self.rng, self.cfg, seeded_users)
            client_records = [cr for cr, _ in client_pairs]
            primary_businesses = [biz for _, biz in client_pairs]

            # Add extra businesses for multi-business clients
            extra_businesses = clients_builder.create_extra_businesses(
                db, self.rng, self.cfg, client_pairs, seeded_users
            )
            all_businesses = primary_businesses + extra_businesses

            db.flush()

            if self.cfg.onboarding_only:
                clients_builder.create_entity_notes(db, self.rng, client_records, seeded_users)
                db.commit()
                if not self.cfg.skip_validation:
                    SeedIntegrityValidator(db).validate()
                self._print_counts(db)
                return

            # ── Demo phase ───────────────────────────────────────────────────
            clients_builder.create_entity_notes(db, self.rng, client_records, seeded_users)

            # Historical binders (on top of initial binder from onboarding)
            demo_binders = binders_builder.create_binders(
                db, self.rng, self.cfg, all_businesses, seeded_users
            )
            # All binders (for notifications/reminders)
            all_binders = self._load_all_binders(db, client_records)

            binder_intakes = binders_builder.create_binder_intakes(db, demo_binders)

            seeded_charges = charges_builder.create_charges(
                db, self.rng, self.cfg, all_businesses, seeded_users
            )
            charges_builder.create_invoices(db, seeded_charges)

            # Historical annual reports (current year shell already exists from onboarding)
            reports_builder.create_annual_reports(
                db, self.rng, self.cfg, all_businesses, seeded_users
            )
            # Load all reports (including onboarding shells) for enrichment
            all_reports = self._load_all_reports(db, client_records)

            contacts_seeded = contacts_builder.create_authority_contacts(
                db, self.rng, self.cfg, client_records, all_businesses
            )
            contacts_builder.create_correspondence(
                db, self.rng, all_businesses, seeded_users, contacts_seeded
            )

            reports_builder.create_annual_report_details(db, self.rng, all_reports)
            reports_builder.create_annual_report_income_lines(db, self.rng, all_reports)
            reports_builder.create_annual_report_schedule_entries(
                db, self.rng, all_reports, seeded_users
            )
            reports_builder.create_annual_report_annex_data(db, self.rng, all_reports)
            reports_builder.create_annual_report_credit_points(db, self.rng, all_reports)
            reports_builder.create_annual_report_audit_logs(db, self.rng, all_reports, seeded_users)

            seeded_documents = documents_builder.create_documents(
                db, self.rng, client_records, all_businesses, seeded_users
            )
            reports_builder.create_annual_report_expense_lines(
                db, self.rng, all_reports, seeded_documents
            )

            binders_builder.create_binder_intake_materials(
                db, self.rng, demo_binders, all_businesses, all_reports, binder_intakes
            )
            binders_builder.create_binder_logs(db, self.rng, demo_binders, seeded_users)
            binders_builder.create_binder_handovers(db, self.rng, demo_binders, seeded_users)
            binders_builder.create_binder_intake_audit_logs(
                db, self.rng, binder_intakes, seeded_users
            )

            users_builder.create_entity_audit_logs(
                db, self.rng, seeded_users, all_businesses, client_records
            )

            notifications_builder.create_notifications(
                db,
                self.rng,
                client_records,
                all_businesses,
                all_binders,
                seeded_users,
                cfg=self.cfg,
            )

            vat_work_items = vat_builder.create_vat_work_items(
                db, self.rng, self.cfg, all_businesses, seeded_users
            )
            vat_builder.create_vat_invoices(db, self.rng, self.cfg, vat_work_items, seeded_users)

            advance_payments_builder.create_advance_payments(db, self.rng, self.cfg, all_businesses)

            sig_requests = sig_builder.create_signature_requests(
                db,
                self.rng,
                self.cfg,
                all_businesses,
                client_records,
                seeded_users,
                all_reports,
                seeded_documents,
            )
            sig_builder.create_signature_audit_logs(db, self.rng, sig_requests)

            db.commit()
            if not self.cfg.skip_validation:
                SeedIntegrityValidator(db).validate()
            self._print_counts(db)

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _reset(self, db) -> None:
        skip = {"users", "user_audit_logs"} if self.cfg.preserve_users else set()
        tables = [t.name for t in Base.metadata.sorted_tables if t.name not in skip]
        if engine.dialect.name == "postgresql":
            names = ", ".join(f'"{t}"' for t in tables)
            db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
            db.execute(
                text(
                    f"ALTER SEQUENCE IF EXISTS client_office_number_seq RESTART WITH {OFFICE_CLIENT_NUMBER_START}"
                )
            )
        else:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in skip:
                    continue
                db.execute(table.delete())
        db.commit()

    def _seed_users(self, db):
        if self.cfg.preserve_users:
            seeded_users = users_builder.get_existing_users(db)
            if not seeded_users:
                raise RuntimeError(
                    "No existing users found for --preserve-users mode. "
                    "Create users first or run without --preserve-users."
                )
            return seeded_users
        seeded_users = users_builder.create_users(db, self.rng, self.cfg)
        users_builder.create_user_audit_logs(db, self.rng, seeded_users)
        return seeded_users

    def _load_all_binders(self, db, client_records):
        from app.binders.models.binder import Binder

        client_ids = [cr.id for cr in client_records]
        binders = (
            db.execute(
                select(Binder).where(
                    Binder.client_record_id.in_(client_ids),
                    Binder.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        clients_by_id = {cr.id: cr for cr in client_records}
        for b in binders:
            client_record = clients_by_id.get(b.client_record_id)
            if client_record is not None:
                attach_seed_client_context(b, client_record)
        return list(binders)

    def _load_all_reports(self, db, client_records):
        from app.annual_reports.models.annual_report_model import AnnualReport

        client_ids = [cr.id for cr in client_records]
        reports = (
            db.execute(
                select(AnnualReport).where(
                    AnnualReport.client_record_id.in_(client_ids),
                    AnnualReport.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        clients_by_id = {cr.id: cr for cr in client_records}
        for r in reports:
            client_record = clients_by_id.get(r.client_record_id)
            if client_record is not None:
                attach_seed_client_context(r, client_record)
        return list(reports)

    def _print_counts(self, db) -> None:
        print("Seeding completed. Row counts:")
        for table in Base.metadata.sorted_tables:
            count = int(db.execute(select(func.count()).select_from(table)).scalar_one())
            if count > 0:
                print(f"  {table.name}: {count}")
