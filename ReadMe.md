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

This project uses benchmark-style data from `LLMRouterBench`, a large-scale benchmark and unified framework for LLM routing.

`LLMRouterBench` is designed around the idea that no single language model performs best across every domain. Instead, different models can perform better on different types of prompts, such as math, coding, logic, knowledge, affective tasks, instruction following, and tool use.

The benchmark includes standardized model outputs across multiple datasets and models, with fields such as:

- `origin_query`
- `prompt`
- `prediction`
- `ground_truth`
- `score`
- `prompt_tokens`
- `completion_tokens`
- `cost`

This project uses that data to train a smaller prompt routing pipeline that predicts task type and recommends a model route.

### Useful links

- `LLMRouterBench` GitHub: https://github.com/ynulihao/LLMRouterBench---

## Project Structure


```text
Prompt-Optimizer/
├── config/
│   └── model_mapping.json
│
├── data_processed/
│   ├── classifier_training.csv
│   ├── classifier_training_cost_aware.csv
│   ├── classifier_training_features.csv
│   ├── classifier_training_with_types.csv
│   ├── flat_records.csv
│   ├── router_training_dataset.csv
│   └── router_training_dataset_top_models.csv
│
├── data_raw/
│
├── evaluation/
│   ├── model_router_plots/
│   │   └── model_router_target_distribution.png
│   │
│   ├── plots/
│   │   ├── class_distribution.png
│   │   ├── confusion_matrix.png
│   │   ├── confusion_matrix_normalized.png
│   │   ├── per_class_f1.png
│   │   ├── precision_recall_f1.png
│   │   └── prediction_confidence.png
│   │
│   ├── router_plots/
│   │   ├── router_target_distribution.png
│   │   ├── tier_router_confusion_matrix.png
│   │   ├── tier_router_confusion_matrix_normalized.png
│   │   └── tier_router_precision_recall_f1.png
│   │
│   ├── misclassified_examples.csv
│   ├── tier_router_metrics.csv
│   └── tier_router_misclassified_examples.csv
│
├── models/
│   ├── task_type_classifier.joblib
│   └── tier_router.joblib
│   ├── model_router.joblib
│
├── src/
│   ├── data/
│   │   ├── __init__.py
│   │   ├── build_classifier_dataset.py
│   │   ├── build_classifier_dataset_cost_aware.py
│   │   └── flatten_raw_jsons.py
│   │
│   ├── demo/
│   │   └── demo_router.py
│   │
│   ├── feature_extraction/
│   │   ├── __init__.py
│   │   ├── build_features.py
│   │   └── Feature_extractor.py
│   │
│   ├── model_router/
│   │   ├── build_top_model_dataset.py
│   │   └── train_model_router.py
│   │
│   ├── model_router_tier/
│   │   ├── build_router_dataset.py
│   │   ├── router_tier_system.py
│   │   └── train_tier_router.py
│   │
│   └── task_classifier/
│       ├── build_question_type.py
│       ├── train_task_classifier_robust.py
│       └── train_task_classifier_simple.py
│
├── .gitattributes
├── LICENSE
└── ReadMe.md
```

---

## Feature Extraction

The feature extraction stage creates handcrafted numeric features from each prompt.

These features help the classifier and router understand more than just the raw words in a query.

Examples of extracted features include:

- Character count
- Word count
- Unique word count
- Average word length
- Maximum word length
- Number count
- Sentence count
- Question mark count
- Punctuation counts
- Code keyword indicators
- Math keyword indicators
- Prompt structure features

These handcrafted features are combined with TF-IDF text features during model training.

The feature extraction files are located in:

```text
src/feature_extraction/
```
---
## Task Type Classifier

The first major model in the project is the Task Type Classifier.

Its job is to predict what kind of task a prompt is asking for.

Example:

```text 
Prompt: Write a Python function that checks whether a string is a palindrome.

Predicted task type: coding
```

The classifier currently predicts categories such as:

- `agentic`
- `coding`
- `emotion`
- `factual`
- `general`
- `knowledge`
- `math`
- `medical`
- `reasoning`
- `writing`

The robust classifier uses:

- Word-level TF-IDF
- Character-level TF-IDF
- Handcrafted numeric prompt features
- Logistic regression
- Balanced class weights
- Joblib model saving/loading

