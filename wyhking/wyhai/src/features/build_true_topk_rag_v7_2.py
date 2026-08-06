#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors


LEVELS = [
    ("model_id", "same_model_id", 1.0),
    ("brand_series_year", "same_brand_series_year", 0.85),
    ("brand_series", "same_brand_series", 0.70),
    ("series_id", "same_series_id", 0.55),
    ("brand_energy_key", "same_brand_energy", 0.35),
]
NUM = ["age_for_training", "mileage_wan_km", "transfer_count"]
CATS = [("city", 0.35), ("color", 0.15), ("energy_type", 0.30), ("condition_group", 0.20), ("trim_keywords", 0.10)]
RAG = [
    "rag_match_level",
    "rag_top1_price",
    "rag_top3_mean_price",
    "rag_top5_mean_price",
    "rag_top10_mean_price",
    "rag_top5_median_price",
    "rag_top10_median_price",
    "rag_top5_min_price",
    "rag_top5_max_price",
    "rag_top5_std_price",
    "rag_top5_count",
    "rag_top10_count",
    "rag_same_model_id_count",
    "rag_same_series_count",
    "rag_same_city_count",
    "rag_distance_mean",
    "rag_confidence_score",
    "rag_top10_source_ids",
    "rag_top10_source_datasets",
    "rag_top10_distances",
    "rag_top10_prices",
]


def fold(df: pd.DataFrame) -> pd.Series:
    return (pd.util.hash_pandas_object(df.source_dataset.astype(str) + "_" + df.source_id.astype(str), index=False).astype("uint64") % 5).astype(int)


