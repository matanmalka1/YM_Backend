#!/usr/bin/env python3
"""Interactive and direct runner for backend maintenance scripts.

Examples:
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py list
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py audit role --json
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py audit all --output reports/audit
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
VENV_PYTHON = ROOT_DIR / ".venv" / "bin" / "python"

ENV = {
    **os.environ,
    "APP_ENV": os.environ.get("APP_ENV", "development"),
    "ENV_FILE": os.environ.get("ENV_FILE", str(ROOT_DIR / ".env.development")),
    "JWT_SECRET": os.environ.get("JWT_SECRET", "dev-seed-secret"),
}

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _ansi(code: str) -> str:
    return f"\033[{code}m" if USE_COLOR else ""


G = _ansi("32")
R = _ansi("31")
Y = _ansi("33")
B = _ansi("1")
D = _ansi("2")
C = _ansi("36")
X = _ansi("0")

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


class Option(TypedDict):
    label: str
    args: list[str]
    dangerous: bool


class ScriptMeta(TypedDict):
    label: str
    path: str
    options: list[Option]
    default_args: list[str]


class CategoryMeta(TypedDict):
    label: str
    scripts: dict[str, ScriptMeta]


Registry = dict[str, CategoryMeta]


def _option(label: str, args: list[str] | None = None, *, dangerous: bool = False) -> Option:
    return {"label": label, "args": args or [], "dangerous": dangerous}


def _script(
    label: str,
    path: str,
    options: list[Option],
    *,
    default_args: list[str] | None = None,
) -> ScriptMeta:
    return {
        "label": label,
        "path": path,
        "options": options,
        "default_args": default_args or [],
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: Registry = {
    "audit": {
        "label": "Code quality and consistency checks",
        "scripts": {
            "migration": _script(
                "Migration chain integrity",
                "audit/check_migration_chain.py",
                [
                    _option("Run check"),
                    _option("Run check, fail on findings", ["--fail-on-findings"]),
                    _option("Run check as JSON", ["--json"]),
                ],
            ),
            "role": _script(
                "Role/auth coverage on all routes",
                "audit/check_role_coverage.py",
                [
                    _option("Run check"),
                    _option("Run check, fail on findings", ["--fail-on-findings"]),
                    _option("Run check as JSON", ["--json"]),
                ],
            ),
            "pagination": _script(
                "Missing pagination on list endpoints",
                "audit/check_missing_pagination.py",
                [
                    _option("Run check"),
                    _option("Run check, fail on findings", ["--fail-on-findings"]),
                    _option("Run check as JSON", ["--json"]),
                ],
            ),
            "unused": _script(
                "Unused backend routes",
                "audit/check_unused_routes.py",
                [
                    _option("Run check, frontend and backend"),
                    _option("Run check, backend only", ["--backend-only"]),
                    _option("Run check, fail on findings", ["--fail-on-findings"]),
                    _option("Run check as JSON", ["--json"]),
                ],
            ),
            "enums": _script(
                "Enum drift, Python vs TypeScript",
                "audit/check_enum_sync.py",
                [
                    _option("Run all enum checks"),
                    _option("Run one enum, prompt for name", ["__enum__"]),
                    _option("Run check, fail on findings", ["--fail-on-findings"]),
                    _option("Run check as JSON", ["--json"]),
                ],
            ),
            "schema": _script(
                "Dump live DB schema",
                "audit/dump_schema.py",
                [
                    _option("Dump all tables"),
                    _option("Dump specific table, prompt", ["__table__"]),
                    _option("Dump all tables as JSON", ["--json"]),
                ],
            ),
            "all": _script(
                "Run all audit checks",
                "__audit_all__",
                [
                    _option("Run all, print to terminal"),
                    _option("Run all, save to reports/audit", ["__output__", "reports/audit"]),
                    _option("Run all, save to custom directory", ["__output__", "__dir__"]),
                ],
            ),
        },
    },
    "dev": {
        "label": "Local database and seed management",
        "scripts": {
            "reset": _script(
                "Full dev DB reset, drop + migrate + seed",
                "dev/reset_dev_db.py",
                [
                    _option("Reset with defaults, 60 clients", ["--yes"], dangerous=True),
                    _option(
                        "Reset with custom client count", ["--yes", "__clients__"], dangerous=True
                    ),
                    _option(
                        "Reset and preserve existing users",
                        ["--yes", "--preserve-users"],
                        dangerous=True,
                    ),
                ],
            ),
            "seed": _script(
                "Seed fake data",
                "dev/seed_fake_data.py",
                [
                    _option("Seed with defaults", ["--reset"], dangerous=True),
                    _option(
                        "Seed onboarding only", ["--reset", "--onboarding-only"], dangerous=True
                    ),
                    _option("Seed users only", ["--reset", "--users-only"], dangerous=True),
                    _option(
                        "Seed preserving existing users",
                        ["--reset", "--preserve-users"],
                        dangerous=True,
                    ),
                    _option(
                        "Seed with custom client count", ["--reset", "__clients__"], dangerous=True
                    ),
                ],
            ),
            "tax-calendar": _script(
                "Bootstrap tax calendar",
                "dev/bootstrap_tax_calendar.py",
                [
                    _option("Bootstrap all years"),
                    _option("Bootstrap year range", ["__year_range__"]),
                ],
            ),
            "bootstrap-user": _script(
                "Create a user in the database",
                "dev/bootstrap_user_production.py",
                [
                    _option("Create user, interactive prompt", ["__bootstrap_user__"]),
                ],
            ),
        },
    },
    "ops": {
        "label": "Health checks and monitoring",
        "scripts": {
            "health": _script(
                "Health check: /health, /info, /auth/me",
                "ops/health_check.py",
                [
                    _option("Check without auth"),
                    _option("Check with auth, prompt for credentials", ["__health_auth__"]),
                    _option("Check custom URL", ["__health_url__"]),
                ],
            ),
        },
    },
    "tooling": {
        "label": "OpenAPI and route inspection",
        "scripts": {
            "routes": _script(
                "List all registered routes",
                "tooling/list_routes.py",
                [
                    _option("List all routes"),
                    _option("Filter by keyword", ["__filter__"]),
                ],
            ),
            "openapi": _script(
                "Export OpenAPI schema to openapi.json",
                "tooling/export_openapi.py",
                [
                    _option("Export to openapi.json"),
                    _option("Export to custom path", ["__openapi_output__"]),
                ],
            ),
            "contract": _script(
                "Verify openapi.json matches current app",
                "tooling/check_contract_sync.py",
                [
                    _option("Run contract sync check"),
                    _option("Check custom OpenAPI path", ["__openapi_path__"]),
                ],
            ),
            "examples": _script(
                "Generate JSON_EXAMPLES.md from the current OpenAPI schema",
                "tooling/json_examples.py",
                [
                    _option("Generate JSON_EXAMPLES.md"),
                ],
            ),
        },
    },
}


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _clear() -> None:
    if sys.stdout.isatty():
        print("\033c", end="")


def _terminal_width() -> int:
    return shutil.get_terminal_size((100, 24)).columns


def _banner() -> None:
    width = min(max(_terminal_width() - 4, 48), 82)
    title = "Backend Scripts"
    line = "═" * width
    print(f"\n{B}{C}╔{line}╗{X}")
    print(f"{B}{C}║{title.center(width)}║{X}")
    print(f"{B}{C}╚{line}╝{X}\n")
    print(f"  {D}env:{X} APP_ENV={ENV['APP_ENV']}  ENV_FILE={ENV['ENV_FILE']}")
    print(f"  {D}python:{X} {VENV_PYTHON}\n")


def _print_help(exit_code: int = 0) -> None:
    print(
        """Usage:
  scripts/run.py                         Open interactive menu
  scripts/run.py list                    List all registered scripts
  scripts/run.py <category> <script>     Open that script's option menu
  scripts/run.py <category> <script> <option-number>
  scripts/run.py <category> <script> [script args...]
  scripts/run.py audit all [--output DIR]

