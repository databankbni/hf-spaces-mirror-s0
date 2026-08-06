# app.py — Heart Disease Prediction API (with calibrated probabilities)
from flask import Flask, request, jsonify
import joblib
import pandas as pd

app = Flask(__name__)

# Use calibrated model for realistic probability spread (not capped at ~60%)
# To generate: run retrain_calibration.py once after deployment
import os
MODEL_PATH = "heart_disease_pipeline_calibrated.pkl"
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = "heart_disease_pipeline_hgb.pkl"   # fallback
    app.logger.warning("Calibrated model not found, using base model")

pipeline = joblib.load(MODEL_PATH)
app.logger.info(f"Loaded model: {MODEL_PATH}")

BINARY_COLS = [
    'Smoking', 'AlcoholDrinking', 'Stroke', 'DiffWalking',
    'PhysicalActivity', 'Asthma', 'KidneyDisease', 'SkinCancer'
]

AGE_MAP = {
    "18-24": 21, "25-29": 27, "30-34": 32, "35-39": 37,
    "40-44": 42, "45-49": 47, "50-54": 52, "55-59": 57,
    "60-64": 62, "65-69": 67, "70-74": 72, "75-79": 77,
    "80 or older": 82
}

DIABETIC_MAP = {
    "yes": 1,
    "no": 0,
    "no, borderline diabetes": 0.131,
    "yes (during pregnancy)": 0.131,
}

VALID_RACES = {"white","black","asian","hispanic","american indian/alaskan native","other"}

REQUIRED_FIELDS = [
    'BMI','Smoking','AlcoholDrinking','Stroke','PhysicalHealth','MentalHealth',
    'DiffWalking','Sex','AgeCategory','Race','Diabetic','PhysicalActivity',
    'GenHealth','SleepTime','Asthma','KidneyDisease','SkinCancer'
]


def preprocess(data: dict) -> pd.DataFrame:
    df = pd.DataFrame([data])

    # 1. Convert Yes/No → 0/1
    for col in BINARY_COLS:
        df[col] = 1 if str(df[col].iloc[0]).strip().lower() == "yes" else 0

    # 2. Encode Diabetic as ordinal float
    df["Diabetic"] = DIABETIC_MAP.get(str(df["Diabetic"].iloc[0]).strip().lower(), 0)

    # 3. Derive numeric Age
    df["Age"] = AGE_MAP.get(str(df["AgeCategory"].iloc[0]).strip(), 21)

    # 4. Compute HighRisk (AND logic — matches training exactly)
    df["HighRisk"] = int(
        df["Diabetic"].iloc[0] == 1 and
        df["Stroke"].iloc[0] == 1 and
        df["KidneyDisease"].iloc[0] == 1
    )

    # 5. Normalise Race
    if str(df["Race"].iloc[0]).strip().lower() not in VALID_RACES:
        df["Race"] = "Other"

    # 6. Cast numeric types
    df["BMI"]            = float(df["BMI"].iloc[0])
    df["PhysicalHealth"] = int(df["PhysicalHealth"].iloc[0])
    df["MentalHealth"]   = int(df["MentalHealth"].iloc[0])
    df["SleepTime"]      = int(df["SleepTime"].iloc[0])

    return df


@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json(force=True)
        app.logger.info("RAW INPUT: %s", data)

        missing = [f for f in REQUIRED_FIELDS if f not in data]
        if missing:
            return jsonify({"error": f"Missing fields: {missing}"}), 400

        df = preprocess(data)
        app.logger.info("PREPROCESSED: %s", df.to_dict(orient="records"))

        probability = float(pipeline.predict_proba(df)[0][1])
        # Clamp to [0, 1] — isotonic calibration can occasionally produce tiny overflows
        probability = max(0.0, min(1.0, probability))

        prediction = "At Risk" if probability >= 0.30 else "Not at Risk"
        risk_level = "High" if probability > 0.7 else "Medium" if probability > 0.4 else "Low"

        result = {
            "prediction":  prediction,
            "probability": round(probability, 4),
            "risk_level":  risk_level,
            "at_risk":     prediction == 1
        }
        app.logger.info("RESULT: %s", result)
        return jsonify(result)

    except Exception as e:
        app.logger.exception("Prediction failed")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MODEL_PATH})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
