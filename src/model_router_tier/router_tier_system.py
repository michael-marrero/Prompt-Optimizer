import os
import sys
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from scipy.sparse import hstack, csr_matrix

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
    precision_recall_fscore_support,
)
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.pipeline import FeatureUnion


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
ROUTER_PLOTS_DIR = os.path.join(EVALUATION_DIR, "router_plots")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(EVALUATION_DIR, exist_ok=True)
os.makedirs(ROUTER_PLOTS_DIR, exist_ok=True)

INPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "router_training_dataset.csv")
ROUTER_MODEL_PATH = os.path.join(MODELS_DIR, "tier_router.joblib")


# ------------------------------------------------------------
# Feature helpers
# ------------------------------------------------------------

def get_numeric_feature_columns(df: pd.DataFrame) -> list:
    """
    Return numeric handcrafted feature columns for router training.

    Removes raw text, labels, metadata, and target columns.
    """

    columns_to_remove = [
        "question_id",
        "dataset",
        "split",
        "origin_query",
        "prompt",
        "best_model",
        "best_score",
        "best_cost",
        "best_model_tier",
        "n_models_compared",
        "models_evaluated",
        "keyword_question_type",
        "question_type",
    ]

    feature_columns = []

    for col in df.columns:
        if col not in columns_to_remove:
            if pd.api.types.is_numeric_dtype(df[col]):
                feature_columns.append(col)

    return feature_columns


def build_text_input(df: pd.DataFrame) -> pd.Series:
    """
    Combine the original query and classifier-generated question type
    into one text field for TF-IDF.

    This lets the router learn from both the raw prompt and the Stage 1 task label.
    """

    origin_query = df["origin_query"].fillna("").astype(str)
    question_type = df["question_type"].fillna("unknown").astype(str)

    combined_text = (
        origin_query
        + " task_type_"
        + question_type
    )

    return combined_text


# ------------------------------------------------------------
# Evaluation plots and reports
# ------------------------------------------------------------

def plot_router_class_distribution(labels_series: pd.Series):
    counts = labels_series.value_counts().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(counts.index, counts.values)

    ax.set_title("Router Target Distribution")
    ax.set_xlabel("Best Model Tier")
    ax.set_ylabel("Number of Examples")
    ax.set_xticks(np.arange(len(counts.index)))
    ax.set_xticklabels(counts.index, rotation=30, ha="right")

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "router_tier_distribution.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved router tier distribution chart to: {output_path}")


def plot_router_confusion_matrix(y_test, y_pred, label_encoder):
    labels = label_encoder.classes_
    cm = confusion_matrix(y_test, y_pred)

    fig, ax = plt.subplots(figsize=(8, 6))

    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=30,
        values_format="d",
        colorbar=True
    )

    ax.set_title("Tier Router Confusion Matrix")
    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "tier_router_confusion_matrix.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved router confusion matrix to: {output_path}")


def plot_router_normalized_confusion_matrix(y_test, y_pred, label_encoder):
    labels = label_encoder.classes_
    cm = confusion_matrix(y_test, y_pred, normalize="true")

    fig, ax = plt.subplots(figsize=(8, 6))

    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=30,
        values_format=".2f",
        colorbar=True
    )

    ax.set_title("Normalized Tier Router Confusion Matrix")
    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "tier_router_confusion_matrix_normalized.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved normalized router confusion matrix to: {output_path}")


def plot_router_precision_recall_f1(y_test, y_pred, label_encoder):
    labels = label_encoder.classes_

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=np.arange(len(labels)),
        zero_division=0
    )

    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(9, 6))

    ax.bar(x - width, precision, width, label="Precision")
    ax.bar(x, recall, width, label="Recall")
    ax.bar(x + width, f1, width, label="F1")

    ax.set_title("Tier Router Precision, Recall, and F1")
    ax.set_xlabel("Best Model Tier")
    ax.set_ylabel("Score")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylim(0, 1)
    ax.legend()

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "tier_router_precision_recall_f1.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved router precision/recall/F1 chart to: {output_path}")


def plot_router_prediction_confidence(model, X_test_combined):
    probabilities = model.predict_proba(X_test_combined)
    max_confidences = probabilities.max(axis=1)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.hist(max_confidences, bins=20)

    ax.set_title("Tier Router Prediction Confidence")
    ax.set_xlabel("Top Prediction Probability")
    ax.set_ylabel("Number of Predictions")

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "tier_router_prediction_confidence.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved router confidence histogram to: {output_path}")


def save_router_metrics_csv(y_test, y_pred, label_encoder):
    labels = label_encoder.classes_

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=np.arange(len(labels)),
        zero_division=0
    )

    metrics_df = pd.DataFrame({
        "best_model_tier": labels,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "support": support
    })

    output_path = os.path.join(EVALUATION_DIR, "tier_router_metrics.csv")
    metrics_df.to_csv(output_path, index=False)

    print(f"Saved router metrics CSV to: {output_path}")


