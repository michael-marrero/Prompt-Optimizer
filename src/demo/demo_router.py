import os
import sys
import json
import joblib
import pandas as pd

from scipy.sparse import hstack, csr_matrix


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

TASK_CLASSIFIER_PATH = os.path.join(MODELS_DIR, "task_type_classifier.joblib")
MODEL_ROUTER_PATH = os.path.join(MODELS_DIR, "model_router.joblib")
MODEL_MAPPING_PATH = os.path.join(CONFIG_DIR, "model_mapping.json")

if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from Feature_extractor import PromptFeatureExtractor
from src.feature_extraction.text_inputs import build_router_text_input_single


# ------------------------------------------------------------
# Load helpers
# ------------------------------------------------------------

def load_joblib_artifacts(path: str, artifact_name: str):
    """
    Load a saved joblib artifact dictionary.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{artifact_name} not found at:\n{path}\n\n"
            f"Train/save {artifact_name} first."
        )

    artifacts = joblib.load(path)

    required_keys = [
        "model",
        "vectorizer",
        "scaler",
        "label_encoder",
        "feature_columns",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"{artifact_name} is missing required key: {key}")

    return artifacts


def load_json(path: str, name: str):
    """
    Load a JSON config file.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{name} not found at:\n{path}"
        )

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


# ------------------------------------------------------------
# Feature preparation
# ------------------------------------------------------------

def build_numeric_features(
    prompt: str,
    feature_columns: list,
    extractor: PromptFeatureExtractor,
    extra_values: dict | None = None
) -> pd.DataFrame:
    """
    Build numeric feature DataFrame matching the saved model's expected columns.
    """

    extracted_features = extractor.extract(prompt)

    row = {}
    row.update(extracted_features)

    if extra_values:
        row.update(extra_values)

    feature_df = pd.DataFrame([row])

    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0

    feature_df = feature_df[feature_columns].fillna(0)

    return feature_df


# ------------------------------------------------------------
# Stage 1: Task classifier
# ------------------------------------------------------------

def predict_task_type(
    prompt: str,
    task_artifacts: dict,
    extractor: PromptFeatureExtractor
):
    """
    Predict the task/question type for a prompt.
    """

    model = task_artifacts["model"]
    vectorizer = task_artifacts["vectorizer"]
    scaler = task_artifacts["scaler"]
    label_encoder = task_artifacts["label_encoder"]
    feature_columns = task_artifacts["feature_columns"]

    text_series = pd.Series([prompt])
    text_features = vectorizer.transform(text_series)

    numeric_df = build_numeric_features(
        prompt=prompt,
        feature_columns=feature_columns,
        extractor=extractor
    )

    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined_features = hstack([text_features, numeric_sparse])

    prediction_encoded = model.predict(combined_features)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    probabilities = model.predict_proba(combined_features)[0]

    confidence_table = []

    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))

    confidence_table.sort(key=lambda item: item[1], reverse=True)

    confidence = confidence_table[0][1]

    return prediction_label, confidence, confidence_table


# ------------------------------------------------------------
# Stage 2: Exact/top model router
# ------------------------------------------------------------

def predict_best_model(
    prompt: str,
    question_type: str,
    question_type_confidence: float,
    model_router_artifacts: dict,
    extractor: PromptFeatureExtractor
):
    """
    Predict the best model class using the trained model router.
    """

    model = model_router_artifacts["model"]
    vectorizer = model_router_artifacts["vectorizer"]
    scaler = model_router_artifacts["scaler"]
    label_encoder = model_router_artifacts["label_encoder"]
    feature_columns = model_router_artifacts["feature_columns"]

    text_features = vectorizer.transform(
        build_router_text_input_single(
            prompt=prompt,
            question_type=question_type
        )
    )

    numeric_df = build_numeric_features(
        prompt=prompt,
        feature_columns=feature_columns,
        extractor=extractor,
        extra_values={
            "question_type_confidence": question_type_confidence
        }
    )

    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined_features = hstack([text_features, numeric_sparse])

    prediction_encoded = model.predict(combined_features)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    probabilities = model.predict_proba(combined_features)[0]

    confidence_table = []

    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))

    confidence_table.sort(key=lambda item: item[1], reverse=True)

    confidence = confidence_table[0][1]

    return prediction_label, confidence, confidence_table


# ------------------------------------------------------------
# Mapping / final route logic
# ------------------------------------------------------------

def choose_final_route(predicted_model: str, model_mapping: dict):
    """
    Convert the predicted model class into route metadata.

    If the model is unknown or OTHER, use the OTHER mapping.
    """

    if predicted_model in model_mapping:
        model_info = model_mapping[predicted_model].copy()
        model_info["source"] = "model_router"
        return model_info

    if "OTHER" in model_mapping:
        model_info = model_mapping["OTHER"].copy()
        model_info["source"] = "fallback_other"
        model_info["original_prediction"] = predicted_model
        return model_info

    return {
        "display_name": predicted_model,
        "provider": "simulated",
        "tier": "unknown",
        "api_model": None,
        "openrouter_verified": False,
        "source": "unmapped_prediction",
        "notes": "Predicted model was not found in model_mapping.json."
    }