def mat(base: pd.DataFrame, q: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    xb, xq = [], []
    for c in NUM:
        med = pd.to_numeric(base[c], errors="coerce").median() if c in base else 0
        b = pd.to_numeric(base[c], errors="coerce").fillna(med).to_numpy(float) if c in base else np.zeros(len(base))
        qq = pd.to_numeric(q[c], errors="coerce").fillna(med).to_numpy(float) if c in q else np.zeros(len(q))
        sd = np.std(b) or 1.0
        xb.append(b / sd)
        xq.append(qq / sd)
    return np.vstack(xb).T, np.vstack(xq).T


def stat(pr: np.ndarray, ds: np.ndarray, level: str, conf: float, cand: pd.DataFrame | None = None, qrow: pd.Series | None = None) -> dict[str, object]:
    pr = np.asarray(pr, float)
    ds = np.asarray(ds, float)
    t3 = pr[: min(3, len(pr))]
    t5 = pr[: min(5, len(pr))]
    t10 = pr[: min(10, len(pr))]
    same_model = same_series = same_city = 0
    top10_source_ids = top10_source_datasets = ""
    if cand is not None and qrow is not None and len(cand) > 0:
        top10 = cand.iloc[: min(10, len(cand))]
        same_model = int((top10.model_id.astype(str) == str(qrow.get("model_id", ""))).sum()) if "model_id" in top10 else 0
        same_series = int((top10.series.astype(str) == str(qrow.get("series", ""))).sum()) if "series" in top10 else 0
        same_city = int((top10.city.astype(str) == str(qrow.get("city", ""))).sum()) if "city" in top10 else 0
        top10_source_ids = "|".join(top10.source_id.astype(str).tolist()) if "source_id" in top10 else ""
        top10_source_datasets = "|".join(top10.source_dataset.astype(str).tolist()) if "source_dataset" in top10 else ""
    return {
        "rag_match_level": level,
        "rag_top1_price": float(pr[0]),
        "rag_top3_mean_price": float(t3.mean()),
        "rag_top5_mean_price": float(t5.mean()),
        "rag_top10_mean_price": float(t10.mean()),
        "rag_top5_median_price": float(np.median(t5)),
        "rag_top10_median_price": float(np.median(t10)),
        "rag_top5_min_price": float(t5.min()),
        "rag_top5_max_price": float(t5.max()),
        "rag_top5_std_price": float(t5.std()) if len(t5) > 1 else 0.0,
        "rag_top5_count": int(len(t5)),
        "rag_top10_count": int(len(t10)),
        "rag_same_model_id_count": same_model,
        "rag_same_series_count": same_series,
        "rag_same_city_count": same_city,
        "rag_distance_mean": float(ds.mean()),
        "rag_confidence_score": float(max(0, min(1, conf * min(1, len(pr) / 5) / (1 + ds.mean())))),
        "rag_top10_source_ids": top10_source_ids,
        "rag_top10_source_datasets": top10_source_datasets,
        "rag_top10_distances": "|".join([str(round(float(x), 6)) for x in ds[: min(10, len(ds))]]),
        "rag_top10_prices": "|".join([str(round(float(x), 2)) for x in t10]),
    }


def fill(df: pd.DataFrame, qidx: np.ndarray, bidx: np.ndarray, out: pd.DataFrame) -> None:
    unresolved = set(qidx.tolist())
    baseall = df.loc[bidx].copy()
    if baseall.empty or not unresolved:
        return
    for key, lvl, conf in LEVELS:
        if not unresolved:
            break
        for val, qg in df.loc[list(unresolved)].groupby(key, dropna=False):
            bg = baseall[baseall[key] == val]
            if bg.empty:
                continue
            k = min(50, len(bg))
            xb, xq = mat(bg, qg)
            nn = NearestNeighbors(n_neighbors=k, metric="euclidean").fit(xb)
            dist, ind = nn.kneighbors(xq)
            for pos, rowid in enumerate(qg.index):
                cand = bg.iloc[ind[pos]].copy()
                score = dist[pos].copy()
                for c, w in CATS:
                    if c in cand and c in df:
                        score += (cand[c].astype(str).values != str(df.at[rowid, c])) * w
                if "source_dataset" in cand and "source_id" in cand:
                    self_mask = (cand["source_dataset"].astype(str).values == str(df.at[rowid, "source_dataset"])) & (cand["source_id"].astype(str).values == str(df.at[rowid, "source_id"]))
                    score[self_mask] = 1e9
                order = np.argsort(score)
                order = order[score[order] < 1e8][:10]
                if len(order) == 0:
                    continue
                chosen = cand.iloc[order]
                s = stat(chosen.target_price.values, score[order], lvl, conf, chosen, df.loc[rowid])
                for cc, v in s.items():
                    out.at[rowid, cc] = v
                unresolved.discard(rowid)
    if unresolved:
        pr = baseall.target_price.values
        fb = {
            "rag_match_level": "global_train_fallback",
            "rag_top1_price": float(np.median(pr)),
            "rag_top3_mean_price": float(np.mean(pr)),
            "rag_top5_mean_price": float(np.mean(pr)),
            "rag_top10_mean_price": float(np.mean(pr)),
            "rag_top5_median_price": float(np.median(pr)),
            "rag_top10_median_price": float(np.median(pr)),
            "rag_top5_min_price": float(np.percentile(pr, 5)),
            "rag_top5_max_price": float(np.percentile(pr, 95)),
            "rag_top5_std_price": float(np.std(pr)),
            "rag_top5_count": 0,
            "rag_top10_count": 0,
            "rag_same_model_id_count": 0,
            "rag_same_series_count": 0,
            "rag_same_city_count": 0,
            "rag_distance_mean": 999.0,
            "rag_confidence_score": 0.01,
            "rag_top10_source_ids": "",
            "rag_top10_source_datasets": "",
            "rag_top10_distances": "",
            "rag_top10_prices": "",
        }
        for rowid in unresolved:
            for cc, v in fb.items():
                out.at[rowid, cc] = v


def build(inp: str, outp: str, trace_out: str | None = None) -> None:
    df = pd.read_csv(inp, low_memory=False)
    df["brand_energy_key"] = df.brand.astype(str) + "_" + df.energy_type.astype(str)
    for c in RAG:
        df[c] = np.nan
    tr = df.index[df.split.eq("train")].to_numpy()
    df["rag_oof_fold"] = -1
    df.loc[tr, "rag_oof_fold"] = fold(df.loc[tr]).values
    for f in range(5):
        q = df.index[df.split.eq("train") & df.rag_oof_fold.eq(f)].to_numpy()
        b = df.index[df.split.eq("train") & ~df.rag_oof_fold.eq(f)].to_numpy()
        print("fold", f, "query", len(q), "base", len(b))
        fill(df, q, b, df)
    q = df.index[~df.split.eq("train")].to_numpy()
    print("valid_test query", len(q), "base", len(tr))
    fill(df, q, tr, df)
    final = df.drop(columns=["brand_energy_key"], errors="ignore")
    final.to_csv(outp, index=False, encoding="utf-8-sig")
    meta = {"input": inp, "output": outp, "rows": len(final), "rag_columns": RAG}
    Path(outp).with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if trace_out:
        trace_cols = [
            c for c in [
                "source_dataset", "source_id", "split", "target_task", "target_price", "rag_match_level",
                "rag_confidence_score", "rag_top10_source_ids", "rag_top10_source_datasets", "rag_top10_distances", "rag_top10_prices",
            ] if c in final
        ]
        Path(trace_out).parent.mkdir(parents=True, exist_ok=True)
        final[trace_cols].to_csv(trace_out, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--trace-output")
    a = ap.parse_args()
    build(a.input, a.output, a.trace_output)
