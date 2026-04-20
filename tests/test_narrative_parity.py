"""AST-based parity test for narrative_en.py and narrative_zh.py.

Ensures both locale narrative modules expose the same public function set
and that each dimension function cites the same set of metric keys via
metrics["<key>"] or metrics.get("<key>", ...). See
docs/superpowers/specs/2026-04-20-i18n-explanations-design.md Section 4.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

NARRATIVE_ROOT = Path(__file__).parent.parent / "scripts"
EN_PATH = NARRATIVE_ROOT / "narrative_en.py"
ZH_PATH = NARRATIVE_ROOT / "narrative_zh.py"

DIM_FUNCTION_NAMES = [
    f"d{d}_{kind}" for d in range(1, 10) for kind in ("explanation", "pattern")
]  # 18 functions total


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in module")


def _extract_metrics_keys(func: ast.FunctionDef) -> set[str]:
    keys: set[str] = set()
    for sub in ast.walk(func):
        # metrics["foo"] subscript
        if (
            isinstance(sub, ast.Subscript)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "metrics"
            and isinstance(sub.slice, ast.Constant)
            and isinstance(sub.slice.value, str)
        ):
            keys.add(sub.slice.value)
        # metrics.get("foo", ...)
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "get"
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "metrics"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
            and isinstance(sub.args[0].value, str)
        ):
            keys.add(sub.args[0].value)
    return keys


def _public_function_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }


@pytest.fixture(scope="module")
def en_tree() -> ast.Module:
    return _parse(EN_PATH)


@pytest.fixture(scope="module")
def zh_tree() -> ast.Module:
    return _parse(ZH_PATH)


def test_public_function_set_is_identical(en_tree, zh_tree):
    en = _public_function_names(en_tree)
    zh = _public_function_names(zh_tree)
    assert en == zh, (
        f"Public function set differs.\n"
        f"  en-only: {en - zh}\n"
        f"  zh-only: {zh - en}"
    )


@pytest.mark.parametrize("func_name", DIM_FUNCTION_NAMES)
def test_metric_key_parity(func_name, en_tree, zh_tree):
    en_keys = _extract_metrics_keys(_function_node(en_tree, func_name))
    zh_keys = _extract_metrics_keys(_function_node(zh_tree, func_name))
    assert en_keys == zh_keys, (
        f"{func_name}: metric keys diverge.\n"
        f"  en-only: {en_keys - zh_keys}\n"
        f"  zh-only: {zh_keys - en_keys}"
    )


def test_no_dynamic_metrics_access_in_en(en_tree):
    _assert_no_dynamic_metrics(en_tree, EN_PATH.name)


def test_no_dynamic_metrics_access_in_zh(zh_tree):
    _assert_no_dynamic_metrics(zh_tree, ZH_PATH.name)


def _assert_no_dynamic_metrics(tree: ast.Module, filename: str) -> None:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "metrics"
            and not (isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str))
        ):
            raise AssertionError(
                f"{filename}: dynamic metrics[...] access at line {node.lineno}. "
                "Narrative functions must use string-literal keys so parity scan stays valid."
            )
