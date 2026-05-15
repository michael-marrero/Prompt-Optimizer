"""Top-level ``apps`` namespace.

Houses runnable application packages such as ``apps.api`` (the FastAPI
backend that wraps the Phase 1 routing brain in Phase 3). This package
is intentionally empty — it only marks ``apps`` as a regular Python
package so wheels built via ``pyproject.toml`` (which lists
``packages = ["src", "apps"]``) include it.
"""
