# Plan 00 Task 3 — SECURE-04 KeyStore tests (D-10 lazy keyring extra).
#
# Test contracts:
#   - Memory primary: set() then get() returns the same value without
#     consulting keyring or env.
#   - Env fallback: when memory empty and use_keyring=False, lookup
#     resolves via _ENV_MAP -> os.environ.
#   - use_keyring=True without the optional extra installed raises
#     RuntimeError mentioning the remediation command.
#   - Unknown provider returns None.

from __future__ import annotations

import pytest


def test_memory_primary_takes_precedence(monkeypatch) -> None:
    from apps.api.backends.keystore import KeyStore

    monkeypatch.setenv("OPENROUTER_API_KEY", "env-value")
    store = KeyStore()
    store.set("openrouter", "memory-value")
    assert store.get("openrouter") == "memory-value"


def test_env_fallback_when_memory_empty(monkeypatch) -> None:
    from apps.api.backends.keystore import KeyStore

    monkeypatch.setenv("OPENROUTER_API_KEY", "envkey")
    store = KeyStore()
    assert store.get("openrouter") == "envkey"


def test_env_fallback_for_anthropic(monkeypatch) -> None:
    from apps.api.backends.keystore import KeyStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-envkey")
    store = KeyStore()
    assert store.get("anthropic") == "anthropic-envkey"


def test_unknown_provider_returns_none(monkeypatch) -> None:
    from apps.api.backends.keystore import KeyStore

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store = KeyStore()
    assert store.get("openrouter") is None
    assert store.get("anthropic") is None
    assert store.get("not_a_real_provider") is None


def test_use_keyring_raises_when_extra_missing(monkeypatch) -> None:
    """D-10: explicit opt-in to keyring without the extra installed
    must raise RuntimeError with the canonical remediation hint."""

    import apps.api.backends.keystore as keystore_mod

    monkeypatch.setattr(keystore_mod, "_HAS_KEYRING", False)
    with pytest.raises(RuntimeError) as exc_info:
        keystore_mod.KeyStore(use_keyring=True)
    assert "uv sync --extra keyring" in str(exc_info.value)


def test_service_name_constant() -> None:
    """Cross-process keyring identifier locked by Pattern 12."""

    from apps.api.backends.keystore import SERVICE_NAME

    assert SERVICE_NAME == "prompt-optimizer"


def test_env_map_includes_both_providers() -> None:
    from apps.api.backends.keystore import _ENV_MAP

    assert _ENV_MAP["openrouter"] == "OPENROUTER_API_KEY"
    assert _ENV_MAP["anthropic"] == "ANTHROPIC_API_KEY"


def test_get_caches_env_value_into_memory(monkeypatch) -> None:
    """Once an env lookup resolves, subsequent gets read from memory."""

    from apps.api.backends.keystore import KeyStore

    monkeypatch.setenv("OPENROUTER_API_KEY", "envkey")
    store = KeyStore()
    assert store.get("openrouter") == "envkey"
    # Now mutate the env var; the cached memory value should still win.
    monkeypatch.setenv("OPENROUTER_API_KEY", "different")
    assert store.get("openrouter") == "envkey"
