# Evaluation Summary

This file summarizes the main evaluation results for the Prompt Optimizer project.

The project tested multiple routing strategies:

1. Task type classification
2. Tier routing
3. Exact model routing
4. Embedding-based routing
5. Simple baseline strategies

The goal was to understand which routing target is most stable and useful for prompt-to-model selection.

---

## 1. Task Type Classifier

The task type classifier predicts the category of a prompt before routing.

**Example task labels:**

- `coding`
- `math`
- `reasoning`
- `knowledge`
- `medical`
- `writing`
- `emotion`
- `agentic`

The classifier performed best on clearer task categories such as coding, emotion, medical, reasoning, factual, and agentic prompts.

The weaker categories were mostly overlapping labels such as:

- `general`
- `knowledge`
- `factual`

These labels can describe very similar prompts, so some confusion is expected.

### Key finding

The task classifier is useful as an intermediate signal for routing, but some labels should be merged in a future version to reduce overlap.

---

## 2. Tier Router

The tier router predicts a broad model tier:

```text
cheap
medium
strong
```

This router was trained as a coarse-grained routing system.

### Results

| Metric       | Score  |
| ------------ | ------ |
| Accuracy     | 0.7798 |
| Macro F1     | 0.7519 |
| Weighted F1  | 0.7845 |

### Interpretation

The tier router was the strongest and most stable router in the project.

It performed well because tier prediction is simpler than exact model prediction. Instead of choosing one model out of many similar models, the router only needs to decide whether a prompt should go to a cheaper, medium, or stronger model class.

The main weakness was that some strong prompts were predicted as medium.

### Key finding

Tier routing is the most practical routing target in the current project.

---

## 3. Exact Model Router

The exact model router predicts a specific model class from the benchmark data.

This task is harder because there are many possible model labels and some labels have much more training data than others.

### Results

| Metric        | Score |
| ------------- | ----- |
| Accuracy      | 0.21  |
| Macro F1      | 0.17  |
| Weighted F1   | 0.22  |

### Interpretation

Exact model routing was significantly harder than tier routing.

The model struggled because:

- The model labels are highly imbalanced.
- Some models have very low support.
- Several model classes behave similarly.
- Exact model prediction is stricter than tier prediction.

For example, predicting the wrong model inside the same general capability group still counts as fully incorrect.

### Key finding

Exact model routing is possible, but it is not stable enough to be the main routing method in this version.

---

## 4. Embedding Router

The embedding router is a separate semantic-routing experiment.

Unlike the main router, it does not use:

- Task classifier output
- Handcrafted prompt features
- TF-IDF
- Top-model grouping

Instead, it uses:

`origin_query` → sentence embedding → `best_model`

The embedding model used was:

**`sentence-transformers/all-MiniLM-L6-v2`**

### Purpose

This experiment tests whether semantic prompt meaning alone can learn model routing patterns.

### Results

| Metric        | Value |
| ------------- | ----- |
| Accuracy      | TBD   |
| Macro F1      | TBD   |
| Weighted F1   | TBD   |

### Interpretation

The embedding router provides a useful comparison against the TF-IDF router.

- If the embedding router improves exact model prediction, it suggests that semantic prompt representations are more useful than sparse word features.
- If it does not improve performance, it suggests that exact model routing is difficult because of the target labels, not just the feature representation.

### Key finding

Embedding-based routing is a useful semantic experiment, even if exact model prediction remains difficult.

---

## 5. Baseline Comparison

The project also compares routing models against simple baselines.

**Baseline strategies include:**

- Oracle
- Always Cheapest
- Always GPT-5
- Embedding Router

### Baseline meanings

**Oracle**

The oracle uses the true `best_model` label from the dataset. This is not deployable. It represents the upper bound.

**Always Cheapest**

This baseline always predicts the globally cheapest model. It represents the lowest-cost strategy.

**Always GPT-5**

This baseline always predicts `gpt-5`. It represents an expensive / strong-model strategy.

**Embedding Router**

This is the learned semantic router using sentence embeddings.

### Results

| Strategy          | Accuracy | Macro F1 | Weighted F1 | Estimated avg cost |
| ----------------- | -------- | -------- | ----------- | ------------------ |
| Oracle            | 1.000    | 1.000    | 1.000       | n/a (upper bound)  |
| Always Cheapest   | skipped  | skipped  | skipped     | n/a¹               |
| Always GPT-5      | 0.024    | 0.001    | 0.001       | n/a¹               |
| Embedding Router² | 0.239    | 0.208    | 0.246       | n/a¹               |

