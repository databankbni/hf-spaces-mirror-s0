# Savant RRF API - Hybrid Meta-Logic Implementation
import os
import json
import joblib
import torch
import numpy as np
import torch.nn as nn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

app = FastAPI()

# Global components
embedder = SentenceTransformer('antonypamo/RRFSAVANTMADE')
meta_logit = joblib.load('logreg_rrf_savant.joblib')
phi_nodes_embeddings = torch.load('rrf_nodes.pt', map_location='cpu').numpy()

def compute_scores_batch(embeddings: np.ndarray, query_emb: np.ndarray) -> np.ndarray:
    N = embeddings.shape[0]
    energy = np.sum(embeddings**2, axis=1)
    phi = 1 - np.exp(-energy.astype(float))
    fft_vals = np.abs(np.fft.fft(embeddings, axis=1))
    total_power = np.sum(fft_vals, axis=1) + 1e-9
    dom_bin = np.argmax(fft_vals, axis=1)
    dom_pow = np.max(fft_vals, axis=1)
    c_rrf = dom_pow / total_power
    s_rrf = 1 - (np.mean(fft_vals, axis=1) / (dom_pow + 1e-9))
    coherence = 0.5 * s_rrf + 0.5 * c_rrf
    omega = np.tanh(dom_bin.astype(float) * 10)
    node_sims = embeddings @ phi_nodes_embeddings.T
    nearest = np.argmax(node_sims, axis=1)
    onehot = np.zeros((N, 8))
    onehot[np.arange(N), nearest] = 1.0
    batch = np.zeros((N, 15))
    batch[:, 0], batch[:, 1], batch[:, 2] = phi, omega, coherence
    batch[:, 3], batch[:, 4], batch[:, 5], batch[:, 6] = s_rrf, c_rrf, energy, dom_bin
    batch[:, 7:15] = onehot
    return batch

@app.get("/")
def read_root():
    return {"project": "Savant RRF", "status": "online"}

@app.post("/quality")
async def quality(request: Request):
    try:
        data = await request.json()
        prompt = data.get("prompt", "")
        answer = data.get("answer", "")
        
        # Encode both components
        p_vec = embedder.encode(prompt)
        a_vec = embedder.encode(answer)
        
        # Extract features for the answer relative to the prompt context
        features = compute_scores_batch(np.array([a_vec]), p_vec)
        p_good = float(meta_logit.predict_proba(features)[0, 1])
        label = int(np.argmax(meta_logit.predict_proba(features)[0]))
        
        return {
            "p_good": p_good,
            "label": label,
            "feature_map": features[0].tolist()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/rerank")
async def rerank(request: Request):
    global embedder, meta_logit
    try:
        data = await request.json()
        query_input = data.get("query")
        documents = data.get("documents", [])
        alpha = data.get("alpha", 0.5)
        if not query_input or not documents:
            return {"results": []}
        if isinstance(query_input, list):
            query_vec = np.array(query_input)
        else:
            query_vec = embedder.encode(query_input)
        doc_embeddings = np.array([embedder.encode(d) if isinstance(d, str) else d.get('embedding') for d in documents])
        features = compute_scores_batch(doc_embeddings, query_vec)
        p_good = meta_logit.predict_proba(features)[:, 1]
        cos_sim = doc_embeddings @ query_vec
        hybrid = (alpha * cos_sim) + ((1 - alpha) * p_good)
        results = []
        for i, score in enumerate(hybrid):
            results.append({"index": i, "score": float(score), "text": documents[i] if isinstance(documents[i], str) else "", "rank": 0})
        results.sort(key=lambda x: x['score'], reverse=True)
        for i, res in enumerate(results):
            res['rank'] = i + 1
        return {"results": results}
    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))
