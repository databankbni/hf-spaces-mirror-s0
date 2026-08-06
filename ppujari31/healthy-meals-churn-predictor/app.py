

import pandas as pd
import numpy as np
import joblib
import gradio as gr



import joblib

model = joblib.load("churn_model.pkl")



def predict_churn(
    age,
    tech_score,
    total_sessions,
    total_session_length,
    active_days,
    active_quarters,
    avg_sessions_per_quarter,
    education,
    income_level,
    device_type
):

    # -----------------------------------------
    # Initialize all dummy variables to zero
    # -----------------------------------------

    education_high_school = 0
    education_other = 0
    education_post_grad = 0

    income_low = 0
    income_medium = 0
    income_very_high = 0

    device_mobile = 0
    device_multi = 0

    # -----------------------------------------
    # Education Encoding
    # Baseline = Graduate
    # -----------------------------------------

    if education == "High School":
        education_high_school = 1

    elif education == "Other":
        education_other = 1

    elif education == "Post-Graduate":
        education_post_grad = 1

    # -----------------------------------------
    # Income Encoding
    # Baseline = High
    # -----------------------------------------

    if income_level == "Low":
        income_low = 1

    elif income_level == "Medium":
        income_medium = 1

    elif income_level == "Very High":
        income_very_high = 1

    # -----------------------------------------
    # Device Encoding
    # Baseline = Desktop
    # -----------------------------------------

    if device_type == "Mobile-only":
        device_mobile = 1

    elif device_type == "Multi-device":
        device_multi = 1

    # -----------------------------------------
    # Create DataFrame
    # -----------------------------------------

    customer = pd.DataFrame({

        "AGE":[age],

        "TECH_COMFORT_SCORE":[tech_score],

        "TOTAL_NUM_SESSIONS":[total_sessions],

        "GROSS_TOTAL_SESSION_LENGTH":[total_session_length],

        "ACTIVE_DAYS":[active_days],

        "ACTIVE_QUARTERS":[active_quarters],

        "AVG_SESSIONS_PER_ACTIVE_QUARTER":[avg_sessions_per_quarter],

        "EDUCATION_High School":[education_high_school],

        "EDUCATION_Other":[education_other],

        "EDUCATION_Post-Graduate":[education_post_grad],

        "INCOME_LEVEL_Low":[income_low],

        "INCOME_LEVEL_Medium":[income_medium],

        "INCOME_LEVEL_Very High":[income_very_high],

        "DEVICE_TYPE_Mobile-only":[device_mobile],

        "DEVICE_TYPE_Multi-device":[device_multi]

    })

    probability = model.predict_proba(customer)[0][1]

    prediction = model.predict(customer)[0]

    if prediction == 1:
        status = "Likely to Renew"
    else:
        status = "Likely to Churn"

    return f"{status}\n\nChurn Probability: {probability:.2%}"



app = gr.Interface(

    fn=predict_churn,

    inputs=[

        gr.Number(label="Age", value=40),

        gr.Number(label="Technology Comfort Score", value=7),

        gr.Number(label="Total Number of Sessions", value=120),

        gr.Number(label="Gross Total Session Length", value=1800),

        gr.Number(label="Active Days", value=90),

        gr.Number(label="Active Quarters", value=4),

        gr.Number(label="Average Sessions per Active Quarter", value=30),

        gr.Dropdown(

            choices=[

                "Graduate",
                "High School",
                "Other",
                "Post-Graduate"

            ],

            value="Graduate",

            label="Education"

        ),

        gr.Dropdown(

            choices=[

                "High",
                "Medium",
                "Low",
                "Very High"

            ],

            value="High",

            label="Income Level"

        ),

        gr.Dropdown(

            choices=[

                "Desktop",
                "Mobile-only",
                "Multi-device"

            ],

            value="Desktop",

            label="Device Type"

        )

    ],

    outputs=gr.Textbox(label="Prediction"),

    title="Healthy Meals Churn Prediction",

    description="""
Enter customer information to estimate the likelihood of customer churn.
""",

    theme=gr.themes.Soft()

)


app.launch()


