"""PlaywrightScreen — Chromium browser wrapper for the computer-use adapter.

Public surface (BACKEND-05 / D-13):

    PlaywrightScreen(*, viewport=(1280, 800), headless=True)
        async def start() -> None
        async def screenshot() -> bytes        PNG bytes via page.screenshot
        async def left_click(x, y, *, modifier=None) -> None
        async def type_text(text) -> None
        async def press_key(key) -> None       Anthropic "ctrl+s" -> Playwright "Control+s"
        async def scroll(x, y, direction, amount) -> None
        async def goto(url) -> None
        async def aclose() -> None             close browser + stop Playwright

The adapter constructs one ``PlaywrightScreen`` per stream call (one
browser context per turn) inside an ``async with``-shaped lifecycle:
``start()`` in the try-block prelude, ``aclose()`` in the finally
block. ``aclose()`` swallows close errors so a half-initialised screen
still terminates cleanly within the BACKEND-07 2-second cancellation
budget.

Default ``headless=True`` is locked by RESEARCH anti-pattern line 1727 —
the v1 CLI must NEVER default to a headed Chromium. A debug toggle
exists in the constructor signature so a developer can opt in for
manual inspection, but the default is firmly ``True``.

Coordinate system: at 1280×800 the ``computer_20251124`` tool is 1:1
pixel-to-coordinate (RESEARCH Pattern 5 line 1208). No scaling math
needed inside ``left_click`` / ``scroll`` — the (x, y) we receive from
Anthropic maps directly to the page-relative pixel space Playwright
expects.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 5" lines 1140-1202 (canonical source)
    - 02-RESEARCH.md §"Anti-Patterns" line 1727 (headless=True default lock)
    - 02-CONTEXT.md D-13 (1280×800 viewport, action mapping)
    - 02-PATTERNS.md "computer_use/screen.py" lines 793-795 (novel module)
"""

from __future__ import annotations

from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


class PlaywrightScreen:
    """Async wrapper around ``playwright.async_api`` for the computer-use loop.

    The wrapper owns the Playwright runtime, the Chromium browser, the
    browser context, and the single page (one tab) that the agent
    drives. The same instance is reused across iterations within one
    stream; ``aclose()`` is the single cleanup hook called from the
    adapter's ``finally`` block.
    """

    def __init__(
        self,
        *,
        viewport: tuple[int, int] = (1280, 800),
        headless: bool = True,
    ) -> None:
        # Default headless=True per anti-pattern line 1727. Constructor
        # accepts headless= so a developer can opt in for debugging;
        # production / CI / live-smoke always passes the default.
        self._viewport = viewport
        self._headless = headless
        # Lazy-initialised in ``start()``. Annotating Optional so type
        # checkers warn on un-awaited use after ``aclose``.
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> None:
        """Start Playwright, launch headless Chromium, open one page.

        The adapter calls this BEFORE the agent loop's first iteration.
        Failure here surfaces as the adapter's terminal pair (an
        exception inside ``start()`` is caught by the adapter's
        ``except Exception`` block, which logs the traceback, yields
        ``StreamError(internal_error)`` + ``Done``, and routes to
        ``finally`` for ``aclose()`` — which is safe to call against a
        half-initialised instance).
        """

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        # Per-context viewport — keeps the agent's coordinate space
        # locked at 1280×800 regardless of the host display.
        self._context = await self._browser.new_context(
            viewport={
                "width": self._viewport[0],
                "height": self._viewport[1],
            },
        )
        self._page = await self._context.new_page()

    async def screenshot(self) -> bytes:
        """Return PNG bytes for the current viewport.

        ``full_page=False`` per D-14 — we capture exactly what the
        agent's coordinate space sees, not the full scroll height.
        ``type="png"`` per D-14 — lossless format for downstream UI
        rendering.
        """

        assert self._page is not None, "screenshot called before start()"
        return await self._page.screenshot(type="png", full_page=False)

    async def left_click(
        self,
        x: int,
        y: int,
        *,
        modifier: str | None = None,
    ) -> None:
        """Click ``(x, y)`` with an optional modifier key.

        Anthropic's ``left_click`` action carries an optional ``text``
        field naming a modifier (e.g. ``"shift"``); we capitalize it to
        match Playwright's ``modifiers=[...]`` convention.
        """

        assert self._page is not None, "left_click called before start()"
        modifiers = [modifier.capitalize()] if modifier else []
        await self._page.mouse.click(x, y, modifiers=modifiers)

    async def type_text(self, text: str) -> None:
        """Type ``text`` at the current focus (mimics keystrokes)."""

        assert self._page is not None, "type_text called before start()"
        await self._page.keyboard.type(text)

    async def press_key(self, key: str) -> None:
        """Press ``key`` (Anthropic ``"ctrl+s"`` -> Playwright ``"Control+s"``).

        Anthropic uses lowercase modifier names (``ctrl``, ``super``);
        Playwright expects ``Control`` / ``Meta``. We translate inline
        rather than maintain a separate mapping table — the cases
        listed here are the only ones the computer-use tool emits
        (RESEARCH Pattern 5 lines 1176-1178).
        """

        assert self._page is not None, "press_key called before start()"
        normalized = key.replace("ctrl", "Control").replace("super", "Meta")
        await self._page.keyboard.press(normalized)

    async def scroll(
        self,
        x: int,
        y: int,
        direction: str,
        amount: int,
    ) -> None:
        """Move pointer to ``(x, y)`` and scroll ``amount`` ticks in ``direction``.

        ``amount * 100`` is the rough pixels-per-tick conversion from
        Anthropic's discrete scroll counts to Playwright's continuous
        wheel-delta API (RESEARCH Pattern 5 line 1182).
        """

        assert self._page is not None, "scroll called before start()"
        await self._page.mouse.move(x, y)
        delta = amount * 100  # rough pixels-per-tick
        if direction == "down":
            await self._page.mouse.wheel(0, delta)
        elif direction == "up":
            await self._page.mouse.wheel(0, -delta)
        elif direction == "right":
            await self._page.mouse.wheel(delta, 0)
        elif direction == "left":
            await self._page.mouse.wheel(-delta, 0)

    async def goto(self, url: str) -> None:
        """Navigate the page to ``url``."""

        assert self._page is not None, "goto called before start()"
        await self._page.goto(url)

    async def aclose(self) -> None:
        """Close the browser and stop Playwright.

        Safe to call against a half-initialised instance — each step
        is guarded by its own None check. The try/finally pairing
        ensures the Playwright runtime is stopped even if the browser
        close raises (e.g. when Chromium has already exited from a
        crash).
        """

        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._pw is not None:
                await self._pw.stop()
