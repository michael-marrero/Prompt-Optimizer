import os
import sys
import joblib
import numpy as np
import pandas as pd

from sentence_transformers import SentenceTransformer

from sklearn.metrics import accuracy_score, f1_score


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

_MODEL_ROUTER_DIR = os.path.join(PROJECT_ROOT, "src", "model_router")

if _MODEL_ROUTER_DIR not in sys.path:
    sys.path.insert(0, _MODEL_ROUTER_DIR)

import train_embedding_router as train_embedding_router_mod  # noqa: E402
from model_family import infer_model_vendor_family  # noqa: E402


def embedding_router_y_true(df: pd.DataFrame, artifacts: dict):
    """Match training labels saved on the embedding router artifact."""

    if artifacts.get("target_type") == "model_family":
        series = df["best_model"].fillna("").astype(str)

        return series.map(infer_model_vendor_family).to_numpy()

    return df["best_model"].astype(str).to_numpy()


def filter_embedding_router_eval_df(df: pd.DataFrame, artifacts: dict):
    """Rows whose inferred vendor bucket exists in saved label_encoder.classes_."""

    allowed = set(artifacts["label_encoder"].classes_)
    inferred = df["best_model"].fillna("").astype(str).map(infer_model_vendor_family)
    mask = inferred.isin(allowed).to_numpy()
    dropped = int((~mask).sum())

    if dropped:
        print(
            "\nEmbedding router evaluation: omitting rows whose inferred vendor buckets "
            f"were withheld during training ({dropped} rows)."
        )

    return df.loc[mask].reset_index(drop=True)


DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")

os.makedirs(EVALUATION_DIR, exist_ok=True)

CLASSIFIER_TRAINING_CSV = os.path.join(
    DATA_PROCESSED_DIR,
    "classifier_training.csv"
)

FLAT_RECORDS_CSV = os.path.join(
    DATA_PROCESSED_DIR,
    "flat_records.csv"
)

EMBEDDING_ROUTER_MODEL_PATH = os.path.join(
    MODELS_DIR,
    "embedding_router.joblib"
)

OUTPUT_CSV = os.path.join(
    EVALUATION_DIR,
    "baseline_comparison_metrics.csv"
)


# ------------------------------------------------------------
# Data loading
# ------------------------------------------------------------

def load_classifier_training_data():
    """
    Load the main evaluation dataset.

    Expected target:
    best_model
    """

    if not os.path.exists(CLASSIFIER_TRAINING_CSV):
        raise FileNotFoundError(
            f"Missing file:\n{CLASSIFIER_TRAINING_CSV}"
        )

    df = pd.read_csv(CLASSIFIER_TRAINING_CSV)

    required_columns = [
        "origin_query",
        "best_model",
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"classifier_training.csv is missing required column: {col}")

    df = df.dropna(subset=["origin_query", "best_model"]).copy()

    df["origin_query"] = df["origin_query"].astype(str)
    df["best_model"] = df["best_model"].astype(str)

    return df


def build_average_cost_table():
    """
    Build average cost per model from flat_records.csv if available.

    This is used for the always-cheapest baseline and estimated route cost.
    """

    if not os.path.exists(FLAT_RECORDS_CSV):
        print("\nflat_records.csv not found. Cost estimates will be unavailable.")
        return None

    df = pd.read_csv(FLAT_RECORDS_CSV)

    if "cost" not in df.columns:
        print("\nflat_records.csv has no cost column. Cost estimates will be unavailable.")
        return None

    if "model_name" in df.columns:
        model_col = "model_name"
    elif "model_dir" in df.columns:
        model_col = "model_dir"
    else:
        print("\nflat_records.csv has no model_name or model_dir column.")
        return None

    df["cost"] = pd.to_numeric(df["cost"], errors="coerce")

    cost_df = (
        df.dropna(subset=[model_col, "cost"])
        .groupby(model_col)["cost"]
        .mean()
        .reset_index()
        .rename(columns={
            model_col: "model",
            "cost": "avg_cost"
        })
    )

    if cost_df.empty:
        return None

    return cost_df


# ------------------------------------------------------------
# Baselines
# ------------------------------------------------------------

def get_cheapest_model(cost_df):
    """
    Return globally cheapest model by average cost.
    """

    if cost_df is None or cost_df.empty:
        return None

    cheapest_row = cost_df.sort_values("avg_cost", ascending=True).iloc[0]
    return cheapest_row["model"]


def get_average_cost_for_predictions(predictions, cost_df):
    """
    Estimate average cost for a list of predicted models.
    """

    if cost_df is None or cost_df.empty:
        return np.nan

    cost_map = dict(zip(cost_df["model"], cost_df["avg_cost"]))

    costs = []

    for model in predictions:
        cost = cost_map.get(model)

        if cost is not None:
            costs.append(cost)

    if not costs:
        return np.nan

    return float(np.mean(costs))


def evaluate_predictions(
    name,
    y_true,
    y_pred,
    cost_df=None,
    notes="",
    evaluation_target="best_model",
):
    """
    Calculate accuracy, macro F1, weighted F1, and estimated average cost.
    """

    return {
        "strategy": name,
        "evaluation_target": evaluation_target,
        "target": evaluation_target,
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "estimated_avg_cost": get_average_cost_for_predictions(y_pred, cost_df),
        "notes": notes,
    }


