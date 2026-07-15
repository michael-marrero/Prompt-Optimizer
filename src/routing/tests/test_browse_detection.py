# Story 6.3 — robust browse-intent detection via a URL/web-domain signal
# (implements the D-15 "URL -> computer-use" intent policy.py described but
# never built). A named website in an agentic prompt with no competing coding
# signal routes to computer-use.
#
# Hardened per code review: bounded regex (no ReDoS), email exclusion, curated
# TLDs (no code-extension / short-word collisions), and a URL defers to a
# coding signal (a domain in a coding prompt is NOT a browse task).

from __future__ import annotations

import pytest

from src.routing.config import COMPUTER_USE_SENTINEL
from src.routing.policy import _contains_url_or_domain, decide_backend


def _route(prompt: str, *, agentic: bool = True, task_type: str = "reasoning") -> str:
    backend, _, _ = decide_backend(
        agentic_intent=agentic,
        agentic_confidence=0.9,
        task_type=task_type,
        prompt=prompt,
    )
    return backend


# ---------------------------------------------------------------------------
# _contains_url_or_domain — precision of the matcher (AC1, AC4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "bloomberg.com",
        "return the top 3 headlines on bloomberg.com right now",
        "https://news.ycombinator.com — summarize the front page",
        "check nytimes.com and tell me the lead story",
        "open http://example.org/path?q=1",
        "the startup at example.io launched",
    ],
)
def test_matcher_detects_urls_and_domains(text: str) -> None:
    assert _contains_url_or_domain(text.lower()) is True


@pytest.mark.parametrize(
    "text",
    [
        "fix the bug in app.py",            # code filename — 'py' not a web TLD
        "refactor utils.ts and index.tsx",  # ts/tsx excluded
        "i run node.js daily",              # js excluded
        "what's 3.14 rounded to 2 dp",      # number
        "the u.s. gdp figure",              # initialism
        "explain the difference between tcp and udp",  # no dot-TLD
        "e.g. this is an example",          # 'g' not a TLD
        "email me at user@example.com",     # email domain — excluded (lookbehind)
        "see the read.me and note.to files",  # me/to dropped from WEB_TLDS
        "link libssl.so at build time",     # so dropped from WEB_TLDS
    ],
)
def test_matcher_rejects_non_domains(text: str) -> None:
    assert _contains_url_or_domain(text.lower()) is False


@pytest.mark.timeout(2)
def test_matcher_is_not_redos_on_dot_chain() -> None:
    # Bounded quantifiers keep this linear. Before the fix, a long dotted chain
    # backtracked O(n^2) (~5.7s at 32k chars). The 2s timeout fails if it regresses.
    big = "a." * 40000  # 80k chars, no trailing TLD → worst case for backtracking
    assert _contains_url_or_domain(big) is False


# ---------------------------------------------------------------------------
# decide_backend — browse routing via URL/domain alone (AC1, AC2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "prompt",
    [
        "return the top 3 headlines on Bloomberg.com right now",  # URL alone, no verb
        "go to bloomberg.com and give me the top 3 headlines",    # URL, 'go to' is NOT a kw
        "https://news.ycombinator.com summarize the top stories",  # scheme
        "check nytimes.com and tell me the lead story",           # URL, 'check' not a kw
        "open https://x.com and click subscribe",                 # browse keyword + URL
    ],
)
def test_agentic_url_prompts_route_to_computer_use(prompt: str) -> None:
    backend, sentinel, reason = decide_backend(
        agentic_intent=True,
        agentic_confidence=0.9,
        task_type="reasoning",
        prompt=prompt,
    )
    assert backend == "computer_use", f"{prompt!r} -> {backend} ({reason})"
    assert sentinel == COMPUTER_USE_SENTINEL


# ---------------------------------------------------------------------------
# No over-capture (AC4) — the guardrails from code review.
# ---------------------------------------------------------------------------

def test_coding_prompt_with_code_filename_not_browsed() -> None:
    assert _route("fix the bug in app.py", task_type="coding") == "claude_code"


def test_refactor_with_ts_file_not_browsed() -> None:
    assert _route("refactor utils.ts to remove the duplication", task_type="coding") == "claude_code"


@pytest.mark.parametrize(
    "prompt,task",
    [
        # A domain in a CODING prompt is not a browse task — URL defers to the
        # coding signal (build keyword and/or coding task_type).
        ("refactor the client for api.stripe.com", "coding"),
        ("clone github.com/user/repo and fix the bug", "coding"),
        ("build an asp.net service that calls example.com", "general"),  # 'build' kw
    ],
)
def test_domain_in_coding_prompt_defers_to_claude_code(prompt: str, task: str) -> None:
    assert _route(prompt, task_type=task) == "claude_code"


@pytest.mark.parametrize(
    "prompt",
    [
        "go to the next step and implement the parser",  # generic verb, no domain
        "implement scroll behavior in the component",
        "add a screenshot to the readme",
    ],
)
def test_generic_verbs_do_not_over_capture_coding(prompt: str) -> None:
    assert _route(prompt, task_type="coding") != "computer_use"


def test_email_mention_not_browsed() -> None:
    # An agentic prompt naming an email address must NOT route to computer_use.
    assert _route("email the summary to user@example.com") != "computer_use"


def test_non_agentic_domain_mention_not_browsed() -> None:
    # A domain in a CONVERSATIONAL prompt must NOT route to computer_use — the
    # agentic gate is what suppresses false positives from domain mentions.
    assert _route("what is the difference between openai.com and anthropic.com", agentic=False) == "openrouter"


def test_bare_site_name_without_tld_is_a_known_gap() -> None:
    # DOCUMENTED LIMITATION (deferred-work): a bare site NAME with no TLD and no
    # browse keyword ("go to hacker news and summarize") is not detected — it
    # falls through to openrouter. When the user names a domain, it IS caught.
    assert _route("go to hacker news and summarize the top 3 stories") == "openrouter"


def test_conversational_prompt_unaffected() -> None:
    assert _route("what's 3.14 rounded to two decimals", agentic=False) == "openrouter"
