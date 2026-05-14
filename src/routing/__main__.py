"""Package-level entry point so `python -m src.routing` runs the CLI.

D-17 locks `python -m src.routing.decide '<prompt>'` as the canonical
invocation; this module-level fallback aliases `python -m src.routing`
to the same `main()` so a typo-tolerant pipeline (`python -m
src.routing` instead of `python -m src.routing.decide`) still works.
"""

from src.routing.decide import main

raise SystemExit(main())
