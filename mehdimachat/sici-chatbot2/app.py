"""
Chatbot SICI Pro — version web (Gradio + Hugging Face Spaces, gratuit, sans GPU)
=================================================================================
Adaptation FIDÈLE du notebook "v5" (6 tables fusionnées + boîte à outils +
auto-correction + mémoire de session). La SEULE différence avec le notebook :
- le LLM Qwen2.5-7B n'est plus chargé localement (ça demandait un GPU) : on
  appelle à la place l'API gratuite Groq, qui héberge des modèles Qwen et
  répond en 1-2 secondes, sans carte bancaire ;
- l'affichage passe par Gradio (HTML + Plotly) au lieu de IPython display().

Toute la logique métier (nettoyage des 6 CSV, fusion, STATS, réponses directes,
prompts few-shot, exécuteur sécurisé, auto-heal, mémoire des corrections) est
inchangée par rapport au notebook.
"""

import os, re, sys, warnings, time, traceback, ast, unicodedata, difflib
from io import StringIO
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import gradio as gr
from groq import Groq

warnings.filterwarnings("ignore")

# ────────────────────────────────────────────────────────────────────────
# 1. CONFIGURATION
# ────────────────────────────────────────────────────────────────────────
# Les 6 fichiers doivent être à la racine du Space, avec exactement ces noms
# (ce sont les mêmes noms que dans le notebook / dans ton dossier de données).
DATA_DIR = ""
FILES = {
    "secteur"   : DATA_DIR + "rc_secteur.csv",
    "geo"       : DATA_DIR + "rc_decoup_geo.csv",
    "fin"       : DATA_DIR + "v_financement.csv",
    "projet"    : DATA_DIR + "v_projet_globale.csv",
    "zone_link" : DATA_DIR + "zone_interv_projet.csv",
    "sect_link" : DATA_DIR + "projet_secteurs.csv",
}

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
# Qwen le plus récent hébergé par Groq (remplaçant recommandé de llama-3.3-70b) :
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY manquant. Ajoute-le dans Settings → Variables and secrets "
        "de ton Space Hugging Face (clé gratuite sur https://console.groq.com)."
    )
groq_client = Groq(api_key=GROQ_API_KEY)


# ────────────────────────────────────────────────────────────────────────
# 2. FORMATAGE À LA FRANÇAISE
# ────────────────────────────────────────────────────────────────────────
def fmt_mtnd(x) -> str:
    try:
        if pd.isna(x):
            return "N/A"
        s = f"{float(x):,.2f}"
        return s.replace(",", "§").replace(".", ",").replace("§", " ")
    except Exception:
        return str(x)


def fmt_pct(x) -> str:
    try:
        return f"{float(x):.1f}".replace(".", ",") + "%"
    except Exception:
        return str(x)


def _norm(s) -> str:
    if s is None:
        return ""
    s = str(s).lower().strip()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# ────────────────────────────────────────────────────────────────────────
# 3. CHARGEMENT ROBUSTE DES 6 CSV BRUTS (séparateur auto + nombres FR)
# ────────────────────────────────────────────────────────────────────────
def smart_read_csv(path: str) -> pd.DataFrame:
    best = None
    for sep in [";", ",", "|"]:
        try:
            d = pd.read_csv(path, sep=sep, encoding="utf-8-sig", dtype=str)
            if d.shape[1] > 1 and (best is None or d.shape[1] > best.shape[1]):
                best = d
        except Exception:
            continue
    if best is None:
        best = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    best.columns = [c.strip().strip('"') for c in best.columns]
    return best


def parse_fr_number(x):
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return np.nan
    s = s.replace("\u202f", "").replace("\xa0", "").replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def to_id(series: pd.Series) -> pd.Series:
    return series.map(parse_fr_number).round(0).astype("Int64")


def parse_fr_date(series: pd.Series, with_time: bool = False) -> pd.Series:
    fmt = "%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y"
    out = pd.to_datetime(series, format=fmt, errors="coerce")
    mask = out.isna() & series.notna()
    if mask.any():
        out.loc[mask] = pd.to_datetime(series[mask], errors="coerce")
    return out


missing = [p for p in FILES.values() if not os.path.exists(p)]
if missing:
    raise FileNotFoundError(
        "Fichiers manquants à la racine du Space : " + ", ".join(missing) +
        "\nUploade les 6 CSV (rc_secteur.csv, rc_decoup_geo.csv, v_financement.csv, "
        "v_projet_globale.csv, zone_interv_projet.csv, projet_secteurs.csv)."
    )

print("⏳ Chargement des 6 fichiers CSV...")
raw = {k: smart_read_csv(p) for k, p in FILES.items()}
for k, d in raw.items():
    print(f"  📄 {k:10s} → {d.shape[0]:4d} lignes, {d.shape[1]:3d} colonnes")

# ────────────────────────────────────────────────────────────────────────
# 4. NETTOYAGE DÉTAILLÉ + FUSION DES 6 TABLES
# ────────────────────────────────────────────────────────────────────────
df_secteur = raw["secteur"].copy()
df_secteur["id"] = to_id(df_secteur["id"])
df_secteur["id_parent"] = to_id(df_secteur["id_parent"])
df_secteur["libelle_fr"] = df_secteur["libelle_fr"].str.strip()

df_geo = raw["geo"].copy()
df_geo["id"] = to_id(df_geo["id"])
df_geo["id_nm_parent"] = to_id(df_geo["id_nm_parent"])
df_geo["libelle_fr"] = df_geo["libelle_fr"].str.strip()

df_sect_link = raw["sect_link"].copy()
df_sect_link["id_projet"] = to_id(df_sect_link["id_projet"])
df_sect_link["id_rc_secteur"] = to_id(df_sect_link["id_rc_secteur"])

df_zone_link = raw["zone_link"].copy()
df_zone_link["id_projet"] = to_id(df_zone_link["id_projet"])
df_zone_link["id_rc_dec_geo"] = to_id(df_zone_link["id_rc_dec_geo"])

df_fin = raw["fin"].copy()
df_fin["id"] = to_id(df_fin["id"])
df_fin["id_projet"] = to_id(df_fin["id_projet"])
for c in ["montant", "montant_tnd", "cour_ref", "mnt_decaiss", "mnt_reste_decaiss",
          "pourc_decaiss", "cout_glob", "besoin_fin_ext"]:
    if c in df_fin.columns:
        df_fin[c] = df_fin[c].map(parse_fr_number)
for c in ["dt_signatures", "dt_cloture_init", "dt_cloture_act"]:
    if c in df_fin.columns:
        df_fin[c] = parse_fr_date(df_fin[c])
if "dt_maj" in df_fin.columns:
    df_fin["dt_maj"] = parse_fr_date(df_fin["dt_maj"], with_time=True)

