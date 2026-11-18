#!/usr/bin/env bash
# Pre-commit hook: keep package __init__.py files lightweight.
#
# Package initializers should define import/export surfaces from their own
# package, not hold implementation logic or reexport cross-package names.
# This hook checks every __init__.py file passed by pre-commit, including all
# files during `pre-commit run --all-files`.

set -euo pipefail

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - "$@" <<'PY'
from __future__ import annotations

import ast
import sys
import os

IMPLEMENTATION_NODES = (
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.For,
    ast.Match,
    ast.Try,
    ast.While,
    ast.With,
)


def _is_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"


def _has_call(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Call) for child in ast.walk(node))


def _targets_only_all(node: ast.Assign | ast.AnnAssign) -> bool:
    if isinstance(node, ast.Assign):
        return all(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
    return isinstance(node.target, ast.Name) and node.target.id == "__all__"


def _literal_string_collection(node: ast.AST) -> bool:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return False
    return all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in node.elts
    )


def _is_allowed_all_assignment(node: ast.Assign | ast.AnnAssign) -> bool:
    value = node.value
    if value is None:
        return False
    return _targets_only_all(node) and _literal_string_collection(value)


def _package_name(path: str) -> str:
    package_dir = os.path.dirname(path)
    return package_dir.replace(os.sep, ".")


def _same_package_module(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")


def _is_allowed_import_from(node: ast.ImportFrom, package: str) -> bool:
    if node.module == "__future__":
        return True
    if node.module == "typing":
        return all(alias.name == "TYPE_CHECKING" for alias in node.names)
    if any(alias.name == "__getattr__" for alias in node.names):
        return False
    if any(alias.name == "*" for alias in node.names):
        return False
    if node.level == 1:
        return True
    if node.level > 1:
        return False
    if node.module is None:
        return False
    return _same_package_module(node.module, package)


def _is_allowed_import(node: ast.Import, package: str) -> bool:
    if any(
        alias.name.rsplit(".", maxsplit=1)[-1] == "__getattr__"
        for alias in node.names
    ):
        return False
    return all(_same_package_module(alias.name, package) for alias in node.names)


def _type_checking_errors(path: str, node: ast.If, package: str) -> list[str]:
    errors: list[str] = []
    for child in node.body:
        if isinstance(child, ast.ImportFrom) and _is_allowed_import_from(
            child, package
        ):
            continue
        if isinstance(child, ast.Import) and _is_allowed_import(child, package):
            continue
        errors.append(
            f"{path}:{child.lineno}: TYPE_CHECKING blocks in __init__.py "
            "may contain only imports from the same package."
        )
    return errors


def _implementation_errors(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        source = handle.read()

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [f"{path}: could not parse Python AST: {exc}"]

    errors: list[str] = []
    package = _package_name(path)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            errors.append(
                f"{path}:{node.lineno}: package __init__.py contains "
                "module-level FunctionDef. Move implementation into a "
                "real module and reexport from the same package only."
            )
            continue
        if isinstance(node, ast.ImportFrom):
            if _is_allowed_import_from(node, package):
                continue
            errors.append(
                f"{path}:{node.lineno}: package __init__.py may only "
                "import from its own package. Do not reexport "
                "cross-package names."
            )
            continue
        if isinstance(node, ast.Import):
            if _is_allowed_import(node, package):
                continue
            errors.append(
                f"{path}:{node.lineno}: package __init__.py may not use "
                "`import ...` for unrelated packages. Reexport only "
                "same-package modules or names."
            )
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if _is_allowed_all_assignment(node):
                continue
            errors.append(
                f"{path}:{node.lineno}: package __init__.py may only "
                "assign a literal string collection to __all__."
            )
            continue
        if isinstance(node, IMPLEMENTATION_NODES):
            errors.append(
                f"{path}:{node.lineno}: package __init__.py contains "
                f"module-level {type(node).__name__}. Move implementation "
                "into a real module and reexport from the same package only."
            )
            continue
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            errors.extend(_type_checking_errors(path, node, package))
            continue
        if isinstance(node, ast.If):
            errors.append(
                f"{path}:{node.lineno}: package __init__.py contains "
                "module-level control flow. Move implementation into a "
                "real module and reexport from the same package only."
            )
            continue
        if isinstance(node, ast.AugAssign):
            errors.append(
                f"{path}:{node.lineno}: package __init__.py may only "
                "assign a literal string collection to __all__."
            )
            continue
        if isinstance(node, ast.Expr) and _has_call(node):
            errors.append(
                f"{path}:{node.lineno}: package __init__.py executes a "
                "module-level call. Move side-effect logic into a real "
                "module or an explicit entry point."
            )
    return errors


all_errors: list[str] = []
for filename in sys.argv[1:]:
    if os.path.basename(filename) != "__init__.py":
        continue
    if not filename.endswith(".py") or not os.path.isfile(filename):
        continue
    all_errors.extend(_implementation_errors(filename))

if all_errors:
    sys.stdout.write("\n".join(all_errors))
    sys.stdout.write("\n")
    raise SystemExit(1)
PY
