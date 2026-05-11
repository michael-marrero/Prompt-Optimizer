import os
import sys
import joblib
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
    precision_recall_fscore_support,
    top_k_accuracy_score,
)
from sklearn.preprocessing import LabelEncoder

_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROUTER_DIR not in sys.path:
    sys.path.insert(0, _ROUTER_DIR)

from model_family import infer_model_vendor_family


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
EMBEDDING_PLOTS_DIR = os.path.join(EVALUATION_DIR, "embedding_router_plots")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(EVALUATION_DIR, exist_ok=True)
os.makedirs(EMBEDDING_PLOTS_DIR, exist_ok=True)

INPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "classifier_training.csv")

EMBEDDING_ROUTER_MODEL_PATH = os.path.join(
    MODELS_DIR,
    "embedding_router.joblib"
)

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Drop rare families — tiny classes inflate macro-noise without helping deployment.
MIN_CLASS_SAMPLES = 25

# Optional weak context (different cache filenames so toggles cannot reuse stale rows).
PREPEND_DATASET_TO_QUERY = False
PREPEND_PROMPT_STUB = False
PROMPT_STUB_MAX_CHARS = 400


# ------------------------------------------------------------
# Data helpers
# ------------------------------------------------------------

def embeddings_cache_path(
    *,
    embedding_model_name: str,
    prepend_dataset: bool,
    prepend_prompt_stub: bool,
) -> str:
    slug = embedding_model_name.replace("/", "_").replace(".", "_")
    parts = ["emb_router", slug, "l2", "fam"]
    if prepend_dataset:
        parts.append("ds_prefix")
    if prepend_prompt_stub:
        parts.append("prompt_stub")
    return os.path.join(DATA_PROCESSED_DIR, "_".join(parts) + ".npy")


def validate_input_columns(
    df: pd.DataFrame,
    *,
    prepend_dataset: bool,
    prepend_prompt_stub: bool,
):
    required = ["origin_query", "best_model"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Input CSV is missing required column: {col}")
    if prepend_dataset and "dataset" not in df.columns:
        raise ValueError(
            "PREPEND_DATASET_TO_QUERY requires a dataset column in the CSV."
        )
    if prepend_prompt_stub and "prompt" not in df.columns:
        raise ValueError(
            "PREPEND_PROMPT_STUB requires a prompt column in the CSV."
        )


def build_router_input_strings(
    df: pd.DataFrame,
    *,
    prepend_dataset: bool,
    prepend_prompt_stub: bool,
) -> list:
    base = df["origin_query"].fillna("").astype(str)

    if prepend_dataset:
        ds = df["dataset"].fillna("unknown").astype(str)
        base = ds + " | " + base

    if prepend_prompt_stub:
        stub = (
            df["prompt"]
            .fillna("")
            .astype(str)
            .str.slice(0, PROMPT_STUB_MAX_CHARS)
        )
        base = base + " | instr_stub: " + stub

    return base.tolist()


def format_demo_prompt_text(prompt: str, artifacts: dict) -> str:
    """Match saved train recipe for interactive probing (datasets default to unknown)."""

    prompt = prompt.strip()

    if not prompt:
        return prompt

    if artifacts.get("prepend_dataset_to_query"):
        prompt = f"unknown | {prompt}"

    if artifacts.get("prepend_prompt_stub"):
        prompt = prompt + " | instr_stub: "

    return prompt


def build_inference_strings(df: pd.DataFrame, artifacts: dict) -> list:
    """
    Inference-time text recipe packaged with artifacts (evaluation + batch scoring).
    """

    prepend_ds = bool(artifacts.get("prepend_dataset_to_query", False))
    prepend_stub = bool(artifacts.get("prepend_prompt_stub", False))

    return build_router_input_strings(
        df,
        prepend_dataset=prepend_ds,
        prepend_prompt_stub=prepend_stub,
    )


# ------------------------------------------------------------
# Embedding helpers
# ------------------------------------------------------------

def load_or_create_embeddings(
    texts: list,
    embeddings_path: str,
    model_name: str = EMBEDDING_MODEL_NAME,
    force_rebuild: bool = False,
):
    if os.path.exists(embeddings_path) and not force_rebuild:
        print("\nLoading cached embeddings from:")
        print(embeddings_path)

        embeddings = np.load(embeddings_path)

        if len(embeddings) != len(texts):
            raise ValueError(
                "Cached embeddings row count does not match input dataset. "
                "Delete the .npy file or rerun with force_rebuild=True."
            )

        return embeddings

    print("\nComputing sentence embeddings...")
    print(f"Embedding model: {model_name}")
    print(f"Number of prompts: {len(texts)}")

    embedding_model = SentenceTransformer(model_name)

    embeddings = embedding_model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    np.save(embeddings_path, embeddings)

    print("\nSaved embeddings to:")
    print(embeddings_path)

    return embeddings


# ------------------------------------------------------------
# Evaluation plots
# ------------------------------------------------------------

def plot_target_distribution(labels_series: pd.Series, target_column: str):
    counts = labels_series.value_counts().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.bar(counts.index, counts.values)

    ax.set_title(f"Embedding Router Target Distribution: {target_column}")
    ax.set_xlabel("Model Family")
    ax.set_ylabel("Number of Examples")
    ax.set_xticks(np.arange(len(counts.index)))
    ax.set_xticklabels(counts.index, rotation=45, ha="right")

    plt.tight_layout()

    output_path = os.path.join(
        EMBEDDING_PLOTS_DIR,
        "embedding_router_target_distribution.png"
    )

    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved target distribution chart to: {output_path}")


def plot_top_class_f1(y_test, y_pred, label_encoder, top_n=20):
    labels = label_encoder.classes_

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=np.arange(len(labels)),
        zero_division=0
    )

    metrics_df = pd.DataFrame({
        "model_family": labels,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "support": support
    })

    metrics_df = metrics_df.sort_values("support", ascending=False).head(top_n)

    x = np.arange(len(metrics_df))

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.bar(x, metrics_df["f1_score"])

    ax.set_title(f"Top {top_n} Embedding Router Families by Support - F1 Score")
    ax.set_xlabel("Model Family")
    ax.set_ylabel("F1 Score")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics_df["model_family"], rotation=45, ha="right")
    ax.set_ylim(0, 1)

    plt.tight_layout()

    output_path = os.path.join(
        EMBEDDING_PLOTS_DIR,
        "embedding_router_top_class_f1.png"
    )

    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved top-class F1 chart to: {output_path}")


