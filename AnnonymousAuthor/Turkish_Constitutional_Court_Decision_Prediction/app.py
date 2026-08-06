# -*- coding: utf-8 -*-
"""
Created on Thu Feb 12 21:37:24 2026

@author: firis
"""

import os
import re
import joblib
import numpy as np
import torch
import torch.nn as nn
import gradio as gr
from huggingface_hub import login
from pathlib import Path
from huggingface_hub import hf_hub_download
import shutil
from transformers import BigBirdModel, BigBirdTokenizerFast
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq

import sys
import joblib
import sklearn
import numpy as np

print("Python:", sys.version)
print("joblib:", joblib.__version__)
print("scikit-learn:", sklearn.__version__)
print("numpy:", np.__version__)

# =========================
# 0) RUNTIME CONFIG
# =========================



torch.manual_seed(42)
torch.set_num_threads(1)

#hf_token = os.environ.get("HF_TOKEN")  
#if hf_token:
#   login(token=hf_token)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_LENGTH = 3072

# Qdrant local DB folder in Space
QDRANT_PATH = os.environ.get("QDRANT_PATH", "qdrant_db")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "aym_rag")

# Retrieval embedding model (same as your functions default)
E5_MODEL_NAME = os.environ.get("E5_MODEL_NAME", "intfloat/multilingual-e5-base")

# Groq
groq_api_key = os.environ.get("GROQ_API_KEY")
if not groq_api_key:
    raise ValueError("Missing GROQ_API_KEY. Set it as a Hugging Face Space Secret.")

llm = ChatGroq(
    groq_api_key=groq_api_key,
    model_name="llama-3.3-70b-versatile",
    temperature=0.0,
    max_tokens=1024,
)


# =========================
# 1) TOKENIZER
# =========================
tokenizer = BigBirdTokenizerFast.from_pretrained("FiratIsmailoglu/turkish-bigbird-tokenizer")


# =========================
# 2) MODEL CLASSES (YOUR CODE)
# =========================
class MLPHead(nn.Module):
    def __init__(self, input_dim, hidden_dim):
        super().__init__()
        self.layer1 = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 64),
            nn.LayerNorm(64),
            nn.ReLU()
        )

    def forward(self, x):
        return self.layer1(x)


class CommonBodyLogRegTFIDF(nn.Module):
    def __init__(self, num_classes_level1=2, num_classes_level2=2):
        super().__init__()

        self.bert = BigBirdModel.from_pretrained(
            "FiratIsmailoglu/bigbird-turkish-pretrained",
            attention_type="block_sparse"
        )

        self.proj_tfidf_main = nn.Sequential(
            nn.Linear(1, 16),
            nn.ReLU(),
        )

        self.proj_tfidf_sub = nn.Sequential(
            nn.Linear(1, 16),
            nn.ReLU(),
        )

        HIDDEN_DIM = 128
        BERT_DIM = self.bert.config.hidden_size

        self.common_body = MLPHead(BERT_DIM, HIDDEN_DIM)

        self.fuse_main = nn.Sequential(
            nn.Linear(64 + 16, 128),
            nn.LayerNorm(128),
            nn.ReLU()
        )

        self.fuse_sub = nn.Sequential(
            nn.Linear(64 + 16, 128),
            nn.LayerNorm(128),
            nn.ReLU()
        )

        self.main_head = nn.Linear(128, 1)  # inad vs adm
        self.sub_head  = nn.Linear(128, 1)  # adm_ihlal vs adm_no_ihlal

    def forward(self,
        input_ids=None,
        attention_mask=None,
        log_reg_logit_main=None,
        log_reg_logit_sub=None,
        inputs_embeds=None,          # ← MUST be here
    ):
        outputs = self.bert(
            input_ids=input_ids,
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
        )
        pooled_output = outputs.last_hidden_state[:, 0, :]  # CLS
        shared_features = self.common_body(pooled_output)

        h_main = self.proj_tfidf_main(log_reg_logit_main)      # (B,16)
        h_main = torch.cat([h_main, shared_features], dim=1)   # (B,80)
        h_main = self.fuse_main(h_main)
        logits_level1 = self.main_head(h_main)                 # (B,1)

        h_sub = self.proj_tfidf_sub(log_reg_logit_sub)
        h_sub = torch.cat([h_sub, shared_features], dim=1)
        h_sub = self.fuse_sub(h_sub)
        logits_level2 = self.sub_head(h_sub)

        return logits_level1, logits_level2