df_projet = raw["projet"].copy()
df_projet["id"] = to_id(df_projet["id"])
df_projet["id_parent"] = to_id(df_projet["id_parent"])
for c in ["cout_glob", "cout_glob_tnd", "besoin_fin_ext", "cours_ref", "taux_avance",
          "budg_etat_dev", "auto_fin_dev", "besoin_fin_ext_dev", "budg_etat", "auto_fin"]:
    if c in df_projet.columns:
        df_projet[c] = df_projet[c].map(parse_fr_number)
for c in ["dt_deb_prevue", "dt_fin_prevue", "dt_deb_act", "dt_fin_act", "dt_cnap", "dt_soumission"]:
    if c in df_projet.columns:
        df_projet[c] = parse_fr_date(df_projet[c])
if "dt_maj" in df_projet.columns:
    df_projet["dt_maj"] = parse_fr_date(df_projet["dt_maj"], with_time=True)

print("✅ Nettoyage terminé pour les 6 tables")

_sect_merged = df_sect_link.merge(
    df_secteur[["id", "libelle_fr"]], left_on="id_rc_secteur", right_on="id",
    how="left", suffixes=("", "_sect"))
sect_agg = _sect_merged.groupby("id_projet").agg(
    secteurs_str=("libelle_fr", lambda s: ", ".join(sorted(set(s.dropna())))),
    nb_secteurs=("libelle_fr", "nunique"),
    secteur_principal=("libelle_fr", lambda s: s.dropna().iloc[0] if s.dropna().size else np.nan),
).reset_index()

_zone_merged = df_zone_link.merge(
    df_geo[["id", "libelle_fr"]], left_on="id_rc_dec_geo", right_on="id",
    how="left", suffixes=("", "_geo"))
zone_agg = _zone_merged.groupby("id_projet").agg(
    zones_str=("libelle_fr", lambda s: ", ".join(sorted(set(s.dropna())))),
    nb_zones=("libelle_fr", "nunique"),
).reset_index()

fin_agg = df_fin.groupby("id_projet").agg(
    nb_financements=("id", "count"),
    montant_total_finance_tnd=("montant_tnd", "sum"),
    pourc_decaiss_moyen=("pourc_decaiss", "mean"),
    bailleurs_str=("bailleur_fr", lambda s: ", ".join(sorted(set(s.dropna())))),
    types_fin_str=("type_fin_fr", lambda s: ", ".join(sorted(set(s.dropna())))),
).reset_index()

df = df_projet.merge(sect_agg, left_on="id", right_on="id_projet", how="left", suffixes=("", "_sl")).drop(columns=["id_projet"])
df = df.merge(zone_agg, left_on="id", right_on="id_projet", how="left", suffixes=("", "_zl")).drop(columns=["id_projet"])
df = df.merge(fin_agg, left_on="id", right_on="id_projet", how="left", suffixes=("", "_fl")).drop(columns=["id_projet"])

print(f"✅ Table centrale fusionnée : {df.shape[0]} projets · {df.shape[1]} colonnes")

df["etat_simple"] = df["etat_prj_fr"].fillna("Non précisé")
df["benef_simple"] = df["org_ouvrage_fr"].fillna("Non précisé")
df["oeuvre_simple"] = df["org_oeuvre_fr"].fillna("Non précisé")
df["devise_simple"] = df["devise"].fillna("Non précisé")

_devise_counts = df["devise_simple"].value_counts()
_devise_rares = _devise_counts[_devise_counts < 2].index
df["devise_groupee"] = df["devise_simple"].apply(lambda x: "Autres" if x in _devise_rares else x)

df["cout_M_TND"] = df["cout_glob_tnd"]
df["montant_finance_M_TND"] = df["montant_total_finance_tnd"]

df["annee_debut"] = df["dt_deb_prevue"].dt.year.astype("Int64")
df["annee_fin"] = df["dt_fin_prevue"].dt.year.astype("Int64")
df["duree_mois_prevue"] = ((df["dt_fin_prevue"] - df["dt_deb_prevue"]).dt.days / 30.44).round(1)

_today = pd.Timestamp.now()
df["est_en_retard"] = (df["dt_fin_prevue"] < _today) & (~df["etat_simple"].isin(["Achevé"]))
df["statut_retard"] = df["est_en_retard"].map({True: "En retard", False: "À temps"})
df["retard_mois"] = np.where(df["est_en_retard"], ((_today - df["dt_fin_prevue"]).dt.days / 30.44).round(1), np.nan)

df["secteurs_str"] = df["secteurs_str"].fillna("Non précisé")
df["secteur_principal"] = df["secteur_principal"].fillna("Non précisé")
df["zones_str"] = df["zones_str"].fillna("Non précisé")
df["bailleurs_str"] = df["bailleurs_str"].fillna("Non précisé")
df["types_fin_str"] = df["types_fin_str"].fillna("Non précisé")
df["nb_financements"] = df["nb_financements"].fillna(0).astype(int)
df["nb_secteurs"] = df["nb_secteurs"].fillna(0).astype(int)
df["nb_zones"] = df["nb_zones"].fillna(0).astype(int)
df["is_pilote"] = df["is_pilote"].astype(bool) if "is_pilote" in df.columns else False
df["is_prog"] = df["is_prog"].astype(bool) if "is_prog" in df.columns else False
df["a_financement"] = df["nb_financements"] > 0
df["statut_financement"] = df["a_financement"].map({True: "Avec financement", False: "Sans financement"})

STATS = {
    "total_projets": len(df),
    "total_financements": len(df_fin),
    "total_secteurs_ref": len(df_secteur),
    "total_zones_ref": len(df_geo),
    "budget_total_M_TND": round(df["cout_glob_tnd"].sum(), 2),
    "budget_moyen_M_TND": round(df["cout_glob_tnd"].mean(), 2),
    "en_execution": int((df["etat_simple"] == "En exécution").sum()),
    "acheves": int((df["etat_simple"] == "Achevé").sum()),
    "en_retard": int(df["est_en_retard"].sum()),
    "pct_retard": round(df["est_en_retard"].mean() * 100, 1),
    "duree_moy_mois": round(df["duree_mois_prevue"].mean(), 1),
    "projets_apres_2020": int((df["annee_debut"] >= 2020).sum()),
    "budget_apres_2020_M": round(df.loc[df["annee_debut"] >= 2020, "cout_glob_tnd"].sum(), 2),
    "annee_min": int(df["annee_debut"].min()) if df["annee_debut"].notna().any() else None,
    "annee_max": int(df["annee_fin"].max()) if df["annee_fin"].notna().any() else None,
    "nb_pilotes": int(df["is_pilote"].sum()),
    "nb_programmes": int(df["is_prog"].sum()),
}

