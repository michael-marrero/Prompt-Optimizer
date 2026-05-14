"""One-shot script that materialises ``data_processed/agentic_intent_seeds.csv``.

Per 01-03-PLAN.md Task 1, we hand-author 30 high-quality agentic seed prompts
anchored to the README golden-path examples (D-05). The plan asks us to use
``csv.writer`` rather than hand-typing the CSV so commas, quotes, and other
RFC-4180 escapes are handled correctly.

This script is intentionally tiny and lives under ``scripts/`` because it is a
one-off author tool, NOT part of the runtime pipeline. The pipeline-grade
script is ``src/task_classifier/build_agentic_dataset.py`` (Task 3).

Run once from the repo root:

    uv run python scripts/write_agentic_seeds.py
"""

from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "data_processed" / "agentic_intent_seeds.csv"


# Three sub-buckets per D-05 / RESEARCH §Pattern 3 Step 1:
#   ~10 build/edit prompts anchored to "build me a finance app" (Claude Code intent)
#   ~10 browse/click prompts anchored to "open this URL and check the price" (computer-use intent)
#   ~10 multi-step prompts combining reasoning + action (clearly agentic, either backend)
#
# All prompts use imperative verbs from the locked 26-verb set (Plan 01-02 D-decision)
# so PromptFeatureExtractor._agentic_features will see imperative_verb_count >= 1
# on every row. The browse bucket includes literal "https://" URLs to also light up
# has_url for the agentic-intent classifier.
BUILD_EDIT_PROMPTS: list[str] = [
    "build me a small finance dashboard that tracks my monthly spending",
    "write a CLI tool that summarizes my AWS bill by service and region",
    "create a Python script that scrapes Hacker News front-page headlines into a CSV",
    "refactor my Flask app to use FastAPI and async endpoints",
    "implement a binary search tree with insert, find, and delete operations",
    "add unit tests for the auth module covering the JWT refresh flow",
    "fix the off-by-one bug in pagination.py that drops the last record on every page",
    "edit my Dockerfile to use Python 3.12 and a slim base image",
    "rewrite this regex to run in O(n) and not catastrophically backtrack",
    "generate a sqlx schema for a todo-list app with users, lists, and items",
]

BROWSE_CLICK_PROMPTS: list[str] = [
    "open https://news.ycombinator.com and summarize the top 5 stories for me",
    "navigate to amazon.com and find a USB-C charger under $20 with prime shipping",
    "click the subscribe button on this newsletter page and confirm the opt-in email",
    "fill out the contact form at https://example.com/contact with my standard intro",
    "submit my resume PDF to the careers page at https://acme.io/jobs/staff-engineer",
    "browse to my Gmail inbox and report the count of unread messages from last week",
    "visit https://github.com/microsoft/vscode and tell me the current star count",
    "download the latest invoice from https://stripe.com and save it to my Downloads",
    "scrape https://example.com/products and list every item with its current price",
    "check if my flight UA853 on united.com is delayed or on time today",
]

MULTI_STEP_PROMPTS: list[str] = [
    "open my repo, find all TODO comments, and write a summary report grouped by author",
    "build a Streamlit app that fetches weather from openweathermap.org and plots a 7-day forecast",
    "refactor my data pipeline to read from S3 and write to BigQuery using batch loads",
    "create a GitHub Action that runs pytest on every PR and comments coverage deltas",
    "investigate why the prod API returns 500s on /checkout and fix the root cause",
    "write a script that monitors my CPU usage every minute and alerts via webhook over 80%",
    "set up a cron job that backs up my notes folder to S3 nightly with versioning",
    "port my React app from Create React App to Vite without breaking the build",
    "add OAuth2 login to my Express server using passport and the Google strategy",
    "convert my Jupyter notebook to a reusable Python module with a proper CLI entry point",
]


def main() -> None:
    rows = []
    for prompt in BUILD_EDIT_PROMPTS + BROWSE_CLICK_PROMPTS + MULTI_STEP_PROMPTS:
        rows.append(
            {
                "text": prompt,
                "label": "agentic",
                "source": "seed",
                "dataset": "hand-written",
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["text", "label", "source", "dataset"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} hand-written agentic seeds to: {OUTPUT}")


if __name__ == "__main__":
    main()
