import os
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
# Target helper
# ------------------------------------------------------------

def get_target_column(df: pd.DataFrame) -> str:
    """
    Prefer cost-aware value tier if available.
    Fall back to absolute best model tier if needed.
    """

    if "best_value_model_tier" in df.columns:
        return "best_value_model_tier"

    if "best_model_tier" in df.columns:
        return "best_model_tier"

    raise ValueError(
        "Router dataset must contain either 'best_value_model_tier' "
        "or 'best_model_tier'."
    )


# ------------------------------------------------------------
# Feature helpers
# ------------------------------------------------------------

def get_numeric_feature_columns(df: pd.DataFrame, target_column: str) -> list:
    """
    Return numeric feature columns for router training.

    Removes raw text, labels, metadata, cost/result columns, and target columns.
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

        "best_value_model",
        "best_value_score",
        "best_value_cost",
        "best_value_model_tier",

        "cost_saved_vs_best",
        "score_drop_vs_best",
        "value_model_changed",

        "score_rel_tolerance",
        "min_acceptable_score",

        "n_models_compared",
        "n_models_in_value_band",
        "models_evaluated",

        "keyword_question_type",
        "question_type",

        target_column,
    ]

    feature_columns = []

    for col in df.columns:
        if col not in columns_to_remove:
            if pd.api.types.is_numeric_dtype(df[col]):
                feature_columns.append(col)

    return feature_columns


def build_text_input(df: pd.DataFrame) -> pd.Series:
    """
    Combine original prompt text with Stage 1 task labels.

    This lets the router learn from:
    - raw query wording
    - classifier-generated question type
    - old keyword question type, if available
    """

    origin_query = df["origin_query"].fillna("").astype(str)

    if "question_type" in df.columns:
        question_type = df["question_type"].fillna("unknown").astype(str)
    else:
        question_type = pd.Series(["unknown"] * len(df), index=df.index)

    if "keyword_question_type" in df.columns:
        keyword_question_type = df["keyword_question_type"].fillna("unknown").astype(str)
    else:
        keyword_question_type = pd.Series(["unknown"] * len(df), index=df.index)

    combined_text = (
        origin_query
        + " task_type_"
        + question_type
        + " keyword_type_"
        + keyword_question_type
    )

    return combined_text


# ------------------------------------------------------------
# Evaluation plots
# ------------------------------------------------------------

def plot_target_distribution(labels_series: pd.Series, target_column: str):
    counts = labels_series.value_counts().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(counts.index, counts.values)

    ax.set_title(f"Router Target Distribution: {target_column}")
    ax.set_xlabel("Router Target")
    ax.set_ylabel("Number of Examples")
    ax.set_xticks(np.arange(len(counts.index)))
    ax.set_xticklabels(counts.index, rotation=30, ha="right")

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "router_target_distribution.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved target distribution chart to: {output_path}")


def plot_confusion(y_test, y_pred, label_encoder, normalized=False):
    labels = label_encoder.classes_

    if normalized:
        cm = confusion_matrix(y_test, y_pred, normalize="true")
        filename = "tier_router_confusion_matrix_normalized.png"
        title = "Normalized Tier Router Confusion Matrix"
        values_format = ".2f"
    else:
        cm = confusion_matrix(y_test, y_pred)
        filename = "tier_router_confusion_matrix.png"
        title = "Tier Router Confusion Matrix"
        values_format = "d"

    fig, ax = plt.subplots(figsize=(8, 6))

    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=30,
        values_format=values_format,
        colorbar=True
    )

    ax.set_title(title)
    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, filename)
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved confusion matrix to: {output_path}")


def plot_precision_recall_f1(y_test, y_pred, label_encoder):
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
    ax.set_xlabel("Tier")
    ax.set_ylabel("Score")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylim(0, 1)
    ax.legend()

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "tier_router_precision_recall_f1.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved precision/recall/F1 chart to: {output_path}")


def plot_prediction_confidence(model, X_test_combined):
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

    print(f"Saved prediction confidence histogram to: {output_path}")


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

    output_path = os.path.join(EVALUATION_DIR, "tier_router_metrics.csv")
    metrics_df.to_csv(output_path, index=False)

    print(f"Saved router metrics CSV to: {output_path}")


def save_misclassified_examples(df_test, y_test, y_pred, label_encoder, target_column: str):
    true_labels = label_encoder.inverse_transform(y_test)
    pred_labels = label_encoder.inverse_transform(y_pred)

    rows = []

    for idx, true_label, pred_label in zip(df_test.index, true_labels, pred_labels):
        if true_label != pred_label:
            row = df_test.loc[idx]

            rows.append({
                "origin_query": row.get("origin_query", ""),
                "question_type": row.get("question_type", ""),
                "keyword_question_type": row.get("keyword_question_type", ""),
                "question_type_confidence": row.get("question_type_confidence", ""),

                "best_model": row.get("best_model", ""),
                "best_score": row.get("best_score", ""),
                "best_cost": row.get("best_cost", ""),

                "best_value_model": row.get("best_value_model", ""),
                "best_value_score": row.get("best_value_score", ""),
                "best_value_cost": row.get("best_value_cost", ""),

                "true_tier": true_label,
                "predicted_tier": pred_label,
                "target_column": target_column,
            })

    mistakes_df = pd.DataFrame(rows)

    output_path = os.path.join(EVALUATION_DIR, "tier_router_misclassified_examples.csv")
    mistakes_df.to_csv(output_path, index=False)

    print(f"Saved misclassified examples to: {output_path}")


# ------------------------------------------------------------
# Save/load artifacts
# ------------------------------------------------------------

def save_router_artifacts(
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns,
    target_column,
    output_path=ROUTER_MODEL_PATH
):
    artifacts = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "label_encoder": label_encoder,
        "feature_columns": feature_columns,
        "target_column": target_column,
    }

    joblib.dump(artifacts, output_path)

    print("\nSaved tier router artifacts to:")
    print(output_path)


def load_router_artifacts(model_path=ROUTER_MODEL_PATH):
    """
    Load a previously trained tier router.
    """

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No saved tier router found at:\n{model_path}\n\n"
            "Run this script in 'train' mode first."
        )

    artifacts = joblib.load(model_path)

    required_keys = [
        "model",
        "vectorizer",
        "scaler",
        "label_encoder",
        "feature_columns",
        "target_column",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"Saved router artifact is missing key: {key}")

    print("\nLoaded saved tier router from:")
    print(model_path)

    return (
        artifacts["model"],
        artifacts["vectorizer"],
        artifacts["scaler"],
        artifacts["label_encoder"],
        artifacts["feature_columns"],
        artifacts["target_column"],
    )


# ------------------------------------------------------------
# Single prompt prediction
# ------------------------------------------------------------

def predict_user_input(
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns,
    text,
    question_type="unknown",
    keyword_question_type="unknown",
    question_type_confidence=0.0,
):
    """
    Predict model tier for one user prompt using the trained tier router.

    For this standalone script, the Stage 1 question type is entered manually.
    Later, demo_router.py can call the task classifier first and pass it here.
    """

    input_df = pd.DataFrame([{
        "origin_query": text,
        "question_type": question_type,
        "keyword_question_type": keyword_question_type,
        "question_type_confidence": question_type_confidence,
    }])

    text_data = build_text_input(input_df)

    numeric_df = pd.DataFrame([{col: 0 for col in feature_columns}])

    for col in feature_columns:
        if col in input_df.columns:
            numeric_df[col] = input_df[col]

    numeric_df = numeric_df[feature_columns].fillna(0)

    text_features = vectorizer.transform(text_data)

    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined_features = hstack([text_features, numeric_sparse])

    prediction_encoded = model.predict(combined_features)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    probabilities = model.predict_proba(combined_features)[0]

    confidence_table = []

    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))

    confidence_table.sort(key=lambda x: x[1], reverse=True)

    return prediction_label, confidence_table


# ------------------------------------------------------------
# Training
# ------------------------------------------------------------

def train_tier_router(df: pd.DataFrame):
    """
    Train a router that predicts a model tier.

    Input:
    - origin_query
    - classifier-generated question_type
    - keyword_question_type if available
    - numeric handcrafted features
    - question_type_confidence if available

    Target:
    - best_value_model_tier if available
    - otherwise best_model_tier
    """

    if "origin_query" not in df.columns:
        raise ValueError("Router dataset must contain 'origin_query'.")

    target_column = get_target_column(df)

    print(f"\nRouter target column: {target_column}")

    feature_columns = get_numeric_feature_columns(df, target_column)

    print("\nUsing numeric router feature columns:")
    print(feature_columns)
    print(f"\nTotal numeric router features: {len(feature_columns)}")

    text_data = build_text_input(df)
    numeric_features = df[feature_columns].fillna(0)
    labels = df[target_column].fillna("unknown").astype(str)

    valid_mask = labels != "unknown"

    text_data = text_data[valid_mask]
    numeric_features = numeric_features[valid_mask]
    labels = labels[valid_mask]
    df_valid = df[valid_mask].copy()

    print(f"\nTraining rows after removing unknown labels: {len(df_valid)}")

    plot_target_distribution(labels, target_column)

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

    X_train_text_features = vectorizer.fit_transform(X_text_train)
    X_test_text_features = vectorizer.transform(X_text_test)

    scaler = StandardScaler()
    X_train_numeric_scaled = scaler.fit_transform(X_num_train)
    X_test_numeric_scaled = scaler.transform(X_num_test)

    X_train_numeric_sparse = csr_matrix(X_train_numeric_scaled)
    X_test_numeric_sparse = csr_matrix(X_test_numeric_scaled)

    X_train_combined = hstack([X_train_text_features, X_train_numeric_sparse])
    X_test_combined = hstack([X_test_text_features, X_test_numeric_sparse])

    model = LogisticRegression(
        max_iter=1500,
        class_weight="balanced",
        solver="saga",
        C=2.0,
        n_jobs=-1
    )

    print("\nTraining tier router...")
    model.fit(X_train_combined, y_train)

    y_pred = model.predict(X_test_combined)

    # Evaluation artifacts
    plot_confusion(y_test, y_pred, label_encoder, normalized=False)
    plot_confusion(y_test, y_pred, label_encoder, normalized=True)
    plot_precision_recall_f1(y_test, y_pred, label_encoder)
    plot_prediction_confidence(model, X_test_combined)

    save_metrics_csv(y_test, y_pred, label_encoder, target_column)
    save_misclassified_examples(df_test, y_test, y_pred, label_encoder, target_column)

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
        feature_columns=feature_columns,
        target_column=target_column,
    )

    return model, vectorizer, scaler, label_encoder, feature_columns, target_column


# ------------------------------------------------------------
# Main user interface
# ------------------------------------------------------------

def main():
    print("\nModel Tier Router")
    print("-----------------")
    print("Type 'train' to train and save a new tier router.")
    print("Type 'load' to load the existing saved tier router.")

    mode = input("\nMode: ").strip().lower()

    if mode == "train":
        if not os.path.exists(INPUT_CSV):
            raise FileNotFoundError(
                f"Router training dataset not found at:\n{INPUT_CSV}\n\n"
                "Run src/model_router/build_router_dataset.py first."
            )

        print("\nLoading router training dataset from:")
        print(INPUT_CSV)

        df = pd.read_csv(INPUT_CSV)

        print(f"\nLoaded rows: {len(df)}")
        print(f"Loaded columns: {len(df.columns)}")

        (
            model,
            vectorizer,
            scaler,
            label_encoder,
            feature_columns,
            target_column,
        ) = train_tier_router(df)

    elif mode == "load":
        (
            model,
            vectorizer,
            scaler,
            label_encoder,
            feature_columns,
            target_column,
        ) = load_router_artifacts()

    else:
        print("Invalid mode. Please type 'train' or 'load'.")
        return

    print("\nType a question to test the tier router.")
    print("Type 'quit' to stop.")
    print("\nFor now, manually enter the Stage 1 question type.")
    print("Example question types: coding, math, reasoning, knowledge, medical, writing")

    while True:
        user_text = input("\nQuestion: ").strip()

        if user_text.lower() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        if not user_text:
            print("Please enter a question.")
            continue

        question_type = input("Predicted question type: ").strip().lower()

        if not question_type:
            question_type = "unknown"

        confidence_text = input("Question type confidence [default 0.0]: ").strip()

        try:
            question_type_confidence = float(confidence_text) if confidence_text else 0.0
        except ValueError:
            question_type_confidence = 0.0

        predicted_tier, confidence_table = predict_user_input(
            model=model,
            vectorizer=vectorizer,
            scaler=scaler,
            label_encoder=label_encoder,
            feature_columns=feature_columns,
            text=user_text,
            question_type=question_type,
            keyword_question_type="unknown",
            question_type_confidence=question_type_confidence,
        )

        print(f"\nRouter target: {target_column}")
        print(f"Predicted model tier: {predicted_tier}")
        print("Prediction source: tier router model")

        print("\nTop predictions:")
        for label, probability in confidence_table[:5]:
            print(f"- {label}: {probability:.4f}")


if __name__ == "__main__":
    main()