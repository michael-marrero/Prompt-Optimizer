"""Package-level entry point so `python -m src.routing` runs the CLI.

D-17 locks `python -m src.routing.decide '<prompt>'` as the canonical
invocation; this module-level fallback aliases `python -m src.routing`
to the same `main()` so a typo-tolerant pipeline (`python -m
src.routing` instead of `python -m src.routing.decide`) still works.

WR-07 fix: the body wraps the dispatch in `if __name__ == "__main__":`
so any tool that imports `src.routing.__main__` directly (some IDE
auto-discovery, some doc builders, a poorly-written test that walks
subpackages) doesn't hard-exit the calling process. `python -m
src.routing` still works because the interpreter sets __name__ to
"__main__" for the package-execution entry point.
"""

from src.routing.decide import main


def _entrypoint() -> None:
    """Indirection so `python -m src.routing` raises SystemExit, but
    `import src.routing.__main__` does not."""
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