def plot_classifier_uncertainty(model, X_test):
    """
    Histogram of classifier confidence — ``predict_proba`` when available else max |decision_function|.
    """

    if hasattr(model, "predict_proba"):
        max_scores = model.predict_proba(X_test).max(axis=1)
        x_label = "Top predicted probability"
        title_root = "Probability"
        filename = "embedding_router_top_probability.png"
    else:
        decision_scores = model.decision_function(X_test)
        if decision_scores.ndim == 1:
            max_scores = np.abs(decision_scores)
        else:
            max_scores = decision_scores.max(axis=1)
        x_label = "Top decision score magnitude"
        title_root = "Decision score"
        filename = "embedding_router_decision_scores.png"

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.hist(max_scores, bins=20)

    ax.set_title(f"Embedding Router {title_root} Distribution")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Number of predictions")

    plt.tight_layout()

    output_path = os.path.join(EMBEDDING_PLOTS_DIR, filename)

    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved classifier confidence histogram to: {output_path}")


def plot_top_confusion_matrix(y_test, y_pred, label_encoder, top_n=20):
    true_labels = label_encoder.inverse_transform(y_test)
    pred_labels = label_encoder.inverse_transform(y_pred)

    support_counts = pd.Series(true_labels).value_counts()
    top_labels = support_counts.head(top_n).index.tolist()

    mask = [
        true_label in top_labels and pred_label in top_labels
        for true_label, pred_label in zip(true_labels, pred_labels)
    ]

    filtered_true = [true for true, keep in zip(true_labels, mask) if keep]
    filtered_pred = [pred for pred, keep in zip(pred_labels, mask) if keep]

    if not filtered_true:
        print("Skipped top confusion matrix because no filtered examples were available.")
        return

    cm = confusion_matrix(
        filtered_true,
        filtered_pred,
        labels=top_labels
    )

    fig, ax = plt.subplots(figsize=(12, 10))

    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=top_labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=45,
        values_format="d",
        colorbar=True
    )

    ax.set_title(f"Embedding Router Confusion Matrix - Top {top_n} Families")
    plt.tight_layout()

    output_path = os.path.join(
        EMBEDDING_PLOTS_DIR,
        "embedding_router_top_confusion_matrix.png"
    )

    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved top confusion matrix to: {output_path}")


