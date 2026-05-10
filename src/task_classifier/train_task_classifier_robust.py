import os
import sys
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
import joblib


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")

EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
PLOTS_DIR = os.path.join(EVALUATION_DIR, "plots")

os.makedirs(EVALUATION_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_PATH = os.path.join(MODELS_DIR, "task_type_classifier.joblib")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from Feature_extractor import PromptFeatureExtractor


INPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "classifier_training_with_types.csv")


# ------------------------------------------------------------
# Feature column helper
# ------------------------------------------------------------

def get_numeric_feature_columns(df: pd.DataFrame) -> list:
    """
    Return only numeric handcrafted feature columns.

    Removes raw text, labels, benchmark metadata, and result-side columns.
    """

    columns_to_remove = [
        "dataset",
        "split",
        "origin_query",
        "prompt",
        "best_model",
        "best_score",
        "best_cost",
        "n_models_compared",
        "models_evaluated",
        "question_type",
    ]

    feature_columns = []

    for col in df.columns:
        if col not in columns_to_remove:
            if pd.api.types.is_numeric_dtype(df[col]):
                feature_columns.append(col)

    return feature_columns


# ------------------------------------------------------------
# Evaluation plots and reports
# ------------------------------------------------------------

def plot_class_distribution(labels_series: pd.Series):
    """
    Save a bar chart showing how many examples exist for each question type.
    """

    counts = labels_series.value_counts().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(counts.index, counts.values)

    ax.set_title("Question Type Distribution")
    ax.set_xlabel("Question Type")
    ax.set_ylabel("Number of Examples")
    ax.set_xticks(np.arange(len(counts.index)))
    ax.set_xticklabels(counts.index, rotation=45, ha="right")

    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "class_distribution.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved class distribution chart to: {output_path}")


def plot_confusion_matrix(y_test, y_pred, label_encoder):
    """
    Save a raw-count confusion matrix.
    """

    labels = label_encoder.classes_
    cm = confusion_matrix(y_test, y_pred)

    fig, ax = plt.subplots(figsize=(12, 10))
    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=45,
        values_format="d",
        colorbar=True
    )

    ax.set_title("Task Type Classifier Confusion Matrix")
    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "confusion_matrix.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved confusion matrix to: {output_path}")


def plot_normalized_confusion_matrix(y_test, y_pred, label_encoder):
    """
    Save a normalized confusion matrix.
    Each row sums to 1.0, so this shows percentages by true class.
    """

    labels = label_encoder.classes_
    cm = confusion_matrix(y_test, y_pred, normalize="true")

    fig, ax = plt.subplots(figsize=(12, 10))
    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=45,
        values_format=".2f",
        colorbar=True
    )

    ax.set_title("Normalized Confusion Matrix")
    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "confusion_matrix_normalized.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved normalized confusion matrix to: {output_path}")


def plot_per_class_f1(y_test, y_pred, label_encoder):
    """
    Save a bar chart of F1 score for each question type.
    """

    labels = label_encoder.classes_

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=np.arange(len(labels)),
        zero_division=0
    )

    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x, f1)

    ax.set_title("Per-Class F1 Score")
    ax.set_xlabel("Question Type")
    ax.set_ylabel("F1 Score")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylim(0, 1)

    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "per_class_f1.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved per-class F1 chart to: {output_path}")


def plot_precision_recall_f1(y_test, y_pred, label_encoder):
    """
    Save a grouped bar chart for precision, recall, and F1 by class.
    """

    labels = label_encoder.classes_

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=np.arange(len(labels)),
        zero_division=0
    )

    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(14, 7))

    ax.bar(x - width, precision, width, label="Precision")
    ax.bar(x, recall, width, label="Recall")
    ax.bar(x + width, f1, width, label="F1")

    ax.set_title("Precision, Recall, and F1 by Question Type")
    ax.set_xlabel("Question Type")
    ax.set_ylabel("Score")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylim(0, 1)
    ax.legend()

    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "precision_recall_f1.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved precision/recall/F1 chart to: {output_path}")


