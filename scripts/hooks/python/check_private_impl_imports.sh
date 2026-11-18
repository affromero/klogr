#!/usr/bin/env bash
# Pre-commit hook: `_impl.py` is private to its package `__init__.py`.
#
# A module named `_impl` is only meaningful as the hidden implementation
# target for a package initializer. If any other file needs to import,
# monkeypatch, or otherwise name it directly, the module needs a real
# domain name instead.

set -euo pipefail

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - "$@" <<'PY'
from __future__ import annotations

import ast
import os
import sys


def _has_impl_segment(module: str | None) -> bool:
    if module is None:
        return False
    return "_impl" in module.split(".")


def _is_adjacent_init_import(node: ast.ImportFrom) -> bool:
    if node.level != 1:
        return False
    if node.module == "_impl":
        return True
    return node.module is None and any(
        alias.name == "_impl" for alias in node.names
    )


def _private_impl_error(path: str, line: int) -> str:
    return (
        f"{path}:{line}: `_impl` modules may only be imported by the "
        "adjacent package `__init__.py` with a relative import. Rename the "
        "module to a domain name before using it anywhere else."
    )


def _check_file(path: str) -> list[str]:
    is_init = os.path.basename(path) == "__init__.py"

    with open(path, encoding="utf-8") as handle:
        source = handle.read()

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [f"{path}: could not parse Python AST: {exc}"]

    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _has_impl_segment(alias.name):
                    errors.append(_private_impl_error(path, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            names_impl = any(alias.name == "_impl" for alias in node.names)
            if _has_impl_segment(module) or names_impl:
                if is_init and _is_adjacent_init_import(node):
                    continue
                errors.append(_private_impl_error(path, node.lineno))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "._impl" in node.value
        ):
            errors.append(
                f"{path}:{node.lineno}: direct `_impl` module references "
                "are not allowed outside `__init__.py`. Use a real module "
                "name for imports, patch targets, and route constants."
            )
    return errors


all_errors: list[str] = []
for filename in sys.argv[1:]:
    if not filename.endswith(".py") or not os.path.isfile(filename):
        continue
    all_errors.extend(_check_file(filename))

if all_errors:
    sys.stdout.write("\n".join(all_errors))
    sys.stdout.write("\n")
    raise SystemExit(1)
PY
