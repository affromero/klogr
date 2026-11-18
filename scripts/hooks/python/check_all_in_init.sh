#!/usr/bin/env bash
# Pre-commit hook: `__all__` may only live in `__init__.py`.
#
# The project restricts the `__all__` export list to package `__init__.py`
# files, where it usefully curates the package's public surface. In a
# regular module an `__all__` only shapes `from module import *` (which
# the project does not use) and otherwise drifts out of sync with the
# real definitions, so it is banned.
#
# This hook flags any module-level `__all__ = [...]` (plain or annotated
# assignment) in a file whose basename is not `__init__.py`. Assignments
# nested in classes or functions are ignored — only the module scope is
# meaningful for `__all__`.

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


def _targets(node: ast.stmt) -> list[ast.expr]:
    """Assignment targets for a module-level statement, if any."""
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    return []


def _check_file(path: str) -> list[str]:
    if os.path.basename(path) == "__init__.py":
        return []

    with open(path, encoding="utf-8") as handle:
        source = handle.read()

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [f"{path}: could not parse Python AST: {exc}"]

    errors: list[str] = []
    for node in tree.body:  # module scope only
        for target in _targets(node):
            if isinstance(target, ast.Name) and target.id == "__all__":
                errors.append(
                    f"{path}:{node.lineno}: `__all__` is only allowed in "
                    "`__init__.py`. Remove it from this module — the "
                    "project does not use `from module import *`."
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