def save_router_misclassified_examples(
    X_text_test,
    y_test,
    y_pred,
    label_encoder,
    original_test_df
):
    true_labels = label_encoder.inverse_transform(y_test)
    pred_labels = label_encoder.inverse_transform(y_pred)

    rows = []

    for index, true_label, pred_label in zip(original_test_df.index, true_labels, pred_labels):
        if true_label != pred_label:
            row = original_test_df.loc[index]

            rows.append({
                "origin_query": row.get("origin_query", ""),
                "question_type": row.get("question_type", ""),
                "question_type_confidence": row.get("question_type_confidence", ""),
                "best_model": row.get("best_model", ""),
                "best_score": row.get("best_score", ""),
                "best_cost": row.get("best_cost", ""),
                "true_best_model_tier": true_label,
                "predicted_best_model_tier": pred_label,
            })

    mistakes_df = pd.DataFrame(rows)

    output_path = os.path.join(EVALUATION_DIR, "tier_router_misclassified_examples.csv")
    mistakes_df.to_csv(output_path, index=False)

    print(f"Saved router misclassified examples to: {output_path}")


# ------------------------------------------------------------
# Save model artifacts
# ------------------------------------------------------------

def save_router_artifacts(
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns,
    output_path=ROUTER_MODEL_PATH
):
    artifacts = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "label_encoder": label_encoder,
        "feature_columns": feature_columns,
    }

    joblib.dump(artifacts, output_path)

    print(f"\nSaved tier router artifacts to:")
    print(output_path)


# ------------------------------------------------------------
# Training
# ------------------------------------------------------------

def train_tier_router(df: pd.DataFrame):
    """
    Train a router that predicts best_model_tier.

    Input features:
    - origin_query text
    - classifier-generated question_type
    - question_type_confidence
    - numeric handcrafted prompt features

    Target:
    - best_model_tier
    """

    required_columns = [
        "origin_query",
        "question_type",
        "best_model_tier",
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    feature_columns = get_numeric_feature_columns(df)

    print("\nUsing numeric router feature columns:")
    print(feature_columns)
    print(f"\nTotal numeric router features: {len(feature_columns)}")

    text_data = build_text_input(df)
    numeric_features = df[feature_columns].fillna(0)
    labels = df["best_model_tier"].fillna("unknown").astype(str)

    # Remove unknown labels if any exist.
    valid_mask = labels != "unknown"

    text_data = text_data[valid_mask]
    numeric_features = numeric_features[valid_mask]
    labels = labels[valid_mask]
    df_valid = df[valid_mask].copy()

    plot_router_class_distribution(labels)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels)

    (
        X_text_train,
        X_text_test,
        X_num_train,
        X_num_test,
        y_train,
        y_test,
        df_train,
        df_test,
    ) = train_test_split(
        text_data,
        numeric_features,
        y,
        df_valid,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    vectorizer = FeatureUnion([
        ("word_tfidf", TfidfVectorizer(
            lowercase=True,
            stop_words=None,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            max_features=12000
        )),
        ("char_tfidf", TfidfVectorizer(
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=2,
            max_features=8000
        ))
    ])

    X_train_tfidf = vectorizer.fit_transform(X_text_train)
    X_test_tfidf = vectorizer.transform(X_text_test)

    scaler = StandardScaler()
    X_train_num_scaled = scaler.fit_transform(X_num_train)
    X_test_num_scaled = scaler.transform(X_num_test)

    X_train_num_sparse = csr_matrix(X_train_num_scaled)
    X_test_num_sparse = csr_matrix(X_test_num_scaled)

    X_train_combined = hstack([X_train_tfidf, X_train_num_sparse])
    X_test_combined = hstack([X_test_tfidf, X_test_num_sparse])

    model = LogisticRegression(
        max_iter=1500,
        class_weight="balanced",
        solver="saga",
        C=2.0,
        n_jobs=-1
    )

    model.fit(X_train_combined, y_train)

    y_pred = model.predict(X_test_combined)

    plot_router_confusion_matrix(y_test, y_pred, label_encoder)
    plot_router_normalized_confusion_matrix(y_test, y_pred, label_encoder)
    plot_router_precision_recall_f1(y_test, y_pred, label_encoder)
    plot_router_prediction_confidence(model, X_test_combined)

    save_router_metrics_csv(y_test, y_pred, label_encoder)
    save_router_misclassified_examples(
        X_text_test=X_text_test,
        y_test=y_test,
        y_pred=y_pred,
        label_encoder=label_encoder,
        original_test_df=df_test
    )

    print("\nTier Router Results")
    print("-------------------")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"Macro F1: {f1_score(y_test, y_pred, average='macro'):.4f}")
    print(f"Weighted F1: {f1_score(y_test, y_pred, average='weighted'):.4f}")

    print("\nClassification Report:")
    print(
        classification_report(
            y_test,
            y_pred,
            target_names=label_encoder.classes_,
            zero_division=0
        )
    )

    save_router_artifacts(
        model=model,
        vectorizer=vectorizer,
        scaler=scaler,
        label_encoder=label_encoder,
        feature_columns=feature_columns
    )

    return model, vectorizer, scaler, label_encoder, feature_columns


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    print("\nTraining tier router...")
    print("-----------------------")

    if not os.path.exists(INPUT_CSV):
        raise FileNotFoundError(
            f"Router training dataset not found at:\n{INPUT_CSV}\n\n"
            "Run src/model_router_tier/build_router_dataset.py first."
        )

    print("\nLoading router training dataset from:")
    print(INPUT_CSV)

    df = pd.read_csv(INPUT_CSV)

    print(f"\nLoaded rows: {len(df)}")
    print(f"Loaded columns: {len(df.columns)}")

    train_tier_router(df)


if __name__ == "__main__":
    main()