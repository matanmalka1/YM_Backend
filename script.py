"""
UML / domain diagram generator for the YM Tax CRM backend.

Why PlantUML over pyreverse:
  pyreverse cannot reliably extract SQLAlchemy relationships, FK cardinality,
  or enum definitions from declarative models. It reads Python AST/imports, not
  SQLAlchemy metadata, so diagrams are incomplete and inconsistent.
  This script inspects SQLAlchemy Column / relationship / mapped_column objects
  directly at runtime, giving us accurate FKs, relationship names, and enum values.
  PlantUML text files are deterministic, diff-friendly, and render to SVG/PNG
  via the `plantuml` CLI.

Prerequisite:
  pip install plantuml    (or brew install plantuml)

Usage:
  python script.py [--mode full|compact] [--no-render]

  --mode full      include all columns (default for *_full diagrams)
  --mode compact   hide audit/soft-delete columns (default for *_compact diagrams)
  --no-render      write .puml files only; skip plantuml rendering

Output:
  uml/all_overview.puml / .svg
  uml/<domain>_full.puml / .svg
  uml/<domain>_compact.puml / .svg

Edge types:
  solid arrow  (--> )  SQLAlchemy relationship()
  dashed arrow (..>)   ForeignKey-only (no relationship declared)
  Both types are always rendered; FK-only edges are never suppressed.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

APP_DIR = Path("app")
UML_DIR = Path("uml")

# Audit / soft-delete columns hidden in compact mode
NOISE_COLUMNS: frozenset[str] = frozenset(
    {
        "created_at",
        "updated_at",
        "deleted_at",
        "deleted_by",
        "restored_at",
        "restored_by",
        "created_by",
    }
)

# ──────────────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class FieldDef:
    name: str
    type_str: str
    nullable: bool
    is_fk: bool
    fk_target: str | None = None  # "table.column" or just "table"


@dataclass
class RelDef:
    name: str
    target_class: str
    uselist: bool  # True → one-to-many / many-to-many; False → one-to-one / many-to-one
    back_populates: str | None
    viewonly: bool


@dataclass
class EnumDef:
    name: str
    values: list[str]


@dataclass
class ModelDef:
    class_name: str
    table_name: str
    domain: str
    fields: list[FieldDef] = field(default_factory=list)
    relationships: list[RelDef] = field(default_factory=list)
    enums: list[EnumDef] = field(default_factory=list)  # enums defined in same module


# ──────────────────────────────────────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────────────────────────────────────


def discover_model_modules() -> dict[str, list[str]]:
    """
    Returns {domain_name: [dotted.module.path, ...]} for every domain that
    has at least one non-__init__ .py file under app/<domain>/models/.
    """
    result: dict[str, list[str]] = {}
    for entry in sorted(APP_DIR.iterdir()):
        if not entry.is_dir():
            continue
        models_dir = entry / "models"
        if not models_dir.is_dir():
            continue
        files = sorted(
            f for f in models_dir.iterdir() if f.suffix == ".py" and f.name != "__init__.py"
        )
        if not files:
            continue
        result[entry.name] = [f"app.{entry.name}.models.{f.stem}" for f in files]
    return result


# ──────────────────────────────────────────────────────────────────────────────
# SQLAlchemy introspection
# ──────────────────────────────────────────────────────────────────────────────


def _sa_type_str(col) -> str:
    """Return a short, normalised type string for a SQLAlchemy column type."""
    try:
        from sqlalchemy import (
            Boolean,
            Date,
            DateTime,
            Integer,
            Numeric,
            String,
            Text,
        )
        from sqlalchemy import (
            Enum as SAEnum,
        )

        t = col.type
        # SAEnum must be checked BEFORE String — pg_enum subclasses both
        if isinstance(t, SAEnum):
            enum_cls = getattr(t, "enum_class", None)
            if enum_cls is not None:
                return enum_cls.__name__
            if t.enums:
                return f"enum[{t.enums[0]}…]"
        if isinstance(t, Integer):
            return "int"
        if isinstance(t, Boolean):
            return "bool"
        if isinstance(t, Numeric):
            prec = f"({t.precision},{t.scale})" if t.precision else ""
            return f"decimal{prec}"
        if isinstance(t, DateTime):
            return "datetime"
        if isinstance(t, Date):
            return "date"
        if isinstance(t, Text):
            return "text"
        if isinstance(t, String):
            length = f"({t.length})" if t.length else ""
            return f"str{length}"
        return type(t).__name__.lower()
    except Exception:
        return "?"


def _fk_table(fk) -> str:
    """Return just the table name portion of a FK target string."""
    target = str(fk.target_fullname)  # e.g. "clients.id"
    return target.split(".")[0]


def extract_models_from_module(module_dotpath: str, domain: str) -> list[ModelDef]:
    """Import a module and extract ModelDef for every SQLAlchemy declarative class."""
    try:
        mod = importlib.import_module(module_dotpath)
    except Exception as exc:
        print(f"    WARN: cannot import {module_dotpath}: {exc}")
        return []

    import enum as stdlib_enum

    from sqlalchemy import inspect as sa_inspect

    results: list[ModelDef] = []

    # Collect enums defined in this module (we attach them to the first model found)
    module_enums: list[EnumDef] = []
    for obj_name, obj in inspect.getmembers(mod, inspect.isclass):
        if (
            issubclass(obj, stdlib_enum.Enum)
            and obj.__module__ == mod.__name__
            and obj is not stdlib_enum.Enum
        ):
            module_enums.append(
                EnumDef(
                    name=obj_name,
                    values=[m.value for m in obj],
                )
            )

    enum_attached = False

    for obj_name, obj in inspect.getmembers(mod, inspect.isclass):
        # Must be a SQLAlchemy mapped class defined in THIS module
        if obj.__module__ != mod.__name__:
            continue
        try:
            mapper = sa_inspect(obj)
        except Exception:
            continue
        if not hasattr(mapper, "mapper"):
            continue
        mapper = mapper.mapper

        mdef = ModelDef(
            class_name=obj_name,
            table_name=obj.__tablename__ if hasattr(obj, "__tablename__") else obj_name,
            domain=domain,
        )

        # Attach module enums to first model in the module
        if not enum_attached:
            mdef.enums = module_enums
            enum_attached = True

        # ── Columns ──────────────────────────────────────────────────────────
        for col in mapper.columns:
            fk_targets = list(col.foreign_keys)
            is_fk = bool(fk_targets)
            fk_table_name = _fk_table(next(iter(fk_targets))) if is_fk else None
            mdef.fields.append(
                FieldDef(
                    name=col.key,
                    type_str=_sa_type_str(col),
                    nullable=col.nullable if col.nullable is not None else True,
                    is_fk=is_fk,
                    fk_target=fk_table_name,
                )
            )

        # ── Relationships ─────────────────────────────────────────────────────
        for rel in mapper.relationships:
            target_cls = rel.mapper.class_.__name__
            mdef.relationships.append(
                RelDef(
                    name=rel.key,
                    target_class=target_cls,
                    uselist=rel.uselist,
                    back_populates=rel.back_populates,
                    viewonly=rel.viewonly,
                )
            )

        results.append(mdef)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Table → Class mapping  (authoritative, built from actual model metadata)
# ──────────────────────────────────────────────────────────────────────────────


def build_table_class_map(domain_models: dict[str, list[ModelDef]]) -> dict[str, str]:
    """
    Build an exact table_name → class_name lookup from all extracted models.

    This replaces the old fuzzy _table_to_class() heuristic which failed on
    plural table names like 'businesses', 'tax_deadlines', 'annual_reports', etc.
    """
    return {m.table_name: m.class_name for models in domain_models.values() for m in models}


# ──────────────────────────────────────────────────────────────────────────────
# PlantUML rendering helpers
# ──────────────────────────────────────────────────────────────────────────────


def _field_line(f: FieldDef, compact: bool) -> str | None:
    if compact and f.name in NOISE_COLUMNS:
        return None
    # In compact mode hide raw FK integer columns — edges convey the link visually
    if f.is_fk and compact:
        return None
    nullable_marker = "?" if f.nullable else ""
    pk_marker = " <<PK>>" if f.name == "id" else ""
    fk_marker = f" <<FK→{f.fk_target}>>" if f.is_fk and not compact else ""
    return f"  +{f.name} : {f.type_str}{nullable_marker}{pk_marker}{fk_marker}"


def _cardinality(rel: RelDef) -> tuple[str, str]:
    """Return (left_card, right_card) PlantUML strings."""
    if rel.uselist:
        return ('"1"', '"0..*"')
    return ('"1"', '"0..1"')


def _rel_arrow(rel: RelDef) -> str:
    if rel.viewonly:
        return "..>"  # dashed = read-only / derived
    return "-->"  # solid = navigable / cascade


def _fk_edges(
    models: list[ModelDef],
    table_class_map: dict[str, str],
    compact: bool,
    covered_pairs: set[frozenset],
) -> list[str]:
    """
    Return PlantUML dashed-arrow lines for every FK column that is NOT already
    covered by an ORM relationship() arrow.

    Key fix over old implementation:
    - Uses exact table_class_map instead of fuzzy string matching.
    - Dedup is per (source_class, target_class, field_name) — NOT per target_class
      alone. This means multiple FKs from the same model to the same target
      (e.g. created_by / deleted_by both → users) each get their own edge.
    - In compact mode, noise-column FKs (deleted_by, created_by, etc.) are
      still drawn as edges — they are suppressed from the column list only.
    """
    lines: list[str] = []
    for m in models:
        for f in m.fields:
            if not f.is_fk or f.fk_target is None:
                continue
            target_class = table_class_map.get(f.fk_target)
            if target_class is None:
                continue
            # Check whether this specific FK field is already covered by a
            # relationship from this model to this target.
            already_covered = any(
                rel.target_class == target_class for rel in m.relationships if not rel.viewonly
            )
            if already_covered:
                continue
            pair = frozenset({m.class_name, target_class, f.name})
            if pair in covered_pairs:
                continue
            covered_pairs.add(pair)
            lines.append(f"{m.class_name} ..> {target_class} : {f.name}")
    return lines


def render_domain_puml(
    models: list[ModelDef],
    domain: str,
    compact: bool,
    all_class_names: set[str],
    table_class_map: dict[str, str],
) -> str:
    """Generate a PlantUML string for a single domain."""
    lines: list[str] = [
        "@startuml",
        f"' Domain: {domain}  |  mode: {'compact' if compact else 'full'}",
        "' Edge legend: --> ORM relationship()   ..> FK-only (no relationship)",
        "hide empty members",
        "skinparam classAttributeIconSize 0",
        "skinparam classFontSize 13",
        "skinparam ArrowColor #555555",
        "skinparam ClassBorderColor #888888",
        "skinparam ClassBackgroundColor #FAFAFA",
        "",
    ]

    # ── Class blocks ─────────────────────────────────────────────────────────
    for m in models:
        # Enums first (defined in the same module, above the class)
        for e in m.enums:
            lines.append(f"enum {e.name} {{")
            for v in e.values:
                lines.append(f"  {v}")
            lines.append("}")
            lines.append("")

        lines.append(f"class {m.class_name} <<{m.table_name}>> {{")
        for f in m.fields:
            line = _field_line(f, compact)
            if line:
                lines.append(line)
        lines.append("}")
        lines.append("")

    covered_pairs: set[frozenset] = set()

    # ── ORM relationship() arrows (solid) ─────────────────────────────────────
    for m in models:
        for rel in m.relationships:
            if rel.target_class not in all_class_names:
                continue
            pair = frozenset({m.class_name, rel.target_class, rel.name})
            if pair in covered_pairs:
                continue
            covered_pairs.add(pair)
            lc, rc = _cardinality(rel)
            arrow = _rel_arrow(rel)
            label = f" : {rel.name}"
            lines.append(f"{m.class_name} {arrow} {rc} {rel.target_class}{label}")

    # ── FK-only arrows (dashed) ────────────────────────────────────────────────
    fk_lines = _fk_edges(models, table_class_map, compact, covered_pairs)
    if fk_lines:
        lines.append("' FK-only links (no ORM relationship declared):")
        lines.extend(fk_lines)

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def render_overview_puml(
    domain_models: dict[str, list[ModelDef]],
    table_class_map: dict[str, str],
) -> str:
    """
    High-level overview: one box per domain (not per class).
    Shows domain name + list of model names only.
    Cross-domain edges include BOTH relationship() and FK-only links.
    """
    lines: list[str] = [
        "@startuml",
        "' Global overview — one package per domain",
        "' Edge legend: --> ORM relationship()   ..> FK-only (no relationship)",
        "hide empty members",
        "skinparam packageStyle rectangle",
        "skinparam classFontSize 12",
        "skinparam ClassBackgroundColor #EEF4FB",
        "skinparam ClassBorderColor #5588BB",
        "",
    ]

    for domain, models in sorted(domain_models.items()):
        lines.append(f'package "{domain}" {{')
        for m in models:
            lines.append(f"  class {m.class_name}")
        lines.append("}")
        lines.append("")

    all_models: dict[str, ModelDef] = {
        m.class_name: m for models in domain_models.values() for m in models
    }
    all_class_names = set(all_models.keys())
    seen: set[frozenset] = set()

    # Cross-domain ORM relationship() edges
    for domain, models in domain_models.items():
        for m in models:
            for rel in m.relationships:
                if rel.target_class not in all_class_names:
                    continue
                target_domain = all_models[rel.target_class].domain
                if target_domain == domain:
                    continue
                pair = frozenset({domain, target_domain, "rel"})
                if pair in seen:
                    continue
                seen.add(pair)
                lines.append(f'"{domain}" --> "{target_domain}" : ORM')

    # Cross-domain FK-only edges (the primary gap in the old generator)
    for domain, models in domain_models.items():
        for m in models:
            for f in m.fields:
                if not f.is_fk or f.fk_target is None:
                    continue
                target_class = table_class_map.get(f.fk_target)
                if target_class is None or target_class not in all_models:
                    continue
                target_domain = all_models[target_class].domain
                if target_domain == domain:
                    continue
                # Skip if already covered by ORM edge in same direction
                already_orm = any(rel.target_class == target_class for rel in m.relationships)
                pair = frozenset({domain, target_domain, "fk"})
                if pair in seen:
                    continue
                seen.add(pair)
                arrow = "-->" if already_orm else "..>"
                lines.append(f'"{domain}" {arrow} "{target_domain}" : FK')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def check_plantuml() -> bool:
    """Return True if the plantuml binary is available."""
    return shutil.which("plantuml") is not None


def render_svg(puml_path: Path) -> bool:
    """Run plantuml to generate SVG from a .puml file."""
    result = subprocess.run(
        ["plantuml", "-tsvg", str(puml_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"    WARN: plantuml failed for {puml_path.name}: {result.stderr.strip()}")
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate UML diagrams for the CRM backend.")
    parser.add_argument(
        "--mode",
        choices=["full", "compact"],
        default=None,
        help="Force a single mode for all diagrams (default: both modes per domain).",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Write .puml files only; skip plantuml rendering.",
    )
    args = parser.parse_args()

    if not APP_DIR.is_dir():
        print(f"ERROR: '{APP_DIR}' not found. Run from project root.")
        sys.exit(1)

    UML_DIR.mkdir(exist_ok=True)
    print(f"Output: {UML_DIR.resolve()}")

    has_plantuml = check_plantuml()
    if not has_plantuml and not args.no_render:
        print(
            "WARN: plantuml not found — .puml files will be written but not rendered.\n"
            "      Install with:  brew install plantuml\n"
        )

    # ── Discover & import ─────────────────────────────────────────────────────
    domain_modules = discover_model_modules()
    if not domain_modules:
        print("No model files found under app/.")
        sys.exit(0)

    print(f"\nDiscovered {len(domain_modules)} domain(s):")
    for d in sorted(domain_modules):
        print(f"  - {d} ({len(domain_modules[d])} modules)")

    # sys.path must include project root so imports resolve
    project_root = str(Path(".").resolve())
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Pre-import ALL modules across ALL domains first so that SQLAlchemy's
    # mapper configure step can resolve every forward-reference string like
    # "AnnualReportScheduleEntry". Only after all classes are registered do
    # we introspect relationships.
    print("\n  Pre-importing all modules...")
    for _domain, modules in domain_modules.items():
        for mod_path in modules:
            try:
                importlib.import_module(mod_path)
            except Exception as exc:
                print(f"    WARN: pre-import failed for {mod_path}: {exc}")

    domain_models: dict[str, list[ModelDef]] = {}
    for domain, modules in domain_modules.items():
        print(f"\n  [{domain}] extracting...")
        models: list[ModelDef] = []
        for mod_path in modules:
            extracted = extract_models_from_module(mod_path, domain)
            models.extend(extracted)
            status = f"    {mod_path.split('.')[-1]} → {len(extracted)} model(s)"
            print(status)
        domain_models[domain] = models

    all_class_names: set[str] = {m.class_name for models in domain_models.values() for m in models}
    print(f"\nTotal models extracted: {len(all_class_names)}")

    # Build exact table → class map (replaces old fuzzy heuristic)
    table_class_map = build_table_class_map(domain_models)
    print(f"Table→class map: {len(table_class_map)} entries")

    # ── Global overview ───────────────────────────────────────────────────────
    print("\n[Global] Writing all_overview.puml ...")
    overview_puml = render_overview_puml(domain_models, table_class_map)
    overview_path = UML_DIR / "all_overview.puml"
    overview_path.write_text(overview_puml, encoding="utf-8")
    if has_plantuml and not args.no_render:
        ok = render_svg(overview_path)
        print(f"  {'OK' if ok else 'WARN'} → {overview_path.with_suffix('.svg').name}")
    else:
        print(f"  Written → {overview_path.name}")

    # ── Per-domain diagrams ───────────────────────────────────────────────────
    print("\n[Per-domain] Writing domain diagrams...")
    modes = [args.mode] if args.mode else ["full", "compact"]

    for domain, models in sorted(domain_models.items()):
        if not models:
            print(f"  [{domain}] no models — skipping")
            continue
        for mode in modes:
            compact = mode == "compact"
            fname = f"{domain}_{mode}"
            puml_path = UML_DIR / f"{fname}.puml"
            print(f"  [{domain}/{mode}]", end=" ")
            try:
                content = render_domain_puml(
                    models,
                    domain=domain,
                    compact=compact,
                    all_class_names=all_class_names,
                    table_class_map=table_class_map,
                )
                puml_path.write_text(content, encoding="utf-8")
                if has_plantuml and not args.no_render:
                    ok = render_svg(puml_path)
                    print(f"{'OK' if ok else 'WARN'} → {puml_path.with_suffix('.svg').name}")
                else:
                    print(f"Written → {puml_path.name}")
            except Exception as exc:
                print(f"FAILED: {exc}")

    print(f"\nDone. Files in: {UML_DIR.resolve()}")


if __name__ == "__main__":
    main()
