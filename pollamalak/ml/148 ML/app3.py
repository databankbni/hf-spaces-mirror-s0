from flask import Flask, request, jsonify
import joblib
import pandas as pd

app = Flask(__name__)

# تحميل الموديل + ال encoders + الأعمدة
pipeline = joblib.load("new_pipeline.pkl")
encoders = joblib.load("new_label_encoders.pkl")
columns = joblib.load("new_model_columns.pkl")

# ── Preprocessing (متوافق مع training) ─────────────────────────────

def preprocess(data):
    df = pd.DataFrame([data])

    # Apply same LabelEncoders used in training
    for col, le in encoders.items():
        if col in df:
            try:
                df[col] = le.transform(df[col])
            except:
                return None, f"Invalid value for {col}: {df[col].iloc[0]}"

    # Ensure same column order
    df = df[columns]

    return df, None

# ── Routes ─────────────────────────────────────────────────────────

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json(force=True)
        app.logger.info(f"RAW INPUT: {data}")

        df, error = preprocess(data)

        if error:
            return jsonify({"error": error}), 400

        # Prediction
        probability = float(pipeline.predict_proba(df)[0][1])
        prediction = 1 if probability >= 0.5 else 0

        # Risk Levels
        if probability > 0.7:
            risk_level = "High"
        elif probability > 0.4:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        result = {
            "prediction": "At Risk" if prediction == 1 else "Not at Risk",
            "probability": round(probability, 4),
            "risk_level": risk_level
        }

        app.logger.info(f"RESULT: {result}")
        return jsonify(result)

    except Exception as e:
        app.logger.exception("Prediction failed")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)