# ------------------------------------------------------------
# Embedding router prediction
# ------------------------------------------------------------

def load_embedding_router():
    """
    Load saved embedding router artifacts.
    """

    if not os.path.exists(EMBEDDING_ROUTER_MODEL_PATH):
        raise FileNotFoundError(
            f"Missing embedding router model:\n{EMBEDDING_ROUTER_MODEL_PATH}\n\n"
            "Run src/model_router/train_embedding_router.py first."
        )

    artifacts = joblib.load(EMBEDDING_ROUTER_MODEL_PATH)

    required_keys = [
        "model",
        "label_encoder",
        "embedding_model_name",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"embedding_router.joblib is missing required key: {key}")

    artifacts.setdefault("scaler", None)
    artifacts.setdefault("prepend_dataset_to_query", False)
    artifacts.setdefault("prepend_prompt_stub", False)

    return artifacts


def predict_with_embedding_router(df: pd.DataFrame, artifacts):
    """
    Run the embedding router row-aligned with classifier_training.csv metadata.
    """

    model = artifacts["model"]
    label_encoder = artifacts["label_encoder"]
    embedding_model_name = artifacts["embedding_model_name"]

    print("\nLoading sentence embedding model:")
    print(embedding_model_name)

    embedding_model = SentenceTransformer(embedding_model_name)

    texts = train_embedding_router_mod.build_inference_strings(df, artifacts)

    print("\nEncoding prompts for embedding router evaluation...")

    embeddings = embedding_model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    scaler = artifacts.get("scaler")
    features = scaler.transform(embeddings) if scaler is not None else embeddings

    y_pred_encoded = model.predict(features)
    y_pred = label_encoder.inverse_transform(y_pred_encoded)

    return y_pred


# ------------------------------------------------------------
# Main evaluation
# ------------------------------------------------------------

def evaluate_baselines():
    """
    Evaluate straightforward routing baselines against raw best_model labels.

    Strategies:
    - Oracle
    - Always cheapest model
    - Always GPT-5
    - Embedding router
    """

    print("\nEvaluating routing baselines")
    print("----------------------------")

    df = load_classifier_training_data()
    cost_df = build_average_cost_table()

    y_true = df["best_model"].astype(str).to_numpy()
    rows = []

    # --------------------------------------------------------
    # Oracle baseline
    # --------------------------------------------------------

    oracle_predictions = y_true.copy()

    rows.append(
        evaluate_predictions(
            name="Oracle",
            y_true=y_true,
            y_pred=oracle_predictions,
            cost_df=cost_df,
            evaluation_target="best_model",
            notes="Upper bound. Uses the true best_model label from the dataset.",
        )
    )

    # --------------------------------------------------------
    # Always cheapest baseline
    # --------------------------------------------------------

    cheapest_model = get_cheapest_model(cost_df)

    if cheapest_model is not None:
        cheapest_predictions = np.array([cheapest_model] * len(y_true))

        rows.append(
            evaluate_predictions(
                name="Always Cheapest",
                y_true=y_true,
                y_pred=cheapest_predictions,
                cost_df=cost_df,
                evaluation_target="best_model",
                notes=f"Always predicts the globally cheapest average-cost model: {cheapest_model}.",
            )
        )
    else:
        print("\nSkipped Always Cheapest because cost table was unavailable.")

    # --------------------------------------------------------
    # Always GPT-5 baseline
    # --------------------------------------------------------

    gpt5_predictions = np.array(["gpt-5"] * len(y_true))

    rows.append(
        evaluate_predictions(
            name="Always GPT-5",
            y_true=y_true,
            y_pred=gpt5_predictions,
            cost_df=cost_df,
            evaluation_target="best_model",
            notes="Expensive/strong baseline. Always predicts gpt-5.",
        )
    )

    # --------------------------------------------------------
    # Embedding router
    # --------------------------------------------------------

    artifacts = load_embedding_router()

    df_emb = filter_embedding_router_eval_df(df, artifacts)

    family_y_true = embedding_router_y_true(df_emb, artifacts)

    embedding_predictions = predict_with_embedding_router(
        df_emb,
        artifacts=artifacts,
    )

    evaluation_axis = artifacts.get("target_column", "best_model_family")

    rows.append(
        evaluate_predictions(
            name="Embedding Router",
            y_true=family_y_true,
            y_pred=embedding_predictions,
            cost_df=cost_df,
            evaluation_target=evaluation_axis,
            notes=(
                f"Semantic router label space: {evaluation_axis}. "
                "Metrics are vendor-family granularity (not comparable to exact-model baselines). "
                "Rows withheld during embedding training are omitted here so y matches the encoder."
            ),
        )
    )

    results_df = pd.DataFrame(rows)

    results_df = results_df.sort_values(
        by="weighted_f1",
        ascending=False
    )

    results_df.to_csv(OUTPUT_CSV, index=False)

    print("\nBaseline comparison:")
    print(
        results_df[
            [
                "strategy",
                "target",
                "accuracy",
                "macro_f1",
                "weighted_f1",
                "estimated_avg_cost",
                "notes",
            ]
        ].to_string(index=False)
    )

    print("\nSaved baseline comparison to:")
    print(OUTPUT_CSV)


if __name__ == "__main__":
    evaluate_baselines()