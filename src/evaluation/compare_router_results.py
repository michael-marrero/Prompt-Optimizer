import os
import pandas as pd
import matplotlib.pyplot as plt


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
COMPARISON_PLOTS_DIR = os.path.join(EVALUATION_DIR, "comparison_plots")

os.makedirs(EVALUATION_DIR, exist_ok=True)
os.makedirs(COMPARISON_PLOTS_DIR, exist_ok=True)


# ------------------------------------------------------------
# Input files
# ------------------------------------------------------------

TASK_CLASSIFIER_METRICS = os.path.join(
    EVALUATION_DIR,
    "classification_metrics.csv"
)

TIER_ROUTER_METRICS = os.path.join(
    EVALUATION_DIR,
    "tier_router_metrics.csv"
)

MODEL_ROUTER_METRICS = os.path.join(
    EVALUATION_DIR,
    "model_router_metrics.csv"
)

EMBEDDING_ROUTER_METRICS = os.path.join(
    EVALUATION_DIR,
    "embedding_router_metrics.csv"
)


# ------------------------------------------------------------
# Output files
# ------------------------------------------------------------

SUMMARY_OUTPUT = os.path.join(
    EVALUATION_DIR,
    "router_comparison_summary.csv"
)


# ------------------------------------------------------------
# Metric helpers
# ------------------------------------------------------------

def load_metrics_file(path: str, router_name: str):
    """
    Load a per-class metrics CSV.

    Expected columns:
    - precision
    - recall
    - f1_score
    - support

    The class label column can have any name.
    """

    if not os.path.exists(path):
        print(f"Skipped {router_name}: file not found at {path}")
        return None

    df = pd.read_csv(path)

    required_columns = [
        "precision",
        "recall",
        "f1_score",
        "support",
    ]

    for col in required_columns:
        if col not in df.columns:
            print(f"Skipped {router_name}: missing column '{col}' in {path}")
            return None

    return df


def summarize_metrics(metrics_df: pd.DataFrame):
    """
    Calculate macro and weighted metrics from a per-class metrics table.
    """

    support = metrics_df["support"].fillna(0)

    total_support = support.sum()

    macro_precision = metrics_df["precision"].mean()
    macro_recall = metrics_df["recall"].mean()
    macro_f1 = metrics_df["f1_score"].mean()

    if total_support > 0:
        weighted_precision = (
            metrics_df["precision"] * support
        ).sum() / total_support

        weighted_recall = (
            metrics_df["recall"] * support
        ).sum() / total_support

        weighted_f1 = (
            metrics_df["f1_score"] * support
        ).sum() / total_support
    else:
        weighted_precision = 0
        weighted_recall = 0
        weighted_f1 = 0

    return {
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "weighted_precision": weighted_precision,
        "weighted_recall": weighted_recall,
        "weighted_f1": weighted_f1,
        "support": int(total_support),
        "num_classes": int(len(metrics_df)),
    }


def build_summary_row(
    router_name: str,
    target: str,
    feature_style: str,
    metrics_path: str,
    notes: str
):
    """
    Build one row for the comparison table.
    """

    metrics_df = load_metrics_file(
        path=metrics_path,
        router_name=router_name
    )

    if metrics_df is None:
        return None

    summary = summarize_metrics(metrics_df)

    return {
        "router_name": router_name,
        "target": target,
        "feature_style": feature_style,
        "num_classes": summary["num_classes"],
        "support": summary["support"],
        "macro_precision": summary["macro_precision"],
        "macro_recall": summary["macro_recall"],
        "macro_f1": summary["macro_f1"],
        "weighted_precision": summary["weighted_precision"],
        "weighted_recall": summary["weighted_recall"],
        "weighted_f1": summary["weighted_f1"],
        "metrics_file": os.path.relpath(metrics_path, PROJECT_ROOT),
        "notes": notes,
    }


# ------------------------------------------------------------
# Plot helpers
# ------------------------------------------------------------

def plot_metric_comparison(summary_df: pd.DataFrame, metric: str):
    """
    Save a bar chart comparing routers by one metric.
    """

    if summary_df.empty:
        return

    if metric not in summary_df.columns:
        return

    plot_df = summary_df.sort_values(metric, ascending=False)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(plot_df["router_name"], plot_df[metric])

    ax.set_title(f"Router Comparison: {metric}")
    ax.set_xlabel("Router")
    ax.set_ylabel(metric)
    ax.set_ylim(0, 1)
    ax.set_xticks(range(len(plot_df["router_name"])))
    ax.set_xticklabels(plot_df["router_name"], rotation=30, ha="right")

    plt.tight_layout()

    output_path = os.path.join(
        COMPARISON_PLOTS_DIR,
        f"router_{metric}_comparison.png"
    )

    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved {metric} comparison plot to: {output_path}")


# ------------------------------------------------------------
# Main comparison logic
# ------------------------------------------------------------

def compare_router_results():
    """
    Build a single comparison table across all available router/classifier metrics.
    """

    print("\nComparing router results")
    print("------------------------")

    rows = []

    candidates = [
        {
            "router_name": "Task Type Classifier",
            "target": "question_type",
            "feature_style": "TF-IDF + handcrafted prompt features",
            "metrics_path": TASK_CLASSIFIER_METRICS,
            "notes": "Stage 1 classifier used to identify prompt/task category.",
        },
        {
            "router_name": "Tier Router",
            "target": "best_model_tier",
            "feature_style": "TF-IDF + task type + handcrafted prompt features",
            "metrics_path": TIER_ROUTER_METRICS,
            "notes": "Coarse-grained router predicting cheap, medium, or strong model tier.",
        },
        {
            "router_name": "TF-IDF Model Router",
            "target": "best_model or best_model_top15",
            "feature_style": "TF-IDF + task type + handcrafted prompt features",
            "metrics_path": MODEL_ROUTER_METRICS,
            "notes": "Exact/top-model router. Harder due to many imbalanced model classes.",
        },
        {
            "router_name": "Embedding Router",
            "target": "best_model_vendor_family",
            "feature_style": "Sentence embeddings only",
            "metrics_path": EMBEDDING_ROUTER_METRICS,
            "notes": "Vendor-family softmax head on origin_query embeddings (see train_embedding_router).",
        },
    ]

    for candidate in candidates:
        row = build_summary_row(**candidate)

        if row is not None:
            rows.append(row)

    if not rows:
        print("\nNo available metrics files found. Nothing to compare.")
        return

    summary_df = pd.DataFrame(rows)

    # Sort by weighted F1 because it reflects overall performance under class imbalance.
    summary_df = summary_df.sort_values(
        by="weighted_f1",
        ascending=False
    )

    summary_df.to_csv(SUMMARY_OUTPUT, index=False)

    print("\nRouter comparison summary:")
    print(
        summary_df[
            [
                "router_name",
                "target",
                "num_classes",
                "support",
                "macro_f1",
                "weighted_f1",
                "notes",
            ]
        ].to_string(index=False)
    )

    print("\nSaved summary CSV to:")
    print(SUMMARY_OUTPUT)

    plot_metric_comparison(summary_df, "macro_f1")
    plot_metric_comparison(summary_df, "weighted_f1")
    plot_metric_comparison(summary_df, "macro_precision")
    plot_metric_comparison(summary_df, "macro_recall")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

if __name__ == "__main__":
    compare_router_results()