CURATED_COLUMNS = [
    "id", "code", "intitule", "objectif_general", "etat_simple", "type_projet_fr",
    "devise_simple", "devise_groupee", "cout_glob_tnd", "cout_M_TND",
    "benef_simple", "oeuvre_simple",
    "secteurs_str", "secteur_principal", "nb_secteurs",
    "zones_str", "nb_zones",
    "nb_financements", "montant_finance_M_TND", "bailleurs_str", "types_fin_str", "pourc_decaiss_moyen",
    "dt_deb_prevue", "dt_fin_prevue", "annee_debut", "annee_fin", "duree_mois_prevue",
    "est_en_retard", "statut_retard", "retard_mois", "a_financement", "statut_financement",
    "is_pilote", "is_prog", "taux_avance",
]
CURATED_COLUMNS = [c for c in CURATED_COLUMNS if c in df.columns]
df = df[CURATED_COLUMNS].copy()

print(f"✅ Dataset final : {STATS['total_projets']} projets · {len(df.columns)} colonnes utiles")
print(f"📅 Période couverte : {STATS['annee_min']} → {STATS['annee_max']}")
print(f"💰 Budget total : {fmt_mtnd(STATS['budget_total_M_TND'])} M TND")
print(f"⚠️  Projets en retard : {STATS['en_retard']} ({fmt_pct(STATS['pct_retard'])})")


# ────────────────────────────────────────────────────────────────────────
# 5. BOÎTE À OUTILS (find_project, financements, recherche texte)
# ────────────────────────────────────────────────────────────────────────
def find_project(identifier=None, **kw):
    if identifier is None:
        for v in kw.values():
            if v is not None:
                identifier = v
                break
    if identifier is None:
        return None
    s = str(identifier).strip()

    m = df[df["code"].str.upper() == s.upper()]
    if not m.empty:
        return m.iloc[0]

    digits = re.sub(r"\D", "", s)
    if digits:
        try:
            idnum = int(digits)
            m = df[df["id"] == idnum]
            if not m.empty:
                return m.iloc[0]
        except ValueError:
            pass
        m = df[df["code"].str.contains(digits, na=False)]
        if not m.empty:
            return m.iloc[0]

    if len(s) >= 5:
        m = df[df["intitule"].str.contains(re.escape(s), case=False, na=False)]
        if not m.empty:
            return m.iloc[0]
    return None


def get_financements_projet(identifier=None, **kw) -> pd.DataFrame:
    row = find_project(identifier, **kw)
    if row is None:
        return pd.DataFrame()
    return df_fin[df_fin["id_projet"] == row["id"]]


def get_bailleurs_projet(identifier=None, **kw) -> list:
    f = get_financements_projet(identifier, **kw)
    return sorted(f["bailleur_fr"].dropna().unique().tolist()) if not f.empty else []


def search_text(keyword=None, cols=None, source=None, *args, **kw):
    if keyword is None:
        if args:
            keyword = args[0]
        else:
            for v in kw.values():
                if isinstance(v, str):
                    keyword = v
                    break
    if not keyword:
        return (source if source is not None else df).iloc[0:0]
    base = source if source is not None else df
    if cols is None:
        cols = [c for c in ["intitule", "objectif_general", "secteurs_str", "zones_str",
                             "benef_simple", "bailleurs_str", "oeuvre_simple"] if c in base.columns]
    kwn = _norm(keyword)
    mask = pd.Series(False, index=base.index)
    for c in cols:
        mask = mask | base[c].fillna("").map(_norm).str.contains(re.escape(kwn), na=False)
    return base[mask]


_PREFERRED_DISPLAY_COLS = ["code", "intitule", "cout_M_TND", "etat_simple", "secteurs_str",
                           "zones_str", "benef_simple", "bailleurs_str", "annee_debut", "nb_financements"]


def _coerce_xy(data, x=None, y=None):
    if isinstance(data, pd.Series):
        data = data.reset_index()
        data.columns = ["catégorie", "valeur"]
        return data, "catégorie", "valeur"
    data = data.copy()
    if x is None or y is None:
        num_cols = [c for c in data.columns if pd.api.types.is_numeric_dtype(data[c])]
        cat_cols = [c for c in data.columns if c not in num_cols]
        x = x or (cat_cols[0] if cat_cols else data.columns[0])
        y = y or (num_cols[0] if num_cols else data.columns[-1])
    return data, x, y


# ────────────────────────────────────────────────────────────────────────
# 6. CAPTURE POUR LE WEB — remplace IPython display()/fig.show() (Gradio)
# ────────────────────────────────────────────────────────────────────────
class _Capture:
    def __init__(self):
        self.html_blocks = []
        self.figure = None

    def add_html(self, html: str):
        self.html_blocks.append(html)

    def set_figure(self, fig):
        self.figure = fig


