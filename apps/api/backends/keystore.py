"""KeyStore — in-memory primary store + optional OS keyring persistence.

Public surface (SECURE-04, D-10):

    SERVICE_NAME   Final[str] — keyring service identifier
    _ENV_MAP       Internal provider -> env-var mapping
    KeyStore       Per-instance key cache with optional keyring sync

The default constructor (``KeyStore()``) is purely in-memory plus an
``os.environ`` fallback through ``_ENV_MAP``. Users who explicitly
opt in via ``KeyStore(use_keyring=True)`` get cross-session
persistence via the platform OS keyring (macOS Keychain, Windows
DPAPI, Linux Secret Service). The ``keyring`` library is an OPTIONAL
extra (``pyproject.toml [project.optional-dependencies] keyring``)
so the default ``uv sync`` does not pull in a heavyweight,
platform-specific dependency for users who do not need disk
persistence.

The lazy try/except import pattern (D-10) keeps the module importable
on a fresh clone where ``keyring`` is not yet installed:

    try:
        import keyring as _keyring
        _HAS_KEYRING = True
    except ImportError:
        _HAS_KEYRING = False

A constructor that requests keyring but cannot honour it raises
``RuntimeError`` with explicit remediation text
(``uv sync --extra keyring``) so the user can self-serve.

This module NEVER logs key material. Combined with the
``RedactionFilter`` installed by ``apps/api/__init__.py``, a defense
in depth keeps secrets out of the logs even if a future change adds a
stray ``logger.info(key)`` call somewhere downstream.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 12" lines 1623-1681 (canonical source)
    - 02-CONTEXT.md D-10 (keyring optional extra rationale)
"""

from __future__ import annotations

import os
from typing import Final

SERVICE_NAME: Final[str] = "prompt-optimizer"

# Optional dep — set the import flag at module load so the constructor
# can raise a clean RuntimeError if the user opts in without
# installing the extra.
try:
    import keyring as _keyring

    _HAS_KEYRING = True
except ImportError:  # pragma: no cover — exercised only when extra absent
    _HAS_KEYRING = False


# Provider -> environment variable name. Adapters reading from the
# keystore use the provider sentinel (``"openrouter"`` / ``"anthropic"``)
# as the lookup key.
_ENV_MAP: Final[dict[str, str]] = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class KeyStore:
    """In-memory primary store with optional OS-keyring persistence.

    Resolution order for ``get(provider)``:

        1. In-memory cache (set via ``set(provider, key)`` or
           populated by an earlier ``get`` that fell through to
           keyring / env).
        2. OS keyring, ONLY if ``use_keyring=True`` AND the
           ``keyring`` extra is installed.
        3. ``os.environ`` lookup via ``_ENV_MAP``.

    Unknown providers return ``None`` — adapters then surface
    ``StreamError(code="auth_failed", ...)`` at construction time so
    the failure mode is consistent with explicit empty-key passes.
    """

    def __init__(self, *, use_keyring: bool = False):
        if use_keyring and not _HAS_KEYRING:
            raise RuntimeError(
                "use_keyring=True but the 'keyring' extra is not installed. "
                "Run: uv sync --extra keyring"
            )
        self._memory: dict[str, str] = {}
        self._use_keyring = use_keyring

    def get(self, provider: str) -> str | None:
        if provider in self._memory:
            return self._memory[provider]
        if self._use_keyring and _HAS_KEYRING:
            stored = _keyring.get_password(SERVICE_NAME, provider)
            if stored:
                self._memory[provider] = stored
                return stored
        env_var = _ENV_MAP.get(provider)
        if env_var:
            val = os.environ.get(env_var)
            if val:
                self._memory[provider] = val
                return val
        return None

    def set(self, provider: str, key: str) -> None:
        self._memory[provider] = key
        if self._use_keyring and _HAS_KEYRING:
            _keyring.set_password(SERVICE_NAME, provider, key)