# ------------------------------------------------------------
# Evaluation CSVs
# ------------------------------------------------------------

def save_metrics_csv(y_test, y_pred, label_encoder, target_column: str):
    labels = label_encoder.classes_

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=np.arange(len(labels)),
        zero_division=0
    )

    metrics_df = pd.DataFrame({
        target_column: labels,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "support": support
    })

    metrics_df = metrics_df.sort_values("support", ascending=False)

    output_path = os.path.join(
        EVALUATION_DIR,
        "embedding_router_metrics.csv"
    )

    metrics_df.to_csv(output_path, index=False)

    print(f"Saved embedding router metrics CSV to: {output_path}")


def save_misclassified_examples(
    df_test: pd.DataFrame,
    y_test,
    y_pred,
    label_encoder,
    target_column: str
):
    true_labels = label_encoder.inverse_transform(y_test)
    pred_labels = label_encoder.inverse_transform(y_pred)

    rows = []

    for idx, true_label, pred_label in zip(df_test.index, true_labels, pred_labels):
        if true_label != pred_label:
            row = df_test.loc[idx]

            rows.append({
                "origin_query": row.get("origin_query", ""),
                "best_model": row.get("best_model", ""),
                "best_model_family": row.get("best_model_family", ""),
                "true_model_family": true_label,
                "predicted_model_family": pred_label,
                "target_column": target_column,
            })

    mistakes_df = pd.DataFrame(rows)

    output_path = os.path.join(
        EVALUATION_DIR,
        "embedding_router_misclassified_examples.csv"
    )

    mistakes_df.to_csv(output_path, index=False)

    print(f"Saved embedding router misclassified examples to: {output_path}")


# ------------------------------------------------------------
# Save/load artifacts
# ------------------------------------------------------------

def save_embedding_router_artifacts(
    model,
    label_encoder,
    target_column,
    embedding_model_name,
    *,
    prepend_dataset_to_query: bool,
    prepend_prompt_stub: bool,
    classifier_type: str,
    output_path=EMBEDDING_ROUTER_MODEL_PATH,
):
    artifacts = {
        "model": model,
        "scaler": None,
        "label_encoder": label_encoder,
        "target_column": target_column,
        "embedding_model_name": embedding_model_name,
        "input_text_column": "origin_query",
        "uses_task_classifier": False,
        "uses_handcrafted_features": False,
        "uses_tfidf": False,
        "uses_top_model_grouping": False,
        "target_type": "model_family",
        "classifier_type": classifier_type,
        "embedding_vectors_are_normalized": True,
        "prepend_dataset_to_query": prepend_dataset_to_query,
        "prepend_prompt_stub": prepend_prompt_stub,
    }

    joblib.dump(artifacts, output_path)

    print("\nSaved embedding router artifacts to:")
    print(output_path)


def load_embedding_router_artifacts(model_path=EMBEDDING_ROUTER_MODEL_PATH):
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No saved embedding router found at:\n{model_path}\n\n"
            "Run this script in 'train' mode first."
        )

    artifacts = joblib.load(model_path)

    required_keys = [
        "model",
        "label_encoder",
        "target_column",
        "embedding_model_name",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"Saved embedding router artifact is missing key: {key}")

    print("\nLoaded saved embedding router from:")
    print(model_path)

    return artifacts


# ------------------------------------------------------------
# Training
# ------------------------------------------------------------

