# Prompt-Optimizer

## What This Is

A quality-first prompt router behind a multi-turn chat UI. The user types into a single chat box and the system silently routes the prompt to the most efficient LLM or agent for the task — Claude Sonnet/GPT-5/Gemini via OpenRouter for conversational work, Claude Code SDK for build-and-edit coding tasks, Anthropic computer-use for browse-and-act tasks — and streams the response back. The goal is "no more manual model picking": every prompt goes to the right backend automatically. Comet/Perplexity-style auto-routing with a transparent rationale shown alongside each answer.

## Core Value

Every prompt routes to the LLM or agent best suited to deliver a high-quality answer, with no manual model selection from the user.

## Requirements

### Validated

<!-- Inferred from existing code in the repo (mapped in .planning/codebase/). -->

- ✓ **Task type classifier** — Stage-1 model predicts coding / math / writing / factual / agentic / etc. from prompt text + handcrafted features (`models/task_type_classifier.joblib`, `src/task_classifier/train_task_classifier_robust.py`).
- ✓ **Two-stage benchmark-model router** — Stage-2 model predicts the best benchmark model class given task signal + features (`models/model_router.joblib`, `src/model_router/train_model_router.py`).
- ✓ **Tier router experiment** — alternate Stage-2 head that predicts cheap / medium / strong tier (`models/tier_router.joblib`, `src/model_router_tier/train_tier_router.py`).
- ✓ **Embedding router experiment** — sentence-transformer baseline that bypasses TF-IDF (`models/embedding_router.joblib`, `src/model_router/train_embedding_router.py`).
- ✓ **Feature extraction contract** — `PromptFeatureExtractor` shared by training and inference; saved alongside model artifacts (`src/feature_extraction/Feature_extractor.py`).
- ✓ **Model-mapping config** — benchmark model names → `{display_name, provider, tier, api_model, openrouter_verified}` (`config/model_mapping.json`).
- ✓ **Evaluation infrastructure** — baselines (oracle / cheapest / always-GPT-5 / embedding) and per-class confusion / F1 / PR plots (`src/evaluation/`, `evaluation/`).
- ✓ **CLI demo** — interactive REPL that loads saved models and prints simulated route metadata (`src/demo/demo_router.py`, `src/demo/demo_embedding_router.py`).

### Active

<!-- v1 scope, hypothesis until shipped. -->

- [ ] **Agentic-intent classifier** — new trained binary head that distinguishes conversational prompts ("explain X") from agentic prompts ("build me X", "open this URL and do Y"), feeding the agent-vs-chat decision.
- [ ] **OpenRouter integration** — live API calls (not simulated metadata) to the chat models referenced in `config/model_mapping.json`, with streaming responses.
- [ ] **Claude Code SDK integration** — agentic backend invoked when the router decides a task needs file edits / multi-step coding work.
- [ ] **Anthropic computer-use integration** — agentic backend invoked when the router decides a task needs browser-style action (open URL, fill form, check status).
- [ ] **Routing decision layer** — composes existing classifier + new agentic-intent classifier + model_router + budget heuristic into a single routing call that returns `{backend, model_or_agent, rationale}`.
- [ ] **FastAPI back-end** — wraps the Python routing pipeline behind HTTP / streaming endpoints; loads `joblib` artifacts at startup; orchestrates calls to OpenRouter / Claude Code SDK / computer-use.
- [ ] **Next.js chat UI** — single-input chat surface with multi-turn threads, persistent history sidebar, streamed responses, and a visible "routed to X because Y" chip per turn.
- [ ] **Persistent thread storage** — chat history persists across sessions (local SQLite or filesystem; no shared / hosted store).
- [ ] **BYOK key management** — users supply their own OpenRouter / Anthropic / Google keys via `.env` or in-app settings panel; never persisted server-side beyond the local instance.
- [ ] **Quality-first scoring** — when multiple backends are eligible, pick the highest predicted-quality option; tiebreak on cost.
- [ ] **Demo path** — opinionated golden-path README walkthrough proving the routing thesis end-to-end (build-app prompt → Claude Code; capital-of-France prompt → cheap chat model; URL-action prompt → computer-use).

### Out of Scope

