"""Package-level CLI: ``python -m apps.api.backends.computer_use``.

Streams one prompt through ``ComputerUseAdapter`` and prints each
``ChatChunk`` as a single JSON line on stdout. The last line always
has ``"type":"done"`` (D-04 invariant).

Usage::

    COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=sk-ant-... \\
        python -m apps.api.backends.computer_use \\
        --prompt "open https://example.com and take a screenshot" \\
        --model claude-opus-4-7 \\
        --max-cost-usd 0.30 \\
        --max-steps 5

SECURE-05 belt-and-suspenders: the CLI's preflight EXPLICITLY re-checks
``COMPUTER_USE_OPT_IN`` and prints the most actionable error message to
stderr before even importing the adapter. The adapter's constructor
would raise the same RuntimeError, but doing the check here first means
the user gets a friendly message instead of a Python traceback.

The script returns:
    0  success — Done chunk landed
    1  missing ANTHROPIC_API_KEY
    2  missing COMPUTER_USE_OPT_IN  (SECURE-05 — distinct exit code so
        CI / wrappers can detect this case separately from auth issues)

Errors emitted mid-stream by the adapter still appear as
``StreamError`` JSON lines followed by a ``Done`` line — they do NOT
flip the exit code, because the stream itself terminated cleanly.

Cross-refs:
    - 02-RESEARCH.md §"Common Operation 2" lines 1873-1914
    - 02-PATTERNS.md "computer_use/__main__.py" (parallel to openrouter)
    - apps/api/backends/openrouter/__main__.py (parallel template)
    - apps/api/backends/claude_code/__main__.py (parallel template)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def _run(
    prompt: str,
    model: str,
    max_cost_usd: float,
    max_steps: int,
) -> int:
    """Stream one turn through the adapter, printing JSON lines."""

    # SECURE-05 belt-and-suspenders: re-check at the CLI before
    # touching the adapter module. The adapter __init__ would raise
    # the same RuntimeError; checking here gives a cleaner stderr
    # message (no traceback) AND a distinct exit code so CI can
    # detect "user forgot to opt in" vs "user forgot the key".
    if os.environ.get("COMPUTER_USE_OPT_IN") != "1":
        print(
            "ERROR: computer-use is OFF — set COMPUTER_USE_OPT_IN=1 to enable.",
            file=sys.stderr,
        )
        return 2

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "ERROR: set ANTHROPIC_API_KEY in env or .env",
            file=sys.stderr,
        )
        return 1

    # Lazy import — avoids SDK side effects when this module is merely
    # imported (e.g. by tests inspecting ``main()`` signature) so the
    # CLI tooling overhead lives behind the actual execution path.
    from apps.api.backends.computer_use.adapter import ComputerUseAdapter
    from apps.api.backends.protocol import AdapterOptions

    adapter = ComputerUseAdapter(
        api_key=api_key,
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
    )
    options = AdapterOptions(
        model=model,
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
    )
    async for chunk in adapter.stream(
        prompt=prompt,
        history=[],
        options=options,
    ):
        print(chunk.model_dump_json(), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Argparse entry point — returns process exit code."""

    parser = argparse.ArgumentParser(
        prog="python -m apps.api.backends.computer_use",
        description=(
            "Stream a single prompt through the computer-use adapter "
            "and print each ChatChunk as one JSON line on stdout. "
            "Requires COMPUTER_USE_OPT_IN=1 + ANTHROPIC_API_KEY."
        ),
    )
    parser.add_argument(
        "--prompt", required=True, help="The user prompt text."
    )
    parser.add_argument(
        "--model",
        default="claude-opus-4-7",
        help="Anthropic model id (default: claude-opus-4-7).",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=0.50,
        help="Per-turn USD cap (default: 0.50 from DEFAULT_PER_TURN_COST_USD).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Step cap (default: 15 from DEFAULT_STEP_CAP; D-15).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run(
            args.prompt,
            args.model,
            args.max_cost_usd,
            args.max_steps,
        )
    )


def _entrypoint() -> None:
    """Indirection so ``import apps.api.backends.computer_use.__main__``
    doesn't SystemExit the calling process (WR-07 fix)."""

    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
