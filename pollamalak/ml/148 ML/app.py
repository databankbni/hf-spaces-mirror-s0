from flask import Flask, request, jsonify
import joblib
import pandas as pd

app = Flask(__name__)

pipeline = joblib.load("heart_disease_pipeline_hgb.pkl")

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.json

        df = pd.DataFrame([data])

        age_map = {
            "18-24":21,"25-29":27,"30-34":32,"35-39":37,
            "40-44":42,"45-49":47,"50-54":52,"55-59":57,
            "60-64":62,"65-69":67,"70-74":72,"75-79":77,
            "80 or older":82
        }

        df["Age"] = df["AgeCategory"].map(age_map)

        df["HighRisk"] = (
            (df["Smoking"] == "Yes") |
            (df["Stroke"] == "Yes") |
            (df["Diabetic"] == "Yes")
        ).astype(int)

        prediction = pipeline.predict(df)[0]

        prediction_label = "At Risk" if prediction == 1 else "Not at Risk"
        probability = pipeline.predict_proba(df)[0][1]

        risk_level = "High" if probability > 0.7 else "Medium" if probability > 0.4 else "Low"

        return jsonify({
            "prediction": prediction_label,
            "probability": float(probability),
            "risk_level": risk_level
        })

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5001, debug=True)