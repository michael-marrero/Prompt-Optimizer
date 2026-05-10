import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder
import sys
sys.path.append("../feature_extraction")
from Feature_extractor import PromptFeatureExtractor


INPUT_CSV = "../../data_processed/classifier_training_with_types.csv"

def rule_based_question_type(text: str):
    text = text.lower()

    coding_words = [
        "python", "java", "c++", "javascript", "function", "loop",
        "class", "method", "array", "list", "debug", "error",
        "traceback", "code", "program", "script"
    ]

    math_words = [
        "solve", "equation", "derivative", "integral", "probability",
        "calculate", "simplify", "factor", "limit", "mean",
        "standard deviation"
    ]

    medical_words = [
        "symptom", "symptoms", "diagnosis", "infection", "virus",
        "bacterial", "blood pressure", "dehydration", "medicine",
        "medical", "doctor"
    ]

    emotion_words = [
        "emotion", "sentiment", "feeling", "feel", "happy", "sad",
        "angry", "nervous", "excited", "scared"
    ]

    writing_words = [
        "rewrite", "essay", "paragraph", "email", "speech",
        "presentation", "summarize", "summary", "thesis", "conclusion"
    ]

    agentic_words = [
        "book", "schedule", "calendar", "email", "flight", "find me",
        "reserve", "meeting", "appointment"
    ]

    if any(word in text for word in coding_words):
        return "coding"

    if any(word in text for word in math_words) or "=" in text:
        return "math"

    if any(word in text for word in medical_words):
        return "medical"

    if any(word in text for word in emotion_words):
        return "emotion"

    if any(word in text for word in writing_words):
        return "writing"

    if any(word in text for word in agentic_words):
        return "agentic"

    return None


def get_feature_columns(df: pd.DataFrame) -> list:
    """
    Return only the feature columns.

    We remove columns that are labels, metadata, or result-side benchmark info.
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


def train_task_type_classifier(df: pd.DataFrame):
    """
    Train a classifier to predict broad question type.
    """

    if "question_type" not in df.columns:
        raise ValueError("CSV must contain a 'question_type' column.")

    feature_columns = get_feature_columns(df)

    X = df[feature_columns]
    y = df["question_type"]

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y_encoded,
        test_size=0.2,
        random_state=42,
        stratify=y_encoded
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

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
            target_names=label_encoder.classes_
        )
    )

    return model, label_encoder, feature_columns


def predict_user_input(
    model,
    label_encoder,
    feature_columns: list,
    extractor: PromptFeatureExtractor,
    text: str
):
    """
    Extract features from one user question and predict its question type.
    """

    features = extractor.extract(text)
    feature_df = pd.DataFrame([features])

    # Make sure the user-input feature dataframe has the same columns as training.
    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0

    feature_df = feature_df[feature_columns]
    rule_prediction = rule_based_question_type(text)

    if rule_prediction is not None:
        return rule_prediction, [(rule_prediction, 1.0)]

    prediction_encoded = model.predict(feature_df)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    probabilities = model.predict_proba(feature_df)[0]

    confidence_table = []

    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))

    confidence_table.sort(key=lambda x: x[1], reverse=True)

    return prediction_label, confidence_table


def main():
    df = pd.read_csv(INPUT_CSV)

    model, label_encoder, feature_columns = train_task_type_classifier(df)

    extractor = PromptFeatureExtractor()

    print("\nType a question to test the classifier.")
    print("Type 'quit' to stop.")

    while True:
        user_text = input("\nQuestion: ")

        if user_text.lower().strip() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        predicted_type, confidence_table = predict_user_input(
            model=model,
            label_encoder=label_encoder,
            feature_columns=feature_columns,
            extractor=extractor,
            text=user_text
        )

        print(f"\nPredicted question type: {predicted_type}")

        print("\nTop predictions:")
        for label, probability in confidence_table[:5]:
            print(f"- {label}: {probability:.4f}")


if __name__ == "__main__":
    main()