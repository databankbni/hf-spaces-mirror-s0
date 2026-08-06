
import numpy as np  # Numerical support
import joblib  # Load saved model
import pandas as pd  # Data handling
from flask import Flask, request, jsonify  # Flask API tools
from datetime import datetime

superkart_api = Flask("SuperKart Sales Predictor")  # Keep original Flask app name

model = joblib.load("superkart_sales_prediction_model_v1_0.joblib")  # Keep original model filename

CURRENT_YEAR = datetime.now().year

MODEL_COLUMNS = [  # Columns expected by trained model
    "Product_Weight",
    "Product_Sugar_Content",
    "Product_Allocated_Area",
    "Product_MRP",
    "Store_Size",
    "Store_Location_City_Type",
    "Store_Type",
    "Product_Family",
    "Store_Age_Years",
    "Product_Type_Category"
]

PRODUCT_FAMILY_MAP = {  # Product_Id prefix mapping
    "FD": "Food",
    "DR": "Drinks",
    "NC": "Non-Consumable"
}

PERISHABLE_TYPES = [  # Product_Type values mapped as perishables
    "Dairy",
    "Meat",
    "Fruits and Vegetables",
    "Breakfast",
    "Breads",
    "Seafood"
]


def prepare_model_input(input_data):  # Handles original or engineered CSV
    input_data = input_data.copy()  # Avoid modifying original data

    if "Product_Id" in input_data.columns and "Product_Family" not in input_data.columns:
        input_data["Product_Family"] = input_data["Product_Id"].astype(str).str[:2].map(PRODUCT_FAMILY_MAP)  # Create family

    if "Store_Establishment_Year" in input_data.columns and "Store_Age_Years" not in input_data.columns:
        input_data["Store_Age_Years"] = CURRENT_YEAR - pd.to_numeric(input_data["Store_Establishment_Year"], errors="coerce")  # Create age

    if "Product_Type" in input_data.columns and "Product_Type_Category" not in input_data.columns:
        input_data["Product_Type_Category"] = input_data["Product_Type"].apply(
            lambda x: "Perishables" if x in PERISHABLE_TYPES else "Non Perishables"
        )  # Create type category

    missing_cols = [col for col in MODEL_COLUMNS if col not in input_data.columns]  # Check missing columns
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")  # Return clear error

    input_data = input_data[MODEL_COLUMNS]  # Keep only model columns

    return input_data  # Return model-ready data


@superkart_api.get("/")  # Home route
def home():
    return "Welcome to the SuperKart Sales Prediction API!"  # Simple status message


@superkart_api.post("/v1/predict")  # Single prediction route
def predict_sales():
    try:
        data = request.get_json()  # Get JSON request

        input_data = pd.DataFrame([data])  # Convert JSON to DataFrame
        input_data = prepare_model_input(input_data)  # Validate/prepare input

        prediction = model.predict(input_data).tolist()[0]  # Make prediction

        return jsonify({"Predicted_Sales": round(float(prediction), 2)})  # Return result

    except Exception as e:
        return jsonify({"error": str(e)}), 500  # Return readable error


@superkart_api.post("/v1/predictbatch")  # Batch prediction route
def predict_sales_batch():
    try:
        file = request.files["file"]  # Get uploaded CSV

        original_data = pd.read_csv(file)  # Read uploaded data
        model_data = prepare_model_input(original_data)  # Handle old or new format

        predictions = model.predict(model_data).tolist()  # Predict all rows

        result_data = original_data.copy()  # Keep uploaded columns
        result_data["Predicted_Sales"] = [round(float(p), 2) for p in predictions]  # Add predictions

        result = result_data.to_dict(orient="records")  # Convert to JSON format
        return jsonify(result)  # Return batch results

    except Exception as e:
        return jsonify({"error": str(e)}), 500  # Return readable error


if __name__ == "__main__":  # Local run only
    superkart_api.run(debug=True)  # Keep original debug run
