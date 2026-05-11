# External Integrations

**Analysis Date:** 2026-05-11

## APIs & External Services

**LLM Provider Aggregator (metadata-only, not yet wired):**
- **OpenRouter** (`https://openrouter.ai`) - The project's target model-serving aggregator. Mapped via `config/model_mapping.json`. The demo (`src/demo/demo_router.py`) only *simulates* routes — there is no live HTTP call to OpenRouter.
  - SDK / Client: **None.** No `requests`, `httpx`, `aiohttp`, `urllib`, or `openai` import appears anywhere under `src/`. The demo's `get_api_model_for_real_call()` (`src/demo/demo_router.py:274-284`) returns the OpenRouter API model slug *if* `openrouter_verified` is true, but no code consumes that string to make a request.
  - Auth: **Not configured.** No `OPENROUTER_API_KEY` environment variable is read (no `os.environ` / `os.getenv` calls in `src/`). When live calls are added, the canonical env var would be `OPENROUTER_API_KEY` against base URL `https://openrouter.ai/api/v1`.
  - Notes (per `ReadMe.md` "Limitations"): *"The final demo simulates routing decisions instead of calling live model APIs"* and *"Some benchmark model names do not directly map to verified OpenRouter routes."*

**Hugging Face Hub (transitive):**
- **`sentence-transformers/all-MiniLM-L6-v2`** - Downloaded on first run of the embedding router (`src/model_router/train_embedding_router.py:54`) and the baseline evaluation (`src/evaluation/evaluate_baselines.py`). Fetched implicitly by the `SentenceTransformer(...)` constructor; cached under the user's `~/.cache/huggingface/` directory by default.
  - SDK: `sentence-transformers` (which wraps `transformers` + `torch`)
  - Auth: None required for this public model.

**NLTK Corpus Server:**
- **NLTK data** - `nltk.download("punkt_tab")` and `nltk.download("punkt")` are invoked lazily by `_ensure_nltk_sentence_tokenizer()` in `src/feature_extraction/Feature_extractor.py:11-18` the first time `sent_tokenize` is needed. Downloads from NLTK's public data host; no auth.

## Model Providers (via `config/model_mapping.json`)

The mapping is the **single source of truth** for "which provider serves this model slug." It is loaded by `src/demo/demo_router.py:load_json()` and consulted by `choose_final_route()` (`src/demo/demo_router.py:245-271`).

### Schema

Each entry in `config/model_mapping.json` is keyed by a **benchmark model slug** (the label predicted by the model router) and maps to:

| Field | Type | Purpose |
|-------|------|---------|
| `display_name` | string | Human-readable name printed by the demo |
| `provider` | `"openrouter"` \| `"simulated"` | Whether this route can hit OpenRouter or is a stub |
| `tier` | `"cheap"` \| `"medium"` \| `"strong"` | Tier-router target for cost/quality routing |
| `api_model` | string \| `null` | The exact OpenRouter model ID (e.g. `openai/gpt-5`) when verified; `null` otherwise |
| `openrouter_verified` | bool | Gate used by `get_api_model_for_real_call()` to decide if `api_model` is safe to call |
| `notes` | string | Human notes on verification status |

### Full Slug -> Provider / API Model / Tier Map

| Benchmark slug | Provider | API model (OpenRouter ID) | Tier | Verified |
|----------------|----------|---------------------------|------|----------|
| `qwen3-235b-a22b-2507` | openrouter | `qwen/qwen3-235b-a22b-2507` | strong | yes |
| `qwen3-235b-a22b-thinking-2507` | openrouter | `qwen/qwen3-235b-a22b-thinking-2507` | strong | yes |
| `openrouter` | openrouter | `openrouter/auto` | medium | yes |
| `deepseek-v3.1-terminus` | openrouter | `deepseek/deepseek-v3.1-terminus` | strong | yes |
| `deepseek-v3-0324` | openrouter | `deepseek/deepseek-chat-v3-0324` | strong | yes |
| `gpt-5` | openrouter | `openai/gpt-5` | strong | yes |
| `gpt-5-chat` | openrouter | `openai/gpt-5-chat` | strong | yes |
| `kimi-k2-0905` | openrouter | `moonshotai/kimi-k2-0905` | strong | yes |
| `gemini-2.5-flash` | openrouter | `google/gemini-2.5-flash` | medium | yes |
| `internlm3-8b-instruct` | simulated | `null` | cheap | no |
| `granite-3.3-8b-instruct` | simulated | `null` | cheap | no |
| `glm-4-9b-chat` | simulated | `null` | cheap | no |
| `MiniCPM4.1-8B` | simulated | `null` | cheap | no |
| `cogito-v1-preview-llama-8B` | simulated | `null` | cheap | no |
| `OpenThinker3-7B` | simulated | `null` | cheap | no |
| `OTHER` | simulated | `null` | medium | no |

