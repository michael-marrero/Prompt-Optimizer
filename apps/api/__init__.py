"""``apps.api`` package — backend API surface for the prompt router.

Public surface (Phase 2 Plan 00):
    - Re-imported indirectly via ``apps.api.backends`` once submodules
      land. This file itself exposes no names.

This module performs TWO SIDE EFFECTS at import time:

    1. ``dotenv.load_dotenv()`` (D-11 + SECURE-04). Loads
       ``./.env`` from the current working directory if present so
       BYOK environment variables (``OPENROUTER_API_KEY``,
       ``ANTHROPIC_API_KEY``, ``COMPUTER_USE_OPT_IN``) are populated
       before any adapter constructor reads them. ``load_dotenv()`` is
       a defensive no-op when ``.env`` is absent — the standard
       open-source distribution ships without one.

    2. ``install_redaction_filter()`` (SECURE-01). Attaches a
       ``RedactionFilter`` to the root logger so any log record
       containing a recognised secret (``sk-…``, ``sk-ant-…``,
       ``Bearer …``) is rewritten before a handler sees it. The filter
       is idempotent on the root logger so re-imports do not duplicate
       filters.

Cross-refs:
    - 02-CONTEXT.md D-11 (python-dotenv at import) and SECURE-01 in
      .planning/REQUIREMENTS.md
    - 02-RESEARCH.md §"Pattern 10" (RedactionFilter source)
    - 02-PATTERNS.md §"Group A" first entry (path-discovery preamble)

The path-discovery preamble uses ``pathlib`` (CONTEXT line 245) rather
than the ``os.path.dirname`` chain that the Phase 1 ``src/`` tree
inherited; Phase 2 establishes the cleaner ``pathlib`` convention
inside the ``apps/`` subtree.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from apps.api.backends.logging_filter import install_redaction_filter

# Path discovery — apps/api/__init__.py is two levels below the repo
# root, so ``parents[1]`` lands at ``<repo>/apps`` and ``parents[2]``
# at the repo root itself. We use ``parents[2]`` so downstream code
# referring to ``PROJECT_ROOT`` matches the layout the Phase 1
# ``src/routing/config.py`` uses.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_DIR: Path = PROJECT_ROOT / "config"

# Side effect #1: load .env from the current working directory if it
# exists. No-op when absent. We do NOT pass ``override=True`` so an
# already-exported environment variable wins over the .env value.
load_dotenv()

# Side effect #2: install the redaction filter exactly once. The
# helper is idempotent so a second import does not double-install.
install_redaction_filter()
