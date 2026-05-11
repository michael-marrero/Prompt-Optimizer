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
| Oracle            | TBD      | TBD      | TBD         | TBD                |
| Always Cheapest   | TBD      | TBD      | TBD         | TBD                |
| Always GPT-5      | TBD      | TBD      | TBD         | TBD                |
| Embedding Router  | TBD      | TBD      | TBD         | TBD                |

### Key finding

Baseline comparison helps show whether the learned router is doing better than simple fixed strategies.

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