def train_embedding_router(df: pd.DataFrame, force_rebuild_embeddings: bool = False):
    validate_input_columns(
        df,
        prepend_dataset=PREPEND_DATASET_TO_QUERY,
        prepend_prompt_stub=PREPEND_PROMPT_STUB,
    )

    target_column = "best_model_family"

    df = df.dropna(subset=["origin_query", "best_model"]).copy()
    df["origin_query"] = df["origin_query"].astype(str)
    df["best_model"] = df["best_model"].astype(str)

    df[target_column] = df["best_model"].apply(infer_model_vendor_family)

    labels = df[target_column].fillna("other").astype(str)

    df = df.reset_index(drop=True)
    labels = labels.reset_index(drop=True)

    prepend_ds = PREPEND_DATASET_TO_QUERY
    prepend_stub = PREPEND_PROMPT_STUB

    text_inputs = build_router_input_strings(
        df,
        prepend_dataset=prepend_ds,
        prepend_prompt_stub=prepend_stub,
    )

    cache_file = embeddings_cache_path(
        embedding_model_name=EMBEDDING_MODEL_NAME,
        prepend_dataset=prepend_ds,
        prepend_prompt_stub=prepend_stub,
    )

    print(f"\nTarget column: {target_column}")
    print(f"Number of rows: {len(df)}")
    print(f"Number of model families: {labels.nunique()}")
    print("\nTarget distribution:")
    print(labels.value_counts())

    plot_target_distribution(labels, target_column)

    embeddings = load_or_create_embeddings(
        texts=text_inputs,
        embeddings_path=cache_file,
        model_name=EMBEDDING_MODEL_NAME,
        force_rebuild=force_rebuild_embeddings,
    )

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels)

    label_counts = pd.Series(y).value_counts()
    valid_encoded_labels = label_counts[
        label_counts >= MIN_CLASS_SAMPLES
    ].index

    keep_mask = pd.Series(y).isin(valid_encoded_labels).to_numpy()

    removed_count = int(len(y) - keep_mask.sum())

    if removed_count > 0:
        print(
            f"\nRemoved {removed_count} rows from families with "
            f"fewer than {MIN_CLASS_SAMPLES} examples."
        )

    embeddings = embeddings[keep_mask]
    labels = labels.iloc[keep_mask].reset_index(drop=True)
    df = df.iloc[keep_mask].reset_index(drop=True)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels)

    if labels.nunique() < 2:
        raise ValueError(
            "Only one vendor family remains after filtering. Lower MIN_CLASS_SAMPLES or expand the dataset."
        )

    (
        X_train,
        X_test,
        y_train,
        y_test,
        df_train,
        df_test,
    ) = train_test_split(
        embeddings,
        y,
        df,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    clf_type = "logistic_multinomial_lbfgs"
    # L-BFGS multinomial fits dense ~10k–50k × few-hundred-dim inputs much faster
    # than SAGA, which can appear stuck here.
    model = LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        solver="lbfgs",
        C=4.0,
        random_state=42,
    )

    print(
        f"\nTraining embedding router ({clf_type}) on "
        f"{X_train.shape[0]:,} × {X_train.shape[1]} matrix..."
    )
    t_fit = time.perf_counter()
    model.fit(X_train, y_train)
    print(f"Classifier fit finished in {time.perf_counter() - t_fit:.2f}s.")

    y_pred = model.predict(X_test)

    plot_top_confusion_matrix(y_test, y_pred, label_encoder, top_n=20)
    plot_top_class_f1(y_test, y_pred, label_encoder, top_n=20)
    plot_classifier_uncertainty(model, X_test)

    save_metrics_csv(y_test, y_pred, label_encoder, target_column)
    save_misclassified_examples(df_test, y_test, y_pred, label_encoder, target_column)

    n_classes_total = len(label_encoder.classes_)
    top_k_requested = []

    if n_classes_total > 3:
        top_k_requested.append(3)
    if n_classes_total > 5:
        top_k_requested.append(5)

    scores_block = ""

    try:
        y_proba = model.predict_proba(X_test)

        lines = []

        for k in top_k_requested:
            tk = top_k_accuracy_score(y_test, y_proba, k=k, labels=np.arange(n_classes_total))
            lines.append(f"Top-{k} accuracy: {tk:.4f}")

        scores_block = "\n".join(lines) + "\n"
    except AttributeError:
        scores_block = "(Top-k unavailable for this estimator.)\n"

    print("\nEmbedding Router Results")
    print("------------------------")
    print(scores_block, end="")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"Macro F1: {f1_score(y_test, y_pred, average='macro', zero_division=0):.4f}")
    print(f"Weighted F1: {f1_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")

    print("\nClassification Report:")
    print(
        classification_report(
            y_test,
            y_pred,
            target_names=label_encoder.classes_,
            zero_division=0,
        )
    )

    save_embedding_router_artifacts(
        model=model,
        label_encoder=label_encoder,
        target_column=target_column,
        embedding_model_name=EMBEDDING_MODEL_NAME,
        prepend_dataset_to_query=prepend_ds,
        prepend_prompt_stub=prepend_stub,
        classifier_type=clf_type,
    )

    return model, label_encoder, target_column


