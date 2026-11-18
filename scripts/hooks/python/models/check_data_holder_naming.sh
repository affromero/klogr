#!/usr/bin/env bash
# Pre-commit hook: flag base-less data-holder classes (BLOCKING).
#
# A class whose name reads like a data container (ends in Config, Result,
# Info, Args, Params, or Spec), carries annotated fields, has no behaviour
# (only dunder methods, if any), and inherits from nothing is almost
# always a plain struct that should be a `PydanticBaseModel` — it gets
# validation, serialization, and `extra="forbid"` for free. A bare class
# silently accepts garbage.
#
# A ClassDef is flagged ONLY when ALL hold:
#   * zero base classes (empty bases list), AND
#   * name ends in one of: Config Result Info Args Params Spec, AND
#   * at least one class-level annotated field (AnnAssign), AND
#   * no non-dunder methods (every Function/AsyncFunction it defines is a
#     `__dunder__`).
#
# Skipped:
#   * test files (test_*.py / *_test.py) and anything under a tests/ dir.
#   * class names matching Test* / _Stub* / _Fake* / _Mock*.
#   * classes nested inside a function body (locals, not public schemas).
#   * a class with a `# pydantic-exempt:` comment on the header line or in
#     the two lines directly above it.

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

NAME_SUFFIXES = ("Config", "Result", "Info", "Args", "Params", "Spec")
NAME_PREFIXES = ("Test", "_Stub", "_Fake", "_Mock")


def _is_test_path(path: str) -> bool:
    norm = path.replace("\\", "/")
    base = os.path.basename(norm)
    if base.startswith("test_") or base.endswith("_test.py"):
        return True
    return "/tests/" in norm or norm.startswith("tests/")


def _has_exempt_comment(source_lines: list[str], lineno: int) -> bool:
    """True if a `# pydantic-exempt:` marker sits on/above the header.

    Checks the class header line (``lineno`` is 1-based) and the two
    lines directly above it.
    """
    start = max(0, lineno - 3)
    for line in source_lines[start:lineno]:
        if "# pydantic-exempt:" in line:
            return True
    return False


def _has_annotated_field(cls: ast.ClassDef) -> bool:
    return any(isinstance(stmt, ast.AnnAssign) for stmt in cls.body)


def _has_non_dunder_method(cls: ast.ClassDef) -> bool:
    for stmt in cls.body:
        if not isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        name = stmt.name
        is_dunder = name.startswith("__") and name.endswith("__")
        if not is_dunder:
            return True
    return False


def _nested_class_ids(tree: ast.Module) -> set[int]:
    """Collect ids of ClassDefs that live inside a function body."""
    nested: set[int] = set()

    def _walk(node: ast.AST, in_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                if in_function:
                    nested.add(id(child))
                _walk(child, in_function)
            elif isinstance(
                child, ast.FunctionDef | ast.AsyncFunctionDef
            ):
                _walk(child, True)
            else:
                _walk(child, in_function)

    _walk(tree, False)
    return nested


def _check_file(path: str) -> list[str]:
    if _is_test_path(path):
        return []

    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [f"{path}: could not parse Python AST: {exc}"]

    nested = _nested_class_ids(tree)
    pydantic_dataclasses = {
        alias.asname or alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "pydantic.dataclasses"
        for alias in node.names
        if alias.name == "dataclass"
    }

    errors: list[str] = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        if id(cls) in nested:
            continue
        if cls.bases or cls.keywords:
            continue
        decorators = (
            node.func if isinstance(node, ast.Call) else node
            for node in cls.decorator_list
        )
        if any(
            isinstance(node, ast.Name) and node.id in pydantic_dataclasses
            for node in decorators
        ):
            continue
        if not cls.name.endswith(NAME_SUFFIXES):
            continue
        if cls.name.startswith(NAME_PREFIXES):
            continue
        if not _has_annotated_field(cls):
            continue
        if _has_non_dunder_method(cls):
            continue
        if _has_exempt_comment(source_lines, cls.lineno):
            continue
        errors.append(
            f"{path}:{cls.lineno}: base-less data-holder `{cls.name}` "
            "should use a Pydantic model or dataclass, or add a "
            "`# pydantic-exempt: <reason>` comment above it."
        )
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
