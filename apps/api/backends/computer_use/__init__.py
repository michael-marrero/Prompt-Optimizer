"""Computer-use adapter package.

NO import-time side effects: the ``COMPUTER_USE_OPT_IN`` check is at
constructor time per CONTEXT specifics line 263, NOT at import. This is
intentionally different from ``apps.api.backends.claude_code/__init__.py``
which sets ``CLAUDE_ENABLE_STREAM_WATCHDOG=1`` via ``os.environ.setdefault``
on import — there is no parallel side effect for computer-use because
opt-in must gate the adapter object, not the package import.

The ``ComputerUseAdapter`` re-export is deferred to the Plan 02-03 Task 2
commit — Task 1 ships this ``__init__.py`` WITHOUT it so the cost /
errors / step_counter / screen submodules are importable during the
Task 1 RED phase without an unresolved import chain (same pattern as
Plan 02-01 Decision #4 and Plan 02-02 Decision #4).

Cross-refs:
    - 02-CONTEXT.md specifics line 263 (opt-in at constructor, not import)
    - 02-PATTERNS.md "computer_use/__init__.py" lines 779-781
    - 02-RESEARCH.md §"Pattern 13" lines 1683-1685 (SECURE-05)
"""