# =========================
# 3) LOAD SKLEARN PIPELINES + TORCH WEIGHTS
# =========================
pipeline_main = joblib.load("tfidf_logreg_main.joblib")
pipeline_sub  = joblib.load("tfidf_logreg_sub.joblib")

torch.manual_seed(42)
model = CommonBodyLogRegTFIDF().to(DEVICE)



checkpoint_path = Path("CommonBodyLogRegTFIDF.pth")

print("Checkpoint size:", checkpoint_path.stat().st_size)

with checkpoint_path.open("rb") as f:
    header = f.read(200)

print("Checkpoint header:", header)

if header.startswith(b"version https://git-lfs.github.com/spec/v1"):
    raise RuntimeError(
        "CommonBodyLogRegTFIDF.pth is only a Git LFS/Xet pointer. "
        "Upload the actual checkpoint file."
    )
state = torch.load("CommonBodyLogRegTFIDF.pth", map_location=DEVICE)  # deploy-friendly
model.load_state_dict(state)
model.eval()


def log_reg_logit(pipeline, mean, std, text):
    # mean for the main LR: 0.922, std: 1.635
    # mean for the sub LR: 2.159, std: 1.927
    score = pipeline.named_steps["clf"].decision_function(
        pipeline.named_steps["tfidf"].transform([text])
    )[0]
    return float((score - mean) / std)


def decide_document_class(
    text, model, tokenizer, device,
    pipeline_main, pipeline_sub, max_length=3072,use_no_grad=True
):
    enc = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_length)
    input_ids = enc["input_ids"].to(device)
    attention_mask = enc["attention_mask"].to(device)

    # ---- real LR logits (constants computed by sklearn) ----
    log_main_real = torch.tensor(
        log_reg_logit(pipeline_main, mean=0.922, std=1.635, text=text),
        device=device
    )
    log_sub_real = torch.tensor(
        log_reg_logit(pipeline_sub, mean=2.159, std=1.927, text=text),
        device=device
    )
    if use_no_grad:
        with torch.no_grad():
            logits1, logits2 = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                log_reg_logit_main=log_main_real.reshape(1, 1),
                log_reg_logit_sub=log_sub_real.reshape(1, 1)
            )
    else:
            logits1, logits2 = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                log_reg_logit_main=log_main_real.reshape(1, 1),
                log_reg_logit_sub=log_sub_real.reshape(1, 1)
            )

    p_adm = torch.sigmoid(logits1)      # P(admissible)
    p_adm_ihl = torch.sigmoid(logits2)  # P(ihlal | admissible)

    if p_adm < 0.5:
        decision = "inadmissible"
    elif p_adm_ihl > 0.65:
        decision = "merits (violation)"
    else:
        decision = "merits (no violation)"

    return decision, logits1.item(), logits2.item()


# =========================
# 4) SENTENCE SPLITTER (YOUR CODE)
# =========================
TR_UPPER = "A-ZÇĞİÖŞÜ"
TR_LOWER = "a-zçğıöşü"

RE_DECIMAL = re.compile(r"\d\.\d")
RE_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}")
RE_LEGAL_NUMBERING = re.compile(
    r"(\d+)\.\s*(madde|fıkra|fikra|bent|no|nolu|numara|numaralı|sayılı|sayili)\b",
    re.IGNORECASE
)

ABBR = ["T.C", "Dr", "Prof", "Doç", "Doc", "Av", "Sn", "No", "Bkz", "vd", "vs", "örn", "m"]
RE_ABBR = re.compile(r"\b(" + "|".join(map(re.escape, ABBR)) + r")\.$", re.IGNORECASE)

END_PUNCT = {".", "!", "?", "…"}


