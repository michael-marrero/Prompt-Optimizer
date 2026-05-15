"""OpenRouter adapter package — public surface (BACKEND-03).

Re-exports the ``OpenRouterAdapter`` class so callers can write::

    from apps.api.backends.openrouter import OpenRouterAdapter

instead of reaching into the module directly. Implementation lives in
``apps.api.backends.openrouter.adapter``.
"""

from apps.api.backends.openrouter.adapter import OpenRouterAdapter

__all__ = ["OpenRouterAdapter"]