**`OTHER`** is the fallback bucket for any predicted slug not present in the mapping (`src/demo/demo_router.py:257-261`).

### Vendor families

`src/model_router/model_family.py:infer_model_vendor_family()` collapses raw checkpoint names into coarse vendor buckets used by the embedding-router target and baseline eval: `qwen`, `deepseek`, `gpt`, `gemini`, `internlm`, `granite`, `glm`, `kimi`, `openrouter`, `llama`, `minicpm`, `openthinker`, `claude`, `mimo`, `fin-r1`, `gemma`, `other`.

## Data Storage

**Databases:** None. No SQL, no SQLite, no ORM, no `psycopg`, no `sqlalchemy` imports.

**File Storage:** Local filesystem only.
- Trained models: `models/*.joblib`
- Processed data: `data_processed/*.csv`, `data_processed/*.npy` (embedding caches)
- Evaluation artifacts: `evaluation/*.csv`, `evaluation/*/*.png`

**Caching:**
- Sentence-transformer embedding cache: `.npy` files under `data_processed/` with filenames derived from `embeddings_cache_path()` (`src/model_router/train_embedding_router.py:69-81`). Filename encodes the embedding model slug and any context-prepending flags (`PREPEND_DATASET_TO_QUERY`, `PREPEND_PROMPT_STUB`) so toggling the flags cannot silently reuse stale rows.
- Hugging Face transformer weights are cached under `~/.cache/huggingface/` by the `sentence-transformers` library (default behavior, not overridden by this repo).
- NLTK data is cached under `~/nltk_data/` (default).

## Authentication & Identity

Not applicable. The project has no user-auth, no service-account, and (currently) no outbound API authentication. When OpenRouter integration is added, the standard pattern is a single `OPENROUTER_API_KEY` bearer token in the `Authorization: Bearer ...` header — no such code path exists today.

## Monitoring & Observability

**Error tracking:** None.

**Logging:** Python `logging` module (stdlib), configured per-script.
- `src/data/flatten_raw_jsons.py:_setup_logging()` - Sets level based on `-v`/`-vv` flags, format `%(asctime)s | %(levelname)-7s | %(message)s`.
- Other scripts use `print()` for progress, not `logging`.

## CI/CD & Deployment

**Hosting:** None. The repo is a local research/demo project.

**CI Pipeline:** None. No `.github/workflows/`, no `.gitlab-ci.yml`, no `.circleci/`, no `Jenkinsfile`.

**Deployment:** The user runs `python src/demo/demo_router.py` locally. There is no Dockerfile, no docker-compose, no Procfile, no serverless config.

## Environment Configuration

**Required env vars:** None currently consumed.

**Anticipated future env vars** (not yet implemented, mentioned in `ReadMe.md` "Future Work" as *"Add real OpenRouter API calls for verified routes"*):
- `OPENROUTER_API_KEY` - Bearer token for OpenRouter

**Secrets location:** No secrets are stored, read, or referenced. No `.env`, `.env.example`, `credentials.json`, or `*.pem` files exist in the repo.

## Webhooks & Callbacks

**Incoming:** None. The repo has no HTTP server, no Flask/FastAPI/Django, no webhook handlers.

**Outgoing:** None implemented (see "OpenRouter" above — the route metadata exists but `get_api_model_for_real_call()` in `src/demo/demo_router.py:274-284` is only consumed to *print* the resolved model ID).

## Dataset Source

**LLMRouterBench** - The benchmark data this project trains on.
- Upstream repo: `https://github.com/ynulihao/LLMRouterBench`
- Cited in `ReadMe.md` (sections "Benchmark Data", "Citation") as: *"LLMRouterBench: A Massive Benchmark and Unified Framework for LLM Routing" (Li et al., 2026, Findings of ACL 2026)*.
- Format: Nested JSON tree (`data_raw/<benchmark-release>/<dataset>/<split>/<model_dir>/<file>.json`) — each file holds top-level metadata plus a `records` array with fields `origin_query`, `prompt`, `prediction`, `ground_truth`, `score`, `prompt_tokens`, `completion_tokens`, `cost`, `instance_id`, `index`.
- Ingestion script: `src/data/flatten_raw_jsons.py` (entrypoint `python -m src.data.flatten_raw_jsons --input data_raw --output data_processed/flat_records.csv`).
- `data_raw/` is **not** committed. Users must clone LLMRouterBench separately and place its release tree under `data_raw/` before running the pipeline.

---

*Integration audit: 2026-05-11*