def split_sentences_with_spans_legal_tr(text: str):
    t = text
    n = len(t)
    spans = []

    start = 0
    i = 0

    def next_nonspace(j):
        while j < n and t[j].isspace():
            j += 1
        return j

    while i < n:
        ch = t[i]
        if ch in END_PUNCT:
            left = max(0, i - 30)
            right = min(n, i + 30)
            window = t[left:right]

            if ch == "." and i + 1 < n and t[i - 1].isdigit() and t[i + 1].isdigit():
                i += 1
                continue

            if ch == ".":
                m = RE_DATE.search(window)
                if m:
                    date_start = left + m.start()
                    date_end = left + m.end()
                    if date_start <= i < date_end:
                        i += 1
                        continue

            if ch == ".":
                local_left = max(0, i - 20)
                local_right = min(n, i + 30)
                local = t[local_left:local_right]
                m = RE_LEGAL_NUMBERING.search(local)
                if m:
                    dot_pos = local_left + m.start(0) + len(m.group(1))
                    if dot_pos == i:
                        i += 1
                        continue

            if ch == ".":
                token_left = max(0, i - 10)
                token = t[token_left:i + 1]
                if RE_ABBR.search(token.strip()):
                    i += 1
                    continue

            j = next_nonspace(i + 1)
            if j >= n:
                end = n
                sent = t[start:end].strip()
                if sent:
                    s0 = start
                    e0 = end
                    while s0 < e0 and t[s0].isspace():
                        s0 += 1
                    while e0 > s0 and t[e0 - 1].isspace():
                        e0 -= 1
                    spans.append((s0, e0, t[s0:e0]))
                break

            nxt = t[j]
            if re.match(rf"[{TR_UPPER}\"\(\[\{{]", nxt):
                end = i + 1
                sent = t[start:end].strip()
                if sent:
                    s0 = start
                    e0 = end
                    while s0 < e0 and t[s0].isspace():
                        s0 += 1
                    while e0 > s0 and t[e0 - 1].isspace():
                        e0 -= 1
                    spans.append((s0, e0, t[s0:e0]))
                start = j
                i = j
                continue

        i += 1

    if start < n:
        tail = t[start:n].strip()
        if tail:
            s0 = start
            e0 = n
            while s0 < e0 and t[s0].isspace():
                s0 += 1
            while e0 > s0 and t[e0 - 1].isspace():
                e0 -= 1
            if not spans or spans[-1][0] != s0 or spans[-1][1] != e0:
                spans.append((s0, e0, t[s0:e0]))

    return spans


# =========================
# 5) IG FUNCTIONS (YOUR CODE)
# =========================
def pick_target_from_outputs(z_A, z_V, decision: str):
    z_A = z_A.view(-1)
    z_V = z_V.view(-1)

    if decision == "inadmissible":
        target = -z_A
    elif decision == "merits (violation)":
        target = z_A + z_V
    elif decision == "merits (no violation)":
        target = z_A - z_V
    else:
        raise ValueError(f"Unknown decision: {decision}")

    return target.sum()


def ig_document_token_attributions_bimodal(
    model, tokenizer, text, decision, device,
    pipeline_main, pipeline_sub,
    steps=24, max_length=3072,
    lr_baseline="empty"
):
    model.eval()

    enc = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
        return_offsets_mapping=True
    )
    input_ids = enc["input_ids"].to(device)
    attention_mask = enc["attention_mask"].to(device)
    offsets = enc["offset_mapping"][0].tolist()

    log_main_real = torch.tensor(
        log_reg_logit(pipeline_main, mean=0.922, std=1.635, text=text)
    ).reshape(1, 1).to(device)
    log_sub_real = torch.tensor(
        log_reg_logit(pipeline_sub, mean=2.159, std=1.927, text=text)
    ).reshape(1, 1).to(device)

    if lr_baseline == "zero":
        log_main_base = torch.zeros_like(log_main_real)
        log_sub_base  = torch.zeros_like(log_sub_real)
    elif lr_baseline == "empty":
        log_main_base = torch.tensor(
            log_reg_logit(pipeline_main, mean=0.922, std=1.635, text="")
        ).reshape(1, 1).to(device)
        log_sub_base = torch.tensor(
            log_reg_logit(pipeline_sub, mean=2.159, std=1.927, text="")
        ).reshape(1, 1).to(device)
    else:
        raise ValueError(lr_baseline)

    pad_id = tokenizer.pad_token_id
    baseline_ids = torch.full_like(input_ids, pad_id)
    baseline_ids[0, 0] = input_ids[0, 0]
    baseline_ids[0, -1] = input_ids[0, -1]

    embed_layer = model.bert.get_input_embeddings()
    emb_real = embed_layer(input_ids)
    emb_base = embed_layer(baseline_ids)

    total_grad_emb = torch.zeros_like(emb_real)
    total_grad_main = torch.zeros_like(log_main_real)
    total_grad_sub  = torch.zeros_like(log_sub_real)

    for i in range(1, steps + 1):
        alpha = i / steps

        emb = emb_base + alpha * (emb_real - emb_base)
        log_main = log_main_base + alpha * (log_main_real - log_main_base)
        log_sub  = log_sub_base  + alpha * (log_sub_real  - log_sub_base)

        emb = emb.detach().requires_grad_(True)
        log_main = log_main.detach().requires_grad_(True)
        log_sub  = log_sub.detach().requires_grad_(True)

        z_A, z_V = model(
            inputs_embeds=emb,
            attention_mask=attention_mask,
            log_reg_logit_main=log_main,
            log_reg_logit_sub=log_sub,
        )

        target = pick_target_from_outputs(z_A, z_V, decision)

        model.zero_grad(set_to_none=True)
        target.backward()

        g_sub = log_sub.grad
        if g_sub is None:
            g_sub = torch.zeros_like(log_sub)

        total_grad_emb += emb.grad.detach()
        total_grad_main += log_main.grad.detach()
        total_grad_sub  += g_sub.detach()

    avg_grad_emb  = total_grad_emb / steps
    avg_grad_main = total_grad_main / steps
    avg_grad_sub  = total_grad_sub  / steps

    ig_emb  = (emb_real - emb_base) * avg_grad_emb
    ig_main = (log_main_real - log_main_base) * avg_grad_main
    ig_sub  = (log_sub_real  - log_sub_base)  * avg_grad_sub

    token_attr = ig_emb.abs().sum(dim=-1).squeeze(0)

    for t_idx, (a, b) in enumerate(offsets):
        if a == b:
            token_attr[t_idx] = 0.0

    return token_attr.detach().cpu(), offsets, ig_main.item(), ig_sub.item()