*(Run 2026-07-13, `evaluate_baselines.py` → `evaluation/baseline_comparison_metrics.csv`. ¹Cost columns unavailable: `flat_records.csv` is regenerated from the uncommitted `data_raw/`, so per-model cost/score is absent in this checkout. Always-Cheapest skipped for the same reason. ²Embedding Router is graded at vendor-family granularity — not directly comparable to the exact-model strategies.)*

### Key finding — the metric, not just the router, is the problem

These numbers look alarming (Always-GPT-5 = 0.024) but the **target is misleading for a quality-first product**. `best_model` is defined as the *cheapest* model that achieves the top score, and `best_score` is essentially binary (0/1) correctness, so on any prompt where many models answer correctly the label collapses to a cost tiebreak among ~16–38 near-interchangeable models.

Consequences:
- **Oracle = 1.000 is a tautology** (it reads the label it's graded against).
- **Always-GPT-5 = 0.024 does NOT mean GPT-5 gives bad answers** — it means GPT-5 is rarely the *cheapest* correct model. It says nothing about answer quality.
- **Exact-model / embedding routers at ~0.2 are near the ceiling of an almost-unwinnable target**, not evidence a better feature representation would help (the embedding router — different features, same target — lands at the same ~0.2, which points at the target, not the features).

**What was missing — now resolved.** A *quality-regret* metric — for each routing choice, the answer-quality (score) given up versus the oracle's best-available model, alongside cost — is the number that decides whether learned routing beats "always route to one strong model." The tool now exists: `src/evaluation/evaluate_quality_regret.py` (per-model mean regret + cost + coverage; reports the best fixed-model baseline; synthetic `--selftest`). It needs per-(model, question) scores (`flat_records.csv`), which regenerate from the uncommitted `data_raw/`; on a data-materialized machine run `python -m src.data.flatten_raw_jsons` then the regret eval.

**Partial resolution from materialized data (`classifier_training.csv`, 27,203 questions, 2026-07-13):** the benchmark's routing target is dominated by cost, not quality —
- **88.4%** of questions are solved by *some* model (`best_score` = 1.0): quality is abundant, not scarce.
- **55%** of `best_model` picks are **zero-cost** models; median winner cost = 0; median 20 models compared per question.
- `best_model` concentrates on small/cheap models (`internlm3-8b-instruct` 32%, `qwen3-235b` 19%); GPT-5 is the labelled best on only **2.4%**.

**Implication for the product:** on this benchmark, picking *a* correct model is easy (many tie); the label is a cost tiebreak among interchangeable correct models — which is why exact-model routing caps at ~0.2 and Always-GPT-5 at 0.024. The defensible design is **detect the ~12% genuinely-hard prompts and route those strong; serve the easy 88% from any competent cheap model chosen by cost/latency** — i.e. the tier router (0.78) + a hard-prompt detector, not a 40-class exact-model head. **Caveat:** `best_score` is 0/1 benchmark-graded correctness on benchmark datasets; open-ended real chat prompts are not 0/1 gradeable, so "88% solved" will not transfer — quality differences on real traffic can only come from production feedback (Epic 3), and the benchmark should drive hard-prompt detection + cost, not exact-model choice.

---

## 6. Cost-Aware Routing Experiment

A cost-aware dataset builder was also tested.

The goal was to select the cheapest model whose score was close to the best-performing model.

However, the benchmark data made this difficult because many scores were binary: **`0.0` or `1.0`**.

This means many models either fully succeeded or failed on a prompt. When several models all scored **1.0**, the cost-aware label often became the cheapest correct model rather than a meaningful quality–cost tradeoff.

### Key finding

Pure cost-aware routing was limited by the structure of the benchmark scores. Because of this, tier routing became the better practical cost-aware proxy.

---

## 7. Overall Conclusion

The strongest result from the project is that **broad routing targets are more stable than exact model targets**.

### Best performing approach

**Task type classifier → tier router**

The tier router performed much better than exact model routing and provides a more realistic approach for model selection.

### Experimental extensions

The project also tested:

- Exact model routing
- Top-model routing
- Cost-aware value routing
- Embedding-based routing

These experiments showed that exact model prediction is much harder because the labels are imbalanced and model performance can be very similar across prompts.

### Final takeaway

The most reliable routing strategy in this project is to classify prompts by task type and route them to a broad model tier. Exact model routing and embedding-based routing are useful extensions, but tier routing is the strongest current implementation.

---

## 8. Future Evaluation Work

Future evaluation improvements could include:

- Compare against more baselines
- Add model-family routing
- Evaluate answer quality after routing
- Add confidence-based fallback routing
- Measure simulated cost savings
- Test routing on unseen prompt datasets
- Add real API calls for verified model routes

Once you obtain the embedding-router and baseline numbers, replace every **`TBD`** in this document. This file is intended to serve as the project evidence board for what was tested, what worked, what did not, and what we learned.