def build_toolbox(capture: "_Capture") -> dict:
    """Reconstruit show_table/show_bar/show_pie/show_treemap/show_line/show_stacked_bar,
    identiques au notebook, mais qui CAPTURENT le résultat au lieu de l'afficher dans
    un notebook Jupyter."""

    def show_table(data, title: str = None, max_rows: int = 50, max_cols: int = 9):
        nonlocal capture
        if isinstance(data, pd.Series):
            data = data.reset_index()
            data.columns = [str(c) for c in data.columns]
        if data is None or len(data) == 0:
            capture.add_html("<div style='color:#e5c07b;padding:8px'>Aucun résultat trouvé pour cette requête.</div>")
            return data
        if len(data.columns) > max_cols:
            cols_present = [c for c in _PREFERRED_DISPLAY_COLS if c in data.columns]
            data = data[cols_present] if len(cols_present) >= 3 else data.iloc[:, :max_cols]
        d = data.head(max_rows).copy()
        for c in d.select_dtypes(include=["float", "float64"]).columns:
            d[c] = d[c].map(fmt_mtnd)
        html = d.to_html(index=False, border=0, escape=True)
        # !important est nécessaire car le thème Gradio (classes "prose") applique sa
        # propre couleur de texte par-dessus, ce qui rendait les tableaux illisibles
        # (texte foncé sur fond foncé) malgré le style posé uniquement sur <table>.
        html = html.replace(
            '<table',
            '<table style="color:#f2f2f2 !important;background:#1a1a2e !important;'
            'width:100%;border-collapse:collapse;font-size:0.92em"'
        )
        html = html.replace(
            '<th>',
            '<th style="color:#f2f2f2 !important;background:#12002b !important;'
            'padding:7px 12px;border-bottom:2px solid #444;text-align:left">'
        )
        html = html.replace(
            '<td>',
            '<td style="color:#f2f2f2 !important;background:#1a1a2e !important;'
            'padding:6px 12px;border-bottom:1px solid #333">'
        )
        html = "<div style='overflow-x:auto;border-radius:8px'>" + html + "</div>"
        if title:
            capture.add_html(f"<div style='color:#61afef;font-weight:700;margin:4px 0'>{title}</div>")
        capture.add_html(html)
        if len(data) > max_rows:
            capture.add_html(f"<div style='color:#5c6370;font-size:0.85em'>… {len(data) - max_rows} lignes supplémentaires non affichées.</div>")
        return d

    def show_bar(data, x=None, y=None, title: str = "", top_n=None, ascending=False, horizontal=False, **kw):
        d, x, y = _coerce_xy(data, x, y)
        if len(d) == 0:
            capture.add_html("<div style='color:#e5c07b;padding:8px'>Aucune donnée à afficher pour ce graphique.</div>")
            return
        d = d.sort_values(y, ascending=ascending)
        if top_n:
            d = d.head(int(top_n))
        if horizontal:
            fig = px.bar(d, x=y, y=x, orientation="h", title=title, template="plotly_dark",
                         height=max(400, 35 * len(d)), color=y, color_continuous_scale="Viridis", text_auto=True)
            fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
        else:
            fig = px.bar(d, x=x, y=y, title=title, template="plotly_dark", height=500,
                         color=y, color_continuous_scale="Viridis", text_auto=True)
            fig.update_layout(showlegend=False)
        capture.set_figure(fig)

    def show_pie(data, names=None, values=None, title: str = "", top_n=None, **kw):
        d, names, values = _coerce_xy(data, names, values)
        if len(d) == 0:
            capture.add_html("<div style='color:#e5c07b;padding:8px'>Aucune donnée à afficher pour ce graphique.</div>")
            return
        d = d.sort_values(values, ascending=False)
        if top_n:
            d = d.head(int(top_n))
        fig = px.pie(d, names=names, values=values, title=title, template="plotly_dark", height=500,
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        capture.set_figure(fig)

    def show_treemap(data, path=None, values=None, title: str = "", top_n=None, **kw):
        d, path, values = _coerce_xy(data, path, values)
        if len(d) == 0:
            capture.add_html("<div style='color:#e5c07b;padding:8px'>Aucune donnée à afficher pour ce graphique.</div>")
            return
        d = d.sort_values(values, ascending=False)
        if top_n:
            d = d.head(int(top_n))
        fig = px.treemap(d, path=[path], values=values, title=title, template="plotly_dark", height=550,
                          color=values, color_continuous_scale="Viridis")
        capture.set_figure(fig)

    def show_line(data, x=None, y=None, title: str = ""):
        d, x, y = _coerce_xy(data, x, y)
        if len(d) == 0:
            capture.add_html("<div style='color:#e5c07b;padding:8px'>Aucune donnée à afficher pour ce graphique.</div>")
            return
        d = d.sort_values(x)
        fig = px.line(d, x=x, y=y, title=title, template="plotly_dark", height=500, markers=True)
        capture.set_figure(fig)

    def show_stacked_bar(data_long: pd.DataFrame, x: str, y: str, color: str, title: str = ""):
        if data_long is None or len(data_long) == 0:
            capture.add_html("<div style='color:#e5c07b;padding:8px'>Aucune donnée à afficher pour ce graphique.</div>")
            return
        fig = px.bar(data_long, x=x, y=y, color=color, title=title, template="plotly_dark",
                     height=550, barmode="stack", text_auto=True)
        capture.set_figure(fig)

    return {
        "show_table": show_table, "show_bar": show_bar, "show_pie": show_pie,
        "show_treemap": show_treemap, "show_line": show_line, "show_stacked_bar": show_stacked_bar,
    }


# ────────────────────────────────────────────────────────────────────────
# 7. ROUTEUR + RÉPONSES DIRECTES
# ────────────────────────────────────────────────────────────────────────
CONTEXT_KEYWORDS = [
    "qu'est-ce que", "c'est quoi", "définition", "explique", "contexte",
    "sici", "coopération internationale", "cgdsr", "signifie", "que veut dire",
    "rôle du", "conseil de la république", "différence entre",
]


def classify_question(q: str) -> str:
    q_low = q.lower().strip()
    graph_kw = ["graphique", "graph", "chart", "visualis", "courbe", "barres", "camembert", "pie",
                "treemap", "histogramme", "diagramme", "évolution", "montre", "affiche", "trace"]
    if any(kw in q_low for kw in graph_kw):
        return "graph"
    if any(kw in q_low for kw in CONTEXT_KEYWORDS):
        return "context"
    return "analyse"


CGDSR_CONTEXT = """
🏛️ Le CGDSR (Comité Général de Développement et de Suivi des Ressources) est l'organe officiel
tunisien qui évalue et émet des avis consultatifs sur les projets de coopération internationale
avant leur soumission au Conseil de la République (CR).
📊 Base actuelle : {total} projets.
"""

CONTEXT_SICI = """
📌 Le SICI (Système d'Information de Coopération Internationale) est une plateforme de gestion et
de suivi des projets de coopération internationale de la Tunisie.
📊 Base de données actuelle : {total} projets, {n_fin} financements, {n_sect} secteurs référencés
et {n_zone} zones géographiques référencées, période {annee_min}–{annee_max}, budget total {budget} M TND.
"""


def _match_known_zone(question: str):
    q_norm = _norm(question)
    best = None
    for lib in df_geo["libelle_fr"].dropna().unique():
        lib_norm = _norm(lib)
        if len(lib_norm) >= 3 and lib_norm in q_norm:
            if best is None or len(lib_norm) > len(_norm(best)):
                best = lib
    return best


def try_direct_answer(question: str, q_type: str):
    q = question.lower().strip()
    if q_type == "graph" or re.search(r"\b(top\s*\d+|les?\s*\d+|liste|tous|toutes|classement)\b", q):
        return None

    if q_type == "context":
        if "cgdsr" in q:
            return CGDSR_CONTEXT.format(total=STATS["total_projets"])
        if any(kw in q for kw in ["qu'est-ce que le sici", "c'est quoi le sici"]):
            return CONTEXT_SICI.format(total=STATS["total_projets"], n_fin=STATS["total_financements"],
                n_sect=STATS["total_secteurs_ref"], n_zone=STATS["total_zones_ref"],
                annee_min=STATS["annee_min"], annee_max=STATS["annee_max"], budget=fmt_mtnd(STATS["budget_total_M_TND"]))
        return None

    if re.search(r"combien.*projet.*ex[eé]cution|en ex[eé]cution.*combien", q):
        budget_exec = df.loc[df["etat_simple"] == "En exécution", "cout_glob_tnd"].sum()
        return f"📌 Projets en exécution : {STATS['en_execution']} projets\n💰 Budget total : {fmt_mtnd(budget_exec)} M TND"

    if re.search(r"combien.*projet.*retard|pourcentage.*retard|taux.*retard", q):
        return f"⚠️ Projets en retard : {STATS['en_retard']} sur {STATS['total_projets']} ({fmt_pct(STATS['pct_retard'])})"

    ident_match = re.search(r"\b([A-Za-z]{1,5}\d{3,6}|\d{3,6})\b", question)
    if ident_match and any(kw in q for kw in ["budget", "coût", "cout", "fiche", "détail"]) and not any(kw in q for kw in ["bailleur", "financ"]):
        row = find_project(ident_match.group(1))
        if row is not None:
            return (f"💰 Projet {row['code']} :\n• Intitulé : {row['intitule']}\n"
                    f"• Budget : {fmt_mtnd(row['cout_glob_tnd'])} M TND\n• Devise : {row['devise_simple']}\n"
                    f"• Secteur(s) : {row['secteurs_str']}\n• Zone(s) : {row['zones_str']}\n"
                    f"• Bailleur(s) : {row['bailleurs_str']}\n• État : {row['etat_simple']}")
        return f"❌ Aucun projet trouvé avec l'identifiant '{ident_match.group(1)}'."

    if ident_match and any(kw in q for kw in ["bailleur", "financement", "finance"]):
        row = find_project(ident_match.group(1))
        if row is not None:
            bailleurs = get_bailleurs_projet(ident_match.group(1))
            fin_rows = get_financements_projet(ident_match.group(1))
            montant = fin_rows["montant_tnd"].sum() if not fin_rows.empty else 0
            return (f"🏦 Projet {row['code']} — {row['intitule'][:80]} :\n"
                    f"• Nombre de financements : {len(fin_rows)}\n"
                    f"• Bailleur(s) : {', '.join(bailleurs) if bailleurs else 'Non précisé'}\n"
                    f"• Montant total financé : {fmt_mtnd(montant)} M TND")
        return f"❌ Aucun projet trouvé avec l'identifiant '{ident_match.group(1)}'."

    if "combien" in q and "projet" in q:
        zone_hit = _match_known_zone(question)
        if zone_hit and "secteur" not in q:
            res = search_text(zone_hit, cols=["zones_str"])
            return f"📌 Projets liés à la zone '{zone_hit}' : {len(res)} projet(s)"

    return None


# ────────────────────────────────────────────────────────────────────────
# 8. SCHÉMA + FEW-SHOT + PROMPT
# ────────────────────────────────────────────────────────────────────────
SCHEMA_CONTEXT = f"""
DONNÉES : projets de coopération internationale de la Tunisie, 6 tables sources fusionnées/nettoyées.

① `df` — TABLE CENTRALE, une ligne = un projet ({STATS['total_projets']} projets), colonnes RÉELLES :
  id (int), code (str, ex 'P26057'), intitule (str), objectif_general (str, souvent NaN)
  etat_simple (str: 'En exécution'/'Achevé'/'Nouveau'/...), type_projet_fr (str)
  devise_simple / devise_groupee (str) — utilise devise_groupee pour les graphiques (devises rares regroupées en 'Autres')
  cout_glob_tnd / cout_M_TND (float, en Millions de TND)
  benef_simple (str, organisme responsable/maître d'ouvrage), oeuvre_simple (str, maître d'œuvre)
  secteurs_str (str, secteurs séparés par ', '), secteur_principal (str), nb_secteurs (int)
  zones_str (str, zones séparées par ', '), nb_zones (int)
  nb_financements (int), montant_finance_M_TND (float), bailleurs_str (str), types_fin_str (str), pourc_decaiss_moyen (float)
  dt_deb_prevue / dt_fin_prevue (datetime), annee_debut / annee_fin (Int64), duree_mois_prevue (float)
  est_en_retard (bool), statut_retard (str: 'En retard'/'À temps'), retard_mois (float)
  a_financement (bool), statut_financement (str: 'Avec financement'/'Sans financement')
  is_pilote / is_prog (bool), taux_avance (float)

② `df_secteur` ({len(df_secteur)} lignes) : id, code, libelle_fr, id_parent (référentiel des secteurs)
③ `df_geo` ({len(df_geo)} lignes) : id, code, libelle_fr, id_nm_parent (référentiel des zones géographiques)
④ `df_fin` ({len(df_fin)} lignes, PLUSIEURS lignes par projet) :
     id_projet (clé vers df.id), bailleur_fr, type_fin_fr ('Prêt'/'Don'), montant_tnd (M TND),
     pourc_decaiss (0-100), mnt_decaiss, mnt_reste_decaiss, dt_signatures, num_fin
⑤ `df_sect_link` ({len(df_sect_link)} lignes) : id_projet, id_rc_secteur (liaison brute projet↔secteur)
⑥ `df_zone_link` ({len(df_zone_link)} lignes) : id_projet, id_rc_dec_geo (liaison brute projet↔zone)

RELATIONS : df.id ↔ df_fin.id_projet | df.id ↔ df_sect_link.id_projet ↔ df_secteur.id | df.id ↔ df_zone_link.id_projet ↔ df_geo.id

FONCTIONS D'AIDE DISPONIBLES (utilise-les seulement pour ce que pandas seul ne fait pas bien) :
  find_project(identifiant) → Series d'UN projet (par code 'P26059', id 1258, ou titre)
  get_financements_projet(identifiant) / get_bailleurs_projet(identifiant)
  search_text(mot_cle, cols=None, source=df) → lignes contenant mot_cle (insensible accents/casse) dans les colonnes texte
  fmt_mtnd(x) → "1 234,56" (ajoute toi-même " M TND" après)   fmt_pct(x) → "89,3%" (symbole déjà inclus, n'en rajoute pas)
  show_table(data, title=None) → affiche un DataFrame OU une Series en tableau HTML stylé
  show_bar(data, x=None, y=None, title, top_n=None, horizontal=False) → barres (accepte Series ou DataFrame)
  show_pie(data, names=None, values=None, title, top_n=None) → camembert (accepte Series ou DataFrame)
  show_treemap(data, path=None, values=None, title, top_n=None) → treemap (accepte Series ou DataFrame)
  show_stacked_bar(data_long, x, y, color, title) → barres empilées (format LONG, voir exemple crosstab)
  show_line(data, x=None, y=None, title) → courbe (accepte Series ou DataFrame)

POUR TOUT LE RESTE (compter, grouper, filtrer, calculer, croiser, comparer...) : ÉCRIS DU PANDAS
STANDARD directement sur df / df_fin / df_secteur / df_geo / df_sect_link / df_zone_link.
TU N'ES JAMAIS LIMITÉ À UNE LISTE DE FONCTIONS PRÉDÉFINIES : si aucune fonction ci-dessus ne
correspond exactement à la question, écris le code pandas qui répond directement — c'est
l'usage NORMAL et ATTENDU, pas un cas de secours.

IMPORTANT — UN SEUL GRAPHIQUE PAR RÉPONSE : n'appelle jamais deux fonctions show_* (ou show_*
et un fig.show() séparé) dans le même code ; une seule visualisation peut être affichée à la fois.
"""

FEW_SHOT = """
Exemples illustrant le STYLE attendu (pandas standard + fonctions d'affichage) — ce sont des
ILLUSTRATIONS DE STYLE, pas des recettes à copier : adapte toujours le raisonnement à la question
posée, même si elle est différente de tous ces exemples.

Q: "Camembert des états des projets"
```python
result = df['etat_simple'].value_counts()
show_pie(result, title="Répartition des projets par état")
print(f"\\n📊 Analyse : L'état '{result.index[0]}' est dominant avec {int(result.iloc[0])} projets ({fmt_pct(result.iloc[0]/len(df)*100)}).")
```

Q: "Barres du budget total par devise"
```python
result = df.groupby('devise_groupee')['cout_M_TND'].sum().sort_values(ascending=False)
show_bar(result, title="Budget total par devise")
print(f"\\n📊 Analyse : La devise dominante est '{result.index[0]}' avec {fmt_mtnd(result.iloc[0])} M TND.")
```

Q: "Les 10 secteurs les plus fréquents"
```python
merged = df_sect_link.merge(df_secteur[['id', 'libelle_fr']], left_on='id_rc_secteur', right_on='id')
result = merged['libelle_fr'].value_counts().head(10)
show_bar(result, title="Top 10 des secteurs", horizontal=True)
print(f"\\n📊 Analyse : Le secteur '{result.index[0]}' est le plus représenté avec {int(result.iloc[0])} projets.")
```

Q: "Les 5 projets les plus coûteux"
```python
result = df.nlargest(5, 'cout_glob_tnd')[['code', 'intitule', 'cout_M_TND', 'etat_simple', 'benef_simple']]
show_table(result, title="Top 5 des projets les plus coûteux")
part = result['cout_M_TND'].sum()
pct = part / df['cout_glob_tnd'].sum() * 100
print(f"\\n📊 Analyse : Ces 5 projets représentent ensemble {fmt_mtnd(part)} M TND, soit {fmt_pct(pct)} du budget total.")
```

Q: "Camembert des projets en retard vs à temps"
```python
result = df['statut_retard'].value_counts()
show_pie(result, title="Projets en retard vs à temps")
print(f"\\n📊 Analyse : {int(result.get('En retard', 0))} projets ({fmt_pct(result.get('En retard', 0)/len(df)*100)}) sont en retard, {int(result.get('À temps', 0))} sont à temps.")
```

Q: "Barres empilées des états par devise"
```python
long_df = pd.crosstab(df['devise_groupee'], df['etat_simple']).reset_index().melt(id_vars='devise_groupee', var_name='etat_simple', value_name='valeur')
long_df = long_df[long_df['valeur'] > 0]
show_stacked_bar(long_df, x='devise_groupee', y='valeur', color='etat_simple', title="États des projets par devise")
top_devise = df['devise_groupee'].value_counts().index[0]
etat_dom = df[df['devise_groupee'] == top_devise]['etat_simple'].value_counts().index[0]
print(f"\\n📊 Analyse : Pour '{top_devise}' (devise la plus fréquente), l'état dominant est '{etat_dom}'.")
```

Q: "Treemap des organismes bénéficiaires"
```python
result = df['benef_simple'].value_counts().head(15)
show_treemap(result, title="Projets par organisme bénéficiaire (Top 15)")
print(f"\\n📊 Analyse : '{result.index[0]}' est l'organisme avec le plus de projets ({int(result.iloc[0])}).")
```

Q: "Quel bailleur finance le plus de projets liés au secteur de la santé ?" (question croisée entre plusieurs tables)
```python
projets_sante = search_text('sante', cols=['secteurs_str'])
fin_sante = df_fin[df_fin['id_projet'].isin(projets_sante['id'])]
result = fin_sante['bailleur_fr'].value_counts()
show_table(result.reset_index().rename(columns={'index': 'Bailleur', 'bailleur_fr': 'Nombre de financements'}).head(10),
           title="Bailleurs des projets du secteur santé")
if len(result) > 0:
    print(f"\\n📊 Analyse : '{result.index[0]}' est le bailleur le plus présent sur les projets du secteur santé, avec {int(result.iloc[0])} financements.")
else:
    print("\\n📊 Analyse : Aucun financement identifié pour les projets du secteur santé.")
```

Q: "Quel est le pourcentage de financements, par bailleur, signés il y a plus de 2 ans avec un taux de décaissement inférieur à 50% ?" (question à conditions combinées : calcule et AFFICHE le résultat exact, jamais une phrase vague)
```python
seuil_date = pd.Timestamp.now() - pd.DateOffset(years=2)
mask = (df_fin['dt_signatures'] < seuil_date) & (df_fin['pourc_decaiss'] < 50)
total_par_bailleur = df_fin.groupby('bailleur_fr').size()
filtre_par_bailleur = df_fin[mask].groupby('bailleur_fr').size()
result = (filtre_par_bailleur / total_par_bailleur * 100).dropna().sort_values(ascending=False)
show_table(result.reset_index().rename(columns={0: 'Pourcentage', 'bailleur_fr':'Bailleur'}), title="% de financements signés il y a plus de 2 ans et décaissés à moins de 50%, par bailleur")
if len(result) > 0:
    print(f"\\n📊 Analyse : {result.index[0]} a le taux le plus élevé avec {fmt_pct(result.iloc[0])}.")
```
"""


def build_prompt(question: str, q_type: str, history: list = None) -> str:
    hist_str = ""
    if history:
        for h in history[-3:]:
            marker = "réussi" if h.get("ok") else "échoué"
            hist_str += f'- "{h["q"][:70]}" → {marker}\n'
        if hist_str:
            hist_str = f"\nQuestions précédentes de cette session (contexte, ne pas répéter) :\n{hist_str}"

    return f"""Tu es un data scientist expert en pandas/plotly. Tu analyses une base de projets de
coopération internationale tunisiens (6 tables reliées).

{SCHEMA_CONTEXT}

{FEW_SHOT}

RÈGLES IMPÉRATIVES :
1. Réponds UNIQUEMENT avec du code Python entre ```python et ```.
2. Tu n'es JAMAIS limité aux exemples ci-dessus : ils illustrent un STYLE, pas une liste fermée de
   cas possibles. Pour une question inédite, raisonne depuis le schéma et écris le pandas qu'il faut.
3. N'utilise QUE les noms de colonnes/DataFrames listés dans le schéma — n'invente jamais de colonne
   ni de nom d'argument de fonction non documenté ci-dessus.
4. Si la question cite un identifiant de projet (code ou nombre), utilise find_project(...).
5. fmt_pct(x) contient déjà le symbole '%' — ne l'ajoute jamais une seconde fois.
   Convertis toujours les années/entiers en int() avant affichage (jamais '2019.0').
6. Termine TOUJOURS par un print("\\n📊 Analyse : ...") donnant le(s) chiffre(s) EXACT(S) qui
   répondent à la question — jamais de phrase vague ("le graphique montre...").
7. Si la question a plusieurs conditions combinées, calcule et affiche (show_table ou print) le
   résultat filtré AVANT tout graphique.
8. Code autonome, aucun import supplémentaire. Gère les NaN avec .fillna()/.dropna().
9. Réponse textuelle toujours en FRANÇAIS.
10. Un seul show_* (un seul graphique) par réponse.
{hist_str}
QUESTION : {question}

```python"""


# ────────────────────────────────────────────────────────────────────────
# 9. LLM (Groq / Qwen) + EXTRACTION DE CODE + EXÉCUTEUR SÉCURISÉ
# ────────────────────────────────────────────────────────────────────────
def llm_generate(prompt: str, max_new: int = 1600) -> str:
    messages = [
        {"role": "system", "content": "Tu es un expert Python/Data Science. Réponds uniquement avec du code Python valide entre ```python et ```."},
        {"role": "user", "content": prompt},
    ]
    try:
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.15,
            top_p=0.95,
            max_tokens=max_new,
        )
        return completion.choices[0].message.content or ""
    except Exception as e:
        return f"⚠️ Erreur d'appel au modèle (Groq) : {e}"


