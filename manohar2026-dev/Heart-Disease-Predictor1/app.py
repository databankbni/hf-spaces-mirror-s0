import gradio as gr
import pandas as pd
import joblib

model = joblib.load("model.pkl")


def predict(
    male,
    age,
    education,
    currentSmoker,
    cigsPerDay,
    BPMeds,
    prevalentStroke,
    prevalentHyp,
    diabetes,
    totChol,
    sysBP,
    diaBP,
    BMI,
    heartRate,
    glucose,
):

    data = pd.DataFrame({

        "male":[male],
        "age":[age],
        "education":[education],
        "currentSmoker":[currentSmoker],
        "cigsPerDay":[cigsPerDay],
        "BPMeds":[BPMeds],
        "prevalentStroke":[prevalentStroke],
        "prevalentHyp":[prevalentHyp],
        "diabetes":[diabetes],
        "totChol":[totChol],
        "sysBP":[sysBP],
        "diaBP":[diaBP],
        "BMI":[BMI],
        "heartRate":[heartRate],
        "glucose":[glucose]

    })

    prediction = model.predict(data)[0]

    probability = model.predict_proba(data)[0][1]

    if prediction == 1:

        result = "⚠️ High Risk of Heart Disease"

    else:

        result = "✅ Low Risk of Heart Disease"

    return result, f"{probability*100:.2f}%"



demo = gr.Interface(

    fn=predict,

    inputs=[

        gr.Radio([0,1],label="Male (0=Female,1=Male)"),

        gr.Number(label="Age"),

        gr.Number(label="Education"),

        gr.Radio([0,1],label="Current Smoker"),

        gr.Number(label="Cigarettes Per Day"),

        gr.Radio([0,1],label="BP Medicines"),

        gr.Radio([0,1],label="Previous Stroke"),

        gr.Radio([0,1],label="Hypertension"),

        gr.Radio([0,1],label="Diabetes"),

        gr.Number(label="Total Cholesterol"),

        gr.Number(label="Systolic BP"),

        gr.Number(label="Diastolic BP"),

        gr.Number(label="BMI"),

        gr.Number(label="Heart Rate"),

        gr.Number(label="Glucose")

    ],

    outputs=[

        gr.Textbox(label="Prediction"),

        gr.Textbox(label="Probability")

    ],

    title="Heart Disease Prediction",

    description="Predict whether a patient is likely to develop heart disease within the next 10 years."

)

demo.launch()