The main training file is:

```text 
src/task_classifier/train_task_classifier_robust.py
```
The saved model is stored at:
```text
models/task_type_classifier.joblib
```
This saved classifier is later used by the router pipeline.

---
## Task Classifier Results

The task classifier performed well on several clear task categories.

Some of the strongest categories were:

- `agentic`
- `coding`
- `emotion`
- `factual`
- `medical`
- `reasoning`

Some weaker categories were:

- `general`
- `math`
- `writing`
- `knowledge`

The weaker categories are understandable because some labels overlap. For example, knowledge, factual, and general can describe very similar prompts.

This suggests that a future version of the dataset could merge overlapping labels to improve classifier performance.

Evaluation plots are saved in:
```text 
evaluation/plots/
```
Important plots include:

- `class_distribution.png`
- `confusion_matrix.png`
- `confusion_matrix_normalized.png`
- `per_class_f1.png`
- `precision_recall_f1.png`
- `prediction_confidence.png`

---

## Router Training Dataset

After the task classifier is trained, the project builds a router training dataset.

The router dataset combines:

-   `Original prompt text`
- `Old keyword-based question type`
- `New classifier-predicted question type`
- `Question type confidence`
- `Handcrafted numeric prompt features`
- `Benchmark best-model labels`

The router dataset builder is located at:

```text 
src/model_router_tier/build_router_dataset.py
```

The output file is:
```text 
data_processed/router_training_dataset.csv
```
This file acts as the bridge between the task classifier and the model router.

---

## Top-Model Router Dataset

The raw router dataset contains many possible model labels.

Some models appear many times, while others only appear a few times. This creates a long-tail class imbalance problem.

To make exact model routing more stable, this project creates a top-model dataset.

The top model labels are kept, and rare model labels are grouped into:

`OTHER`

This creates a cleaner target for the model router.

The builder file is:

```text 
src/model_router/build_top_model_dataset.py
```

The output file is:

```text 
data_processed/router_training_dataset_top_models.csv
```

This dataset is used by the exact model router.

---

## Model Router

The `Model Router` is the main routing model.

Instead of only using the `raw prompt`, it uses the output of the `task classifier` as an extra signal.

The model router receives:

- `Original query`
- `Predicted question type`
- `Question type confidence`
- `Handcrafted numeric features`

The model router predicts a recommended model class.

The routing pipeline is:
```text
User Prompt
   ↓
Task Type Classifier
   ↓
Predicted Task Type + Prompt Features
   ↓
Model Router
   ↓
Recommended Model Class
```

The main model router training file is:
```text
src/model_router/train_model_router.py
```

The saved model router is stored at:
```text
models/model_router.joblib
```
---

## Tier Router Experiment

This project also includes a `tier router experiment`.

The `tier router` predicts a broad model tier instead of an exact model name.

The possible tiers are:
```text 
cheap
medium
strong
```
The tier router is useful because tier prediction is simpler and more stable than exact model prediction.

Tier router results:
```text
Accuracy: 0.7798
Macro F1: 0.7519
Weighted F1: 0.7845
```

The `tier router `performed best on cheap and medium prompts. The main weakness was that some strong prompts were predicted as medium.

The tier router is located in:

```text 
src/model_router_tier/
```

This is treated as an experimental coarse-grained router. The final demo focuses on the task classifier and exact model router.

---

## Cost-Aware Experiment

This project includes an exploratory `cost-aware dataset builder`.

The goal was to select the cheapest model whose score was within a tolerance band of the best-performing model.

The cost-aware builder is located at:

```text
src/data/build_classifier_dataset_cost_aware.py
```

The output file is:

```text
data_processed/classifier_training_cost_aware.csv
```

However, the cost-aware signal was weaker than expected.

Many benchmark scores are binary, often 0 or 1, and many model costs are zero or tied. Because of this, the cost-aware value model often matched the absolute best model in both score and cost.

For that reason, the final project focuses on task-informed model routing. The cost-aware work remains as an experimental extension.

--- 

## Demo Router

The final demo router loads saved models and runs the full routing pipeline without retraining.

The demo uses:

- ```models/task_type_classifier.joblib```
- ```models/model_router.joblib```
- ```config/model_mapping.json```