def extract_code(text: str) -> str:
    m = re.search(r"```python\s*(.+?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.+?)```", text, re.DOTALL)
    if m:
        code_ = m.group(1).strip()
        if any(kw in code_ for kw in ["df", "pd", "print", "show_", "fig"]):
            return code_
    lines = text.strip().split("\n")
    code_lines = [l for l in lines if l.strip() and not l.strip().startswith("#") and
                  any(kw in l for kw in ["df[", "df.", "show_", "print(", "fig", "= df", "find_project"])]
    return "\n".join(lines) if len(code_lines) >= 2 else ""


def safe_exec(code_: str, context: dict) -> tuple:
    try:
        ast.parse(code_)
    except SyntaxError as e:
        return False, "", f"SyntaxError: {e}"
    old_stdout = sys.stdout
    sys.stdout = captured = StringIO()
    success, error_msg = False, ""
    try:
        exec(compile(code_, "<chatbot>", "exec"), context)
        success = True
    except Exception:
        error_msg = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
    return success, captured.getvalue(), error_msg


# Mémoire de session : corrections apprises (typos de noms réapparaissant)
LEARNED_FIXES: dict = {}


def apply_learned_fixes(code_: str) -> str:
    for wrong, right in LEARNED_FIXES.items():
        code_ = re.sub(rf"\b{re.escape(wrong)}\b", right, code_)
    return code_


