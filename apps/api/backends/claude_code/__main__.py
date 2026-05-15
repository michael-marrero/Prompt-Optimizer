"""Package-level CLI: ``python -m apps.api.backends.claude_code``.

Streams one prompt through ``ClaudeCodeAdapter`` and prints each
``ChatChunk`` as a single JSON line on stdout. The last line always
has ``"type":"done"`` (D-04 invariant).

Usage::

    ANTHROPIC_API_KEY=sk-ant-... \\
        python -m apps.api.backends.claude_code \\
        --prompt "create hello.py" \\
        --model claude-agent-sdk \\
        --max-cost-usd 0.20 \\
        --max-steps 25 \\
        --cwd /path/to/repo   # optional; default = tempfile.mkdtemp

The ``--cwd`` flag is BACKEND-08's opt-in: when present, the adapter
runs Claude inside the user-supplied directory and does NOT clean it
up. When absent (default), the adapter creates a fresh
``tempfile.mkdtemp(prefix='pomu-cc-')`` per turn and rmtrees it on
exit (T-02-05 leak mitigation).

The script returns 0 on success and 1 when ``ANTHROPIC_API_KEY`` is
unset. Errors emitted mid-stream by the adapter still appear as
``StreamError`` JSON lines followed by a ``Done`` line — they do NOT
flip the exit code, because the stream itself terminated cleanly.

Cross-refs:
    - 02-RESEARCH.md §"Common Operation 2" lines 1873-1914
    - 02-PATTERNS.md "claude_code/__main__.py" lines 687-690
    - apps/api/backends/openrouter/__main__.py (parallel template)
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
    cwd: str | None,
) -> int:
    """Stream one turn through the adapter, printing JSON lines."""

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
    from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter
    from apps.api.backends.protocol import AdapterOptions

    adapter = ClaudeCodeAdapter(
        api_key=api_key,
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
    )
    options = AdapterOptions(
        model=model,
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
        cwd=cwd,
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
        prog="python -m apps.api.backends.claude_code",
        description=(
            "Stream a single prompt through the Claude Code adapter "
            "and print each ChatChunk as one JSON line on stdout."
        ),
    )
    parser.add_argument(
        "--prompt", required=True, help="The user prompt text."
    )
    parser.add_argument(
        "--model",
        default="claude-agent-sdk",
        help="Logical model id used for pricing lookup (default: claude-agent-sdk).",
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
        help="Step cap (one step = one AssistantMessage; D-15).",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help=(
            "Workspace directory (BACKEND-08 opt-in). Default: a fresh "
            "tempfile.mkdtemp(prefix='pomu-cc-') that the adapter removes "
            "on exit."
        ),
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run(
            args.prompt,
            args.model,
            args.max_cost_usd,
            args.max_steps,
            args.cwd,
        )
    )


def _entrypoint() -> None:
    """Indirection so ``import apps.api.backends.claude_code.__main__``
    doesn't SystemExit the calling process (WR-07 fix)."""

    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
