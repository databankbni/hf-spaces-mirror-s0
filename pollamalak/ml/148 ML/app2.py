# app.py — Heart Disease Prediction API
# Handles all preprocessing so Node/Flutter can send raw values
from flask import Flask, request, jsonify
import joblib
import pandas as pd

app = Flask(__name__)
pipeline = joblib.load("new_pipeline.pkl")

# ── Constants matching training data exactly ──────────────────────────────────

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

VALID_RACES = {
    "white", "black", "asian",
    "hispanic", "american indian/alaskan native", "other"
}

REQUIRED_FIELDS = [
    'BMI', 'Smoking', 'AlcoholDrinking', 'Stroke', 'PhysicalHealth',
    'MentalHealth', 'DiffWalking', 'Sex', 'AgeCategory', 'Race',
    'Diabetic', 'PhysicalActivity', 'GenHealth', 'SleepTime',
    'Asthma', 'KidneyDisease', 'SkinCancer'
]

# sample = {
#   "BMI": 65,
#   "Smoking": "Yes",
#   "AlcoholDrinking": "Yes",
#   "Stroke": "Yes",
#   "PhysicalHealth": 30,
#   "MentalHealth": 30,
#   "DiffWalking": "Yes",
#   "Sex": "Male",
#   "AgeCategory": "80 or older",
#   "Race": "White",
#   "Diabetic": "Yes",
#   "PhysicalActivity": "No",
#   "GenHealth": "Poor",
#   "SleepTime": 2,
#   "Asthma": "Yes",
#   "KidneyDisease": "Yes",
#   "SkinCancer": "Yes",
#   "Age": 82,
#   "HighRisk": 1
# }

# df = pd.DataFrame([sample])
# print(pipeline.predict_proba(df))
# ── Preprocessing ─────────────────────────────────────────────────────────────

def preprocess(data: dict) -> pd.DataFrame:
    df = pd.DataFrame([data])

    # Step 1: Convert Yes/No strings → 0/1 integers for binary columns
    # Model's OrdinalEncoder was trained on 0.0/1.0 — strings cause unknown=-1
    for col in BINARY_COLS:
        val = str(df[col].iloc[0]).strip().lower()
        df[col] = 1 if val == "yes" else 0

    # Step 2: Encode Diabetic as ordinal float (4 categories in training data)
    diabetic_val = str(df["Diabetic"].iloc[0]).strip().lower()
    df["Diabetic"] = DIABETIC_MAP.get(diabetic_val, 0)

    # Step 3: Derive numeric Age from AgeCategory (required model feature)
    df["Age"] = AGE_MAP.get(str(df["AgeCategory"].iloc[0]).strip(), 21)

    # Step 4: Compute HighRisk engineered feature (AND logic — matches training)
    df["HighRisk"] = int(
        df["Diabetic"].iloc[0] == 1 and
        df["Stroke"].iloc[0] == 1 and
        df["KidneyDisease"].iloc[0] == 1
    )

    # Step 5: Normalise Race to valid training category
    race_val = str(df["Race"].iloc[0]).strip().lower()
    if race_val not in VALID_RACES:
        df["Race"] = "Other"

    # Step 6: Cast numeric fields to correct types
    df["BMI"]           = float(df["BMI"].iloc[0])
    df["PhysicalHealth"]= int(df["PhysicalHealth"].iloc[0])
    df["MentalHealth"]  = int(df["MentalHealth"].iloc[0])
    df["SleepTime"]     = int(df["SleepTime"].iloc[0])

    return df

# ── Route ─────────────────────────────────────────────────────────────────────

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json(force=True)
        app.logger.info("RAW INPUT: %s", data)

        # Validate required fields
        missing = [f for f in REQUIRED_FIELDS if f not in data]
        if missing:
            return jsonify({"error": f"Missing fields: {missing}"}), 400

        df = preprocess(data)
        print(pipeline.predict(df))
        app.logger.info("PREPROCESSED: %s", df.to_dict(orient="records"))

        probability = float(pipeline.predict_proba(df)[0][1])
        prediction  = 'At Risk' if probability >= 0.30 else 'Not at Risk'
        risk_level  = "High" if probability > 0.7 else "Medium" if probability > 0.4 else "Low"

        result = {
            "prediction":  prediction,           # 0 = not at risk, 1 = at risk
            "probability": round(probability, 4),
            "risk_level":  risk_level,
            # "at_risk":     prediction == 1
        }
        app.logger.info("RESULT: %s", result)
        return jsonify(result)

    except Exception as e:
        app.logger.exception("Prediction failed")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)  # port matches Node controller