def aggregate_to_sentence_scores(token_attr, offsets, sent_spans, norm="sum"):
    scores = []
    counts = []

    for (s_start, s_end, _) in sent_spans:
        scores.append(0.0)
        counts.append(0)

    s_idx = 0
    for t_idx, (a, b) in enumerate(offsets):
        if a == b:
            continue

        while s_idx < len(sent_spans) and a >= sent_spans[s_idx][1]:
            s_idx += 1
        if s_idx >= len(sent_spans):
            break

        s_start, s_end, _ = sent_spans[s_idx]

        if a >= s_start and b <= s_end:
            scores[s_idx] += float(token_attr[t_idx].item())
            counts[s_idx] += 1

    norm_scores = []
    for s, c in zip(scores, counts):
        if c == 0:
            norm_scores.append(0.0)
            continue
        if norm == "sum":
            norm_scores.append(s)
        elif norm == "mean":
            norm_scores.append(s / c)
        elif norm == "sqrt":
            norm_scores.append(s / (c ** 0.5))
        else:
            raise ValueError(norm)

    return norm_scores, counts


def top_k_sentences_full_doc(
    model, tokenizer, text, device,
    pipeline_main, pipeline_sub,
    k=10, steps=24, max_length=3072, norm="sum",
):
    sent_spans = split_sentences_with_spans_legal_tr(text)

    decision, zA, zV = decide_document_class(
        text, model, tokenizer, device,
        pipeline_main, pipeline_sub,use_no_grad=False
    )

    token_attr, offsets, lr_main_attr, lr_sub_attr = ig_document_token_attributions_bimodal(
        model, tokenizer, text, decision, device,
        pipeline_main, pipeline_sub,
        steps=steps, max_length=max_length, lr_baseline="empty"
    )

    sent_scores, sent_counts = aggregate_to_sentence_scores(
        token_attr, offsets, sent_spans, norm=norm
    )

    ranked = []
    for i, ((s_start, s_end, s_text), sc, c) in enumerate(zip(sent_spans, sent_scores, sent_counts)):
        ranked.append((i, sc, c, s_text))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return {
        "decision": decision,
        "z_A": zA,
        "z_V": zV,
        "lr_main_attr": lr_main_attr,
        "lr_sub_attr": lr_sub_attr,
        "top_sentences": ranked[:k],
        "all_sentence_scores": ranked
    }


# =========================
# 6) QDRANT + FORMATTING (YOUR CODE)
# =========================


from pathlib import Path
import os

print("QDRANT_PATH:", QDRANT_PATH)

qdrant_path = Path(QDRANT_PATH)