Examples:
  ./.venv/bin/python scripts/run.py audit role --json
  ./.venv/bin/python scripts/run.py audit role 2
  ./.venv/bin/python scripts/run.py audit all --output reports/audit
  ./.venv/bin/python scripts/run.py tooling routes clients

Notes:
  Option numbers are the same 1-based numbers shown in the interactive menu.
  Direct script args are passed through unchanged when they are not an option number.
"""
    )
    raise SystemExit(exit_code)


def _print_registry() -> None:
    for category, cat in REGISTRY.items():
        print(f"{B}{category}{X}  {D}{cat['label']}{X}")
        for script_key, meta in cat["scripts"].items():
            print(f"  {script_key:<16} {meta['label']}")
        print()


def _pick(items: list[str], prompt: str = "Select") -> int | None:
    for i, item in enumerate(items, 1):
        print(f"  {D}{i:>2}{X}  {item}")
    print(f"\n  {D}0{X}   Back\n")

    while True:
        try:
            raw = input(f"{B}{prompt}{X} [0-{len(items)}]: ").strip()
        except EOFError, KeyboardInterrupt:
            print()
            return None

        if raw in {"", "0", "q", "quit", "exit"}:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return int(raw) - 1
        print(f"  {R}Invalid choice.{X}")


def _prompt(label: str, default: str = "", *, secret: bool = False) -> str:
    default_str = f" [{default}]" if default else ""
    try:
        if secret:
            value = getpass.getpass(f"  {label}{default_str}: ").strip()
        else:
            value = input(f"  {label}{default_str}: ").strip()
    except EOFError, KeyboardInterrupt:
        print()
        return default
    return value or default


def _prompt_int(label: str, default: int, *, minimum: int = 1) -> str:
    while True:
        raw = _prompt(label, str(default))
        try:
            value = int(raw)
        except ValueError:
            print(f"  {R}Must be a number.{X}")
            continue
        if value < minimum:
            print(f"  {R}Must be at least {minimum}.{X}")
            continue
        return str(value)


def _confirm_danger(option: Option, *, force: bool = False) -> bool:
    if force or not option.get("dangerous"):
        return True

    print(f"\n  {Y}{B}This option can change data.{X}")
    answer = _prompt("Type run to continue")
    return answer.lower() == "run"


def _pause() -> None:
    if not sys.stdin.isatty():
        return
    try:
        input(f"\n  {D}Press Enter to continue...{X}")
    except EOFError, KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------


def _ensure_runtime() -> None:
    if not VENV_PYTHON.exists():
        raise SystemExit(
            f"Virtualenv Python not found: {VENV_PYTHON}\n"
            "Create the repo virtualenv first, then run ./.venv/bin/python scripts/run.py"
        )


def _script_path(path: str) -> Path:
    full = (SCRIPTS_DIR / path).resolve()
    try:
        full.relative_to(SCRIPTS_DIR.resolve())
    except ValueError as exc:
        raise SystemExit(f"Script path escapes scripts/: {path}") from exc
    if not full.is_file():
        raise SystemExit(f"Script not found: {full}")
    return full


def _run(path: str, args: list[str]) -> int:
    full = _script_path(path)
    command = [str(VENV_PYTHON), str(full), *args]
    return subprocess.run(command, env=ENV, cwd=ROOT_DIR).returncode


def _run_capture(path: str, args: list[str]) -> tuple[int, str]:
    full = _script_path(path)
    command = [str(VENV_PYTHON), str(full), *args]
    result = subprocess.run(command, env=ENV, cwd=ROOT_DIR, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def _extract_json(raw: str) -> list[Any] | dict[str, Any] | None:
    clean = ANSI_RE.sub("", raw).strip()
    decoder = json.JSONDecoder()
    offset = 0
    for line in clean.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped.startswith(("[", "{")):
            offset += len(line)
            continue
        idx = offset + (len(line) - len(stripped))
        try:
            parsed, _ = decoder.raw_decode(clean[idx:])
            return parsed
        except json.JSONDecodeError:
            offset += len(line)
            continue
    return None


def _count_findings(data: list[Any] | dict[str, Any] | None) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        findings = data.get("findings")
        if isinstance(findings, list):
            return len(findings)
    return 0


def _resolve_output_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _run_audit_all(output_dir: Path | None) -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = (output_dir / f"audit_{timestamp}") if output_dir else None

    if run_dir:
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n{B}Running all audit checks -> {run_dir}{X}\n")
    else:
        print(f"\n{B}Running all audit checks{X}\n")

    total = 0
    failed: list[str] = []
    summary: dict[str, Any] = {"timestamp": timestamp, "checks": {}}
    audit_scripts = {
        key: value for key, value in REGISTRY["audit"]["scripts"].items() if key != "all"
    }

    for key, meta in audit_scripts.items():
        if run_dir:
            rc, raw = _run_capture(meta["path"], [*meta.get("default_args", []), "--json"])
            data = _extract_json(raw)
            if data is None and rc != 0:
                data = {
                    "error": "script failed before emitting JSON",
                    "exit_code": rc,
                    "output": raw[-4000:],
                }
            elif data is None:
                data = []
            out = run_dir / f"{key}.json"
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            count = _count_findings(data)
            total += count
            status = f"{G}OK{X}" if rc == 0 else f"{R}FAIL{X}"
            print(f"  {status:<8} {key:<14} {count:>3} findings  {D}{out.name}{X}")
            summary["checks"][key] = {"exit_code": rc, "findings": count, "file": str(out)}
            if rc != 0:
                failed.append(key)
        else:
            print(f"\n{B}-- {meta['label']} --{X}")
            rc = _run(meta["path"], meta.get("default_args", []))
            if rc != 0:
                failed.append(key)

    if run_dir:
        summary["total_findings"] = total
        summary["failed_checks"] = failed
        summary_path = run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\n  Summary: {D}{summary_path}{X}")

    print()
    if failed:
        print(f"{R}{B}Checks with issues: {', '.join(failed)}{X}")
        return 1

    print(f"{G}{B}All audit checks passed.{X}")
    return 0


# ---------------------------------------------------------------------------
# Option execution
# ---------------------------------------------------------------------------


def _resolve_args(args: list[str]) -> list[str] | None:
    resolved: list[str] = []
    i = 0

    while i < len(args):
        arg = args[i]

        if arg == "__table__":
            value = _prompt("Table name, substring filter")
            if not value:
                return None
            resolved += ["--table", value]

        elif arg == "__enum__":
            value = _prompt("Python enum class name")
            if not value:
                return None
            resolved += ["--enum", value]

        elif arg == "__filter__":
            value = _prompt("Filter keyword")
            if value:
                resolved.append(value)

        elif arg == "__clients__":
            resolved += ["--clients", _prompt_int("Number of clients", 20)]

        elif arg == "__year_range__":
            start = _prompt_int("Start year", datetime.now().year - 1, minimum=2000)
            end = _prompt_int("End year", datetime.now().year + 1, minimum=int(start))
            resolved += ["--start-year", start, "--end-year", end]

        elif arg == "__health_auth__":
            email = _prompt("Email")
            if not email:
                return None
            password = _prompt("Password", secret=True)
            if not password:
                return None
            resolved += ["--email", email, "--password", password]

        elif arg == "__health_url__":
            resolved += ["--url", _prompt("Base URL", "http://localhost:8000")]

        elif arg == "__bootstrap_user__":
            name = _prompt("Full name")
            email = _prompt("Email")
            password = _prompt("Password", secret=True)
            role = _prompt("Role", "advisor")
            phone = _prompt("Phone, optional")
            if not name or not email or not password:
                return None
            resolved += [
                "--full-name",
                name,
                "--email",
                email,
                "--password",
                password,
                "--role",
                role,
            ]
            if phone:
                resolved += ["--phone", phone]

        elif arg == "__openapi_output__":
            resolved += ["--output", _prompt("Output path", "openapi.json")]

        elif arg == "__openapi_path__":
            resolved += ["--path", _prompt("OpenAPI path", "openapi.json")]

        elif arg == "__output__":
            i += 1
            dir_arg = args[i] if i < len(args) else "__dir__"
            dir_value = (
                _prompt("Output directory", "reports/audit") if dir_arg == "__dir__" else dir_arg
            )
            resolved += ["__audit_output__", dir_value]

        else:
            resolved.append(arg)

        i += 1

    return resolved


def _execute_option(
    _category: str,
    _script_key: str,
    meta: ScriptMeta,
    option: Option,
    *,
    force: bool = False,
    pause: bool = True,
) -> int:
    if not _confirm_danger(option, force=force):
        print(f"  {D}Cancelled.{X}")
        return 130

    resolved = _resolve_args(list(option["args"]))
    if resolved is None:
        return 130

    if meta["path"] == "__audit_all__":
        output_dir = None
        for index, arg in enumerate(resolved):
            if arg == "__audit_output__" and index + 1 < len(resolved):
                output_dir = _resolve_output_dir(resolved[index + 1])
                break
        rc = _run_audit_all(output_dir)
        if pause:
            _pause()
        return rc

    print()
    rc = _run(meta["path"], resolved)
    print()
    print(f"  {G}Done{X}" if rc == 0 else f"  {R}Exited with code {rc}{X}")
    if pause:
        _pause()
    return rc


def _run_raw(category: str, script_key: str, meta: ScriptMeta, args: list[str]) -> int:
    if meta["path"] == "__audit_all__":
        output_dir = None
        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "--output":
                if index + 1 >= len(args):
                    raise SystemExit("--output requires a directory")
                output_dir = _resolve_output_dir(args[index + 1])
                index += 2
                continue
            raise SystemExit(f"Unsupported audit all argument: {arg}")
        return _run_audit_all(output_dir)

    print(f"{D}Running {category} {script_key}: {meta['path']} {' '.join(args)}{X}\n", flush=True)
    return _run(meta["path"], args)


# ---------------------------------------------------------------------------
# Menu levels
# ---------------------------------------------------------------------------


def _menu_options(category: str, script_key: str) -> None:
    meta = REGISTRY[category]["scripts"][script_key]
    while True:
        _clear()
        _banner()
        print(f"  {D}{category}{X} / {D}{script_key}{X}  {B}{meta['label']}{X}\n")
        labels = [
            f"{option['label']}{f'  {Y}(changes data){X}' if option.get('dangerous') else ''}"
            for option in meta["options"]
        ]
        choice = _pick(labels, "Option")
        if choice is None:
            return
        option = meta["options"][choice]
        _clear()
        _banner()
        print(f"  {D}{category} / {script_key}{X}  {B}{option['label']}{X}\n")
        _execute_option(category, script_key, meta, option)


def _menu_scripts(category: str) -> None:
    cat = REGISTRY[category]
    keys = list(cat["scripts"].keys())
    while True:
        _clear()
        _banner()
        print(f"  {B}{C}{category.upper()}{X}  {D}{cat['label']}{X}\n")
        labels = [f"{B}{key}{X}  {D}{cat['scripts'][key]['label']}{X}" for key in keys]
        choice = _pick(labels, "Script")
        if choice is None:
            return
        _menu_options(category, keys[choice])


def _menu_main() -> None:
    keys = list(REGISTRY.keys())
    while True:
        _clear()
        _banner()
        labels = [f"{B}{C}{key}{X}  {D}{REGISTRY[key]['label']}{X}" for key in keys]
        choice = _pick(labels, "Category")
        if choice is None:
            print(f"\n{D}Bye.{X}\n")
            raise SystemExit(0)
        _menu_scripts(keys[choice])


# ---------------------------------------------------------------------------
# Direct command mode
# ---------------------------------------------------------------------------


def _parse_option_number(raw: str, total: int) -> int | None:
    if not raw.isdigit():
        return None
    value = int(raw)
    if 1 <= value <= total:
        return value - 1
    return None


def _resolve_command(category: str, script_key: str) -> tuple[ScriptMeta, Literal["ok"]]:
    if category not in REGISTRY:
        raise SystemExit(f"Unknown category: {category}\nRun scripts/run.py list")
    scripts = REGISTRY[category]["scripts"]
    if script_key not in scripts:
        raise SystemExit(f"Unknown script: {category} {script_key}\nRun scripts/run.py list")
    return scripts[script_key], "ok"


def main() -> None:
    _ensure_runtime()
    args = sys.argv[1:]

    if args and args[0] in {"-h", "--help", "help"}:
        _print_help()
    if args and args[0] == "list":
        _print_registry()
        raise SystemExit(0)
    if not args:
        _menu_main()

    if len(args) < 2:
        _print_help(2)

    category, script_key, *rest = args
    meta, _ = _resolve_command(category, script_key)

    if not rest:
        if sys.stdin.isatty():
            _menu_options(category, script_key)
            raise SystemExit(0)
        _print_help(2)

    if rest[0] == "--":
        rest = rest[1:]

    option_index = _parse_option_number(rest[0], len(meta["options"])) if rest else None
    if option_index is not None:
        if len(rest) > 1:
            raise SystemExit("Option-number mode does not accept extra script args.")
        rc = _execute_option(
            category,
            script_key,
            meta,
            meta["options"][option_index],
            force=True,
            pause=False,
        )
        raise SystemExit(rc)

    rc = _run_raw(category, script_key, meta, rest)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
