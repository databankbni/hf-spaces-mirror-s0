import gradio as gr
import joblib
import numpy as np

# Cargar modelo y scaler
model = joblib.load("random_forest_model.joblib")
scaler = joblib.load("scaler.joblib")

UMBRAL = 0.374  # umbral optimizado obtenido en el proyecto

def predecir_riesgo(age, sex, cp, trestbps, chol, fbs, restecg,
                     thalach, exang, oldpeak, slope, ca, thal):

    sex_val = 1 if sex == "Hombre" else 0
    fbs_val = 1 if fbs == "Sí" else 0
    exang_val = 1 if exang == "Sí" else 0

    X = np.array([[age, sex_val, cp, trestbps, chol, fbs_val, restecg,
                   thalach, exang_val, oldpeak, slope, ca, thal]])

    X_scaled = scaler.transform(X)
    prob = model.predict_proba(X_scaled)[0][1]

    if prob >= UMBRAL:
        resultado = "⚠️ RIESGO DE ENFERMEDAD CARDÍACA"
        color = "🔴"
    else:
        resultado = "✅ SIN RIESGO DETECTADO"
        color = "🟢"

    return f"""
    {color} **{resultado}**

    **Probabilidad de riesgo:** {prob:.1%}
    **Umbral usado:** {UMBRAL} (optimizado para máxima sensibilidad clínica)

    ---
    *Modelo: Random Forest | Recall en clase de riesgo: 92.9%*
    *Este resultado es orientativo y no reemplaza un diagnóstico médico profesional.*
    """

with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Sistema Inteligente de Evaluación de Riesgo Cardíaco")
    gr.Markdown("""
    Proyecto académico — Aprendizaje Estadístico, UPAO  
    Modelo: Random Forest entrenado sobre el Cleveland Heart Disease Dataset (UCI)  
    
    Ingresa los valores clínicos del paciente para obtener una evaluación de riesgo.
    """)

    with gr.Column():
        age = gr.Slider(18, 100, value=50, label="Edad", step=1)
        sex = gr.Radio(["Hombre", "Mujer"], value="Hombre", label="Sexo")
        cp = gr.Dropdown(
            choices=[("Angina típica", 0), ("Angina atípica", 1),
                     ("Dolor no anginoso", 2), ("Asintomático", 3)],
            value=0, label="Tipo de dolor de pecho (cp)"
        )
        trestbps = gr.Slider(80, 220, value=130, label="Presión arterial en reposo (trestbps)")
        chol = gr.Slider(100, 600, value=240, label="Colesterol sérico (chol)")
        fbs = gr.Radio(["Sí", "No"], value="No", label="Glucosa en ayunas > 120 mg/dl (fbs)")
        restecg = gr.Dropdown(
            choices=[("Normal", 0), ("Anomalía onda ST-T", 1), ("Hipertrofia VI", 2)],
            value=0, label="ECG en reposo (restecg)"
        )
        thalach = gr.Slider(60, 220, value=150, label="Frecuencia cardíaca máxima (thalach)")
        exang = gr.Radio(["Sí", "No"], value="No", label="Angina inducida por ejercicio (exang)")
        oldpeak = gr.Slider(0, 7, value=1.0, label="Depresión ST (oldpeak)", step=0.1)
        slope = gr.Dropdown(
            choices=[("Ascendente", 0), ("Plana", 1), ("Descendente", 2)],
            value=0, label="Pendiente del segmento ST (slope)"
        )
        ca = gr.Slider(0, 3, value=0, label="Vasos coloreados por fluoroscopía (ca)", step=1)
        thal = gr.Dropdown(
            choices=[("Normal", 0), ("Defecto fijo", 1), ("Defecto reversible", 2)],
            value=0, label="Talasemia (thal)"
        )

        btn = gr.Button("Evaluar Riesgo", variant="primary")
        resultado = gr.Markdown()

    btn.click(
        fn=predecir_riesgo,
        inputs=[age, sex, cp, trestbps, chol, fbs, restecg,
                thalach, exang, oldpeak, slope, ca, thal],
        outputs=resultado
    )

demo.launch()