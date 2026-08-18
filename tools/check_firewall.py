#!/usr/bin/env python3
"""
Firewall check for districting-bench.

Enforces one rule: the ensemble generator never sees partisan or racial data.

This script was written before any implementation code, deliberately, so that
the thing being graded did not build its own grader. It must not be modified to
make a failing check pass.

Two checks:
  1. Import edges. Parses the AST of every .py file under src/ and verifies that
     cross-package imports respect the allowed edges in tools/firewall.yaml.
  2. Column references. For packages flagged forbidden_columns, scans identifiers
     and string constants for names matching the partisan/racial column denylist.

Exit codes:
  0  clean
  1  violation found
  2  configuration or usage error

Usage:
    python tools/check_firewall.py [--config tools/firewall.yaml] [--root src]
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    print("check_firewall: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    kind: str
    detail: str

    def render(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root.parent)
        except ValueError:
            rel = self.path
        return f"{rel}:{self.line}: [{self.kind}] {self.detail}"


def load_config(path: Path) -> dict:
    if not path.exists():
        print(f"check_firewall: config not found: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open() as fh:
        cfg = yaml.safe_load(fh)
    for key in ("packages", "column_denylist"):
        if key not in cfg:
            print(f"check_firewall: config missing '{key}'", file=sys.stderr)
            sys.exit(2)
    cfg.setdefault("column_allowlist", [])
    return cfg


def owning_package(path: Path, root: Path, packages: set[str]) -> str | None:
    """Return the src/ package a file belongs to, or None if outside them."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    if not rel.parts:
        return None
    head = rel.parts[0]
    return head if head in packages else None


def imported_packages(tree: ast.AST, packages: set[str]) -> list[tuple[int, str]]:
    """Every sibling package referenced by an import, with line numbers.

    Handles `import src.evaluate.x`, `from src.evaluate import y`,
    `from evaluate import y`, and relative `from ..evaluate import y`.
    """
    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.name.split(".")
                for part in head[:2]:
                    if part in packages:
                        found.append((node.lineno, part))
                        break
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            parts = module.split(".") if module else []
            for part in parts[:2]:
                if part in packages:
                    found.append((node.lineno, part))
                    break
            else:
                # `from . import evaluate` / `from .. import evaluate`
                if node.level and not module:
                    for alias in node.names:
                        if alias.name in packages:
                            found.append((node.lineno, alias.name))
    return found


def matches_denylist(text: str, denylist: list[str], allowlist: list[str]) -> str | None:
    """Return the offending denylist pattern, or None."""
    low = text.lower()
    for ok in allowlist:
        if ok.lower() in low:
            return None
    for bad in denylist:
        if bad.lower() in low:
            return bad
    return None


def scan_columns(
    tree: ast.AST, denylist: list[str], allowlist: list[str]
) -> list[tuple[int, str, str]]:
    """Identifiers and string constants matching the denylist."""
    hits: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            bad = matches_denylist(node.id, denylist, allowlist)
            if bad:
                hits.append((node.lineno, node.id, bad))
        elif isinstance(node, ast.Attribute):
            bad = matches_denylist(node.attr, denylist, allowlist)
            if bad:
                hits.append((node.lineno, node.attr, bad))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            bad = matches_denylist(node.value, denylist, allowlist)
            if bad:
                hits.append((node.lineno, repr(node.value), bad))
        elif isinstance(node, ast.arg):
            bad = matches_denylist(node.arg, denylist, allowlist)
            if bad:
                hits.append((node.lineno, node.arg, bad))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bad = matches_denylist(node.name, denylist, allowlist)
            if bad:
                hits.append((node.lineno, node.name, bad))
    return hits


def check(root: Path, cfg: dict) -> list[Violation]:
    packages: dict = cfg["packages"]
    names = set(packages)
    denylist: list[str] = cfg["column_denylist"]
    allowlist: list[str] = cfg["column_allowlist"]

    violations: list[Violation] = []

    for py in sorted(root.rglob("*.py")):
        pkg = owning_package(py, root, names)
        if pkg is None:
            continue

        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            violations.append(
                Violation(py, exc.lineno or 0, "parse-error", str(exc.msg))
            )
            continue

        allowed = set(packages[pkg].get("allowed_imports") or [])
        for lineno, target in imported_packages(tree, names):
            if target == pkg or target in allowed:
                continue
            violations.append(
                Violation(
                    py,
                    lineno,
                    "forbidden-import",
                    f"'{pkg}' may not import from '{target}' "
                    f"(allowed: {sorted(allowed) or 'none'})",
                )
            )

        if packages[pkg].get("forbidden_columns"):
            for lineno, token, pattern in scan_columns(tree, denylist, allowlist):
                violations.append(
                    Violation(
                        py,
                        lineno,
                        "partisan-data-in-generator",
                        f"{token} matches denied pattern '{pattern}'",
                    )
                )

    return violations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="tools/firewall.yaml", type=Path)
    ap.add_argument("--root", default="src", type=Path)
    args = ap.parse_args()

    if not args.root.exists():
        print(f"check_firewall: no {args.root}/ yet — nothing to check.")
        return 0

    cfg = load_config(args.config)
    violations = check(args.root, cfg)

    if not violations:
        print("check_firewall: clean.")
        return 0

    print(f"check_firewall: {len(violations)} violation(s)\n", file=sys.stderr)
    for v in violations:
        print("  " + v.render(args.root), file=sys.stderr)
    print(
        "\nThe firewall exists so the neutral baseline stays neutral.\n"
        "Fix the code. Do not edit tools/firewall.yaml to make this pass.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
