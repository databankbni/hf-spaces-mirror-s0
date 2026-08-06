from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import json
import numpy as np
import os

app = FastAPI(title='FloodWatch Kudus — Prediksi Banjir')

# CORS — izinkan request dari frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# Load model dan config saat startup
BASE_DIR  = os.path.dirname(__file__)
model     = joblib.load(os.path.join(BASE_DIR, 'model/model_regresi.pkl'))
config    = json.load(open(os.path.join(BASE_DIR, 'model/config.json')))

FITUR     = config['fitur']
THRESHOLD = config['threshold']

def level_ke_status(level: float) -> str:
    if level >= THRESHOLD['bahaya']:  return 'bahaya'
    if level >= THRESHOLD['waspada']: return 'waspada'
    return 'normal'

# Schema input
class SensorInput(BaseModel):
    level_hulu_cm:      float
    level_hilir_cm:     float
    curah_hujan_mmjam:  float
    laju_naik_hulu:     float
    hujan_3jam:         float
    hujan_6jam:         float
    hujan_12jam:        float
    selisih_hulu_hilir: float
    jam:                int
    bulan:              int
    musim_hujan:        int

class SensorBatch(BaseModel):
    sensors: list[SensorInput]

@app.get('/')
def root():
    return {'status': 'ok', 'model': 'Random Forest Regressor', 'fitur': FITUR}

@app.post('/prediksi')
def prediksi_single(data: SensorInput):
    """Prediksi satu sensor"""
    fitur      = [[getattr(data, f) for f in FITUR]]
    level_pred = float(model.predict(fitur)[0])
    status     = level_ke_status(level_pred)

    return {
        'prediksi_level_cm': round(level_pred, 1),
        'prediksi_status'  : status,
        'kirim_notifikasi' : status in ['waspada', 'bahaya']
    }

@app.post('/prediksi-batch')
def prediksi_batch(data: SensorBatch):
    """Prediksi semua sensor sekaligus — dipanggil dari tombol prediksi di peta"""
    from datetime import datetime
    now        = datetime.now()
    jam        = now.hour
    bulan      = now.month
    musim_hujan = 1 if bulan in [11,12,1,2,3] else 0

    hasil = []
    for sen in data.sensors:
        fitur      = [[getattr(sen, f) for f in FITUR]]
        level_pred = float(model.predict(fitur)[0])
        status     = level_ke_status(level_pred)

        hasil.append({
            'prediksi_level_cm': round(level_pred, 1),
            'prediksi_status'  : status,
            'kirim_notifikasi' : status in ['waspada', 'bahaya']
        })

    return {'ok': True, 'prediksi': hasil}