_NAMEERR_SUGGEST = re.compile(r"NameError: name '(\w+)' is not defined\. Did you mean: '(\w+)'\?")
_KEYERR_COLUMN = re.compile(r"KeyError: '(\w+)'")


def autoheal_code(code_: str, error: str, known_names: set, column_names: set = None):
    m = _NAMEERR_SUGGEST.search(error)
    if m:
        wrong, suggestion = m.group(1), m.group(2)
        if suggestion in known_names and wrong != suggestion:
            LEARNED_FIXES[wrong] = suggestion
            return re.sub(rf"\b{re.escape(wrong)}\b", suggestion, code_)

    m2 = re.search(r"NameError: name '(\w+)' is not defined", error)
    if m2:
        wrong = m2.group(1)
        close = difflib.get_close_matches(wrong, list(known_names), n=1, cutoff=0.82)
        if close:
            LEARNED_FIXES[wrong] = close[0]
            return re.sub(rf"\b{re.escape(wrong)}\b", close[0], code_)

    if column_names:
        m3 = _KEYERR_COLUMN.search(error)
        if m3:
            wrong = m3.group(1)
            close = difflib.get_close_matches(wrong, list(column_names), n=1, cutoff=0.55)
            if close and close[0] != wrong:
                LEARNED_FIXES[wrong] = close[0]
                return re.sub(rf"(['\"]){re.escape(wrong)}\1", rf"\g<1>{close[0]}\g<1>", code_)
    return None