def get_api_model_for_real_call(final_model_info: dict):
    """
    Return the API model if verified.

    For simulated/unverified models, return None.
    """

    if final_model_info.get("openrouter_verified") and final_model_info.get("api_model"):
        return final_model_info["api_model"]

    return None


# ------------------------------------------------------------
# Full route pipeline
# ------------------------------------------------------------

def route_prompt(
    prompt: str,
    task_artifacts: dict,
    model_router_artifacts: dict,
    model_mapping: dict,
    extractor: PromptFeatureExtractor
):
    """
    Full two-stage route:

    prompt
    -> task classifier
    -> model router
    -> mapped route metadata
    """

    question_type, question_type_confidence, task_predictions = predict_task_type(
        prompt=prompt,
        task_artifacts=task_artifacts,
        extractor=extractor
    )

    predicted_model, model_confidence, model_predictions = predict_best_model(
        prompt=prompt,
        question_type=question_type,
        question_type_confidence=question_type_confidence,
        model_router_artifacts=model_router_artifacts,
        extractor=extractor
    )

    final_model_info = choose_final_route(
        predicted_model=predicted_model,
        model_mapping=model_mapping
    )

    api_model_for_real_call = get_api_model_for_real_call(final_model_info)

    return {
        "prompt": prompt,

        "question_type": question_type,
        "question_type_confidence": question_type_confidence,
        "task_predictions": task_predictions,

        "predicted_model": predicted_model,
        "model_confidence": model_confidence,
        "model_predictions": model_predictions,

        "final_model_info": final_model_info,
        "api_model_for_real_call": api_model_for_real_call,
    }


# ------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------

def print_top_predictions(title: str, confidence_table: list, top_n: int = 5):
    """
    Print top prediction probabilities.
    """

    print(f"\n{title}")

    for label, probability in confidence_table[:top_n]:
        print(f"- {label}: {probability:.4f}")


def print_route_result(result: dict):
    """
    Pretty terminal output for one route.
    """

    final_model = result["final_model_info"]

    print("\n" + "=" * 70)
    print("PROMPT ROUTING RESULT")
    print("=" * 70)

    print("\nPrompt:")
    print(result["prompt"])

    print("\nStage 1: Task Classifier")
    print(f"Predicted question type: {result['question_type']}")
    print(f"Confidence: {result['question_type_confidence']:.4f}")

    print("\nStage 2: Model Router")
    print(f"Predicted model class: {result['predicted_model']}")
    print(f"Confidence: {result['model_confidence']:.4f}")

    print("\nFinal Simulated Route")
    print(f"Display name: {final_model.get('display_name')}")
    print(f"Provider: {final_model.get('provider')}")
    print(f"Tier: {final_model.get('tier')}")
    print(f"API model: {final_model.get('api_model')}")
    print(f"OpenRouter verified: {final_model.get('openrouter_verified')}")
    print(f"Route source: {final_model.get('source')}")

    api_model = result["api_model_for_real_call"]

    if api_model:
        print(f"Real API model available: {api_model}")
    else:
        print("Real API model available: None, simulated/unverified route")

    original_prediction = final_model.get("original_prediction")
    if original_prediction:
        print(f"Original unmapped prediction: {original_prediction}")

    notes = final_model.get("notes")
    if notes:
        print(f"Notes: {notes}")

    print_top_predictions(
        title="Top task type predictions:",
        confidence_table=result["task_predictions"]
    )

    print_top_predictions(
        title="Top model predictions:",
        confidence_table=result["model_predictions"]
    )

    print("\n" + "=" * 70)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    print("\nPrompt Optimizer Demo Router")
    print("----------------------------")
    print("Pipeline: task classifier -> model router")
    print("Loading saved models and route mappings...")

    task_artifacts = load_joblib_artifacts(
        TASK_CLASSIFIER_PATH,
        "task_type_classifier.joblib"
    )

    model_router_artifacts = load_joblib_artifacts(
        MODEL_ROUTER_PATH,
        "model_router.joblib"
    )

    model_mapping = load_json(
        MODEL_MAPPING_PATH,
        "model_mapping.json"
    )

    extractor = PromptFeatureExtractor()

    print("\nLoaded successfully.")
    print("Type a prompt to route.")
    print("Type 'quit' to stop.")

    while True:
        prompt = input("\nPrompt: ").strip()

        if prompt.lower() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        if not prompt:
            print("Please enter a prompt.")
            continue

        try:
            result = route_prompt(
                prompt=prompt,
                task_artifacts=task_artifacts,
                model_router_artifacts=model_router_artifacts,
                model_mapping=model_mapping,
                extractor=extractor
            )

            print_route_result(result)

        except Exception as error:
            print("\nRouting failed.")
            print(f"Error: {error}")


if __name__ == "__main__":
    main()