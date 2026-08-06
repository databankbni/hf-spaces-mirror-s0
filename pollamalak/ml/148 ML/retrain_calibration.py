# retrain_calibration.py
# Run this ONCE on the server that has the training data.
# Output: heart_disease_pipeline_calibrated.pkl
#
# Usage:  python retrain_calibration.py

import joblib
import pandas as pd
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.model_selection import train_test_split

# ── Load base model ───────────────────────────────────────────────────────────
model = joblib.load("heart_disease_pipeline_hgb.pkl")

# ── Load & preprocess training data ──────────────────────────────────────────
df = pd.read_csv("heart-new.csv")
df['HeartDisease'] = df['HeartDisease'].map({'Yes': 1, 'No': 0})
df['Age'] = df['AgeCategory'].apply(lambda x: int(x.split('-')[0]) if '-' in x else 80)
df['HighRisk'] = (
    (df['Diabetic'] == 'Yes') &
    (df['Stroke'] == 'Yes') &
    (df['KidneyDisease'] == 'Yes')
).astype(int)

for col in ['Smoking','AlcoholDrinking','Stroke','DiffWalking',
            'PhysicalActivity','Asthma','KidneyDisease','SkinCancer']:
    df[col] = df[col].map({'Yes': 1, 'No': 0})

df['Diabetic'] = df['Diabetic'].map({
    'Yes': 1, 'No': 0,
    'No, borderline diabetes': 0.131,
    'Yes (during pregnancy)': 0.131
})

FEATURE_COLS = [
    'BMI','PhysicalHealth','MentalHealth','SleepTime','Age',
    'Smoking','AlcoholDrinking','Stroke','DiffWalking','Diabetic',
    'PhysicalActivity','Asthma','KidneyDisease','SkinCancer','HighRisk',
    'Sex','AgeCategory','Race','GenHealth'
]

X = df[FEATURE_COLS]
y = df['HeartDisease']

# Use 20% of data as calibration set (never seen during training)
_, X_cal, _, y_cal = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# ── Calibrate ────────────────────────────────────────────────────────────────
print("Fitting isotonic calibration...")
calibrated = CalibratedClassifierCV(FrozenEstimator(model), method='isotonic')
calibrated.fit(X_cal, y_cal)

# ── Save ─────────────────────────────────────────────────────────────────────
joblib.dump(calibrated, "heart_disease_pipeline_calibrated.pkl")
print("✅ Saved: heart_disease_pipeline_calibrated.pkl")

# ── Quick sanity check ───────────────────────────────────────────────────────
test = pd.DataFrame([{
    'BMI':40,'PhysicalHealth':25,'MentalHealth':20,'SleepTime':4,'Age':77,
    'Smoking':1,'AlcoholDrinking':1,'Stroke':1,'DiffWalking':1,'Diabetic':1,
    'PhysicalActivity':0,'Asthma':1,'KidneyDisease':1,'SkinCancer':1,'HighRisk':1,
    'Sex':'Male','AgeCategory':'75-79','Race':'White','GenHealth':'Poor'
}])
p_before = model.predict_proba(test)[0][1]
p_after  = calibrated.predict_proba(test)[0][1]
print(f"High-risk patient — before: {p_before*100:.1f}%  after: {p_after*100:.1f}%")
