from flask import Flask, request, jsonify
import joblib
import pandas as pd

app = Flask(__name__)

pipeline = joblib.load("heart_disease_pipeline_hgb.pkl")

# Binary columns the model was trained on with 0/1 integers
BINARY_COLS = [
    'Smoking', 'AlcoholDrinking', 'Stroke', 'DiffWalking',
    'PhysicalActivity', 'Asthma', 'KidneyDisease', 'SkinCancer'
]

# AgeCategory → numeric Age
AGE_MAP = {
    "18-24": 21, "25-29": 27, "30-34": 32, "35-39": 37,
    "40-44": 42, "45-49": 47, "50-54": 52, "55-59": 57,
    "60-64": 62, "65-69": 67, "70-74": 72, "75-79": 77,
    "80 or older": 82
}

# Diabetic ordinal encoding (matches training data exactly)
DIABETIC_MAP = {
    "yes": 1,
    "no": 0,
    "no, borderline diabetes": 0.131,
    "yes (during pregnancy)": 0.131,
}


@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.json
        print("RAW INPUT:", data)

        df = pd.DataFrame([data])

        # FIX 1: Convert Yes/No strings → 0/1 integers
        # (OrdinalEncoder was trained on 0.0/1.0 — strings cause unknown=-1)
        for col in BINARY_COLS:
            val = df[col].iloc[0]
            df[col] = 1 if str(val).strip().lower() == "yes" else 0

        # FIX 2: Encode Diabetic as ordinal float
        diabetic_val = str(df["Diabetic"].iloc[0]).strip().lower()
        df["Diabetic"] = DIABETIC_MAP.get(diabetic_val, 0)

        # FIX 3: Derive numeric Age from AgeCategory
        df["Age"] = AGE_MAP.get(df["AgeCategory"].iloc[0], 21)

        # FIX 4: Compute HighRisk using AND logic (matches training exactly)
        # Training: Diabetic==Yes AND Stroke==Yes AND KidneyDisease==Yes
        df["HighRisk"] = int(
            df["Diabetic"].iloc[0] == 1 and
            df["Stroke"].iloc[0] == 1 and
            df["KidneyDisease"].iloc[0] == 1
        )

        print("PREPROCESSED:", df.to_dict(orient="records"))

        probability = float(pipeline.predict_proba(df)[0][1])
        prediction = 1 if probability >= 0.30 else 0

        risk_level = "High" if probability > 0.7 else "Medium" if probability > 0.4 else "Low"

        result = {
            "prediction": prediction,          # 0 or 1
            "probability": round(probability, 4),
            "risk_level": risk_level,
            "at_risk": prediction == 1
        }
        print("RESULT:", result)
        return jsonify(result)

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5001, debug=True)   # FIX 5: port 5000 matches healthDataController.js