def plot_prediction_confidence(model, X_test_combined):
    """
    Save a histogram of the model's top predicted probability.
    This helps show whether the model is confident or uncertain.
    """

    probabilities = model.predict_proba(X_test_combined)
    max_confidences = probabilities.max(axis=1)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(max_confidences, bins=20)

    ax.set_title("Prediction Confidence Distribution")
    ax.set_xlabel("Top Prediction Probability")
    ax.set_ylabel("Number of Predictions")

    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "prediction_confidence.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved prediction confidence histogram to: {output_path}")


def save_misclassified_examples(X_text_test, y_test, y_pred, label_encoder):
    """
    Save examples where the model predicted the wrong question type.
    """

    true_labels = label_encoder.inverse_transform(y_test)
    pred_labels = label_encoder.inverse_transform(y_pred)

    rows = []

    for question, true_label, pred_label in zip(X_text_test, true_labels, pred_labels):
        if true_label != pred_label:
            rows.append({
                "question": question,
                "true_label": true_label,
                "predicted_label": pred_label
            })

    mistakes_df = pd.DataFrame(rows)

    output_path = os.path.join(EVALUATION_DIR, "misclassified_examples.csv")
    mistakes_df.to_csv(output_path, index=False)

    print(f"Saved misclassified examples to: {output_path}")


def save_classification_metrics_csv(y_test, y_pred, label_encoder):
    """
    Save precision, recall, F1, and support for each class to CSV.
    """

    labels = label_encoder.classes_

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=np.arange(len(labels)),
        zero_division=0
    )

    metrics_df = pd.DataFrame({
        "question_type": labels,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "support": support
    })

    output_path = os.path.join(EVALUATION_DIR, "classification_metrics.csv")
    metrics_df.to_csv(output_path, index=False)

    print(f"Saved classification metrics to: {output_path}")


# ------------------------------------------------------------
# Training
# ------------------------------------------------------------

def train_task_type_classifier(df: pd.DataFrame):
    """
    Train a task type classifier using:
    - Word-level TF-IDF features from origin_query
    - Character-level TF-IDF features from origin_query
    - Handcrafted numeric features from the feature extractor output
    """

    if "origin_query" not in df.columns:
        raise ValueError("CSV must contain an 'origin_query' column.")

    if "question_type" not in df.columns:
        raise ValueError("CSV must contain a 'question_type' column.")

    feature_columns = get_numeric_feature_columns(df)

    print("\nUsing numeric feature columns:")
    print(feature_columns)
    print(f"\nTotal numeric features: {len(feature_columns)}")

    text_data = df["origin_query"].fillna("").astype(str)
    numeric_features = df[feature_columns].fillna(0)
    labels = df["question_type"].fillna("general").astype(str)

    plot_class_distribution(labels)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels)

    X_text_train, X_text_test, X_num_train, X_num_test, y_train, y_test = train_test_split(
        text_data,
        numeric_features,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    # Word TF-IDF learns meaningful terms and short phrases.
    # Char TF-IDF helps with code-like text, symbols, short tokens, and wording patterns.
    vectorizer = FeatureUnion([
        ("word_tfidf", TfidfVectorizer(
            lowercase=True,
            stop_words=None,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            max_features=10000
        )),
        ("char_tfidf", TfidfVectorizer(
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=2,
            max_features=6000
        ))
    ])

    X_train_tfidf = vectorizer.fit_transform(X_text_train)
    X_test_tfidf = vectorizer.transform(X_text_test)

    # Scale numeric handcrafted features.
    scaler = StandardScaler()
    X_train_num_scaled = scaler.fit_transform(X_num_train)
    X_test_num_scaled = scaler.transform(X_num_test)

    X_train_num_sparse = csr_matrix(X_train_num_scaled)
    X_test_num_sparse = csr_matrix(X_test_num_scaled)

    # Combine TF-IDF + handcrafted features.
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

    # Save evaluation visuals and CSV reports.
    plot_confusion_matrix(y_test, y_pred, label_encoder)
    plot_normalized_confusion_matrix(y_test, y_pred, label_encoder)
    plot_per_class_f1(y_test, y_pred, label_encoder)
    plot_precision_recall_f1(y_test, y_pred, label_encoder)
    plot_prediction_confidence(model, X_test_combined)

    save_misclassified_examples(X_text_test, y_test, y_pred, label_encoder)
    save_classification_metrics_csv(y_test, y_pred, label_encoder)

    print("\nTask Type Classifier Results")
    print("----------------------------")
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

    return model, vectorizer, scaler, label_encoder, feature_columns


# ------------------------------------------------------------
# Prediction
# ------------------------------------------------------------

def predict_user_input(
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns: list,
    extractor: PromptFeatureExtractor,
    text: str
):
    """
    Predict question type for one user input using only the trained ML model.
    """

    # Text features
    text_series = pd.Series([text])
    text_features = vectorizer.transform(text_series)

    # Handcrafted numeric features
    extracted_features = extractor.extract(text)
    feature_df = pd.DataFrame([extracted_features])

    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0

    feature_df = feature_df[feature_columns].fillna(0)

    numeric_scaled = scaler.transform(feature_df)
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

def save_classifier_artifacts(
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns,
    output_path=MODEL_PATH
):
    """
    Save all trained classifier artifacts needed for later prediction.
    """

    artifacts = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "label_encoder": label_encoder,
        "feature_columns": feature_columns,
    }

    joblib.dump(artifacts, output_path)

    print(f"\nSaved classifier artifacts to: {output_path}")