- **User accounts / auth** — open-source BYOK; each user runs their own instance.
- **Billing / payments** — no hosted version, so no monetization layer.
- **Hosted multi-tenant SaaS** — repo ships a runnable open-source app, not a service.
- **Mobile / native apps** — web-first; mobile is post-v1 if ever.
- **Fine-tuning the generative LLMs themselves** — we route to existing third-party models; we only train the small routing classifiers (task type, agentic intent).
- **Live retraining loop** — no online learning of the routers from chat-UI traffic in v1; all training stays offline against `data_processed/`.
- **Cost-aware target as a primary objective** — the cost-aware experiment in the existing repo is preserved as a baseline but is not the optimization target (Core Value is quality first, cost only as tiebreaker).

## Context

- **Repo state:** Brownfield. Offline scikit-learn pipeline already produces a working two-stage router and a CLI demo. Codebase mapping is at `.planning/codebase/` (ARCHITECTURE / STACK / STRUCTURE / CONVENTIONS / INTEGRATIONS / CONCERNS / TESTING).
- **Training data:** Trained on `LLMRouterBench` — a benchmark of standardized model outputs across math / coding / logic / knowledge / affective / instruction-following / tool-use tasks. Raw `data_raw/` is not committed; processed CSVs in `data_processed/` are git-LFS pointers.
- **Existing integration shape:** `config/model_mapping.json` already encodes the bridge from benchmark model slugs to OpenRouter routes (16 entries; 9 verified, 7 simulated). The new product makes those routes live.
- **Inspirations:** Perplexity's Comet (auto-routing + agent capability + slick single-input UX) and the broader "no model picker" movement in AI chat UIs.
- **Repo conventions:** Each pipeline stage is a standalone Python script; saved `joblib` carries `feature_columns` so inference reproduces the exact training matrix; no test suite exists today; no requirements lockfile committed.

## Constraints

- **Tech stack — Python pipeline:** Python 3.10+ with scikit-learn / pandas / scipy / joblib / sentence-transformers / nltk (existing — preserve compatibility with saved artifacts).
- **Tech stack — Web stack:** Next.js (TypeScript) front-end + FastAPI (Python) back-end. FastAPI is mandatory because it must load and call the existing `joblib` routing models in-process.
- **Distribution:** Open-source, runnable locally. No hosted backend, no shared infra.
- **Key handling:** Bring-your-own-keys (OpenRouter, Anthropic, optional Google). Keys never leave the user's local instance.
- **Optimization target:** Quality first, cost as tiebreaker — never optimize cost at the expense of expected answer quality.
- **Dependencies on third parties:** OpenRouter, Anthropic Claude Code SDK, Anthropic computer-use. Each adds an availability / pricing dependency outside our control.
- **No fine-tuning of generative LLMs** — we only train the small routing heads.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reuse + extend existing `task_type_classifier` and `model_router` instead of starting fresh | Smallest scope, leverages all prior training work; existing pipeline is already a viable Stage-1/Stage-2 brain | — Pending |
| Backend lineup: OpenRouter (chat) + Claude Code SDK (agentic coding) + Anthropic computer-use (browse/act) | Covers conversational, code-action, and browser-action surfaces with minimal vendor sprawl; one chat aggregator + two named agents | — Pending |
| Detect agent-vs-chat via a trained binary "agentic-intent" classifier | Consistent with repo's ML approach; debuggable, comparable to the existing classifiers; avoids per-turn LLM-as-judge cost | — Pending |
| Web stack: Next.js front-end + FastAPI back-end | FastAPI keeps the Python routing pipeline in-process; Next.js delivers production-grade chat UX | — Pending |
| Multi-turn chat with persistent thread history | Real product feel; matches the Comet inspiration; raises the bar above the current single-shot CLI demo | — Pending |
| Open-source, BYOK, no auth / billing | Removes infra surface entirely; fastest path to a credible demo of the routing thesis | — Pending |
| Keep repo named "Prompt-Optimizer" | Routing is a form of prompt optimization; rename churn isn't worth it | — Pending |
| Quality-first within budget — cost is tiebreaker only | Differentiates from cost-first routers; aligns with the "build me a finance app → Claude Code" example (correct backend matters more than saving pennies) | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-11 after initialization*
