"""Non-key settings I/O + computer-use opt-in helper.

Public surface (D-11, D-12):

    _default_settings()      dict — canonical shape with defaults
    load_settings_file()     dict — reads ``SETTINGS_PATH``; returns
                             defaults if file is absent
    write_settings_file(...) None — atomic ``tmp.write_text() +
                             tmp.replace(target)`` (RESEARCH Example 5)
    computer_use_enabled(s)  bool — D-12 STRICT AND-semantics; True
                             ONLY when ``os.environ["COMPUTER_USE_OPT_IN"]
                             == "1"`` AND ``settings["computer_use_opt_in"]
                             is True``

The file lives at ``apps.api.paths.SETTINGS_PATH``
(``~/.prompt-optimizer/settings.json`` by default; overridable via the
``PROMPT_OPTIMIZER_HOME`` env var). The contents are ALWAYS non-key
fields only — BYOK secrets live in ``apps.api.backends.keystore.KeyStore``
and NEVER enter this file (D-11 explicit, SECURE-04 carry-forward).

The atomic-write pattern uses ``Path.with_suffix(suffix + ".tmp")``
for the tmp filename so it lives in the same directory as the target
file (POSIX + Windows both require same-filesystem for ``replace`` to
be atomic). The single ``replace`` call is the commit point — any
crash before it leaves the tmp file orphaned (recoverable; never
corrupts the target) and any crash after it has fully committed the
new contents.

The D-12 STRICT AND-semantics for ``computer_use_enabled`` extends the
Phase 2 ``ComputerUseAdapter`` single-gate check (CONTEXT anti-pattern
explicit: "Do NOT couple computer-use opt-in to env-only"). The Phase 2
adapter still raises on missing env at construction; Phase 3 adds the
in-app toggle as the second gate so the UI toggle (Phase 5 UI-12)
actually does work. Both gates required to enable.

Cross-refs:
    - 03-CONTEXT.md D-11 (settings file location + atomic write)
    - 03-CONTEXT.md D-12 (computer-use AND-semantics)
    - 03-CONTEXT.md discretion line 177 (tmp + replace pattern)
    - 03-RESEARCH.md §"Pattern 13" lines 742-783 (canonical source)
    - 03-RESEARCH.md §"Example 5" lines 1054-1065 (atomic write)
    - 03-PATTERNS.md §"Excerpt 8" lines 415-440 (lift-source for
      ``computer_use_enabled``; Phase 2 single-gate check extended)
    - apps/api/backends/computer_use/adapter.py lines 210-223 (the
      Phase 2 single-gate adapter check Phase 3 EXTENDS, not replaces)

This module never logs settings content. ``default_max_cost_usd`` is
benign but the ``backends_enabled`` dict reveals provider toggles; we
keep the surface boring. The KeyStore (where secrets live) is NEVER
mentioned in this module's import graph.
"""

from __future__ import annotations

import json
import logging
import os

from apps.api.paths import SETTINGS_PATH

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------
# Defaults — canonical shape used on first boot + when settings.json
# is missing entirely.
# --------------------------------------------------------------------


def _default_settings() -> dict:
    """Return the canonical default settings shape.

    Used on first boot (no ``settings.json`` on disk yet) AND as the
    Pydantic-merge baseline for ``PATCH /api/v1/settings`` (Wave 6).
    Returns a fresh dict per call so callers cannot mutate the
    "defaults" by accident.
    """

    return {
        "backends_enabled": {
            "openrouter": True,
            "claude_code": True,
            "computer_use": False,
        },
        "computer_use_opt_in": False,
        "default_max_cost_usd": 0.50,
    }


# --------------------------------------------------------------------
# Read path — load_settings_file
# --------------------------------------------------------------------


def load_settings_file() -> dict:
    """Read ``SETTINGS_PATH`` and return the parsed JSON dict.

    Returns ``_default_settings()`` when the file is absent (first
    boot). Does NOT merge the on-disk file with defaults — the Wave 6
    PATCH handler owns merge semantics. The lifespan stashes this
    return value verbatim on ``app.state.settings`` and downstream
    code reads keys via ``.get(key, fallback)`` so absent keys flow
    through cleanly.
    """

    if not SETTINGS_PATH.exists():
        return _default_settings()
    with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------
# Write path — atomic via tmp + replace (RESEARCH Example 5)
# --------------------------------------------------------------------


def write_settings_file(settings: dict) -> None:
    """Atomically rewrite ``SETTINGS_PATH`` with ``settings``.

    Pattern (CONTEXT discretion line 177 + RESEARCH Example 5):

        tmp = SETTINGS_PATH.with_suffix(SETTINGS_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(settings, ...), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)

    The tmp file lives in the same directory as the target so the
    final ``replace`` is atomic on POSIX (rename(2) within a single
    filesystem) and on Windows (``MoveFileEx`` with
    ``MOVEFILE_REPLACE_EXISTING`` — the stdlib's ``os.replace`` calls
    this under the hood).

    ``json.dumps(..., indent=2, sort_keys=True)`` keeps the on-disk
    file diff-friendly so a contributor inspecting the file (or a
    future ``git diff`` if they choose to track their settings)
    sees stable ordering.
    """

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # ``with_suffix`` replaces the existing suffix; we want to APPEND
    # ``.tmp`` to the existing one ("settings.json" -> "settings.json.tmp")
    # so the tmp file shape is unambiguous on inspection.
    tmp = SETTINGS_PATH.with_suffix(SETTINGS_PATH.suffix + ".tmp")
    tmp.write_text(
        json.dumps(settings, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(SETTINGS_PATH)


# --------------------------------------------------------------------
# Computer-use enable check — D-12 STRICT AND-semantics
# --------------------------------------------------------------------


def computer_use_enabled(settings: dict) -> bool:
    """Return True ONLY when BOTH gates are set (D-12).

    Gate 1 (env): ``os.environ["COMPUTER_USE_OPT_IN"] == "1"`` —
        literal string equality with ``"1"``. Any other value
        (``"true"``, ``"yes"``, ``"on"``, ``""``, missing) returns
        False. The strict equality matches Phase 2
        ``ComputerUseAdapter.__init__`` exactly (line 217:
        ``os.environ.get("COMPUTER_USE_OPT_IN") != "1"``) so the
        Phase 3 helper agrees with the Phase 2 adapter on every input.

    Gate 2 (settings): ``bool(settings.get("computer_use_opt_in"))`` —
        the UI toggle. ``bool(None)`` and ``bool(False)`` both return
        False so missing-key behaves the same as explicitly-off.

    Both gates required (logical AND). This is the gate Phase 3
    EXTENDS — Phase 2's adapter still raises ``RuntimeError`` on
    missing env, but Phase 3's lazy-build path in
    ``routes/turn.py`` consults THIS helper BEFORE constructing the
    adapter so an env-set + setting-off combination surfaces as a
    clean 400 (not a 500 from the adapter's RuntimeError).
    """

    env_ok = os.environ.get("COMPUTER_USE_OPT_IN") == "1"
    setting_ok = bool(settings.get("computer_use_opt_in"))
    return env_ok and setting_ok
