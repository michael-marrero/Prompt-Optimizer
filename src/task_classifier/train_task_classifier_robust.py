import os
import sys
import pandas as pd

from scipy.sparse import hstack, csr_matrix

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder, StandardScaler


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src/feature_extraction")
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")

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
# Optional rule layer
# ------------------------------------------------------------

def rule_based_question_type(text: str):
    """
    High-confidence rule-based classifier.

    Returns a label if the rule is obvious.
    Returns None if the ML model should decide.
    """

    text = str(text).lower().strip()

    coding_words = [
        "python", "java", "c++", "javascript", "typescript", "html", "css",
        "function", "loop", "class", "method", "array", "list", "dict",
        "dictionary", "debug", "error", "traceback", "code", "program",
        "script", "compile", "runtime", "api", "terminal"
    ]

    math_words = [
        "solve", "equation", "derivative", "integral", "probability",
        "calculate", "simplify", "factor", "limit", "mean",
        "standard deviation", "variance", "matrix", "graph", "algebra"
    ]

    medical_words = [
        "symptom", "symptoms", "diagnosis", "infection", "virus",
        "bacterial", "blood pressure", "dehydration", "medicine",
        "medical", "doctor", "disease", "treatment"
    ]

    emotion_words = [
        "emotion", "sentiment", "feeling", "feel", "happy", "sad",
        "angry", "nervous", "excited", "scared", "upset", "afraid"
    ]

    writing_words = [
        "rewrite", "essay", "paragraph", "email", "speech",
        "presentation", "summarize", "summary", "thesis", "conclusion",
        "introduction", "draft", "make this sound"
    ]

    agentic_words = [
        "book", "schedule", "calendar", "flight", "reserve",
        "meeting", "appointment", "check my email", "send an email"
    ]

    reasoning_words = [
        "compare", "contrast", "why", "explain why", "analyze",
        "evaluate", "pros and cons", "advantages", "disadvantages",
        "tradeoff", "tradeoffs", "which is better", "should i",
        "argue", "justify", "infer", "conclude"
    ]

    # Specific categories first
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

    if any(word in text for word in reasoning_words):
        return "reasoning"

    return None


# ------------------------------------------------------------
# Training
# ------------------------------------------------------------

def train_task_type_classifier(df: pd.DataFrame):
    """
    Train a robust task type classifier using:
    - TF-IDF features from origin_query
    - handcrafted numeric features from the feature extractor output
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

    # TF-IDF handles the actual words in the question
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        max_features=20000
    )

    X_train_tfidf = vectorizer.fit_transform(X_text_train)
    X_test_tfidf = vectorizer.transform(X_text_test)

    # Scale numeric handcrafted features
    scaler = StandardScaler()
    X_train_num_scaled = scaler.fit_transform(X_num_train)
    X_test_num_scaled = scaler.transform(X_num_test)

    X_train_num_sparse = csr_matrix(X_train_num_scaled)
    X_test_num_sparse = csr_matrix(X_test_num_scaled)

    # Combine TF-IDF + handcrafted features
    X_train_combined = hstack([X_train_tfidf, X_train_num_sparse])
    X_test_combined = hstack([X_test_tfidf, X_test_num_sparse])

    model = LogisticRegression(
        max_iter=3000,
        class_weight="balanced",
        solver="saga",
        n_jobs=-1
    )

    model.fit(X_train_combined, y_train)

    y_pred = model.predict(X_test_combined)

    print("\nRobust Task Type Classifier Results")
    print("-----------------------------------")
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
    text: str,
    use_rules: bool = True
):
    """
    Predict question type for one user input.
    """

    if use_rules:
        rule_prediction = rule_based_question_type(text)

        if rule_prediction is not None:
            confidence_table = [(rule_prediction, 1.0)]
            return rule_prediction, confidence_table, "rule"

    # Text features
    text_series = pd.Series([text])
    text_features = vectorizer.transform(text_series)

    # Handcrafted features
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

    return prediction_label, confidence_table, "model"


# ------------------------------------------------------------
# Main test loop
# ------------------------------------------------------------

def main():
    df = pd.read_csv(INPUT_CSV)

    model, vectorizer, scaler, label_encoder, feature_columns = train_task_type_classifier(df)

    extractor = PromptFeatureExtractor()

    print("\nType a question to test the robust classifier.")
    print("Type 'quit' to stop.")
    print("Type 'rules off' to disable rule override.")
    print("Type 'rules on' to enable rule override.")

    use_rules = True

    while True:
        user_text = input("\nQuestion: ").strip()

        if user_text.lower() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        if user_text.lower() == "rules off":
            use_rules = False
            print("Rule layer disabled.")
            continue

        if user_text.lower() == "rules on":
            use_rules = True
            print("Rule layer enabled.")
            continue

        predicted_type, confidence_table, source = predict_user_input(
            model=model,
            vectorizer=vectorizer,
            scaler=scaler,
            label_encoder=label_encoder,
            feature_columns=feature_columns,
            extractor=extractor,
            text=user_text,
            use_rules=use_rules
        )

        print(f"\nPredicted question type: {predicted_type}")
        print(f"Prediction source: {source}")

        print("\nTop predictions:")
        for label, probability in confidence_table[:5]:
            print(f"- {label}: {probability:.4f}")


if __name__ == "__main__":
    main()