print("Exists:", qdrant_path.exists())
print("Is directory:", qdrant_path.is_dir())

if qdrant_path.exists():
    for path in qdrant_path.rglob("*"):
        if path.is_file():
            print(
                "Qdrant file:",
                path,
                "size:",
                path.stat().st_size
            )


qpath = Path(QDRANT_PATH)
for f in qpath.rglob("*"):
    if f.is_file():
        print(f, f.stat().st_size)

        if f.suffix in [".sqlite", ".db"]:
            with open(f, "rb") as fp:
                print("Header:", fp.read(32))

QDRANT_PATH = "qdrant_db"

sqlite_target = Path(
    QDRANT_PATH,
    "collection",
    "aym_rag",
    "storage.sqlite"
)

with sqlite_target.open("rb") as f:
    sqlite_header = f.read(100)

if sqlite_header.startswith(
    b"version https://git-lfs.github.com/spec/v1"
):
    print("SQLite file is an LFS pointer. Downloading the real file...")

    downloaded_sqlite = hf_hub_download(
        repo_id="AnnonymousAuthor/Turkish_Constitutional_Court_Decision_Prediction",
        repo_type="space",
        filename="qdrant_db/collection/aym_rag/storage.sqlite",
        token=os.getenv("HF_TOKEN")
    )

    shutil.copyfile(downloaded_sqlite, sqlite_target)

    print("Downloaded SQLite size:", sqlite_target.stat().st_size)

    with sqlite_target.open("rb") as f:
        print("Downloaded SQLite header:", f.read(32))

client = QdrantClient(path=QDRANT_PATH)

# cache the embedding model so it won't reload each time
_E5_MODEL = None
def _get_e5_model(model_name: str):
    global _E5_MODEL
    if _E5_MODEL is None:
        _E5_MODEL = SentenceTransformer(model_name)
    return _E5_MODEL


def qdrant_search_raw(
    client,
    collection_name: str,
    query_text: str,
    model_name: str = "intfloat/multilingual-e5-base",
    top_k: int = 8,
):
    model = _get_e5_model(model_name)

    q_vec = model.encode(
        [f"query: {query_text}"],
        normalize_embeddings=True
    )[0].tolist()

    res = client.query_points(
        collection_name=collection_name,
        query=q_vec,
        limit=top_k,
        with_payload=True,
    )

    return res.points


def first_sentences(text, n=2):
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r'(?<=[\.\?\!])\s+', text)
    return " ".join(parts[:n]).strip()


