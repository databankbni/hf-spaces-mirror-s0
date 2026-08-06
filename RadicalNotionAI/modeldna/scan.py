#!/usr/bin/env python3
"""
modeldna Stage 1 HF Scanner — core logic.
Given a HuggingFace model_id, validates architectural claims against the
ModelAtlas reference database. No weight download needed — uses config.json only.

This is the heart of the modeldna 'test before you download' feature.
"""
from __future__ import annotations
import json, hashlib, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import requests

HF_API = "https://huggingface.co"
HF_DATASET = "RadicalNotionAI/modelatlas-reference"
DB = "postgresql:///modelatlas?host=/var/run/postgresql&port=5433&user=tim"

# In-process cache — loaded once per worker, refreshes when the file changes
_REF_DF = None
_REF_LOADED_AT: float = 0.0
_REF_TTL = 3600  # reload at most once per hour


def _load_reference_df():
    """Load ModelAtlas reference parquet. Tries local snapshot first, then HF dataset."""
    global _REF_DF, _REF_LOADED_AT
    now = time.time()
    if _REF_DF is not None and (now - _REF_LOADED_AT) < _REF_TTL:
        return _REF_DF

    import pandas as pd

    # 1. Local snapshot (fast, used in dev / on local server)
    local_path = Path(__file__).parent.parent / "snapshots" / "modeldna_reference.parquet"
    if local_path.exists():
        try:
            _REF_DF = pd.read_parquet(local_path)
            _REF_LOADED_AT = now
            return _REF_DF
        except Exception:
            pass

    # 2. HF dataset (used on HF Space — downloaded and cached by huggingface_hub)
    try:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(
            repo_id=HF_DATASET,
            filename="modeldna_reference.parquet",
            repo_type="dataset",
        )
        _REF_DF = pd.read_parquet(path)
        _REF_LOADED_AT = now
        return _REF_DF
    except Exception:
        pass

    return None

def reference_count() -> int:
    """Number of models in the ModelAtlas fingerprint reference (for the 'how we know' moat line)."""
    try:
        df = _load_reference_df()
        return int(len(df)) if df is not None else 0
    except Exception:
        return 0

