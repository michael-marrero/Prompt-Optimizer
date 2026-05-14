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
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.frozen import FrozenEstimator

from src.feature_extraction.text_inputs import build_router_text_input_series


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
ROUTER_PLOTS_DIR = os.path.join(EVALUATION_DIR, "model_router_plots")
CALIBRATION_PLOTS_DIR = os.path.join(EVALUATION_DIR, "calibration_plots")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(EVALUATION_DIR, exist_ok=True)
os.makedirs(ROUTER_PLOTS_DIR, exist_ok=True)
os.makedirs(CALIBRATION_PLOTS_DIR, exist_ok=True)

INPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "router_training_dataset_top_models.csv")
MODEL_ROUTER_PATH = os.path.join(MODELS_DIR, "model_router.joblib")


# ------------------------------------------------------------
# Target helper
# ------------------------------------------------------------

def get_target_column(df: pd.DataFrame) -> str:
    """
    Prefer grouped top-model target if available.
    Fall back to cost-aware best_value_model if available.
    Fall back to raw best_model.
    """

    if "best_model_top15" in df.columns:
        return "best_model_top15"

    if "best_value_model_top15" in df.columns:
        return "best_value_model_top15"

    if "best_value_model" in df.columns:
        return "best_value_model"

    if "best_model" in df.columns:
        return "best_model"

    raise ValueError(
        "Router dataset must contain a model target column."
    )
# ------------------------------------------------------------
# Feature helpers
# ------------------------------------------------------------

def get_numeric_feature_columns(df: pd.DataFrame, target_column: str) -> list:
    """
    Return numeric feature columns for exact model router training.

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


# ------------------------------------------------------------
# Evaluation plots
# ------------------------------------------------------------

def plot_target_distribution(labels_series: pd.Series, target_column: str):
    counts = labels_series.value_counts().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.bar(counts.index, counts.values)

    ax.set_title(f"Exact Model Router Target Distribution: {target_column}")
    ax.set_xlabel("Model")
    ax.set_ylabel("Number of Examples")
    ax.set_xticks(np.arange(len(counts.index)))
    ax.set_xticklabels(counts.index, rotation=75, ha="right")

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "model_router_target_distribution.png")
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
        "model": labels,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "support": support
    })

    metrics_df = metrics_df.sort_values("support", ascending=False).head(top_n)

    x = np.arange(len(metrics_df))

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.bar(x, metrics_df["f1_score"])

    ax.set_title(f"Top {top_n} Model Classes by Support - F1 Score")
    ax.set_xlabel("Model")
    ax.set_ylabel("F1 Score")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics_df["model"], rotation=75, ha="right")
    ax.set_ylim(0, 1)

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "model_router_top_class_f1.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved top-class F1 chart to: {output_path}")


def plot_prediction_confidence(model, X_test_combined):
    probabilities = model.predict_proba(X_test_combined)
    max_confidences = probabilities.max(axis=1)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.hist(max_confidences, bins=20)

    ax.set_title("Exact Model Router Prediction Confidence")
    ax.set_xlabel("Top Prediction Probability")
    ax.set_ylabel("Number of Predictions")

    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "model_router_prediction_confidence.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved prediction confidence histogram to: {output_path}")


def plot_top_confusion_matrix(y_test, y_pred, label_encoder, top_n=20):
    """
    Save a confusion matrix only for the most common classes.

    Full exact-model confusion matrices can be enormous, so this trims it.
    """

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

    fig, ax = plt.subplots(figsize=(14, 12))

    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=top_labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=75,
        values_format="d",
        colorbar=True
    )

    ax.set_title(f"Exact Model Router Confusion Matrix - Top {top_n} Classes")
    plt.tight_layout()

    output_path = os.path.join(ROUTER_PLOTS_DIR, "model_router_top_confusion_matrix.png")
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

    output_path = os.path.join(EVALUATION_DIR, "model_router_metrics.csv")
    metrics_df.to_csv(output_path, index=False)

    print(f"Saved exact model router metrics CSV to: {output_path}")


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

                "true_model": true_label,
                "predicted_model": pred_label,
                "target_column": target_column,
            })

    mistakes_df = pd.DataFrame(rows)

    output_path = os.path.join(EVALUATION_DIR, "model_router_misclassified_examples.csv")
    mistakes_df.to_csv(output_path, index=False)

    print(f"Saved exact model router misclassified examples to: {output_path}")


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
    output_path=MODEL_ROUTER_PATH
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

    print("\nSaved exact model router artifacts to:")
    print(output_path)


def load_router_artifacts(model_path=MODEL_ROUTER_PATH):
    """
    Load a previously trained exact model router.
    """

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No saved exact model router found at:\n{model_path}\n\n"
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

    print("\nLoaded saved exact model router from:")
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
    Predict exact model for one user prompt using the trained router.

    For this standalone script, the Stage 1 question type is entered manually.
    Later, demo_router.py can call the task classifier first and pass it here.
    """

    input_df = pd.DataFrame([{
        "origin_query": text,
        "question_type": question_type,
        "keyword_question_type": keyword_question_type,
        "question_type_confidence": question_type_confidence,
    }])

    text_data = build_router_text_input_series(input_df)

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
# Calibration plot helper
# ------------------------------------------------------------