def format_retrieved_evidence(points, max_chars=900, summary_sentences=2):
    cards = []
    for i, p in enumerate(points, 1):
        pl = p.payload or {}
        text = (pl.get("text") or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + " ..."

        doc_type = pl.get("doc_type") or "unknown"
        source = pl.get("source") or pl.get("_file") or "unknown_source"
        case_id = pl.get("case_id")
        article = pl.get("article_no") or pl.get("madde_no") or pl.get("madde")
        anchor = case_id or (f"Article {article}" if article else pl.get("chunk_id"))

        mini = first_sentences(text, n=summary_sentences)

        cards.append(
            f"Source {i}:\n"
            f"- Source name: {source}\n"
            f"- Type: {doc_type}\n"
            f"- Reference: {anchor}\n"
            f"- Brief summary: {mini}\n"
        )
    return "\n".join(cards) if cards else "(none)"


def format_input_evidence(sentences, keep_top=4, max_chars=240):
    sents = [ (s or "").strip() for s in sentences if (s or "").strip() ]
    sents = sents[:keep_top]
    lines = []
    for s in sents:
        if len(s) > max_chars:
            s = s[:max_chars] + " ..."
        lines.append(f"- Brief evidence from the input text: “{s}”")
    return "\n".join(lines) if lines else "(none)"


def build_user_friendly_prompt(pred_label, influential_sentences, retrieved_points):
    input_block = format_input_evidence(influential_sentences)
    retrieved_block = format_retrieved_evidence(retrieved_points)

    return f"""
MODEL DECISION: {pred_label}
Classes: inadmissible | merits (violation) | merits (no violation)

EVIDENCE FROM THE INPUT TEXT (sentences identified as most influential by the model):
{input_block}

RELEVANT SOURCES RETRIEVED BY RAG (precedent / constitution / regulation / guide, etc.):
{retrieved_block}

TASK:
- Explain the model decision in clear, user-friendly English.
- Do not use codes such as [S#] or [R#] when citing evidence.
- Instead, show evidence at the end of each claim using the following format:

  (1) If the evidence comes from the input text:
      “The input text states: ‘…’”

  (2) If the evidence comes from the retrieved sources:
      “Source: {{"source name"}} ({{"type"}}). Brief summary: …”
      If the type is "precedent", describe it as a "precedent decision".
      Do not make arguments about a chamber or section deciding the case; this is unnecessary.

- Do not invent new facts or claims. If the evidence is insufficient, state this explicitly.

VERY IMPORTANT RULES:
1. Whenever possible, ground at least one part of the reasoning in the constitution/law or a guide/bylaw.
2. Do not make arguments about a chamber or section deciding the case; this is unnecessary.

OUTPUT FORMAT:
1) First, provide the predicted class and a brief conclusion about it (1–2 sentences).
2) Reasoning (4–7 bullet points).
3) Uncertainties / limitations (2–4 bullet points).
""".strip()


# =========================
# 7) FULL PIPELINE (YOUR "INPUT TEXT" BLOCK)
# =========================
SYS_MSG = SystemMessage(content=(
    "You are a legal analytics assistant. Your task is to explain the classification model’s decision in clear, user-friendly English. "
    "Base your explanation only on the provided EVIDENCE SENTENCES and RETRIEVED SOURCES. "
    "Do not invent new facts or claims. When something is uncertain, explicitly say, “This cannot be determined from the available information.” "
    "Provide a source reference at the end of every claim."
))

def run_all(text, ig_steps=24, top_sent_k=10, retr_k=12, norm="sum"):
    text = (text or "").strip()
    if not text:
        return "Error", "Please enter an application text."

    result = top_k_sentences_full_doc(
        model=model,
        tokenizer=tokenizer,
        text=text,
        device=DEVICE,
        pipeline_main=pipeline_main,
        pipeline_sub=pipeline_sub,
        k=top_sent_k,
        steps=ig_steps,
        max_length=MAX_LENGTH,
        norm=norm
    )

    top_k_sentences = [result["top_sentences"][i][3] for i in range(min(top_sent_k, len(result["top_sentences"])))]
    retrieved_points = qdrant_search_raw(
        client,
        collection_name=QDRANT_COLLECTION,
        query_text=" ".join(top_k_sentences),
        model_name=E5_MODEL_NAME,
        top_k=retr_k
    )

    prompt = build_user_friendly_prompt(
        pred_label=result["decision"],
        influential_sentences=top_k_sentences,
        retrieved_points=retrieved_points
    )

    resp = llm.invoke([
        SystemMessage(content=(
            "You are a legal analytics assistant. Your task is to explain the classification model’s decision in clear, user-friendly English. "
            "Base your explanation only on the provided EVIDENCE SENTENCES and RETRIEVED SOURCES. "
            "Do not invent new facts or claims. When something is uncertain, explicitly say, “This cannot be determined from the available information.” "
            "Provide a source reference at the end of every claim."
        )),
        HumanMessage(content=prompt)
    ])

    return result["decision"], resp.content



# =========================
# 8) GRADIO UI
# =========================
with gr.Blocks(title="Constitutional Court Application Analysis (Decision + Explanation)") as demo:
    gr.Markdown("""
# 🏛️ Constitutional Court Application Analysis
Enter the **Application Text** below, preferably including the **Facts and Circumstances** sections.
""")

    inp = gr.Textbox(lines=14, label="Application Text")

    with gr.Accordion("Advanced Settings", open=False):
        ig_steps = gr.Slider(8, 48, value=24, step=1, label="IG Steps (higher = slower, more stable)")
        top_sent_k = gr.Slider(5, 20, value=10, step=1, label="Top-K Influential Sentences")
        retr_k = gr.Slider(4, 20, value=12, step=1, label="Retrieval Top-K")
        norm = gr.Dropdown(choices=["sum", "mean", "sqrt"], value="sum", label="Sentence Score Normalization")

    btn = gr.Button("Analyze", variant="primary")

    out_decision = gr.Textbox(label="Predicted Class")
    out_expl = gr.Textbox(label="Reasoned Explanation", lines=34)

    btn.click(
        fn=run_all,
        inputs=[inp, ig_steps, top_sent_k, retr_k, norm],
        outputs=[out_decision, out_expl]
    )

demo.launch()