# Known base model reference configs (canonical identifiers)
KNOWN_BASES = {
    "qwen3_5_text": {
        "name": "Qwen3.5 (dense)",
        "vocab_size": 248320,
        "model_type_patterns": ["qwen3_5_text", "qwen3_5"],
    },
    "qwen3_5_moe_text": {
        "name": "Qwen3.5 MoE",
        "vocab_size": 248320,
        "model_type_patterns": ["qwen3_5_moe_text", "qwen3_5_moe"],
    },
    "qwen3": {
        "name": "Qwen3",
        "vocab_size": [151936, 152064, 151851, 151670],
        "model_type_patterns": ["qwen3"],
        # 151936/152064 = standard Qwen3; 151851 = BAAI OpenSeek (domain token swap);
        # 151670 = OpenBMB SciCore-Mol (chemistry tokenizer variant)
    },
    "qwen2": {
        "name": "Qwen2.5 (incl. VL)",
        "vocab_size": [151936, 152064, 151680],
        "model_type_patterns": ["qwen2"],
        # 151680 = MiMo-Embodied-7B uses Qwen2.5-VL backbone with this vocab
    },
    "llama3": {
        "name": "Llama 3.x",
        "vocab_size": 128256,
        "model_type_patterns": ["llama"],
        "num_key_value_heads_hint": [8, 32],
    },
    "llama2": {
        "name": "Llama 2",
        "vocab_size": 32000,
        "model_type_patterns": ["llama"],
    },
    "mistral": {
        "name": "Mistral 7B family",
        "vocab_size": 32000,
        "model_type_patterns": ["mistral", "mixtral"],
    },
    "deepseek_v3": {
        "name": "DeepSeek V3/R1",
        "vocab_size": 129280,
        "model_type_patterns": ["deepseek_v3", "deepseek_v2"],
        "kv_lora_rank": 512,
    },
    "gemma": {
        "name": "Gemma family",
        "vocab_size": [256000, 262144],
        "model_type_patterns": ["gemma"],
    },
    "nemotron_h": {
        "name": "NemotronH (NVIDIA Mamba+MoE hybrid)",
        "vocab_size": 131072,
        "model_type_patterns": ["nemotron_h", "nemotronh"],
    },
    "ministral3": {
        "name": "Mistral 3.x (medium/large dense)",
        "vocab_size": 131072,
        "model_type_patterns": ["ministral3", "mistral3"],
        # Mistral Medium 3.5, hidden=12288, 88 layers — dense ~128B
        # Multimodal wrapper uses model_type=mistral3; LLM backbone is ministral3
        # vocab 131072 overlaps with NemotronH — exact model_type match scores higher
    },
    "glm4": {
        "name": "ZhipuAI GLM-4.x (4.5 / 4.6 / 4.7 / 4.6V text backbone)",
        "vocab_size": [151552, 151936, 154880],
        "model_type_patterns": ["glm4v_moe_text", "glm4v_moe", "glm4_moe_lite", "glm4_moe", "glm4", "chatglm"],
        # 151552 = GLM-4.5/4.6 dense+MoE and 4.6V multimodal text backbone
        # 154880 = GLM-4.7 series (including 4.7-Flash, glm4_moe_lite)
    },
    "seed_oss": {
        "name": "ByteDance Seed-OSS (dense)",
        "vocab_size": 155136,
        "model_type_patterns": ["seed_oss"],
        # Dense GQA, RoPE θ=1e7, 512K context, 80→8 KV heads
    },
    "bailing_v2": {
        "name": "AntGroup Bailing-V2 / V2.5 (inclusionAI Ling)",
        "vocab_size": 157184,
        "model_type_patterns": ["bailing_hybrid", "bailing_moe", "bailingmm_moe_v2_lite"],
        # V2 = bailing_moe; V2.5 = bailing_hybrid (MLA + linear-attn + MTP)
        # bailingmm_moe_v2_lite = Ming-flash-omni multimodal lite variant
    },
    "llada2": {
        "name": "inclusionAI LLaDA2 (discrete-diffusion MoE)",
        "vocab_size": [157184, 173568],
        "model_type_patterns": ["llada2_moe", "llada2"],
        # 157184 = text-only discrete diffusion (flash, base)
        # 173568 = Uni any-to-any variant — adds ~16K image codebook tokens to vocab
        # Non-autoregressive masked LM; separate family from Bailing-V2 by training paradigm
    },
    "kimi": {
        "name": "Moonshot Kimi (K2, Kimi-Linear)",
        "vocab_size": 163840,
        "model_type_patterns": ["kimi_linear", "kimi"],
        # Kimi-Linear adds linear_attn_config + MLA + MTP on Kimi MoE backbone
    },
    "ernie4_5_moe": {
        "name": "Baidu ERNIE 4.5 (text MoE)",
        "vocab_size": 103424,
        "model_type_patterns": ["ernie4_5_moe"],
        # Text MoE line: 21B-A3B (28L, hidden 2560), 300B-A47B. Shares the 103424 ERNIE
        # tokenizer with the VL line. exact `ernie4_5_moe` scores above the VL base's
        # startswith on `ernie4_5_moe_vl`, so VL models still resolve to ernie4_5_vl.
    },
    "ernie4_5_vl": {
        "name": "Baidu ERNIE 4.5 VL (MoE multimodal)",
        "vocab_size": 103424,
        "model_type_patterns": ["ernie4_5_moe_vl", "ernie4_5_vl"],
    },
    "qianfan_vl": {
        "name": "Baidu Qianfan-VL (dense multimodal)",
        "vocab_size": 182025,
        "model_type_patterns": ["qianfanvl_chat", "qianfan"],
        # Distinct Baidu tokenizer from ERNIE — two separate VLM lineages
        # model_type is qianfanvl_chat; qianfan prefix catches future variants
    },
    "interns1": {
        "name": "InternLM S1 (dense, long-chain reasoning)",
        "vocab_size": 153216,
        "model_type_patterns": ["interns1"],
    },
    "pangu_pro_moe": {
        "name": "FreedomIntelligence Pangu-R (Huawei Pangu-Pro-MoE)",
        "vocab_size": 153600,
        "model_type_patterns": ["pangupromoe"],
        # model_type in config is "PanguProMoE" — lowercased to pangupromoe for matching
        # MoE 80/8, first_k_dense_replace=4, hidden=4608, layers=50
    },
    "iquest_coder": {
        "name": "IQuest-Coder",
        "vocab_size": 76800,
        "model_type_patterns": ["iquestcoder"],
        # Code-specialized tokenizer (76800 = code-token-dense). Dense GQA 32→2.
        # Same family across 7B (14 layers) and 40B (80 layers).
    },
    "minicpm": {
        "name": "OpenBMB MiniCPM",
        "vocab_size": 73448,
        "model_type_patterns": ["minicpm"],
        # MiniCPM family (AgentCPM-Report etc.). Heavy GQA 32→2.
    },
    "step3_5": {
        "name": "StepFun Step-3.5 Flash",
        "vocab_size": [128815, 128896],
        "model_type_patterns": ["step3p5"],
        # Per-layer RoPE schedule: every 4th layer gets long-context theta (1e6/5e6),
        # others get 1e4. Sliding-window=512. First StepFun entry with multi-freq RoPE.
    },
    "mimo_v2": {
        "name": "Xiaomi MiMo V2.x",
        "vocab_size": 152576,
        "model_type_patterns": ["mimo_v2"],
        # V2.5: hidden=4096, 48 layers; V2.5-Pro: hidden=6144, 70 layers
    },
    "emu3": {
        "name": "BAAI Emu3 family (unified vision+text)",
        "vocab_size": [184622, 282926],
        "model_type_patterns": ["emu3"],
        # Emu3-Stage1 vocab=184622; Emu3.5 vocab=282926 (expanded vision codebook)
        # Emu3.5 also adds hidden 4096→5120, layers 32→64, sliding_window=4096
    },
    "hunyuan_v1": {
        "name": "Tencent Hunyuan V1 (dense + MoT multimodal)",
        "vocab_size": 120818,
        "model_type_patterns": ["hunyuan_v1_dense", "hunyuan_vl_mot", "hunyuan"],
        # Catches HY-Embodied-0.5 and HY-1.8B variants; MoT = Mixture of Tokens
    },
    "gpt_oss": {
        "name": "OpenAI gpt-oss (via InternVL3.5 wrapper)",
        "vocab_size": 200028,
        "model_type_patterns": ["gpt_oss"],
        # Caught via lifted text_config; InternVL3.5-GPT-OSS-20B uses this backbone
    },
    "valley": {
        "name": "ByteDance Valley (video-language)",
        "vocab_size": [151675, 151679],
        "model_type_patterns": ["valley"],
        # Valley-Eagle-7B (151675) and Valley2.5 (151679) — close but distinct vocabs
    },
    "starcoder2": {
        "name": "BigCode StarCoder2",
        "vocab_size": 49152,
        "model_type_patterns": ["starcoder2", "gpt_bigcode"],
        # 3B: hidden=3072/30L (97K dl), 7B: hidden=4608/32L, 15B: hidden=6144/40L
        # gpt_bigcode = tiny_starcoder_py and early StarCoder variants (234K dl)
        # Code-specialized tokenizer (49152 tokens)
    },
    "zaya": {
        "name": "Zyphra ZAYA1 (Global Attn + SWA + MoE)",
        "vocab_size": 262272,
        "model_type_patterns": ["zaya", "zaya1_vl"],
        # Global attention alternating with Sliding Window Attention (4K window) + MoE
        # CCA (Cached Context Attention) is Zyphra's proprietary KV-efficient attn variant
        # 8B:  hidden=2048, 80 layers,  16 experts, 4B active
        # 74B: hidden=4096, 120 layers, 24 experts, 4B active, GQA 16→2
        # Depth (120L at 74B) enabled by SWA — halves KV cache vs all-global attention
        # vocab ≈ Gemma tokenizer + 128 extra tokens; trained on AMD MI300x
        # 74B-Preview is pre-RL reasoning base (no RLHF/instruct tuning)
    },
    "zamba2": {
        "name": "Zyphra Zamba2 (Mamba2 + shared-attention hybrid)",
        "vocab_size": [32000, 32064],
        "model_type_patterns": ["zamba2"],
        # SSM hybrid: majority Mamba2 blocks with a single shared full-attention block
        # applied periodically via skip connections. 1.2B (38L, hidden 2048),
        # 7B (81L, hidden 3584). vocab 32000 (Llama-2 tokenizer); VL variant 32064.
    },
    "hunyuan_v3": {
        "name": "Tencent Hunyuan V3 / Hy-MT2 (MoE)",
        "vocab_size": 120832,
        "model_type_patterns": ["hy_v3"],
        # Hy-MT2 series: 1.8B dense, 7B dense, 30B-A3B MoE (128E/8A).
        # 48 layers, hidden=2048 for MoE tier. QK norm. HYV3ForCausalLM.
    },
    "mellum": {
        "name": "JetBrains Mellum (code-specialized MoE)",
        "vocab_size": 98304,
        "model_type_patterns": ["mellum"],
        # Mellum2-12B-A2.5B: 28 layers all-MoE from layer 0, 64E/8A, GQA 32q/4kv (8:1),
        # QK norm, custom MellumTopKRouter, 128K context, hidden=2304.
        # vocab 98304 = 384×256 — code-optimized tokenizer (JetBrains IDE corpora).
        # Mellum-4B (prior gen): 3.4B dense, 30 layers, hidden=3072, no MoE.
    },
    "plamo": {
        "name": "Preferred Networks PLaMo (plamo / plamo2 / plamo3, JP)",
        "vocab_size": [50112, 100000, 107520],
        "model_type_patterns": ["plamo3", "plamo2", "plamo"],
        # PlamoForCausalLM (100B, vocab 50112) / Plamo2ForCausalLM (plamo-2-8b, vocab 100000,
        # Samba-style Mamba+attention hybrid) / Plamo3ForCausalLM (plamo-3-nict-2b/8b, vocab 107520).
        # Gated repos; config-only scan needs auth (public Space returns None for gated).
    },
    "inkling": {
        "name": "Thinking Machines Inkling (omni-modal MoE)",
        "vocab_size": 201024,
        "model_type_patterns": ["inkling_mm_model", "inkling"],
        # Thinking Machines Lab debut (ex-OpenAI team), 2026-07. ~974B total / ~40B active sparse MoE:
        # 256 routed experts (6 active + 2 shared), 8 MTP layers, GQA (NOT MLA), hidden 6144, 66L.
        # Omni-modal (text+vision+audio), InklingForConditionalGeneration.
        # vocab 201024 + eos 200006 = OpenAI o200k/harmony tokenizer heritage — the ex-OpenAI tell.
    },
    "needle": {
        "name": "Cactus Needle (26M pure-attention encoder-decoder, edge tool-calling)",
        "vocab_size": 8192,
        "model_type_patterns": ["needle"],
        # Cactus Compute Needle, NeedleForCausalLM (actually encoder-decoder): 12 enc + 8 dec layers,
        # PURE ATTENTION (no FFN), GQA 8H/4KV, RoPE, ZCRMSNorm (zero-centered), gated residuals,
        # d_model 512, vocab 8192 SentencePiece, ~26M params, INT4 QAT. Distilled from Gemini 3.1
        # (honestly disclosed — distillation leaves no weight-level trace). On-device function-calling.
    },
}


