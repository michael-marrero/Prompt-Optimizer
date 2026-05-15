"""OpenRouter adapter package — public surface (BACKEND-03).

The package re-export (``from .adapter import OpenRouterAdapter``) is
attached AFTER Task 2 lands ``adapter.py``. Task 1 creates this
package marker so the cost / errors / tests submodules are importable
without forcing the adapter import chain. See ``apps.api.backends.openrouter.adapter``.
"""