# ------------------------------------------------------------
# Prediction
# ------------------------------------------------------------

def predict_user_input(prompt: str, artifacts: dict):
    embedding_model_name = artifacts["embedding_model_name"]
    model = artifacts["model"]
    label_encoder = artifacts["label_encoder"]

    print("\nLoading embedding model for prediction...")
    embedding_model = SentenceTransformer(embedding_model_name)

    routed = format_demo_prompt_text(prompt, artifacts)

    embedding = embedding_model.encode(
        [routed],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    prediction_encoded = model.predict(embedding)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    confidence_table = []

    if hasattr(model, "predict_proba"):
        scores = model.predict_proba(embedding)[0]
        for label, probability in zip(label_encoder.classes_, scores):
            confidence_table.append((label, float(probability)))
    else:
        decision_scores = model.decision_function(embedding)
        if decision_scores.ndim == 1:
            arr = np.asarray([-decision_scores[0], decision_scores[0]])
        else:
            arr = decision_scores[0]

        for label, score in zip(label_encoder.classes_, arr):
            confidence_table.append((label, float(score)))

    confidence_table.sort(key=lambda item: item[1], reverse=True)

    return prediction_label, confidence_table


# ------------------------------------------------------------
# Main user interface
# ------------------------------------------------------------

def main():
    print("\nEmbedding Router")
    print("----------------")
    print("This experiment uses only origin_query semantic embeddings.")
    print("It does not use the task classifier, handcrafted features, TF-IDF, or top-model grouping.")
    print("Target: best_model_family (coarse vendor bucket)")
    print("Classifier: multinomial LogisticRegression (L-BFGS) on L2-normalized embeddings")
    print("\nType 'train' to train and save a new embedding router.")
    print("Type 'load' to load the existing saved embedding router.")

    mode = input("\nMode: ").strip().lower()

    if mode == "train":
        if not os.path.exists(INPUT_CSV):
            raise FileNotFoundError(
                f"Input dataset not found at:\n{INPUT_CSV}\n\n"
                "Make sure classifier_training.csv exists."
            )

        print("\nLoading classifier training dataset from:")
        print(INPUT_CSV)

        df = pd.read_csv(INPUT_CSV)

        print(f"\nLoaded rows: {len(df)}")
        print(f"Loaded columns: {len(df.columns)}")

        force_text = input(
            "\nRebuild embeddings even if cached file exists? [y/N]: "
        ).strip().lower()

        force_rebuild_embeddings = force_text == "y"

        train_embedding_router(
            df=df,
            force_rebuild_embeddings=force_rebuild_embeddings
        )

        artifacts = load_embedding_router_artifacts()

    elif mode == "load":
        artifacts = load_embedding_router_artifacts()

    else:
        print("Invalid mode. Please type 'train' or 'load'.")
        return

    print("\nType a prompt to test the embedding router.")
    print("Type 'quit' to stop.")
    print("Top scores are predicted probabilities when available, else raw decision values.")

    while True:
        prompt = input("\nPrompt: ").strip()

        if prompt.lower() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        if not prompt:
            print("Please enter a prompt.")
            continue

        predicted_model_family, confidence_table = predict_user_input(
            prompt=prompt,
            artifacts=artifacts
        )

        print(f"\nPredicted model family: {predicted_model_family}")
        print("Prediction source: embedding router")

        print("\nTop predictions:")
        for label, score in confidence_table[:5]:
            print(f"- {label}: {score:.4f}")


if __name__ == "__main__":
    main()