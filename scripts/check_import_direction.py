#!/usr/bin/env python3
"""Fail if anything under core/ imports from an outer-layer package."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN_FROM_CORE = {
    "connectors",
    "execution_backends",
    "strategies",
    "quant",
    "backtesting",
    "optimization",
    "machine_learning",
    "database",
    "plugins",
    "analytics",
    "reporting",
    "notifications",
    "benchmarks",
    "research_lab",
    "news_intelligence",
    "decision_engine",
    "macro_data",
}


def _top_level_module(name: str) -> str:
    return name.split(".", 1)[0]


def check_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.module else []
        else:
            continue
        for module in modules:
            top = _top_level_module(module)
            if top in FORBIDDEN_FROM_CORE:
                violations.append(f"{path}:{node.lineno}: core/ must not import '{module}'")
    return violations


def main() -> int:
    core_root = Path(__file__).resolve().parent.parent / "core"
    violations: list[str] = []
    for path in core_root.rglob("*.py"):
        violations.extend(check_file(path))

    if violations:
        print("Import direction violations found:")
        for violation in violations:
            print(f"  {violation}")
        return 1

    print("Import direction check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
