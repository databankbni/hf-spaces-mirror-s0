import os
import math
import numpy as np
import pandas as pd

DATASET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthetic_dataset (4).tsv")

def load_and_prepare():
    df = pd.read_csv(DATASET_PATH, sep="\t")
    df["dt_usg_firsttrim"] = pd.to_datetime(df["dt_usg_firsttrim"], errors="coerce")
    df["dt_usg"] = pd.to_datetime(df["dt_usg"], errors="coerce")
    df["t_weeks"] = (df["dt_usg"] - df["dt_usg_firsttrim"]).dt.days / 7
    df["Garbhini_GA1"] = (-0.02294 * (df["crl1_mm_firsttrim"]/10)**2
                          + 1.15018 * (df["crl1_mm_firsttrim"]/10) + 6.73526)
    df["Gold_Standard_GA"] = df["t_weeks"] + df["Garbhini_GA1"]
    df = df[(df["Gold_Standard_GA"] >= 10) & (df["Gold_Standard_GA"] <= 45)].copy()
    df = df[(df["bpd1"] > 0) & (df["ofd1"] > 0) & (df["hc1"] > 0)
            & (df["ac1"] > 0) & (df["fc1"] > 0)].copy()

    df["Garbhini_GA2"] = np.exp(
        2.05685 + 0.07661 * np.log(df["ofd1"]) * np.log(df["bpd1"])
        + 0.09255 * np.log(df["hc1"])**2)
    df["Hadlock"] = (10.85 + 0.06*df["hc1"]*df["fc1"]
                     + 0.67*df["bpd1"] + 0.168*df["ac1"])
    hc10 = df["hc1"]*10; fc10 = df["fc1"]*10; lhc = np.log(hc10)
    df["INTERGROWTH"] = np.exp(0.03243*lhc**2 + 0.001644*fc10*lhc + 3.813)/7

    df["Error_GA2"]  = df["Gold_Standard_GA"] - df["Garbhini_GA2"]
    df["Error_Hadlock"]    = df["Gold_Standard_GA"] - df["Hadlock"]
    df["Error_INTERGROWTH"]= df["Gold_Standard_GA"] - df["INTERGROWTH"]

    df["Weight_enc"]  = df["Weight"].map({"Normal":0,"Obese":1,"Underweight":2}).fillna(0).astype(int)
    df["Age_enc"]     = df["age_mod"].map({"less_than_24":0,"greater_than_24":1}).fillna(0).astype(int)
    return df

# Singleton data
DF = load_and_prepare()

# ---- Formula calculators ----
def ga1(crl_mm):
    c = float(crl_mm)/10
    return -0.02294*c**2 + 1.15018*c + 6.73526 if c > 0 else 0.0

def ga2(bpd, ofd, hc):
    try:
        return math.exp(2.05685 + 0.07661*math.log(ofd)*math.log(bpd) + 0.09255*math.log(hc)**2)
    except Exception:
        return 0.0

def hadlock(hc, fc, bpd, ac):
    return 10.85 + 0.06*hc*fc + 0.67*bpd + 0.168*ac if all(v>0 for v in [hc,fc,bpd,ac]) else 0.0

def intergrowth(hc, fc):
    try:
        hc10=hc*10; fc10=fc*10; lhc=math.log(hc10)
        return math.exp(0.03243*lhc**2 + 0.001644*fc10*lhc + 3.813)/7
    except Exception:
        return 0.0

def gold_standard_ga(crl_mm, date_first, date_curr):
    try:
        d1 = pd.to_datetime(date_first); d2 = pd.to_datetime(date_curr)
        t = (d2-d1).days/7
    except Exception:
        t = 0.0
    g1 = ga1(crl_mm)
    return (g1 + t) if g1 > 0 else t
