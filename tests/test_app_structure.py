"""Structural smoke test for the Streamlit entrypoint (app.py).

app.py is a Streamlit script, so it cannot simply be imported in a test (the
Streamlit calls need a running runtime). Instead we parse it with `ast` and
assert the invariants that, when broken, ship a silently broken dashboard:

  * the file parses at all (no syntax / indentation errors),
  * no two widgets share the same `key=` (Streamlit raises DuplicateWidgetID
    at runtime, which a compile check would never catch),
  * every `menu == "..."` branch maps to a real MODULES entry and every MODULES
    entry has a branch (no dead tab, no orphan branch),
  * every `switch_tab(...)` navigation target is a real MODULES entry.

This guards the exact class of regression that previously reached the file:
empty `with` bodies, a duplicated card, and a re-used widget key.
"""

import ast
import unittest
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _load_tree() -> ast.AST:
    source = APP_PATH.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(APP_PATH))


def _module_list(tree: ast.AST) -> list[str]:
    """Return the string literals assigned to the top-level MODULES list."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "MODULES" in targets and isinstance(node.value, ast.List):
                return [
                    elt.value
                    for elt in node.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
    raise AssertionError("MODULES list literal not found in app.py")


def _widget_keys(tree: ast.AST) -> list[str]:
    keys: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                    keys.append(kw.value.value)
    return keys


def _menu_branches(tree: ast.AST) -> list[str]:
    """String literals compared against `menu` in if/elif chains."""
    branches: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "menu":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    branches.append(comparator.value)
    return branches


def _switch_tab_targets(tree: ast.AST) -> list[str]:
    """First positional value passed via `args=(...)` to an `on_click=switch_tab`."""
    targets: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        on_click_switch = any(
            kw.arg == "on_click" and isinstance(kw.value, ast.Name) and kw.value.id == "switch_tab"
            for kw in node.keywords
        )
        if not on_click_switch:
            continue
        for kw in node.keywords:
            if kw.arg == "args" and isinstance(kw.value, ast.Tuple) and kw.value.elts:
                first = kw.value.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    targets.append(first.value)
    return targets


class AppStructureTests(unittest.TestCase):
    def setUp(self):
        self.tree = _load_tree()

    def test_app_parses(self):
        # _load_tree() raising SyntaxError would fail here with a clear message.
        self.assertIsNotNone(self.tree)

    def test_widget_keys_are_unique(self):
        keys = _widget_keys(self.tree)
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        self.assertEqual(duplicates, [], f"Duplicate Streamlit widget key(s): {duplicates}")

    def test_every_module_has_a_branch_and_vice_versa(self):
        modules = set(_module_list(self.tree))
        branches = set(_menu_branches(self.tree))
        self.assertEqual(
            branches,
            modules,
            f"Dead tabs (module without branch): {modules - branches}; "
            f"orphan branches (branch without module): {branches - modules}",
        )

    def test_switch_tab_targets_are_real_modules(self):
        modules = set(_module_list(self.tree))
        for target in _switch_tab_targets(self.tree):
            self.assertIn(target, modules, f"switch_tab target not in MODULES: {target!r}")


if __name__ == "__main__":
    unittest.main()
