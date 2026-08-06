"""
FastAPI para Hugging Face Spaces - 100% GRATIS sin límites
Ejecutar en HF Spaces con Docker
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar FastAPI
app = FastAPI(
    title="Emotion Detector API",
    description="API de detección de emociones en español",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica tus dominios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class PredictRequest(BaseModel):
    text: str

class PredictResponse(BaseModel):
    text: str
    emotion: str
    confidence: float

@app.on_event("startup")
async def startup_event():
    """Cargar modelo al iniciar"""
    global model, tokenizer, device

    # En HF Spaces, el modelo debe estar en el mismo repo
    # o especificar el HF_MODEL_ID
    model_id = os.getenv("HF_MODEL_ID", "TomiChapo/emotion-detector-spanish")

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

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "online",
        "message": "Emotion Detector API - Powered by Hugging Face Spaces",
        "model_loaded": model is not None
    }

@app.post("/api/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """Predecir emoción de un texto"""
    if not model or not tokenizer:
        raise HTTPException(status_code=503, detail="Modelo no cargado")

    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")

    try:
        # Tokenizar
        inputs = tokenizer(
            request.text,
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

        logger.info(f"Predicción: '{request.text[:50]}...' → {emotion} ({confidence:.2%})")

        return PredictResponse(
            text=request.text,
            emotion=emotion,
            confidence=round(confidence, 4)
        )

    except Exception as e:
        logger.error(f"Error en predicción: {e}")
        raise HTTPException(status_code=500, detail=f"Error en predicción: {str(e)}")

# Nota: Para feedback, necesitarías agregar MongoDB Atlas o similar
# HF Spaces no tiene almacenamiento persistente
@app.post("/api/feedback")
async def feedback(text: str, prediction: str, correct_emotion: str):
    """
    Endpoint de feedback - requiere base de datos externa
    En HF Spaces gratis no hay storage persistente
    Usar MongoDB Atlas (gratis) o similar
    """
    # TODO: Implementar conexión a MongoDB Atlas
    return {
        "message": "Feedback endpoint - requiere configurar MongoDB Atlas",
        "note": "HF Spaces no tiene storage persistente"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)  # HF Spaces usa puerto 7860
