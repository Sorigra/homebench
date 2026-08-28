"""The lifecycle package stays headless (AD-005, TD-02).

Every module under ``homebench/lifecycle/`` is parsed and its import
statements are checked: nothing from ``homebench.providers``,
``homebench.tui`` or ``homebench.runner``, and nothing from ``rich`` or
``textual``. The single sanctioned exception is the repo's shared error type,
imported as ``from ..providers.base import ProviderError`` -- and only that
name, from only that module.
"""

import ast
import os

import pytest

import homebench.lifecycle

PACKAGE = "homebench.lifecycle"
PACKAGE_DIR = os.path.dirname(homebench.lifecycle.__file__)

#: Importing any of these (or a submodule of them) couples lifecycle to a
#: layer it must not depend on.
FORBIDDEN_ROOTS = (
    "homebench.providers",
    "homebench.tui",
    "homebench.runner",
    "rich",
    "textual",
)


def _is_forbidden(module: str) -> bool:
    return any(module == r or module.startswith(r + ".") for r in FORBIDDEN_ROOTS)


def _is_sanctioned(node: ast.ImportFrom, modules) -> bool:
    """Exactly ``from ..providers.base import ProviderError``.

    Accepts the absolute spelling too. Any other name, or any other module,
    is not covered by the exception.
    """
    return (
        modules == ["homebench.providers.base"]
        and [a.name for a in node.names] == ["ProviderError"]
    )


def _absolute_targets(node, package: str):
    """The absolute module path(s) an import node depends on."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if node.level == 0:
        return [node.module] if node.module else []
    parts = package.split(".")
    keep = len(parts) - (node.level - 1)
    if keep < 0:
        return []
    base = parts[:keep]
    if node.module:
        return [".".join(base + node.module.split("."))]
    # `from . import a, b` -- each name is a submodule of the base package
    return [".".join(base + [a.name]) for a in node.names]


def import_violations(source: str, package: str = PACKAGE):
    """Forbidden module paths imported by ``source``, as ``(lineno, module)``."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        modules = _absolute_targets(node, package)
        if isinstance(node, ast.ImportFrom) and _is_sanctioned(node, modules):
            continue
        for module in modules:
            if _is_forbidden(module):
                out.append((node.lineno, module))
    return out


def _lifecycle_modules():
    return sorted(
        os.path.join(PACKAGE_DIR, f)
        for f in os.listdir(PACKAGE_DIR)
        if f.endswith(".py")
    )


# =====================================================================
# The real package
# =====================================================================
def test_the_package_has_modules_to_scan():
    # a scanner that finds no files would pass vacuously
    names = {os.path.basename(p) for p in _lifecycle_modules()}
    assert {"__init__.py", "models.py", "router.py", "params.py",
            "manager.py"} <= names


@pytest.mark.parametrize("path", _lifecycle_modules(),
                         ids=lambda p: os.path.basename(p))
def test_lifecycle_module_imports_nothing_forbidden(path):
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    assert import_violations(source) == []


def test_providererror_is_the_only_thing_taken_from_providers():
    """The exception is narrow: only that one name crosses the boundary."""
    imported = set()
    for path in _lifecycle_modules():
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            for module in _absolute_targets(node, PACKAGE):
                if module.startswith("homebench.providers"):
                    imported.update((module, a.name) for a in node.names)
    assert imported == {("homebench.providers.base", "ProviderError")}


# =====================================================================
# The scanner itself detects a violation (or the tests above prove nothing)
# =====================================================================
@pytest.mark.parametrize("source, expected", [
    ("import rich", "rich"),
    ("from rich.console import Console", "rich.console"),
    ("import textual.widgets", "textual.widgets"),
    ("from ..runner import Runner", "homebench.runner"),
    ("from ..tui.app import run_tui", "homebench.tui.app"),
    ("from ..providers import get_provider", "homebench.providers"),
    ("from ..providers.ollama import OllamaProvider", "homebench.providers.ollama"),
    ("from homebench.runner import RunConfig", "homebench.runner"),
    ("import homebench.tui.app", "homebench.tui.app"),
    ("from .. import runner", "homebench.runner"),
])
def test_scanner_reports_a_forbidden_import(source, expected):
    assert [m for _line, m in import_violations(source)] == [expected]


def test_scanner_allows_the_sanctioned_providererror_import():
    assert import_violations("from ..providers.base import ProviderError") == []
    assert import_violations(
        "from homebench.providers.base import ProviderError") == []


def test_scanner_rejects_a_wider_import_from_providers_base():
    # widening the sanctioned import is still a boundary break
    assert import_violations(
        "from ..providers.base import Provider, ProviderError"
    ) == [(1, "homebench.providers.base")]


def test_scanner_ignores_the_packages_own_submodules():
    # lifecycle.router must not be mistaken for homebench.runner or providers
    assert import_violations("from .router import LlamaRouterClient") == []
    assert import_violations("from . import router, models") == []
