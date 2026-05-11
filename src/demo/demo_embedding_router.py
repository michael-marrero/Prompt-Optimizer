import os
import sys
import joblib
import numpy as np
import pandas as pd

from sentence_transformers import SentenceTransformer


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")

EMBEDDING_ROUTER_MODEL_PATH = os.path.join(
    MODELS_DIR,
    "embedding_router.joblib"
)


# ------------------------------------------------------------
# Load saved embedding router
# ------------------------------------------------------------

def load_embedding_router_artifacts(model_path=EMBEDDING_ROUTER_MODEL_PATH):
    """
    Load the saved embedding router artifacts.
    """

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No saved embedding router found at:\n{model_path}\n\n"
            "Run src/model_router/train_embedding_router.py first."
        )

    artifacts = joblib.load(model_path)

    required_keys = [
        "model",
        "scaler",
        "label_encoder",
        "target_column",
        "embedding_model_name",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"Saved embedding router artifact is missing key: {key}")

    print("\nLoaded embedding router from:")
    print(model_path)

    return artifacts


# ------------------------------------------------------------
# Prediction
# ------------------------------------------------------------

def predict_prompt(prompt: str, artifacts: dict, embedding_model: SentenceTransformer):
    """
    Predict best model class for one prompt.
    """

    model = artifacts["model"]
    scaler = artifacts.get("scaler")
    label_encoder = artifacts["label_encoder"]

    embedding = embedding_model.encode(
        [prompt],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    features = scaler.transform(embedding) if scaler is not None else embedding

    prediction_encoded = model.predict(features)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(features)[0]
    else:
        decision_scores = model.decision_function(features)
        if decision_scores.ndim == 1:
            probabilities = np.array([-decision_scores[0], decision_scores[0]])
        else:
            probabilities = decision_scores[0]

    confidence_table = []

    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))

    confidence_table.sort(key=lambda item: item[1], reverse=True)

    confidence = confidence_table[0][1]

    return prediction_label, confidence, confidence_table


# ------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------

def print_top_predictions(confidence_table, top_n=5):
    """
    Print top model predictions.
    """

    print("\nTop predictions:")

    for label, probability in confidence_table[:top_n]:
        print(f"- {label}: {probability:.4f}")


def print_result(prompt: str, predicted_model: str, confidence: float, confidence_table):
    """
    Print one routing result.
    """

    print("\n" + "=" * 70)
    print("EMBEDDING ROUTER RESULT")
    print("=" * 70)

    print("\nPrompt:")
    print(prompt)

    print("\nPrediction")
    print(f"Predicted model class: {predicted_model}")
    print(f"Confidence: {confidence:.4f}")
    print("Prediction source: embedding router")

    print_top_predictions(confidence_table)

    print("\n" + "=" * 70)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    print("\nEmbedding Router Demo")
    print("---------------------")
    print("This demo uses only semantic embeddings from origin_query.")
    print("It does not use the task classifier, handcrafted features, or TF-IDF.")

    artifacts = load_embedding_router_artifacts()

    embedding_model_name = artifacts["embedding_model_name"]

    print("\nLoading sentence embedding model:")
    print(embedding_model_name)

    embedding_model = SentenceTransformer(embedding_model_name)

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
            predicted_model, confidence, confidence_table = predict_prompt(
                prompt=prompt,
                artifacts=artifacts,
                embedding_model=embedding_model
            )

            print_result(
                prompt=prompt,
                predicted_model=predicted_model,
                confidence=confidence,
                confidence_table=confidence_table
            )

        except Exception as error:
            print("\nEmbedding router failed.")
            print(f"Error: {error}")


if __name__ == "__main__":
    main()