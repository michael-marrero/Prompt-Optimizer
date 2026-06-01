"""EVAL-01 — D-18 import-graph guard (eval direction).

The whole eval architecture rests on a one-way import arrow: `eval/` may import
`src.routing` / `apps.api.backends`, but NOTHING under `src/` may ever import
`eval` or the eval-only harness package `inspect_ai`. If an eval-only dependency
leaked into the production routing brain's import graph, a `decide()` call could
transitively pull a heavyweight eval dep (D-18 violation; threat T-10-D18).

This test is the sibling/mirror of the existing brain-direction guard in
`src/routing/tests/test_decide_smoke.py` (which asserts `decide()` pulls no
HTTP-client / LLM-SDK at runtime via a sys.modules walk). Here we statically
AST-walk every `*.py` file under `src/` and assert no `import` / `from ... import`
names a top-level package in the forbidden set {"eval", "inspect_ai"}.

Stdlib-only (ast, pathlib) and key-free; the test references the forbidden names
as set members — it does NOT itself import the eval harness package.

Cross-refs:
    - src/routing/tests/test_decide_smoke.py:22-56 (FORBIDDEN_MODULES + split idiom)
    - 10-RESEARCH.md §Code Examples lines 475-490 (AST-walk implementation)
    - 10-PATTERNS.md §test_import_graph.py (D-18 eval direction)
"""

from __future__ import annotations

import ast
import pathlib

# eval/tests/ -> eval/ -> <repo root>
ROOT = pathlib.Path(__file__).resolve().parents[2]

# Mirror the FORBIDDEN_MODULES frozenset idiom from the brain-direction guard.
# Matching is done on the top-level package (`m.split(".")[0]`) so a dotted
# import like `inspect_ai.solver` is caught by the bare "inspect_ai" entry.
FORBIDDEN_TOP_LEVEL: frozenset[str] = frozenset({"eval", "inspect_ai"})


def _imported_module_names(node: ast.AST) -> list[str]:
    """Return the module names referenced by an Import / ImportFrom node."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        # node.level > 0 is a relative import (e.g. `from . import x`); its
        # `module` is package-local to src/ and never names eval/inspect_ai.
        return [node.module] if node.level == 0 else []
    return []


def test_no_src_module_imports_eval_or_inspect() -> None:
    """EVAL-01 / D-18: no module under src/ may import eval or inspect_ai."""
    offenders: list[str] = []
    for py in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            for module in _imported_module_names(node):
                if module and module.split(".")[0] in FORBIDDEN_TOP_LEVEL:
                    offenders.append(f"{py.relative_to(ROOT)}: imports {module}")

    assert not offenders, (
        "D-18 violation (eval direction): a module under src/ imports the "
        "eval-only stack. The arrow is one-way (eval/ -> src.routing), never the "
        f"reverse. Forbidden top-level packages: {sorted(FORBIDDEN_TOP_LEVEL)}.\n"
        + "\n".join(offenders)
    )
