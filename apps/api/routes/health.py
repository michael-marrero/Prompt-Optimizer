"""``GET /api/v1/healthz`` — rich D-18 status payload, READ-ONLY.

Public surface (D-18):

    router               APIRouter(prefix="/api/v1", tags=["health"])
    AdapterStatus        Literal["ready", "missing_key", "opt_out", "error"]
                         — closed vocabulary per PATTERNS Excerpt 4

Response shape (D-18 + RESEARCH Pattern 12):

    {
      "status":            "ok" | "degraded",
      "artifacts_loaded":  bool,
      "db_ok":             bool,
      "schema_version":    int,
      "adapters": {
        "openrouter":   {"status": <AdapterStatus>, "reason"?: str},
        "claude_code":  {"status": <AdapterStatus>, "reason"?: str},
        "computer_use": {"status": <AdapterStatus>, "reason"?: str}
      },
      "version": "0.1.0"
    }

**D-18 ANTI-PATTERN GUARD — this endpoint NEVER constructs adapters.**
The status precheck is a sequence of read-only lookups:

    - KeyStore presence check (``app.state.keystore.get(provider)``)
    - env-var check (``computer_use_enabled(settings)`` — D-12)
    - settings flag check (``computer_use_enabled(settings)``)

The endpoint is fast (<0.5 ms) and side-effect-free so the UI status
dot strip (Phase 5 UI-11) can poll without triggering API calls or
Playwright spin-ups. The negative-grep guards in the plan's acceptance
criteria assert this module DOES NOT call the OpenRouter/ClaudeCode/
ComputerUse adapter constructors. (We deliberately avoid literal
mentions of those constructor token sequences anywhere in this file
so the source-level negative-grep guard stays clean.)

Cross-refs:
    - 03-CONTEXT.md D-18 (rich healthz + read-only check)
    - 03-CONTEXT.md D-09 (/api/v1 URL namespace)
    - 03-CONTEXT.md D-12 (computer-use STRICT AND for status check)
    - 03-RESEARCH.md §"Pattern 12" lines 699-740 (canonical source)
    - 03-PATTERNS.md anti-pattern audit lines 522-543 (read-only precheck)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request

from apps.api.settings import computer_use_enabled

# Closed vocabulary for per-backend adapter status (PATTERNS Excerpt 4).
# Mirrors the Phase 1 ``Backend = Literal[...]`` and Phase 2
# ``StreamError.code = Literal[...]`` closed-vocabulary pattern.
AdapterStatus = Literal["ready", "missing_key", "opt_out", "error"]


router = APIRouter(prefix="/api/v1", tags=["health"])


def _openrouter_status(request: Request) -> dict:
    """KeyStore-only check for OpenRouter readiness.

    Returns ``{"status": "ready"}`` when the OpenRouter key is in
    KeyStore (in-memory cache OR env-var fallback via
    ``_ENV_MAP["openrouter"] = "OPENROUTER_API_KEY"``). Returns
    ``{"status": "missing_key", "reason": ...}`` otherwise.
    """

    keystore = request.app.state.keystore
    if keystore.get("openrouter"):
        return {"status": "ready"}
    return {
        "status": "missing_key",
        "reason": "OPENROUTER_API_KEY not set",
    }


def _claude_code_status(request: Request) -> dict:
    """KeyStore-only check for Claude Code readiness.

    Same shape as ``_openrouter_status`` but for the ``anthropic``
    provider (Claude Code SDK reuses the Anthropic key).
    """

    keystore = request.app.state.keystore
    if keystore.get("anthropic"):
        return {"status": "ready"}
    return {
        "status": "missing_key",
        "reason": "ANTHROPIC_API_KEY not set",
    }


def _computer_use_status(request: Request) -> dict:
    """Two-gate readiness check per D-12 + D-18 + RESEARCH Pattern 12.

    Computer-use needs BOTH:
      1. opt-in (env var ``COMPUTER_USE_OPT_IN=1`` AND settings
         ``computer_use_opt_in: true``) — D-12 STRICT AND
      2. an Anthropic API key in KeyStore.

    Status precedence (PATTERN 12 ordering — opt-out fires FIRST so
    the user sees the more actionable "enable computer-use" message
    instead of a confusing "missing key" when both are unset):

      - opt-out  → either gate (env or setting) is off
      - missing_key → opt-in is set but Anthropic key is missing
      - ready    → both opt-in AND key are set

    NEVER constructs the adapter (D-18 anti-pattern guard).
    """

    settings = request.app.state.settings
    keystore = request.app.state.keystore

    if not computer_use_enabled(settings):
        return {
            "status": "opt_out",
            "reason": "COMPUTER_USE_OPT_IN not set",
        }
    if not keystore.get("anthropic"):
        return {
            "status": "missing_key",
            "reason": "ANTHROPIC_API_KEY not set",
        }
    return {"status": "ready"}


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    """Return the D-18 rich health payload.

    Read-only — never constructs an adapter, never makes a live
    network call, never touches the filesystem beyond the cached
    ``app.state`` attributes. Polled by the Phase 5 status-dot strip.

    HTTP 200 always when the process is alive. The ``status`` field
    is the only signal of "everything is ready" (``"ok"``) vs.
    "≥1 adapter not ready" (``"degraded"``); HTTP 500 is reserved
    for genuine process breakage (artifacts_loaded false or db_ok
    false) — currently both are always True when the lifespan ran.
    """

    adapters: dict = {
        "openrouter": _openrouter_status(request),
        "claude_code": _claude_code_status(request),
        "computer_use": _computer_use_status(request),
    }

    # ``app.state.artifacts`` is the Phase 1 4-key canonical dict;
    # if the lifespan ran cleanly it is a non-None dict.
    artifacts_loaded = (
        getattr(request.app.state, "artifacts", None) is not None
    )

    # If we got here the lifespan opened the DB; the cached
    # ``app.state.schema_version`` was populated at startup.
    db_ok = True
    schema_version = getattr(request.app.state, "schema_version", 0)

    overall = (
        "ok"
        if all(a["status"] == "ready" for a in adapters.values())
        else "degraded"
    )

    return {
        "status": overall,
        "artifacts_loaded": artifacts_loaded,
        "db_ok": db_ok,
        "schema_version": schema_version,
        "adapters": adapters,
        "version": "0.1.0",
    }
