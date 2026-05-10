# Prompt Optimizer

A prompt routing project that classifies user queries by task type and prepares them for model routing.

Instead of sending every prompt to the same language model, this project explores a smarter routing pipeline: analyze the prompt, extract useful features, classify the task type, and eventually route the prompt to a model based on performance and cost.

---

## Project Overview

Large language models do not perform equally well on every task. A model that is strong at coding may not be the best choice for factual QA, math, reasoning, writing, or medical-style questions. At the same time, always using the largest or most expensive model is not cost efficient.

This project works toward a prompt router that can make more informed decisions about which model should handle a given query.

The long-term routing idea is:

```text
User Query
   ↓
Feature Extraction
   ↓
Task Type Classification
   ↓
Model Routing
   ↓
Recommended Model
```
---
## Benchmark Data
This project uses benchmark-style data based on `RouterBench`, a benchmark for evaluating multi-LLM routing systems.

`RouterBench` was introduced in the paper `“ROUTERBENCH: A Benchmark for Multi-LLM Routing System.” `The benchmark is designed around the idea of routing prompts between different language models while balancing model performance and cost.

### Useful links:

- `RouterBench` GitHub: https://github.com/withmartian/routerbench
- `RouterBench` paper: https://arxiv.org/abs/2403.12031

`RouterBench` is useful for this project because it frames model selection as a routing problem instead of assuming one model should answer every prompt.

---