import os
import pandas as pd


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")

INPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "router_training_dataset.csv")
OUTPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "router_training_dataset_top_models.csv")


# ------------------------------------------------------------
# Target helper
# ------------------------------------------------------------

def get_target_column(df: pd.DataFrame) -> str:
    """
    Prefer cost-aware best_value_model if available.
    Fall back to best_model.
    """

    if "best_value_model" in df.columns:
        return "best_value_model"

    if "best_model" in df.columns:
        return "best_model"

    raise ValueError(
        "Dataset must contain either 'best_value_model' or 'best_model'."
    )


# ------------------------------------------------------------
# Main cleanup logic
# ------------------------------------------------------------

def build_top_model_router_dataset(
    input_csv=INPUT_CSV,
    output_csv=OUTPUT_CSV,
    top_n=15,
    other_label="OTHER"
):
    """
    Build a cleaner exact-model router dataset.

    Instead of training on every rare model class, this keeps the top N most common
    model labels and maps all other model labels to OTHER.

    Input:
        data_processed/router_training_dataset.csv

    Output:
        data_processed/router_training_dataset_top_models.csv
    """

    print("\nBuilding top-model router dataset")
    print("---------------------------------")

    print("\nLoading router training dataset from:")
    print(input_csv)

    df = pd.read_csv(input_csv)

    print(f"\nLoaded rows: {len(df)}")
    print(f"Loaded columns: {len(df.columns)}")

    target_column = get_target_column(df)

    print(f"\nOriginal target column: {target_column}")

    model_counts = df[target_column].value_counts()

    print("\nOriginal model distribution:")
    print(model_counts)

    top_models = model_counts.head(top_n).index.tolist()

    print(f"\nKeeping top {top_n} models:")
    for rank, model_name in enumerate(top_models, start=1):
        print(f"{rank}. {model_name} ({model_counts[model_name]} rows)")

    new_target_column = f"{target_column}_top{top_n}"

    df[new_target_column] = df[target_column].apply(
        lambda model_name: model_name if model_name in top_models else other_label
    )

    print(f"\nNew target column: {new_target_column}")

    print("\nNew target distribution:")
    print(df[new_target_column].value_counts())

    rows_in_top_models = df[df[target_column].isin(top_models)].shape[0]
    rows_mapped_to_other = df[~df[target_column].isin(top_models)].shape[0]

    print("\nSummary:")
    print(f"Rows kept as top model labels: {rows_in_top_models}")
    print(f"Rows mapped to {other_label}: {rows_mapped_to_other}")
    print(f"Total rows: {len(df)}")

    df.to_csv(output_csv, index=False)

    print("\nSaved cleaned router dataset to:")
    print(output_csv)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

if __name__ == "__main__":
    build_top_model_router_dataset()