#!/usr/bin/env python3
"""Bootstrap a login user directly in the database.

Usage example (production):
APP_ENV=production ENV_FILE=.env.production JWT_SECRET=... \
./.venv/bin/python scripts/dev/bootstrap_user_production.py \
  --full-name "Admin" \
  --email Matan1391@gmail.com \
  --password 'Aa100100!!' \
  --role advisor
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal  # noqa: E402
from app.users.models.user import UserRole  # noqa: E402
from app.users.repositories.user_repository import UserRepository  # noqa: E402
from app.users.services.user_auth_service import AuthService  # noqa: E402
from app.users.services.user_management_policies import validate_password  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an initial backend user for login.")
    parser.add_argument("--full-name", required=True, help="User full name")
    parser.add_argument("--email", required=True, help="User email (login identifier)")
    parser.add_argument("--password", required=True, help="Plain password")
    parser.add_argument(
        "--role",
        default=UserRole.ADVISOR.value,
        choices=[role.value for role in UserRole],
        help="User role",
    )
    parser.add_argument("--phone", default=None, help="Optional phone number")
    parser.add_argument(
        "--fail-if-exists",
        action="store_true",
        help="Exit with code 1 if email already exists (default: print and exit 0)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()

    try:
        repo = UserRepository(db)
        email = args.email.strip().lower()

        existing = repo.get_by_email(email)
        if existing is not None:
            print(
                f"User already exists: id={existing.id} email={existing.email} role={existing.role.value}"
            )
            return 1 if args.fail_if_exists else 0

        validate_password(args.password)
        role = UserRole(args.role)
        user = repo.create(
            full_name=args.full_name.strip(),
            email=email,
            password_hash=AuthService.hash_password(args.password),
            role=role,
            phone=args.phone,
        )
        db.commit()

        print(f"Created user: id={user.id} email={user.email} role={user.role.value}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