def fetch_config(model_id: str) -> Optional[dict]:
    """Fetch config.json from HuggingFace. Returns None on failure."""
    url = f"{HF_API}/{model_id}/resolve/main/config.json"
    try:
        headers = {}
        token = os.environ.get("HF_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None


def fetch_model_metadata(model_id: str) -> dict:
    """Fetch HF model metadata (downloads, likes, author, tags, file list)."""
    try:
        headers = {}
        token = os.environ.get("HF_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = requests.get(f"{HF_API}/api/models/{model_id}", headers=headers, timeout=10)
        r.raise_for_status()
        d = r.json()
        return {
            "downloads": d.get("downloads", 0),
            "likes": d.get("likes", 0),
            "author": d.get("author", ""),
            "tags": d.get("tags", []),
            "pipeline_tag": d.get("pipeline_tag", ""),
            "base_model": d.get("cardData", {}).get("base_model", ""),
            "license": d.get("cardData", {}).get("license", ""),
            "created_at": d.get("createdAt", ""),
            "last_modified": d.get("lastModified", ""),
            "files": [s.get("rfilename", "") for s in d.get("siblings", [])],
        }
    except Exception:
        return {}


# ── GGUF support (header-only; no weight download / dequantization) ───────────
import struct

_GGUF_MAGIC = b"GGUF"
# value type -> fixed byte size (None = variable: STRING/ARRAY handled specially)
_GGUF_SCALAR = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_GGUF_STRING, _GGUF_ARRAY = 8, 9


def _gguf_read_str(buf, off):
    (ln,) = struct.unpack_from("<Q", buf, off); off += 8
    s = buf[off:off + ln].decode("utf-8", "replace"); off += ln
    return s, off


def _gguf_skip_value(buf, off, vtype):
    """Advance past a value of the given type; return (extracted_string_or_None, new_off)."""
    if vtype in _GGUF_SCALAR:
        return None, off + _GGUF_SCALAR[vtype]
    if vtype == _GGUF_STRING:
        s, off = _gguf_read_str(buf, off)
        return s, off
    if vtype == _GGUF_ARRAY:
        (etype,) = struct.unpack_from("<I", buf, off); off += 4
        (cnt,) = struct.unpack_from("<Q", buf, off); off += 8
        for _ in range(cnt):
            if etype in _GGUF_SCALAR:
                off += _GGUF_SCALAR[etype]
            elif etype == _GGUF_STRING:
                _, off = _gguf_read_str(buf, off)
            else:
                raise ValueError(f"nested array type {etype}")
        return None, off
    raise ValueError(f"unknown gguf value type {vtype}")


def parse_gguf_metadata(buf: bytes) -> dict:
    """Parse GGUF metadata KV pairs from the file header bytes. Returns {key: str_value}
    for string-valued keys (architecture, name, chat_template, etc.). Tolerates truncation."""
    if buf[:4] != _GGUF_MAGIC:
        return {}
    off = 4
    (_ver,) = struct.unpack_from("<I", buf, off); off += 4
    off += 8  # tensor_count (uint64) — skip
    (kv_count,) = struct.unpack_from("<Q", buf, off); off += 8
    out = {}
    for _ in range(kv_count):
        try:
            key, off = _gguf_read_str(buf, off)
            (vtype,) = struct.unpack_from("<I", buf, off); off += 4
            val, off = _gguf_skip_value(buf, off, vtype)
            if val is not None:
                out[key] = val
        except (struct.error, ValueError, IndexError):
            break  # ran past the fetched header window — return what we have
    return out


def fetch_gguf_metadata(model_id: str, max_bytes: int = 12_000_000) -> dict:
    """Find a .gguf file in the repo and range-fetch its header to parse metadata.
    No full download. Returns {} on failure."""
    headers = {}
    token = os.environ.get("HF_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(f"{HF_API}/api/models/{model_id}", headers=headers, timeout=10)
        files = [s["rfilename"] for s in r.json().get("siblings", [])]
    except Exception:
        return {}
    ggufs = [f for f in files if f.lower().endswith(".gguf")]
    # prefer a single-file / first shard
    ggufs.sort(key=lambda f: ("00001" not in f, f))
    for f in ggufs[:1]:
        try:
            h = dict(headers); h["Range"] = f"bytes=0-{max_bytes}"
            rr = requests.get(f"{HF_API}/{model_id}/resolve/main/{f}", headers=h, timeout=30)
            if rr.status_code in (200, 206):
                md = parse_gguf_metadata(rr.content)
                if md:
                    md["_gguf_file"] = f
                    return md
        except Exception:
            continue
    return {}


def resolve_gguf_source(model_id: str, metadata: dict, gguf_md: dict) -> Optional[str]:
    """Best-effort upstream full-weights repo for a GGUF quant."""
    # 1) explicit base_model tag on the GGUF repo
    bm = metadata.get("base_model")
    if bm:
        return bm if isinstance(bm, str) else (bm[0] if bm else None)
    # 2) GGUF metadata general.base_model
    for k in ("general.base_model", "general.base_model.0.repo_url", "general.source.repo"):
        if gguf_md.get(k):
            v = gguf_md[k]
            return v.split("huggingface.co/")[-1].strip("/") if "huggingface.co" in v else v
    # 3) name heuristic: strip common quant/format suffixes
    name = model_id.split("/")[-1]
    stripped = re.sub(r"[-_.]?(GGUF|gguf|Q\d[_A-Za-z0-9]*|i1|IQ\d[_A-Za-z0-9]*|imatrix|"
                      r"fp16|bf16|f16|MLX|mlx|AWQ|GPTQ|NVFP4|mxfp\d+|HyperQuant|SHQ8|ROCmFP4|COHERENT)$",
                      "", name)
    while stripped != name:  # strip repeated suffixes
        name, stripped = stripped, re.sub(
            r"[-_.]?(GGUF|gguf|Q\d[_A-Za-z0-9]*|i1|IQ\d[_A-Za-z0-9]*|imatrix|fp16|bf16|f16|"
            r"MLX|mlx|AWQ|GPTQ|NVFP4|mxfp\d+|HyperQuant|SHQ8|ROCmFP4|COHERENT)$", "", stripped)
    org = model_id.split("/")[0]
    return f"{org}/{stripped}" if stripped and stripped != model_id.split("/")[-1] else None


def fetch_chat_template(model_id: str) -> str:
    """Fetch the chat template (config-only, no weights). Checks tokenizer_config.json's
    chat_template field and the standalone chat_template.jinja. Returns "" on failure."""
    headers = {}
    token = os.environ.get("HF_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    parts = []
    for fname in ("tokenizer_config.json", "chat_template.jinja"):
        try:
            r = requests.get(f"{HF_API}/{model_id}/resolve/main/{fname}", headers=headers, timeout=15)
            if r.status_code != 200:
                continue
            if fname.endswith(".json"):
                ct = r.json().get("chat_template", "")
                if isinstance(ct, list):  # some templates are lists of {name, template}
                    ct = " ".join(str(x.get("template", "")) for x in ct)
                parts.append(ct or "")
            else:
                parts.append(r.text)
        except Exception:
            continue
    return "\n".join(p for p in parts if p)


# Base-org / lab names whose denial in a system prompt indicates provenance concealment
_BASE_ORG_TERMS = [
    "qwen", "alibaba", "llama", "meta", "mistral", "mixtral", "deepseek",
    "gemma", "google", "gpt", "openai", "anthropic", "claude", "yi", "01-ai",
    "phi", "microsoft", "falcon", "glm", "zhipu", "baichuan", "internlm",
]
# Instruction verbs that, combined with a base-org name, indicate an identity scrub
_SCRUB_DENIAL = re.compile(
    r"(never|do not|don'?t|must not|should not|refuse to)\s+(claim|say|state|admit|identify|mention|reveal|acknowledge)",
    re.IGNORECASE,
)
_SCRUB_ASSERT = re.compile(
    r"(always identify (your ?self|as)|your (name|identity) is|you (are|were) (created|developed|made|built|trained) by)",
    re.IGNORECASE,
)
_SCRUB_PERMANENCE = re.compile(
    r"(permanent|override[s]? (conflicting|any|all)|regardless of|even if (asked|instructed)|cannot be changed)",
    re.IGNORECASE,
)


def detect_provenance_scrubbing(chat_template: str) -> Optional[dict]:
    """Stage-1 detector: does the chat template inject a default system prompt that
    instructs the model to DENY its true origin (name a base org after a denial verb)?
    This is the Qwythos pattern. Returns a flag dict or None."""
    if not chat_template:
        return None
    text = chat_template
    has_denial = bool(_SCRUB_DENIAL.search(text))
    has_assert = bool(_SCRUB_ASSERT.search(text))
    has_perm = bool(_SCRUB_PERMANENCE.search(text))
    # which base orgs are named in the template
    orgs = sorted({t for t in _BASE_ORG_TERMS if re.search(r"\b" + re.escape(t) + r"\b", text, re.IGNORECASE)})
    # Strong signal: a denial verb AND >=2 base-org names named for denial (e.g. "never claim
    # to be Qwen, Alibaba, OpenAI, Anthropic") — an explicit lineage scrub.
    if has_denial and len(orgs) >= 2:
        return {
            "type": "PROVENANCE_SCRUBBING",
            "severity": "HIGH",
            "orgs_denied": orgs,
            "explanation": (
                "The chat template injects a default system prompt that instructs the model to "
                f"DENY its origin — it names {', '.join(orgs)} in a 'never claim to be…' style "
                "instruction" + (", marked permanent/overriding user instructions" if has_perm else "")
                + ". Every user of the standard chat template inherits this. This actively "
                "conceals the model's true base lineage at inference time."
            ),
        }
    # Weaker signal: hard-coded identity assertion with permanence, no explicit denial
    if has_assert and has_perm:
        return {
            "type": "IDENTITY_OVERRIDE",
            "severity": "MEDIUM",
            "explanation": (
                "The chat template hard-codes a permanent, override-all identity in its default "
                "system prompt. Not necessarily deceptive, but it prevents the model from "
                "reporting its own provenance and overrides user/system instructions."
            ),
        }
    return None


# ── DNA-001: provenance risk scoring ──────────────────────────────────────────
# Points per flag type (heaviest = active deception). Score clamps to 100; 0 flags = 0 = clean.
_FLAG_WEIGHTS = {
    "PROVENANCE_SCRUBBING": 45,          # actively hides its lineage — worst
    "IMPOSSIBLE_WEIGHT_PROVENANCE": 30,  # claims a closed brand it can't be built on
    "NAMING_MISATTRIBUTION": 20,         # sells a brand that isn't the base
    "IDENTITY_OVERRIDE": 15,             # hard-coded identity, not necessarily deceptive
    "NAME_MISMATCH": 15,
    "UNVERIFIABLE_CLAIM": 10,
}

def _risk_score(flags: list) -> tuple:
    """Aggregate flags into a 0–100 score + band. Higher = more provenance risk."""
    score = 0
    for f in flags:
        w = _FLAG_WEIGHTS.get(f.get("type"), 8)
        if f.get("severity") == "MEDIUM":
            w = int(w * 0.85)
        score += w
    score = min(100, score)
    band = ("CLEAN" if score == 0 else "LOW" if score <= 25
            else "MODERATE" if score <= 55 else "HIGH")
    return score, band


def _engine_panel(flags: list, arch_state: str, chat_template_seen: bool) -> list:
    """DNA-003: group detectors into named 'engines' with per-engine verdicts (VirusTotal-style).
    arch_state: 'confirmed' | 'original' | 'new' | 'unknown'."""
    by_type = {f.get("type") for f in flags}
    def verdict(triggered, ran=True):
        return "🔴 flagged" if triggered else ("✅ pass" if ran else "➖ not run")
    arch_row = {
        "confirmed": ("✅ pass", "base architecture identified against ModelAtlas reference"),
        "original": ("✅ pass", "recognized original architecture, catalogued in ModelAtlas"),
        "new": ("🆕 new", "novel architecture from a known lab; not yet catalogued"),
        "unknown": ("❓ unrecognized", "no known base match"),
    }.get(arch_state, ("❓ unrecognized", "no known base match"))
    return [
        {"engine": "Architecture Match", "status": arch_row[0], "detail": arch_row[1]},
        {"engine": "Provenance Integrity",
         "status": verdict({"PROVENANCE_SCRUBBING", "IDENTITY_OVERRIDE"} & by_type, chat_template_seen),
         "detail": "chat-template lineage scrub / identity override"},
        {"engine": "Naming & Attribution",
         "status": verdict({"NAMING_MISATTRIBUTION", "NAME_MISMATCH", "IMPOSSIBLE_WEIGHT_PROVENANCE",
                            "UNVERIFIABLE_CLAIM"} & by_type),
         "detail": "name vs actual base; closed-brand / impossible claims"},
        {"engine": "License Compliance", "status": "➖ not run",
         "detail": "base-license vs derivative usage — coming soon"},
        {"engine": "Safety Profile", "status": "➖ not run",
         "detail": "behavioral refusal / safety analysis (Stage 2) — coming soon"},
    ]


# Closed-weight brands: no weights ever released, so weight transfer is IMPOSSIBLE (not merely
# unverifiable). Distillation-via-outputs is the only possible link and leaves no weight trace.
_CLOSED_WEIGHT_BRANDS = {
    "claude": "Anthropic Claude", "anthropic": "Anthropic Claude",
    "mythos": "Anthropic Mythos (unreleased)", "fable": "Anthropic Fable (released; weights closed)",
    "gpt": "OpenAI GPT", "chatgpt": "OpenAI GPT", "openai": "OpenAI GPT",
    "gemini": "Google Gemini", "grok": "xAI Grok",
}


def detect_claimed_base(model_id: str, config: dict, metadata: dict) -> dict:
    """Detect what base model a model claims to be derived from."""
    claims = {}
    name = model_id.split("/")[-1].lower()
    # Explicit base_model field
    if metadata.get("base_model"):
        claims["explicit_base"] = metadata["base_model"]
    # Name-based detection
    name_signals = []
    for term, base_key in [
        ("qwen3.5", "qwen3_5"), ("qwen3-5", "qwen3_5"), ("qwen35", "qwen3_5"),
        ("qwen3", "qwen3"), ("qwen2.5", "qwen2"), ("qwen2", "qwen2"),
        ("llama-3", "llama3"), ("llama3", "llama3"), ("llama-2", "llama2"),
        ("mistral", "mistral"), ("mixtral", "mistral"),
        ("deepseek", "deepseek_v3"), ("gemma", "gemma"),
    ]:
        if term in name:
            name_signals.append(base_key)
    if name_signals:
        claims["name_implies"] = name_signals
    # Suspicious claims in name
    suspicious = []
    for term in ["claude", "gpt", "chatgpt", "openai", "gemini", "anthropic", "mythos", "fable"]:
        if term in name:
            suspicious.append(term)
    if suspicious:
        claims["suspicious_name_terms"] = suspicious
    return claims


def stage1_screen(model_id: str, config: dict) -> dict:
    """
    Stage 1: Architecture screening against ModelAtlas reference.
    Returns a structured verdict without downloading any weights.
    Handles nested text_config (Qwen3.5/3.6, Mistral3, MiMo-V2.5 pattern).
    """
    # Lift nested LLM config into top-level when top-level vocab/hidden is absent.
    # Recurse up to 2 levels deep to handle models like Logics-MLLM where LLM backbone
    # is at thinker_config.text_config (two levels: thinker_config → text_config).
    _NESTED_KEYS = ("text_config", "llm_config", "thinker_config", "language_model")
    _SKIP_KEYS = ("text_config", "llm_config", "thinker_config", "language_model",
                  "vision_config", "audio_config", "sound_config")
    if not config.get("vocab_size"):
        for nested_key in _NESTED_KEYS:
            candidate = config.get(nested_key, {})
            if candidate:
                # One level deep
                if candidate.get("vocab_size"):
                    # Let nested model_type win over top-level wrapper type
                    outer = {k: v for k, v in config.items()
                             if k not in _SKIP_KEYS and k != "model_type"}
                    config = {**outer, **candidate}
                    break
                # Two levels deep (e.g. thinker_config.text_config)
                for inner_key in _NESTED_KEYS:
                    inner = candidate.get(inner_key, {})
                    if inner and inner.get("vocab_size"):
                        outer = {k: v for k, v in config.items()
                                 if k not in _SKIP_KEYS and k != "model_type"}
                        config = {**outer, **inner}
                        break
                else:
                    continue
                break

    vocab = config.get("vocab_size")
    model_type = (config.get("model_type") or "").lower()
    hidden = config.get("hidden_size")
    layers = config.get("num_hidden_layers")
    kv_lora = config.get("kv_lora_rank")  # MLA signal
    base_model_field = config.get("base_model") or config.get("_name_or_path", "")

    # Compute architecture signature
    key_fields = sorted([
        f"vocab={vocab}", f"type={model_type}", f"hidden={hidden}",
        f"layers={layers}", f"kv_lora={kv_lora}",
    ])
    arch_sig = hashlib.md5("|".join(str(f) for f in key_fields).encode()).hexdigest()[:12]

    # Match against known bases
    base_matches = []
    for base_key, base_info in KNOWN_BASES.items():
        score = 0
        reasons = []
        # Vocab match
        expected_vocab = base_info.get("vocab_size")
        if isinstance(expected_vocab, list):
            if vocab in expected_vocab: score += 3; reasons.append(f"vocab matches ({vocab})")
        elif vocab == expected_vocab:
            score += 3; reasons.append(f"vocab matches ({vocab})")
        # Model type match
        for pat in base_info.get("model_type_patterns", []):
            if model_type == pat:
                score += 3; reasons.append(f"model_type '{model_type}' exact"); break
            elif model_type.startswith(pat):
                score += 2; reasons.append(f"model_type '{model_type}' matches {pat}"); break
        # MLA signal
        if base_key == "deepseek_v3" and kv_lora and kv_lora > 0:
            score += 2; reasons.append(f"MLA kv_lora_rank={kv_lora}")
        if score >= 3:
            base_matches.append({
                "base": base_key,
                "name": base_info["name"],
                "confidence": "HIGH" if score >= 5 else "MODERATE",
                "score": score,
                "evidence": reasons,
            })

    # Is the scanned model itself catalogued in the ModelAtlas reference? Original /
    # first-party architectures (e.g. poolside/Laguna) are NOT derivatives of a known base;
    # recognize them as catalogued originals rather than labelling them "unrecognized".
    self_catalogued = None
    try:
        ref = _load_reference_df()
        if ref is not None:
            row = ref[ref["model_id"].str.lower() == model_id.lower()]
            if len(row):
                r0 = row.iloc[0]
                def _clean(x):  # NaN-safe: reference cols can be float('nan')
                    return x.strip() if isinstance(x, str) and x.strip() else None
                self_catalogued = {
                    "model_id": model_id,
                    "org": _clean(r0.get("org_display")) or _clean(r0.get("org")),
                    "model_type": model_type or _clean(r0.get("model_type")),
                }
    except Exception:
        pass

    # DNA-016: is the publisher a known lab? (≥3 other models catalogued in the reference)
    lab_catalogued = None
    try:
        if ref is not None and "/" in model_id:
            org = model_id.split("/")[0]
            n = int(ref["model_id"].str.lower().str.startswith(org.lower() + "/").sum())
            if n >= 3:
                lab_catalogued = {"org": org, "model_count": n}
    except Exception:
        pass

    # Query ModelAtlas reference parquet for architecturally similar models
    db_matches = []
    try:
        ref = _load_reference_df()
        if ref is not None and vocab and hidden:
            hit = ref[
                (ref["vocab_size"] == vocab) &
                (ref["hidden_size"] == hidden) &
                (~ref["model_id"].str.contains("tiny", case=False, na=False)) &
                (~ref["model_id"].str.startswith("/", na=False)) &
                (ref["model_id"].str.lower() != model_id.lower())
            ].sort_values("hf_downloads", ascending=False).head(5)
            db_matches = hit[
                ["model_id", "org_display", "hf_downloads", "total_params",
                 "technique_signature", "num_layers", "hidden_size", "vocab_size"]
            ].rename(columns={"org_display": "lab"}).to_dict("records")
    except Exception:
        pass

    # Also try local DB if available (dev / local server)
    if not db_matches:
        try:
            import psycopg2, psycopg2.extras
            conn = psycopg2.connect(DB)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT m.model_id, o.name AS lab, m.hf_downloads, m.release_date,
                       a.technique_signature, a.total_params, a.num_layers, a.hidden_size, a.vocab_size
                FROM analyses a JOIN models m ON m.id=a.model_id
                JOIN organizations o ON m.org_id=o.id
                WHERE a.is_current=true AND a.vocab_size=%s AND a.hidden_size=%s
                  AND m.model_id NOT ILIKE '%%tiny%%' AND m.model_id NOT ILIKE '/%%'
                ORDER BY m.hf_downloads DESC NULLS LAST
                LIMIT 5
            """, (vocab, hidden))
            db_matches = [dict(r) for r in cur.fetchall()]
            cur.close(); conn.close()
        except Exception:
            pass

    return {
        "arch_signature": arch_sig,
        "config_signals": {
            "model_type": model_type,
            "vocab_size": vocab,
            "hidden_size": hidden,
            "num_layers": layers,
            "has_mla": bool(kv_lora and kv_lora > 0),
            "kv_lora_rank": kv_lora,
        },
        "base_matches": sorted(base_matches, key=lambda x: -x["score"]),
        "modelatlas_similar": db_matches,
        "self_catalogued": self_catalogued,
        "lab_catalogued": lab_catalogued,
    }


def generate_verdict(
    model_id: str,
    config: dict,
    metadata: dict,
    claims: dict,
    stage1: dict,
    chat_template: str = "",
) -> dict:
    """Synthesize all signals into a human-readable verdict."""
    now = datetime.now(timezone.utc).isoformat()
    base_matches = stage1["base_matches"]
    suspicious = claims.get("suspicious_name_terms", [])

    # Headline verdict
    self_cat = stage1.get("self_catalogued")
    lab_cat = stage1.get("lab_catalogued")
    if base_matches:
        top = base_matches[0]
        if top["confidence"] == "HIGH":
            architecture_verdict = f"CONFIRMED — architecture matches {top['name']}"
        else:
            architecture_verdict = f"LIKELY — architecture consistent with {top['name']}"
        headline_confidence = top["confidence"]
    elif self_cat:
        mt = self_cat.get("model_type") or "?"
        org = self_cat.get("org")
        architecture_verdict = (
            f"RECOGNIZED — original '{mt}' architecture"
            + (f" from {org}" if org else "")
            + ", catalogued in ModelAtlas (not a derivative of a tracked base model)"
        )
        headline_confidence = "ORIGINAL"
    elif lab_cat and not suspicious:
        # not a derivative, no foreign-brand claim, published by a known lab -> a new original
        architecture_verdict = (
            f"NEW — original architecture from {lab_cat['org']} (known lab, "
            f"{lab_cat['model_count']} catalogued models); not yet in the reference"
        )
        headline_confidence = "NEW"
    else:
        architecture_verdict = "UNRECOGNIZED — architecture does not match any known base model"
        headline_confidence = "NONE"

    # Claim accuracy flags
    flags = []
    confirmed_base_name = base_matches[0]["name"] if base_matches else None

    # (1) IMPOSSIBLE_WEIGHT_PROVENANCE — closed-weight brand named, but architecture is a
    #     known open base. No weights were ever released for these brands, so weight-level
    #     provenance is impossible (not merely unverifiable).
    closed_hits = sorted({_CLOSED_WEIGHT_BRANDS[t] for t in suspicious if t in _CLOSED_WEIGHT_BRANDS})
    for brand in closed_hits:
        flags.append({
            "type": "IMPOSSIBLE_WEIGHT_PROVENANCE",
            "severity": "HIGH",
            "term": brand,
            "explanation": (
                f"The name references {brand}, whose weights have NEVER been publicly released. "
                f"Weight transfer, merging, or initialization from {brand} is therefore impossible"
                + (f" — the architecture is {confirmed_base_name}, accounting for the model." if confirmed_base_name else ".")
                + " The only possible link is training on generated outputs (distillation), which "
                "leaves no weight-level trace, cannot be verified, and may violate the provider's terms."
            ),
        })

    # (2) PROVENANCE_SCRUBBING / IDENTITY_OVERRIDE — from the chat template (config-only).
    scrub = detect_provenance_scrubbing(chat_template)
    if scrub:
        flags.append(scrub)

    # (3) NAMING_MISATTRIBUTION — name foregrounds a brand that is NOT the real base, while
    #     the real base is absent from the name ("sells X, built on Y, hides Y").
    name_l = model_id.split("/")[-1].lower()
    if confirmed_base_name and closed_hits:
        base_token = confirmed_base_name.split()[0].lower().replace("-", "")  # e.g. "qwen3.5"
        base_family = re.sub(r"[0-9.\-]", "", base_token)                     # e.g. "qwen"
        if base_family and base_family not in name_l.replace("-", ""):
            flags.append({
                "type": "NAMING_MISATTRIBUTION",
                "severity": "MEDIUM",
                "explanation": (
                    f"The model name foregrounds {', '.join(closed_hits)} but the actual base is "
                    f"{confirmed_base_name} — and '{base_family}' does not appear in the name. "
                    "The packaging markets a brand the model has no architectural claim to, while "
                    "omitting the base it is actually built from."
                ),
            })

    # (4) NAME_MISMATCH — name implies one open base, architecture says another.
    name_implied = claims.get("name_implies", [])
    if name_implied and base_matches:
        top = base_matches[0]
        top_base = top.get("name") or top.get("base") or ""
        # Match the name token against BOTH the base key ("ministral3") and the human label
        # ("Mistral 3.x …") — case-insensitive. The label carries the family word the raw
        # model_type key may not (e.g. name 'mistral' vs key 'ministral3'). Prevents false
        # NAME_MISMATCH on honestly-labeled models.
        haystack = f"{top.get('base','')} {top.get('name','')}".lower()
        if haystack.strip() and not any(n.lower() in haystack or haystack in n.lower() for n in name_implied):
            flags.append({
                "type": "NAME_MISMATCH",
                "severity": "MEDIUM",
                "explanation": f"Model name implies {name_implied} but architecture suggests {top_base}. Possible mislabeling.",
            })

    # Risk band. An UNRECOGNIZED model with no flags is UNVERIFIED, not CLEAN — we couldn't
    # identify it, so 0 deception flags is absence of evidence, not a clean bill of health.
    _risk, _band = _risk_score(flags)
    if headline_confidence == "NONE" and _risk == 0:
        _band = "UNKNOWN"

    return {
        "model_id": model_id,
        "scanned_at": now,
        "verdict": {
            "architecture": architecture_verdict,
            "base_model_confirmed": (
                base_matches[0]["name"] if base_matches
                else (f"{self_cat.get('model_type')} (original architecture)" if self_cat
                      else (f"original / new (from {lab_cat['org']})" if lab_cat else "Unknown"))
            ),
            "confidence": headline_confidence,
            "risk_score": _risk,
            "risk_band": _band,
            "engines": _engine_panel(
                flags,
                ("confirmed" if base_matches else "original" if self_cat
                 else "new" if (lab_cat and not suspicious) else "unknown"),
                bool(chat_template)),
            "flags": flags,
            "flag_count": len(flags),
            "stage": "Stage 1 (config-only — no weight download)",
        },
        "evidence": {
            "config_signals": stage1["config_signals"],
            "base_matches": stage1["base_matches"][:3],
            "modelatlas_similar": stage1["modelatlas_similar"][:3],
            "claimed_base": claims.get("explicit_base"),
            "name_implies": name_implied,
        },
        "metadata": {
            "downloads": metadata.get("downloads", 0),
            "likes": metadata.get("likes", 0),
            "license": metadata.get("license", ""),
            "created_at": metadata.get("created_at", ""),
        },
        "note": (
            "Stage 1 validates architecture from config.json only (~2KB). "
            "Stage 2 weight analysis (requires model download) provides stronger confirmation. "
            "Powered by ModelAtlas — modeldna.ai · a RadicalNotion product."
        ),
    }


_GGUF_ARCH_MAP = {
    "qwen35": "Qwen3.5", "qwen3_5": "Qwen3.5", "qwen3": "Qwen3", "qwen2": "Qwen2.5",
    "qwen35moe": "Qwen3.5/3.6 MoE", "qwen3moe": "Qwen3 MoE", "qwen2moe": "Qwen2 MoE",
    "llama": "Llama", "llama4": "Llama 4", "gemma": "Gemma", "gemma2": "Gemma", "gemma3": "Gemma",
    "phi3": "Phi-3", "mistral": "Mistral", "deepseek2": "DeepSeek V2/V3",
}


def inspect_gguf(model_id: str) -> dict:
    """OPTIONAL ACTION (offer #1): inspect a GGUF's embedded metadata (header-only, no
    download) and run the provenance detectors on the template baked into the file."""
    now = datetime.now(timezone.utc).isoformat()
    md = fetch_gguf_metadata(model_id)
    if not md:
        return {"model_id": model_id, "scanned_at": now,
                "error": "Could not read GGUF metadata header (file may be gated/missing)."}
    arch_raw = md.get("general.architecture", "")
    arch = _GGUF_ARCH_MAP.get(arch_raw, arch_raw or "unknown")
    chat_template = md.get("tokenizer.chat_template", "")

    flags = []
    # provenance scrub baked into the GGUF's template
    scrub = detect_provenance_scrubbing(chat_template)
    if scrub:
        scrub = dict(scrub); scrub["source"] = "gguf embedded chat_template"
        flags.append(scrub)
    # closed-weight brand + naming misattribution from the name
    name_l = model_id.split("/")[-1].lower()
    closed = sorted({_CLOSED_WEIGHT_BRANDS[t] for t in _CLOSED_WEIGHT_BRANDS if
                     re.search(r"\b" + re.escape(t) + r"\b", name_l)})
    for brand in closed:
        flags.append({
            "type": "IMPOSSIBLE_WEIGHT_PROVENANCE", "severity": "HIGH", "term": brand,
            "explanation": f"Name references {brand}, whose weights were never released — "
                           f"weight provenance is impossible. GGUF architecture is '{arch}'.",
        })
    arch_family = re.sub(r"[0-9.\-]", "", arch.lower())
    if closed and arch_family and arch_family not in name_l.replace("-", ""):
        flags.append({
            "type": "NAMING_MISATTRIBUTION", "severity": "MEDIUM",
            "explanation": f"Name foregrounds {', '.join(closed)} but GGUF architecture is "
                           f"{arch} — '{arch_family}' is absent from the name.",
        })

    return {
        "model_id": model_id, "scanned_at": now,
        "format": "GGUF (quantized)", "gguf_file": md.get("_gguf_file"),
        "verdict": {
            "architecture": f"CONFIRMED — GGUF architecture '{arch_raw}' = {arch}" if arch_raw
                            else "UNRECOGNIZED",
            "risk_score": _risk_score(flags)[0],
            "risk_band": _risk_score(flags)[1],
            "engines": _engine_panel(flags, "confirmed" if arch_raw else "unknown", bool(chat_template)),
            "flags": flags, "flag_count": len(flags),
            "stage": "Stage 1 (GGUF metadata — header only, no download)",
        },
        "evidence": {"gguf_general.name": md.get("general.name"),
                     "gguf_architecture": arch_raw,
                     "chat_template_present": bool(chat_template),
                     "quantization": md.get("general.quantization_version") or md.get("general.file_type")},
        "note": ("Read from the GGUF header only — no weights downloaded. The chat template "
                 "and identity behavior travel INTO the quant, so a scrub in the source is "
                 "present here too. Powered by ModelAtlas — modeldna.ai."),
    }


def scan(model_id: str) -> dict:
    """Full Stage 1 scan. Entry point."""
    t0 = time.time()

    # GGUF: no standard config.json — offer metadata inspection + source resolution.
    # Detect by name OR by the repo actually containing .gguf files (many GGUF-only repos
    # don't put "gguf" in the name, e.g. HauhauCS/Qwen3.6-...-Aggressive).
    name_lower = model_id.lower()
    metadata = fetch_model_metadata(model_id)
    files = metadata.get("files", [])
    repo_has_gguf = any(str(f).lower().endswith(".gguf") for f in files)
    # A repo is a GGUF *distribution* only if it has NO standard config.json. Repos that ship
    # a real model (config.json + safetensors) AND convenience .gguf files (e.g.
    # mixedbread-ai/mxbai-embed-large-v1) must be scanned normally, not treated as a quant.
    has_config = any(str(f) == "config.json" for f in files)
    if ("gguf" in name_lower or repo_has_gguf) and not has_config:
        gguf_md = fetch_gguf_metadata(model_id)
        source = resolve_gguf_source(model_id, metadata, gguf_md)
        offers = []
        offers.append({
            "action": "inspect_gguf", "model_id": model_id,
            "label": "Inspect this GGUF's embedded metadata (architecture + chat template) — "
                     "header-only, no download",
        })
        if source:
            offers.append({
                "action": "scan_source", "model_id": source,
                "label": f"Scan the full-weights source ({source}) — full Stage 1 + Stage 2",
            })
        arch_raw = gguf_md.get("general.architecture", "")
        return {
            "model_id": model_id,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "format": "GGUF (quantized)",
            "detected": (
                f"This is a GGUF quantization"
                + (f" of an '{arch_raw}' architecture model" if arch_raw else "")
                + (f", derived from {source}" if source else "") + ". "
                "A quant is the SAME weights at lower precision — provenance is identical to "
                "the source. The embedded chat template (and any identity scrub) travels into the file."
            ),
            "resolved_source": source,
            "offers": offers,
            "elapsed_s": round(time.time() - t0, 2),
            "note": "Powered by ModelAtlas — modeldna.ai · a RadicalNotion product.",
        }

    config = fetch_config(model_id)
    if not config:
        return {
            "model_id": model_id,
            "error": "Could not fetch config.json — model may be private, gated, or not exist on HuggingFace.",
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }
    claims = detect_claimed_base(model_id, config, metadata)
    stage1 = stage1_screen(model_id, config)
    chat_template = fetch_chat_template(model_id)
    verdict = generate_verdict(model_id, config, metadata, claims, stage1, chat_template)
    verdict["elapsed_s"] = round(time.time() - t0, 2)
    return verdict


if __name__ == "__main__":
    import sys
    model_id = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen3.5-27B"
    result = scan(model_id)
    print(json.dumps(result, indent=2, default=str))
