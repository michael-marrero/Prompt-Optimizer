import pandas as pd


INPUT_CSV = "../../data_processed/classifier_training_features.csv"
OUTPUT_CSV = "../../data_processed/classifier_training_with_types.csv"


def map_dataset_to_question_type(dataset: str) -> str:
    """
    Convert a benchmark dataset name into a broad question type.

    This is weak labeling, not perfect labeling.
    Later, this can be replaced with LLM-generated labels.
    """

    dataset = str(dataset).lower().strip()

    coding_datasets = [
        "humaneval",
        "livecodebench",
        "mbpp",
        "apps",
        "code",
        "arenahard_coding",
        "swe-bench",
        "swebench",
    ]

    math_datasets = [
        "aime",
        "gsm8k",
        "math",
        "minerva",
        "olympiad",
    ]

    reasoning_datasets = [
        "bbh",
        "bigbench",
        "arc",
        "hellaswag",
        "winogrande",
        "boolq",
        "commonsense",
        "korbench",
        "kandk",
    ]

    knowledge_datasets = [
        "mmlu",
        "mmlu_pro",
        "gpqa",
        "triviaqa",
        "natural_questions",
        "nq",
        "hle",
    ]

    factual_datasets = [
        "simpleqa",
    ]

    writing_datasets = [
        "arenahard_creative_writing",
        "creative_writing",
        "writing",
    ]

    medical_datasets = [
        "medqa",
        "medical",
        "medicine",
    ]

    emotion_datasets = [
        "emorynlp",
        "meld",
        "emotion",
        "sentiment",
        "dialogue_emotion",
    ]

    agentic_datasets = [
        "tau2",
        "tau",
        "tool",
        "agent",
    ]

    data_datasets = [
        "tabular",
        "csv",
        "sql",
        "data",
        "database",
    ]

    general_datasets = [
        "arenahard",
    ]

    # More specific classes should come first.
    # Example: "arenahard_coding" contains "code"/"coding",
    # and should become coding before "arenahard" becomes general.

    for name in coding_datasets:
        if name in dataset:
            return "coding"

    for name in writing_datasets:
        if name in dataset:
            return "writing"

    for name in medical_datasets:
        if name in dataset:
            return "medical"

    for name in emotion_datasets:
        if name in dataset:
            return "emotion"

    for name in agentic_datasets:
        if name in dataset:
            return "agentic"

    for name in math_datasets:
        if name in dataset:
            return "math"

    for name in reasoning_datasets:
        if name in dataset:
            return "reasoning"

    for name in factual_datasets:
        if name in dataset:
            return "factual"

    for name in knowledge_datasets:
        if name in dataset:
            return "knowledge"

    for name in data_datasets:
        if name in dataset:
            return "data"

    for name in general_datasets:
        if name == dataset:
            return "general"

    return "general"


def main():
    df = pd.read_csv(INPUT_CSV)

    if "dataset" not in df.columns:
        raise ValueError("CSV must contain a 'dataset' column.")

    df["question_type"] = df["dataset"].apply(map_dataset_to_question_type)

    print("Question type counts:")
    print(df["question_type"].value_counts())

    print("\nDataset to question type mapping:")
    dataset_mapping = (
        df[["dataset", "question_type"]]
        .drop_duplicates()
        .sort_values(by=["question_type", "dataset"])
    )

    for _, row in dataset_mapping.iterrows():
        print(f"- {row['dataset']} -> {row['question_type']}")

    general_datasets = (
        df[df["question_type"] == "general"]["dataset"]
        .dropna()
        .unique()
    )

    print("\nDatasets mapped to general:")
    if len(general_datasets) == 0:
        print("None")
    else:
        for dataset in general_datasets:
            print(f"- {dataset}")

    df.to_csv(OUTPUT_CSV, index=False)

    print(f"\nSaved labeled CSV to: {OUTPUT_CSV}")
    print(f"Total rows: {len(df)}")


if __name__ == "__main__":
    main()