def load_classifier_artifacts(model_path=MODEL_PATH):
    """
    Load trained classifier artifacts from disk.
    """

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No saved model found at {model_path}. Train the classifier first."
        )

    artifacts = joblib.load(model_path)

    model = artifacts["model"]
    vectorizer = artifacts["vectorizer"]
    scaler = artifacts["scaler"]
    label_encoder = artifacts["label_encoder"]
    feature_columns = artifacts["feature_columns"]

    print(f"\nLoaded classifier artifacts from: {model_path}")

    return model, vectorizer, scaler, label_encoder, feature_columns


# ------------------------------------------------------------
# Main test loop
# ------------------------------------------------------------

def main():
    extractor = PromptFeatureExtractor()

    print("\nTask Type Classifier")
    print("--------------------")
    print("Type 'train' to train and save a new model.")
    print("Type 'load' to load the existing saved model.")
    mode = input("\nMode: ").strip().lower()

    if mode == "train":
        df = pd.read_csv(INPUT_CSV)

        model, vectorizer, scaler, label_encoder, feature_columns = train_task_type_classifier(df)

        save_classifier_artifacts(
            model=model,
            vectorizer=vectorizer,
            scaler=scaler,
            label_encoder=label_encoder,
            feature_columns=feature_columns
        )

    elif mode == "load":
        model, vectorizer, scaler, label_encoder, feature_columns = load_classifier_artifacts()

    else:
        print("Invalid mode. Please choose 'train' or 'load'.")
        return

    print("\nType a question to test the classifier.")
    print("Type 'quit' to stop.")

    while True:
        user_text = input("\nQuestion: ").strip()

        if user_text.lower() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        predicted_type, confidence_table = predict_user_input(
            model=model,
            vectorizer=vectorizer,
            scaler=scaler,
            label_encoder=label_encoder,
            feature_columns=feature_columns,
            extractor=extractor,
            text=user_text
        )

        print(f"\nPredicted question type: {predicted_type}")
        print("Prediction source: model")

        print("\nTop predictions:")
        for label, probability in confidence_table[:5]:
            print(f"- {label}: {probability:.4f}")

if __name__ == "__main__":
    main()