def fix_code_with_error(code_: str, error: str, question: str) -> str:
    error_short = error.split("\n")[-2] if "\n" in error else error[:200]
    hint = ""
    m = re.search(r"(NameError: name '(\w+)'|KeyError: '(\w+)')", error_short)
    if m:
        wrong = m.group(2) or m.group(3)
        hint = f"⚠️ IDENTIFIANT FAUTIF : '{wrong}' n'existe pas. Vérifie son orthographe exacte dans le schéma ci-dessous.\n"

    real_columns = {
        "df": list(df.columns), "df_fin": list(df_fin.columns)[:25],
        "df_secteur": list(df_secteur.columns), "df_geo": list(df_geo.columns),
        "df_sect_link": list(df_sect_link.columns), "df_zone_link": list(df_zone_link.columns),
    }
    return f"""{hint}Le code Python suivant a échoué :
```python
{code_[:900]}
```
Erreur : {error_short}

Colonnes RÉELLES et EXACTES disponibles (n'invente AUCUN autre nom) :
{real_columns}

Fonctions d'aide disponibles (noms EXACTS, ne les modifie pas) :
find_project, get_financements_projet, get_bailleurs_projet, search_text, fmt_mtnd, fmt_pct,
show_table, show_bar, show_pie, show_treemap, show_stacked_bar, show_line

Pour tout le reste, utilise du pandas standard (.value_counts(), .groupby(), .merge(), .loc[]...).

Question originale : {question}

Corrige ce code en utilisant UNIQUEMENT les noms listés ci-dessus. Réponds UNIQUEMENT avec le code
corrigé entre ```python et ```.
```python"""


# ────────────────────────────────────────────────────────────────────────
# 10. FONCTION PRINCIPALE run_chat() — logique du notebook, sortie Gradio
# ────────────────────────────────────────────────────────────────────────
chat_history = []
MAX_RETRIES = 3
TYPE_LABEL = {"graph": "📊 Graphique", "context": "📖 Contexte", "analyse": "🔍 Analyse"}


class _HTMLWrap:
    def __init__(self, data):
        self.data = data