def plot_reliability_diagram(
    y_true_binary: np.ndarray,
    y_proba_max: np.ndarray,
    stage_name: str,
    output_dir: str = CALIBRATION_PLOTS_DIR,
):
    """
    Save a reliability diagram (calibration curve) for a calibrated multiclass
    classifier.

    y_true_binary is `(y_pred == y_test).astype(int)` (the "did the argmax
    win?" view), y_proba_max is `proba.max(axis=1)`. A perfectly calibrated
    classifier lies on the diagonal y=x.
    """

    frac_pos, mean_pred = calibration_curve(
        y_true_binary,
        y_proba_max,
        n_bins=10,
        strategy="uniform",
    )

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", label="Perfectly calibrated")
    ax.plot(mean_pred, frac_pos, marker="o", label=stage_name)

    ax.set_xlabel("Mean predicted probability (max class)")
    ax.set_ylabel("Fraction correct")
    ax.set_title(f"Reliability Diagram - {stage_name}")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.legend(loc="best")

    plt.tight_layout()

    output_path = os.path.join(output_dir, f"reliability_diagram_{stage_name}.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved reliability diagram to: {output_path}")


# ------------------------------------------------------------
# Training
# ------------------------------------------------------------

def train_model_router(df: pd.DataFrame):
    """
    Train a router that predicts the exact best model.

    Input:
    - origin_query
    - classifier-generated question_type
    - keyword_question_type if available
    - numeric handcrafted features
    - question_type_confidence if available

    Target:
    - best_value_model if available
    - otherwise best_model
    """

    if "origin_query" not in df.columns:
        raise ValueError("Router dataset must contain 'origin_query'.")

    target_column = get_target_column(df)

    print(f"\nRouter target column: {target_column}")

    feature_columns = get_numeric_feature_columns(df, target_column)

    print("\nUsing numeric router feature columns:")
    print(feature_columns)
    print(f"\nTotal numeric router features: {len(feature_columns)}")

    text_data = build_router_text_input_series(df)
    numeric_features = df[feature_columns].fillna(0)
    labels = df[target_column].fillna("unknown").astype(str)

    valid_mask = labels != "unknown"

    text_data = text_data[valid_mask]
    numeric_features = numeric_features[valid_mask]
    labels = labels[valid_mask]
    df_valid = df[valid_mask].copy()

    print(f"\nTraining rows after removing unknown labels: {len(df_valid)}")
    print(f"Number of model classes: {labels.nunique()}")

    plot_target_distribution(labels, target_column)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels)

    # Stratified split can fail if some model classes only have one sample.
    # Remove classes with fewer than 2 examples for stable train/test splitting.
    label_counts = pd.Series(y).value_counts()
    valid_encoded_labels = label_counts[label_counts >= 2].index

    keep_mask = pd.Series(y).isin(valid_encoded_labels).to_numpy()

    removed_count = len(y) - keep_mask.sum()

    if removed_count > 0:
        print(f"\nRemoved {removed_count} rows from rare model classes with fewer than 2 examples.")

    text_data = text_data[keep_mask]
    numeric_features = numeric_features[keep_mask]
    labels = labels[keep_mask]
    df_valid = df_valid[keep_mask].copy()

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
            max_features=10000
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

    print("\nTraining exact model router...")
    model.fit(X_train_combined, y_train)

    # ------------------------------------------------------------
    # Calibration (ROUTER-03; RESEARCH §Pattern 1; sklearn 1.6+ FrozenEstimator)
    # ------------------------------------------------------------
    # Carve a fresh 0.25 calibration slice from the training data ONLY so the
    # calibrator never sees the held-out test split (Pitfall 3). FrozenEstimator
    # wraps the fitted base; CalibratedClassifierCV does NOT refit the base —
    # it only fits the sigmoid head on the slice (Pitfall 1: the legacy
    # prefit-cv argument is removed in sklearn 1.8; FrozenEstimator is the
    # replacement idiom).
    #
    # method="sigmoid" is the Phase 1 default for all three calibrated heads
    # (RESEARCH Open Question 1). Switch this stage to method="isotonic" in a
    # follow-up commit only if Plan 07's ECE > 0.10 on the canary set.
    X_train_only, X_calib, y_train_only, y_calib = train_test_split(
        X_train_combined,
        y_train,
        test_size=0.25,
        random_state=42,
        stratify=y_train,
    )

    calibrated = CalibratedClassifierCV(
        FrozenEstimator(model),
        method="sigmoid",
    )
    calibrated.fit(X_calib, y_calib)

    # Reassign so downstream metric + persistence code uses the calibrated
    # version. Pitfall 4: the artifact dict's `model` key still holds the
    # primary inference object — we just swap LogisticRegression for
    # CalibratedClassifierCV; all other keys stay identical.
    model = calibrated

    y_pred = model.predict(X_test_combined)

    # Evaluation artifacts
    plot_top_confusion_matrix(y_test, y_pred, label_encoder, top_n=20)
    plot_top_class_f1(y_test, y_pred, label_encoder, top_n=20)
    plot_prediction_confidence(model, X_test_combined)

    save_metrics_csv(y_test, y_pred, label_encoder, target_column)
    save_misclassified_examples(df_test, y_test, y_pred, label_encoder, target_column)

    print("\nExact Model Router Results")
    print("--------------------------")
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

    # Reliability diagram (per stage; saved to evaluation/calibration_plots/).
    proba_test = model.predict_proba(X_test_combined)
    y_true_binary = (y_pred == y_test).astype(int)
    y_proba_max = proba_test.max(axis=1)
    plot_reliability_diagram(
        y_true_binary=y_true_binary,
        y_proba_max=y_proba_max,
        stage_name="model_router",
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
    print("\nExact Model Router")
    print("------------------")
    print("Type 'train' to train and save a new exact model router.")
    print("Type 'load' to load the existing saved exact model router.")

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
        ) = train_model_router(df)

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

    print("\nType a question to test the exact model router.")
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

        predicted_model, confidence_table = predict_user_input(
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
        print(f"Predicted best model: {predicted_model}")
        print("Prediction source: exact model router")

        print("\nTop predictions:")
        for label, probability in confidence_table[:5]:
            print(f"- {label}: {probability:.4f}")


if __name__ == "__main__":
    main()