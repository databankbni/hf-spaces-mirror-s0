from flask import Flask, request, jsonify
import joblib
import pandas as pd

app = Flask(__name__)

# Loading the serialized model pipeline (preprocessing + tuned XGBoost model)
model = joblib.load("model.joblib")


@app.route("/", methods=["GET"])
def home():
    return "SuperKart Sales Forecasting API is up and running."


@app.route("/predict", methods=["POST"])
def predict():
    """
    Expects a JSON body with the raw feature values, e.g.:
    {
        "Product_Weight": 12.66,
        "Product_Sugar_Content": "Low Sugar",
        "Product_Allocated_Area": 0.027,
        "Product_Type": "Frozen Foods",
        "Product_MRP": 117.08,
        "Store_Size": "Medium",
        "Store_Location_City_Type": "Tier 2",
        "Store_Type": "Supermarket Type2",
        "Product_Category": "Food",
        "Store_Age_Years": 18
    }
    """
    try:
        payload = request.get_json(force=True)

        # Supporting both a single record (dict) and a batch of records (list of dicts)
        if isinstance(payload, dict):
            input_df = pd.DataFrame([payload])
        else:
            input_df = pd.DataFrame(payload)

        predictions = model.predict(input_df)

        return jsonify({"predicted_sales": predictions.tolist()})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    # Hugging Face Docker Spaces route external traffic to port 7860 by default
    app.run(host="0.0.0.0", port=7860)
