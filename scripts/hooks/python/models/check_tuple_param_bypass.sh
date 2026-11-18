#!/usr/bin/env bash
# Pre-commit hook: flag 3+ position heterogeneous tuple params (BLOCKING).
#
# Ruff's PLR0913 (`max-args = 5`) pushes wide signatures toward a single
# `PydanticBaseModel` argument so each input gets a name AND a docstring
# sentence. A tuple parameter defeats that entirely: `def f(x: tuple[str,
# int, float])` packs three unrelated, undocumented values behind one
# positional slot — you can no longer tell what each element is.
#
# A parameter annotation is flagged ONLY when it is a fixed-length tuple
# with THREE OR MORE positions AND heterogeneous element types (>= 2
# distinct type expressions), after peeling one `X | None` / `Optional[X]`
# layer. A two-position tuple is a readable pair; a same-type tuple is a
# value group / collection — neither hides "what is each" the way a bundle
# of 3+ distinct values does.
#   * FLAG:  tuple[str, int, float]   tuple[int, int, float, float, str]
#   * allow: tuple[str, int]   tuple[int, float]  (two positions — a pair)
#   * allow: tuple[int, int]   tuple[X, X, X]  (same-type value groups)
#   * allow: tuple[str, ...]              (variadic homogeneous collection)
#   * allow: tuple  /  tuple[int]         (opaque or single element)
#
# Skipped:
#   * test files (test_*.py / *_test.py) and anything under a tests/ dir.
#   * *args / **kwargs (their annotation is an element type, not a bundle).
#   * a parameter (or its enclosing `def`) with a `# pydantic-exempt:`
#     comment on that line or the two lines directly above it.

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

TUPLE_NAMES = ("tuple", "Tuple")


def _is_test_path(path: str) -> bool:
    norm = path.replace("\\", "/")
    base = os.path.basename(norm)
    if base.startswith("test_") or base.endswith("_test.py"):
        return True
    return "/tests/" in norm or norm.startswith("tests/")


def _has_exempt_comment(source_lines: list[str], *linenos: int) -> bool:
    """True if a `# pydantic-exempt:` marker sits on any given line or the
    two lines directly above it (``linenos`` are 1-based)."""
    for lineno in linenos:
        start = max(0, lineno - 3)
        for line in source_lines[start:lineno]:
            if "# pydantic-exempt:" in line:
                return True
    return False


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _unwrap_optional(node: ast.expr) -> ast.expr:
    """Peel one `X | None` / `Optional[X]` layer to reach the inner type."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        if _is_none(node.right):
            return _unwrap_optional(node.left)
        if _is_none(node.left):
            return _unwrap_optional(node.right)
        return node
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Optional"
    ):
        return _unwrap_optional(node.slice)
    return node


def _is_tuple_subscript(node: ast.expr) -> bool:
    if not isinstance(node, ast.Subscript):
        return False
    value = node.value
    if isinstance(value, ast.Name):
        return value.id in TUPLE_NAMES
    if isinstance(value, ast.Attribute):
        return value.attr in TUPLE_NAMES
    return False


def _tuple_elements(node: ast.expr) -> list[ast.expr] | None:
    """Fixed-length element type nodes of a tuple annotation, else None.

    None means "not something to flag": not a tuple, variadic
    `tuple[X, ...]`, unparameterized `tuple`, or empty `tuple[()]`.
    """
    if not _is_tuple_subscript(node):
        return None
    sl = node.slice
    elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
    if not elts:
        return None
    if any(isinstance(e, ast.Constant) and e.value is Ellipsis for e in elts):
        return None
    return elts


def _is_flagged_tuple(elts: list[ast.expr]) -> bool:
    """Flagged only when 3+ positions carry 2+ distinct type expressions.

    Two positions is a readable pair; a same-type tuple is a value group.
    Only a bundle of 3+ heterogeneous values hides "what is each".
    """
    if len(elts) < 3:
        return False
    return len({ast.unparse(e) for e in elts}) >= 2


def _iter_params(func: ast.FunctionDef | ast.AsyncFunctionDef):
    args = func.args
    yield from args.posonlyargs
    yield from args.args
    yield from args.kwonlyargs


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

    errors: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for arg in _iter_params(func):
            if arg.annotation is None:
                continue
            inner = _unwrap_optional(arg.annotation)
            elts = _tuple_elements(inner)
            if elts is None or not _is_flagged_tuple(elts):
                continue
            if _has_exempt_comment(source_lines, arg.lineno, func.lineno):
                continue
            errors.append(
                f"{path}:{arg.lineno}: parameter `{arg.arg}` packs 3+ "
                f"values into the heterogeneous tuple `{ast.unparse(inner)}`"
                ". Bundle them into a Pydantic model with named, documented "
                "fields, or add a `# pydantic-exempt: <reason>` comment."
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