class _MarkdownWrap:
    def __init__(self, data):
        self.data = data


def make_exec_globals(capture: _Capture) -> dict:
    toolbox = build_toolbox(capture)

    def display_override(obj=None, *a, **kw):
        if obj is None:
            return
        html = getattr(obj, "data", None)
        capture.add_html(html if html is not None else str(obj))

    g = {
        "df": df, "df_secteur": df_secteur, "df_geo": df_geo, "df_fin": df_fin,
        "df_sect_link": df_sect_link, "df_zone_link": df_zone_link, "STATS": STATS,
        "pd": pd, "np": np, "px": px, "go": go, "make_subplots": make_subplots,
        "display": display_override, "HTML": _HTMLWrap, "Markdown": _MarkdownWrap,
        "datetime": datetime, "re": re,
        "find_project": find_project, "get_financements_projet": get_financements_projet,
        "get_bailleurs_projet": get_bailleurs_projet, "search_text": search_text,
        "fmt_mtnd": fmt_mtnd, "fmt_pct": fmt_pct,
        "__builtins__": __builtins__,
    }
    g.update(toolbox)
    # Filet de sécurité : si le code généré appelle malgré tout fig.show() directement.
    go.Figure.show = lambda self, *a, **kw: capture.set_figure(self)
    return g


KNOWN_NAMES_BASE = {"df", "df_secteur", "df_geo", "df_fin", "df_sect_link", "df_zone_link", "STATS",
                    "pd", "np", "px", "go", "make_subplots", "display", "HTML", "Markdown", "datetime", "re",
                    "find_project", "get_financements_projet", "get_bailleurs_projet", "search_text",
                    "fmt_mtnd", "fmt_pct", "show_table", "show_bar", "show_pie", "show_treemap",
                    "show_stacked_bar", "show_line"}
ALL_COLUMN_NAMES = set(df.columns) | set(df_fin.columns) | set(df_secteur.columns) | set(df_geo.columns)


def run_chat(question: str):
    """Retourne (texte_markdown, html_tables, figure_plotly_ou_None, badge)."""
    if not question or not question.strip():
        return "Posez une question pour commencer.", "", None, ""

    t0 = time.time()
    q_type = classify_question(question)
    badge_prefix = TYPE_LABEL.get(q_type, "🤖")

    direct = try_direct_answer(question, q_type)
    if direct:
        chat_history.append({"q": question, "ok": True})
        if len(chat_history) > 10:
            chat_history.pop(0)
        return direct, "", None, f"{badge_prefix} · ⚡ Réponse directe · {time.time()-t0:.1f}s"

    code_, success, output, last_error, source = "", False, "", "", "llm"
    token_budget = 1600
    capture = _Capture()
    exec_globals = make_exec_globals(capture)

    for attempt in range(MAX_RETRIES + 1):
        if attempt == 0:
            prompt = build_prompt(question, q_type, chat_history)
        else:
            healed = autoheal_code(code_, last_error, KNOWN_NAMES_BASE, column_names=ALL_COLUMN_NAMES)
            if healed and healed != code_:
                code_ = healed
                capture = _Capture()
                exec_globals = make_exec_globals(capture)
                success, output, last_error = safe_exec(code_, exec_globals)
                source = "heal"
                if success:
                    break
                continue
            prompt = fix_code_with_error(code_, last_error, question)

        raw = llm_generate(prompt, max_new=token_budget)
        code_ = apply_learned_fixes(extract_code(raw))
        source = "llm"

        if not code_:
            chat_history.append({"q": question, "ok": True})
            if len(chat_history) > 10:
                chat_history.pop(0)
            return raw.strip(), "", None, f"{badge_prefix} · 🤖 LLM · {time.time()-t0:.1f}s"

        capture = _Capture()
        exec_globals = make_exec_globals(capture)
        success, output, last_error = safe_exec(code_, exec_globals)
        if success:
            break

    elapsed = time.time() - t0
    chat_history.append({"q": question, "ok": success})
    if len(chat_history) > 10:
        chat_history.pop(0)

    if not success:
        return f"⚠️ Échec après {MAX_RETRIES + 1} tentatives :\n\n```\n{last_error[-800:]}\n```", "", None, badge_prefix

    src_badge = {"direct": "⚡ Direct", "heal": "🛠️ Auto-corrigé", "llm": "🤖 LLM"}.get(source, "🤖 LLM")
    html_out = "".join(capture.html_blocks)
    fig = capture.figure
    text_out = output.strip() if output.strip() else "✅ Terminé."
    return text_out, html_out, fig, f"{badge_prefix} · {src_badge} · {elapsed:.1f}s"


# ────────────────────────────────────────────────────────────────────────
# 11. INTERFACE GRADIO
# ────────────────────────────────────────────────────────────────────────
EXAMPLES = [
    "Qu'est-ce que le SICI et quel est l'objectif de ce système ?",
    "Combien de projets sont actuellement en exécution et quel est leur budget total ?",
    "Affiche un graphique des 10 secteurs les plus fréquents parmi les projets.",
    "Liste moi tous les projets qui concernent le secteur de la santé.",
    "Quels sont les 5 projets les plus coûteux ?",
    "Affiche un graphique camembert de la répartition des états des projets.",
    "Montre un graphique des 10 bailleurs de fonds les plus actifs.",
    "Quel pourcentage des projets sont en retard ?",
]

with gr.Blocks(title="Chatbot SICI Pro", theme=gr.themes.Soft(primary_hue="purple")) as demo:
    gr.Markdown(
        f"""
        # 🤖 Chatbot SICI — Analyse des projets de coopération internationale
        {STATS['total_projets']} projets · {STATS['total_financements']} financements ·
        {STATS['total_secteurs_ref']} secteurs · {STATS['total_zones_ref']} zones ·
        période {STATS['annee_min']}–{STATS['annee_max']}

        Posez une question en langage naturel (calcul, liste, graphique, ou question de contexte).
        """
    )
    with gr.Row():
        question_box = gr.Textbox(label="Votre question", placeholder="Ex: Combien de projets sont en retard ?", scale=4)
        submit_btn = gr.Button("Envoyer", variant="primary", scale=1)

    badge_out = gr.Markdown()
    answer_out = gr.Markdown(label="Réponse")
    html_out = gr.HTML()
    plot_out = gr.Plot(label="Graphique")

    gr.Examples(examples=EXAMPLES, inputs=question_box)

    def _submit(q):
        text, html, fig, badge = run_chat(q)
        return badge, text, html, fig

    submit_btn.click(_submit, inputs=question_box, outputs=[badge_out, answer_out, html_out, plot_out])
    question_box.submit(_submit, inputs=question_box, outputs=[badge_out, answer_out, html_out, plot_out])

if __name__ == "__main__":
    demo.launch()
