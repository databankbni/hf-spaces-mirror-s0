# V3
import sys, types
_stub = types.ModuleType('audioop')
sys.modules['audioop'] = _stub

# gradio 4.44.0 uses old Starlette TemplateResponse(name, context)
# newer Starlette changed to TemplateResponse(request, name, context)
import starlette.templating as _st
_orig_tr = _st.Jinja2Templates.TemplateResponse
def _compat_tr(self, *args, **kwargs):
    if args and isinstance(args[0], str) and len(args) >= 2 and isinstance(args[1], dict):
        name, context = args[0], args[1]
        request = context.get('request')
        if request is not None:
            return _orig_tr(self, request, name, context)
    return _orig_tr(self, *args, **kwargs)
_st.Jinja2Templates.TemplateResponse = _compat_tr



"""
Interfaz Gradio para HF Spaces que también expone API FastAPI
"""
import os
import gradio as gr
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variables globales
model = None
tokenizer = None
device = None

# Mapeo de etiquetas
EMOTION_LABELS = {
    0: "alegría",
    1: "tristeza",
    2: "enojo",
    3: "miedo",
    4: "sorpresa",
    5: "asco",
    6: "neutral"
}

def load_model():
    """Cargar modelo al iniciar"""
    global model, tokenizer, device

    model_id = "TomiChapo/emotion-detector-spanish"
    logger.info(f"Cargando modelo desde: {model_id}")

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForSequenceClassification.from_pretrained(model_id)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()

        logger.info(f"✓ Modelo cargado en dispositivo: {device}")

    except Exception as e:
        logger.error(f"✗ Error al cargar modelo: {e}")
        raise

def predict_emotion(text):
    """Predecir emoción de un texto"""
    if not text or not text.strip():
        return "❌ Por favor ingresa un texto", None

    try:
        # Tokenizar
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            padding=True
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        # Predecir
        with torch.no_grad():
            outputs = model(**inputs)
            probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predicted_class = torch.argmax(probabilities, dim=-1).item()
            confidence = probabilities[0][predicted_class].item()

        emotion = EMOTION_LABELS[predicted_class]

        logger.info(f"Predicción: '{text[:50]}...' → {emotion} ({confidence:.2%})")

        # Crear diccionario de probabilidades para todas las emociones
        all_probs = {
            EMOTION_LABELS[i]: float(probabilities[0][i].item())
            for i in range(len(EMOTION_LABELS))
        }

        result = f"**Emoción detectada:** {emotion.upper()}\n\n**Confianza:** {confidence:.2%}"

        return result, all_probs

    except Exception as e:
        logger.error(f"Error en predicción: {e}")
        return f"❌ Error: {str(e)}", None

# Cargar modelo al inicio
load_model()

# Crear interfaz Gradio
with gr.Blocks(title="Emotion Detector - Español", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # 😊 Detector de Emociones en Español

        **Modelo:** BERT fine-tuned en español (99.99% accuracy)

        **Emociones detectadas:** alegría, tristeza, enojo, miedo, sorpresa, asco, neutral

        Escribe un texto y la IA detectará la emoción predominante.
        """
    )

    with gr.Row():
        with gr.Column():
            text_input = gr.Textbox(
                label="Ingresa tu texto",
                placeholder="Ej: Estoy muy feliz con este servicio",
                lines=3
            )

            submit_btn = gr.Button("🔍 Detectar Emoción", variant="primary")

            gr.Examples(
                examples=[
                    ["Estoy muy feliz hoy"],
                    ["Qué tristeza me da esta situación"],
                    ["Esta app es una porquería"],
                    ["Me da miedo lo que pueda pasar"],
                    ["¡Wow, no me lo esperaba!"],
                    ["Qué asco de servicio"],
                    ["El día está nublado"],
                ],
                inputs=text_input,
            )

        with gr.Column():
            result_output = gr.Markdown(label="Resultado")

            probabilities_output = gr.Label(
                label="Distribución de probabilidades",
                num_top_classes=7
            )

    submit_btn.click(
        fn=predict_emotion,
        inputs=text_input,
        outputs=[result_output, probabilities_output]
    )

    text_input.submit(
        fn=predict_emotion,
        inputs=text_input,
        outputs=[result_output, probabilities_output]
    )

    gr.Markdown(
        """
        ---
        ### 🔗 API Usage

        También podés usar esta API programáticamente:

        ```python
        import requests

        response = requests.post(
            "https://tomichapo-emotion-detector-api.hf.space/api/predict",
            json={"data": ["Tu texto aquí"]}
        )
        print(response.json())
        ```

        **Desarrollado por:** [TomiChapo](https://huggingface.co/TomiChapo)

        **Modelo:** [TomiChapo/emotion-detector-spanish](https://huggingface.co/TomiChapo/emotion-detector-spanish)
        """
    )

# Lanzar app
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, show_error=True)
