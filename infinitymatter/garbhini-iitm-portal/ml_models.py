from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from calculations import DF

FEAT = ["bpd1","ofd1","hc1","ac1","fc1","trimester","Weight_enc","Age_enc",
        "thyroid_preg","anemia","hypertension","prediab_diab"]
FEAT_RISK = ["bpd1","ofd1","hc1","ac1","fc1","trimester","Weight_enc"]

X = DF[FEAT].copy()

print("Training ML models...")
rf_ga   = RandomForestRegressor(n_estimators=80, random_state=42, n_jobs=1)
rf_ga.fit(X, DF["Gold_Standard_GA"])

rf_sga  = RandomForestClassifier(n_estimators=80, random_state=42, n_jobs=1)
rf_sga.fit(X, DF["sga"])

rf_anemia = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=1)
rf_anemia.fit(DF[FEAT_RISK], DF["anemia"])

rf_diab = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=1)
rf_diab.fit(DF[FEAT_RISK], DF["prediab_diab"])
print("Models ready.")

def predict_ga(row_dict):
    import pandas as pd
    X_in = pd.DataFrame([row_dict])[FEAT]
    return float(rf_ga.predict(X_in)[0])

def predict_risks(row_dict, row_risk):
    import pandas as pd
    X_in = pd.DataFrame([row_dict])[FEAT]
    X_r  = pd.DataFrame([row_risk])[FEAT_RISK]
    sga_p   = float(rf_sga.predict_proba(X_in)[0][1])
    anm_p   = float(rf_anemia.predict_proba(X_r)[0][1])
    diab_p  = float(rf_diab.predict_proba(X_r)[0][1])
    return sga_p, anm_p, diab_p
