"""Package-level CLI: ``python -m apps.api.backends.openrouter``.

Streams one prompt through ``OpenRouterAdapter`` and prints each
``ChatChunk`` as a single JSON line on stdout. The last line always
has ``"type":"done"`` (D-04 invariant).

Usage::

    OPENROUTER_API_KEY=sk-or-... \\
        python -m apps.api.backends.openrouter \\
        --prompt "hi" \\
        --model openai/gpt-5 \\
        --max-cost-usd 0.10

The script returns 0 on success and 1 when ``OPENROUTER_API_KEY`` is
unset. Errors emitted mid-stream by the adapter still appear as
``StreamError`` JSON lines followed by a ``Done`` line — they do NOT
flip the exit code, because the stream itself terminated cleanly.

Cross-refs:
    - 02-RESEARCH.md §"Common Operation 2" lines 1873-1914 (canonical source)
    - 02-PATTERNS.md "openrouter/__main__.py" lines 446-489 (WR-07 _entrypoint)
    - src/routing/__main__.py + src/routing/decide.py:_entrypoint (style analog)
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

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(
            "ERROR: set OPENROUTER_API_KEY in env or .env",
            file=sys.stderr,
        )
        return 1

    # Lazy import — avoids SDK side effects when this module is merely
    # imported (e.g. by tests inspecting `main()` signature) so the CLI
    # tooling overhead lives behind the actual execution path.
    from apps.api.backends.openrouter.adapter import OpenRouterAdapter
    from apps.api.backends.protocol import AdapterOptions

    adapter = OpenRouterAdapter(api_key=api_key, max_cost_usd=max_cost_usd)
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
        prog="python -m apps.api.backends.openrouter",
        description=(
            "Stream a single prompt through the OpenRouter adapter "
            "and print each ChatChunk as one JSON line on stdout."
        ),
    )
    parser.add_argument("--prompt", required=True, help="The user prompt text.")
    parser.add_argument(
        "--model",
        default="openai/gpt-5",
        help="OpenRouter model slug (default: openai/gpt-5).",
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
        default=25,
        help="Step cap (carried in AdapterOptions; OpenRouter ignores).",
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
    """Indirection so ``import apps.api.backends.openrouter.__main__``
    doesn't SystemExit the calling process (WR-07 fix)."""

    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
