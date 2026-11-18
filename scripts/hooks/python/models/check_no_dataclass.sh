#!/usr/bin/env bash
# Pre-commit hook: ban stdlib `@dataclass` in first-party code.
#
# The project avoids `@dataclass` from the standard library: it lacks the
# validation and serialization the project relies on. Use
# a Pydantic model or validated dataclass.
#
# Pydantic's own dataclass — `from pydantic.dataclasses import dataclass`
# — IS blessed (it carries the validation policy via
# `@dataclass(config=ConfigDict(...))`). Any file that imports the
# pydantic dataclass is skipped wholesale, since within such a file the
# `dataclass` name unambiguously refers to the pydantic variant.
#
# This hook flags, on every ClassDef, a decorator that is the stdlib
# dataclass — either the bare name `@dataclass` or an attribute form
# `@dataclasses.dataclass` (with or without a `(...)` call).

set -euo pipefail

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - "$@" <<'PY'
from __future__ import annotations

import ast
import sys


def _imports_pydantic_dataclass(tree: ast.Module) -> bool:
    """True if the file imports pydantic's blessed dataclass."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "pydantic.dataclasses":
            continue
        for name in node.names:
            if name.name == "dataclass":
                return True
    return False


def _decorator_name(node: ast.AST) -> str | None:
    """Resolve a decorator to its terminal attribute/name.

    Unwraps a ``@deco(...)`` call to its callee, then reads the final
    ``Name.id`` or ``Attribute.attr``.
    """
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _check_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        source = handle.read()

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [f"{path}: could not parse Python AST: {exc}"]

    # Files importing pydantic's dataclass are exempt: the `dataclass`
    # name there is the blessed variant.
    if _imports_pydantic_dataclass(tree):
        return []

    errors: list[str] = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for decorator in cls.decorator_list:
            if _decorator_name(decorator) == "dataclass":
                errors.append(
                    f"{path}:{cls.lineno}: class `{cls.name}` uses stdlib "
                    "`@dataclass`; use a Pydantic model or validated dataclass."
                )
                break
    return errors


all_errors: list[str] = []
for filename in sys.argv[1:]:
    if not filename.endswith(".py"):
        continue
    try:
        with open(filename, encoding="utf-8"):
            pass
    except FileNotFoundError:
        continue
    all_errors.extend(_check_file(filename))

if all_errors:
    sys.stdout.write("\n".join(all_errors))
    sys.stdout.write("\n")
    raise SystemExit(1)
PY