The demo pipeline is:
```text
User Prompt
   ↓
Task Type Classifier
   ↓
Model Router
   ↓
Model Mapping
   ↓
Final Simulated Route
```
The demo file is:

```text
src/demo/demo_router.py
```

Run it with:
```text
python src/demo/demo_router.py
```

Example prompts:
```text
What is the capital of France?
Write a Python function that checks whether a string has balanced parentheses.
A company’s revenue increased by 20% and then decreased by 10%. If it started at 1,000,000, what is the final revenue?
Rewrite this paragraph to sound more professional: this project is good because it helps pick better AI models.
```
Example output:
```text
Stage 1: Task Classifier
Predicted question type: coding

Stage 2: Model Router
Predicted model class: qwen3-235b-a22b-2507

Final Simulated Route
Display name: Qwen3 235B A22B Instruct 2507
Provider: OpenRouter
API model: qwen/qwen3-235b-a22b-2507
```
---
## Model Mapping
The file:

```text

config/model_mapping.json
```

maps benchmark model names to route metadata.

Each mapping can include:

- `Display name`
- `Provider`
- `Tier`
- `API model name`
- `Whether the OpenRouter route was verified`
- `Notes about the model`

This lets the demo convert a predicted benchmark model label into a simulated route.

Some benchmark model names do not directly map to current OpenRouter model routes. These are marked as simulated or unverified.

---



## Running the Project

### 1. Flatten raw benchmark JSON files

```bash
python src/data/flatten_raw_jsons.py
```
### 2. Build the classifier dataset

```bash
python src/data/build_classifier_dataset.py
```

### 3. Add question types

```bash
python src/task_classifier/build_question_type.py
```
### 4. Build prompt features

```bash
python src/feature_extraction/build_features.py
```

### 5. Train the task classifier

```bash
python src/task_classifier/train_task_classifier_robust.py
```
### 6. Build the router training dataset
```bash
python src/model_router_tier/build_router_dataset.py
```
### 7. Build the top-model router dataset

```bash
python src/model_router/build_top_model_dataset.py
```
### 8. Train the model router

```bash
python src/model_router/train_model_router.py
```

### . Run the demo router
```bash
python src/demo/demo_router.py
```

---

## Requirements

Install the main dependencies with:

``` text
pip install pandas numpy scipy scikit-learn matplotlib joblib
```

---
## Generated Files

Large generated data files are not required to be committed.

The project may include saved models and evaluation images for demonstration, but the large benchmark CSV files should be regenerated locally.

---

Saved model files:
```text
models/task_type_classifier.joblib
models/tier_router.joblib
models/model_router.joblib
```
Evaluation outputs:
```
evaluation/
```

---
## Limitations

Current limitations:

- Some task labels overlap, especially `knowledge`, `factual`, and `general`
- Exact model routing is harder than tier routing because model labels are imbalanced
- Some benchmark models have very low support
- Cost-aware routing was limited by binary benchmark scores and tied or zero costs
- The final demo simulates routing decisions instead of calling live model APIs
- Some benchmark model names do not directly map to verified OpenRouter routes

---
Future Work

Future improvements could include:

- Merge overlapping task labels
- Improve exact model routing with stronger balancing strategies
- Add confidence calibration
- Add real OpenRouter API calls for verified routes
- Add fallback behavior for low-confidence predictions
- Compare against baselines such as always-cheapest, always-strongest, and random routing
- Evaluate answer quality after routing, not just routing-label accuracy
- Add a web interface for interactive prompt routing

---

## Status

The current project includes:

- Feature extraction
- Task type classification
- Saved task classifier model
- Router training dataset generation
- Top-model router dataset generation
- Model router training
- Saved model router
- Simulated demo router
- Evaluation plots and metrics

---
## Citation

This project uses data from `LLMRouterBench`. If you use this project or the original benchmark, cite the LLMRouterBench work.

```bibtex
@misc{li2026llmrouterbench,
  title        = {LLMRouterBench: A Massive Benchmark and Unified Framework for LLM Routing},
  author       = {Yun Li and others},
  year         = {2026},
  howpublished = {\url{https://github.com/ynulihao/LLMRouterBench}},
  note         = {Findings of ACL 2026}
}