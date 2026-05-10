import os
import sys
import joblib
import pandas as pd

from scipy.sparse import hstack, csr_matrix


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")

INPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "classifier_training_with_types.csv")
OUTPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "router_training_dataset.csv")
TASK_CLASSIFIER_PATH = os.path.join(MODELS_DIR, "task_type_classifier.joblib")

if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from Feature_extractor import PromptFeatureExtractor


# ------------------------------------------------------------
# Load saved task classifier
# ------------------------------------------------------------

def load_task_classifier(model_path=TASK_CLASSIFIER_PATH):
    """
    Load the previously trained task classifier.

    This file does not train the classifier.
    It only loads the saved model artifact.
    """

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No saved task classifier found at:\n{model_path}\n\n"
            "Run train_task_classifier_robust.py first and make sure it saves "
            "models/task_type_classifier.joblib."
        )

    artifacts = joblib.load(model_path)

    required_keys = [
        "model",
        "vectorizer",
        "scaler",
        "label_encoder",
        "feature_columns",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"Saved classifier artifact is missing key: {key}")

    print(f"\nLoaded saved task classifier from:")
    print(model_path)

    return (
        artifacts["model"],
        artifacts["vectorizer"],
        artifacts["scaler"],
        artifacts["label_encoder"],
        artifacts["feature_columns"],
    )


# ------------------------------------------------------------
# Predict task types
# ------------------------------------------------------------

def add_classifier_question_types(
    df: pd.DataFrame,
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns
):
    """
    Add classifier-generated question_type values to the router dataset.
    """

    extractor = PromptFeatureExtractor()

    text_data = df["origin_query"].fillna("").astype(str)

    extracted_rows = []

    for text in text_data:
        extracted_rows.append(extractor.extract(text))

    feature_df = pd.DataFrame(extracted_rows)

    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0

    feature_df = feature_df[feature_columns].fillna(0)

    text_features = vectorizer.transform(text_data)

    numeric_scaled = scaler.transform(feature_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined_features = hstack([text_features, numeric_sparse])

    predicted_encoded = model.predict(combined_features)
    predicted_labels = label_encoder.inverse_transform(predicted_encoded)

    probabilities = model.predict_proba(combined_features)
    top_confidences = probabilities.max(axis=1)

    df["question_type"] = predicted_labels
    df["question_type_confidence"] = top_confidences

    return df


# ------------------------------------------------------------
# Best model tier logic
# ------------------------------------------------------------

def assign_cost_tier_from_cost(cost, cheap_cutoff, medium_cutoff):
    """
    Convert best_cost into cheap, medium, or strong.
    """

    if pd.isna(cost):
        return "unknown"

    if cost <= cheap_cutoff:
        return "cheap"

    if cost <= medium_cutoff:
        return "medium"

    return "strong"


def add_best_model_tier(df: pd.DataFrame):
    """
    Add best_model_tier using best_cost percentiles.

    Cheap = lowest third of best_cost values
    Medium = middle third
    Strong = highest third
    """

    if "best_cost" not in df.columns:
        raise ValueError("CSV must contain a 'best_cost' column.")

    valid_costs = df["best_cost"].dropna()

    if valid_costs.empty:
        raise ValueError("No valid best_cost values found.")

    cheap_cutoff = valid_costs.quantile(0.33)
    medium_cutoff = valid_costs.quantile(0.66)

    print("\nCost tier cutoffs:")
    print(f"Cheap cutoff:  {cheap_cutoff:.8f}")
    print(f"Medium cutoff: {medium_cutoff:.8f}")

    df["best_model_tier"] = df["best_cost"].apply(
        lambda cost: assign_cost_tier_from_cost(
            cost=cost,
            cheap_cutoff=cheap_cutoff,
            medium_cutoff=medium_cutoff
        )
    )

    return df


# ------------------------------------------------------------
# Build router dataset
# ------------------------------------------------------------

def build_router_dataset():
    """
    Build the Stage 2 router training dataset.

    This script does NOT train any model.

    It:
    1. Loads classifier_training_with_types.csv
    2. Preserves the old keyword question_type as keyword_question_type
    3. Loads the saved task classifier
    4. Replaces question_type with classifier predictions
    5. Adds best_model_tier
    6. Saves router_training_dataset.csv
    """

    print("\nLoading classifier training dataset...")
    df = pd.read_csv(INPUT_CSV)

    print(f"Loaded rows: {len(df)}")
    print(f"Loaded columns: {len(df.columns)}")

    required_columns = [
        "origin_query",
        "question_type",
        "best_model",
        "best_score",
        "best_cost",
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Preserve old keyword-based question type.
    df = df.rename(columns={
        "question_type": "keyword_question_type"
    })

    print("\nOld keyword question type distribution:")
    print(df["keyword_question_type"].value_counts())

    model, vectorizer, scaler, label_encoder, feature_columns = load_task_classifier()

    print("\nAdding classifier-generated question_type values...")
    df = add_classifier_question_types(
        df=df,
        model=model,
        vectorizer=vectorizer,
        scaler=scaler,
        label_encoder=label_encoder,
        feature_columns=feature_columns
    )

    print("\nAdding best_model_tier...")
    df = add_best_model_tier(df)

    preview_columns = [
        "origin_query",
        "keyword_question_type",
        "question_type",
        "question_type_confidence",
        "best_model",
        "best_score",
        "best_cost",
        "best_model_tier",
    ]

    print("\nRouter dataset preview:")
    print(df[preview_columns].head(10))

    print("\nClassifier question type distribution:")
    print(df["question_type"].value_counts())

    print("\nBest model tier distribution:")
    print(df["best_model_tier"].value_counts())

    df.to_csv(OUTPUT_CSV, index=False)

    print("\nSaved router training dataset to:")
    print(OUTPUT_CSV)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

if __name__ == "__main__":
    build_router_dataset()