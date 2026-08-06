#!/usr/bin/env python3
"""
modeldna — HuggingFace Space
Interactive model provenance scanner.
Replaces the stale RadicalNotionAI/modelatlas-dashboard Space.

Deployed at: https://huggingface.co/spaces/RadicalNotionAI/modeldna
Custom domain: modeldna.ai (via HF Space custom domain setting)
"""
import gradio as gr
import json
import sys
import time
from pathlib import Path

# scan.py is in the same directory as app.py in both local hf_space/ and on HF
sys.path.insert(0, str(Path(__file__).parent))
from scan import scan, inspect_gguf, KNOWN_BASES, reference_count

# ── DNA-017: scan telemetry → HF dataset (fuels derivative discovery + demand-driven ingestion)
# Guarded on LOG_TOKEN (a fine-grained WRITE token for RadicalNotionAI/modeldna-scan-log).
# No-op if the secret isn't set, so deploying this never breaks the Space.
import os as _os, json as _json, datetime as _dt
from pathlib import Path as _Path
_SCAN_LOGGER = None
_LOG_FILE = None
try:
    _log_token = _os.environ.get("LOG_TOKEN")
    if _log_token:
        from huggingface_hub import CommitScheduler
        _LOG_DIR = _Path("scan_logs"); _LOG_DIR.mkdir(exist_ok=True)
        # DNA-017 fix: unique file per Space session. Space storage is ephemeral, so a single
        # shared scans.jsonl got wiped on every restart and the CommitScheduler then overwrote
        # the dataset copy with only post-restart rows (silent truncation). Per-session filenames
        # let each run add its own file; CommitScheduler's upload_folder never deletes the others.
        _session = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _LOG_FILE = _LOG_DIR / f"scans-{_session}-{_os.getpid()}.jsonl"
        _SCAN_LOGGER = CommitScheduler(
            repo_id="RadicalNotionAI/modeldna-scan-log", repo_type="dataset",
            folder_path=str(_LOG_DIR), every=1, token=_log_token,
            path_in_repo="data", squash_history=False,
        )
        print("[DNA-017] scan logging ENABLED -> RadicalNotionAI/modeldna-scan-log (flush every 1 min)", flush=True)
    else:
        print("[DNA-017] scan logging DISABLED: LOG_TOKEN env var not set/empty", flush=True)
except Exception as _e:
    _SCAN_LOGGER = None
    print(f"[DNA-017] scan logging DISABLED: scheduler init failed: {_e!r}", flush=True)

def log_scan(model_id: str, result: dict, source: str = "ui") -> None:
    if _SCAN_LOGGER is None:
        return
    try:
        v = result.get("verdict", {})
        rec = {
            "model_id": model_id,
            "source": source,  # "ui" (web) vs "internal-test" (our gradio_client) — for usage filtering
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "format": result.get("format", "checkpoint"),
            "architecture": v.get("architecture", "") or result.get("detected", "")[:80],
            "confidence": v.get("confidence"),
            "risk_score": v.get("risk_score"),
            "risk_band": v.get("risk_band"),
            "flag_types": [f.get("type") for f in v.get("flags", [])],
            "resolved_source": result.get("resolved_source"),
            "error": result.get("error"),
        }
        with _SCAN_LOGGER.lock:
            with open(_LOG_FILE, "a") as fh:
                fh.write(_json.dumps(rec) + "\n")
        print(f"[DNA-017] logged scan: {model_id} ({rec['confidence']}/{rec['risk_band']})", flush=True)
    except Exception as _e:
        print(f"[DNA-017] log_scan failed for {model_id}: {_e!r}", flush=True)

# ── Discovery: find derivatives that may not attribute properly ────────────

def find_unattributed_derivatives(base_match: str, scanned_id: str) -> list[dict]:
    """
    Query the scan results database for models sharing the same base
    that don't declare attribution to their source.
    Returns models that appear derivative but lack proper attribution.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            "postgresql:///modelatlas?host=/var/run/postgresql&port=5433&user=tim"
        )
        cur = conn.cursor()
        # Find models in the scan results that match this base but lack attribution
        # (placeholder query — will be populated as scans accumulate)
        cur.execute("""
            SELECT model_id, confirmed_base, has_attribution, downloads
            FROM modeldna_scans
            WHERE confirmed_base = %s
              AND model_id != %s
              AND (has_attribution = false OR has_attribution IS NULL)
            ORDER BY downloads DESC NULLS LAST
            LIMIT 5
        """, (base_match, scanned_id))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{"model_id": r[0], "confirmed_base": r[1], "downloads": r[3]} for r in rows]
    except Exception:
        return []


def store_scan_result(result: dict) -> None:
    """Store a scan result for future derivative discovery."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            "postgresql:///modelatlas?host=/var/run/postgresql&port=5433&user=tim"
        )
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS modeldna_scans (
                id SERIAL PRIMARY KEY,
                model_id TEXT UNIQUE,
                confirmed_base TEXT,
                confidence TEXT,
                has_attribution BOOLEAN,
                flag_count INT,
                downloads INT,
                scanned_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        v = result.get("verdict", {})
        m = result.get("metadata", {})
        e = result.get("evidence", {})
        has_attr = bool(e.get("claimed_base"))
        cur.execute("""
            INSERT INTO modeldna_scans
              (model_id, confirmed_base, confidence, has_attribution, flag_count, downloads)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_id) DO UPDATE
              SET confidence=EXCLUDED.confidence,
                  has_attribution=EXCLUDED.has_attribution,
                  flag_count=EXCLUDED.flag_count,
                  downloads=EXCLUDED.downloads,
                  scanned_at=now()
        """, (
            result.get("model_id"),
            v.get("base_model_confirmed"),
            v.get("confidence"),
            has_attr,
            v.get("flag_count", 0),
            m.get("downloads", 0),
        ))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass  # graceful — don't break the scan if storage fails


_RISK_EMOJI = {"CLEAN": "🟢", "LOW": "🟡", "MODERATE": "🟠", "HIGH": "🔴", "UNKNOWN": "⚪"}
_ATTRIB_FLAGS = {"IMPOSSIBLE_WEIGHT_PROVENANCE", "NAMING_MISATTRIBUTION", "NAME_MISMATCH", "UNVERIFIABLE_CLAIM"}
_DECEPTION_FLAGS = {"PROVENANCE_SCRUBBING", "IDENTITY_OVERRIDE"}


def _claimed_brand(flags: list):
    """The closed/foreign brand a deceptive name is riding on (for the headline subtitle)."""
    for f in flags:
        if f.get("type") in ("IMPOSSIBLE_WEIGHT_PROVENANCE", "NAMING_MISATTRIBUTION") and f.get("term"):
            return f["term"]
    return None


def _headline(v: dict, base_matches: list) -> tuple[str, str, str]:
    """DNA-018: verdict-first headline. Verb tracks the FINDING, emoji tracks the RISK.
    Returns (emoji, verb, subtitle). Never labels a misattributed model with a green check."""
    flags = v.get("flags", [])
    ftypes = {f.get("type") for f in flags}
    band = v.get("risk_band", "")
    conf = v.get("confidence", "")
    base_label = base_matches[0]["name"] if base_matches else None
    brand = _claimed_brand(flags)
    re = _RISK_EMOJI.get(band, "⚪")

    if ftypes & _DECEPTION_FLAGS or band == "HIGH":
        if brand and base_label:
            sub = f"conceals its origin — presented as {brand}, actually {base_label}"
        elif base_label:
            sub = f"provenance actively obscured — true base is {base_label}"
        else:
            sub = "provenance actively obscured"
        return re, "DECEPTIVE", sub
    if ftypes & _ATTRIB_FLAGS:
        if brand and base_label:
            sub = f'marketed as "{brand}", but the weights are {base_label}'
        elif base_label:
            sub = f"name overclaims — the actual base is {base_label}"
        else:
            sub = "the name does not match the architecture"
        return re, "MISATTRIBUTED", sub
    if conf == "ORIGINAL":
        return "🧬", "ORIGINAL", "first-party architecture — not a derivative of any known base"
    if conf == "NEW":
        return "🆕", "NEW", f"{v.get('base_model_confirmed','')} — not yet catalogued"
    if base_label:
        if band == "CLEAN":
            return "🟢", "VERIFIED", f"{base_label} — naming is consistent with the architecture"
        return "🔵", "IDENTIFIED", base_label
    return "❓", "UNRECOGNIZED", "does not match any known base in the reference"


def _moat_block(v: dict, e: dict, base_matches: list) -> str:
    """DNA-018: 'How we know' — the ModelAtlas moat, stated. Independent, architecture-derived."""
    n = reference_count()
    n_str = f"{(n // 100) * 100:,}+" if n >= 200 else (f"{n:,}" if n else "our catalogue of")
    out = ["### 🧬 How we know",
           f"Independently fingerprinted against **ModelAtlas — {n_str} catalogued models**."]
    if base_matches:
        top = base_matches[0]
        ev = "; ".join(list(dict.fromkeys(top.get("evidence", [])))[:2])  # dedup, top 2
        out.append(f"**True base:** {top['name']} — {top.get('confidence','')} match ({ev}).")
        out.append("Verified from the model's own architecture — **not** the uploader's declaration.")
    elif v.get("confidence") in ("ORIGINAL", "NEW"):
        out.append(f"**{v.get('base_model_confirmed','')}** — no derivative signature; treated as an original architecture.")
    else:
        out.append("No matching base architecture was found in the reference.")
    return "\n\n".join(out)


def _action_block(v: dict) -> str:
    """DNA-018: 'Why it matters / what to do' — turns the verdict into an actionable reason."""
    flags = v.get("flags", [])
    band = v.get("risk_band", "")
    if band == "UNKNOWN":
        return ("### ❓ What this means\n\n"
                "**Unverified — not a clean bill of health.** We could not match this model's "
                "architecture to any known base in the reference, so we can't confirm what it is "
                "or where it came from. No deception flags fired, but on an unrecognized model "
                "that's *absence of evidence*, not proof it's clean. Treat provenance as unverified; "
                "confirm the base, license, and training claims from the source before you rely on it.")
    if not flags and band in ("CLEAN", ""):
        return ("### ✅ What this means\n\n"
                "No provenance concerns detected — architecture and naming are consistent. "
                "Standard due-diligence (license, intended use) still applies.")
    out = ["### ⚠️ Why it matters / what to do"]
    for f in flags:
        t = f.get("type")
        if t == "IMPOSSIBLE_WEIGHT_PROVENANCE":
            brand = f.get("term", "the referenced closed model")
            out.append(f"- **Impossible weight claim.** {brand} weights were never publicly released, so this model cannot contain them. At best it is trained on generated outputs (distillation) — which leaves no weight-level trace, cannot be verified, and may violate the provider's terms.")
        elif t == "NAMING_MISATTRIBUTION":
            out.append("- **Misattribution.** The name foregrounds a brand the model has no architectural claim to, while omitting the base it is actually built from.")
        elif t == "NAME_MISMATCH":
            out.append("- **Name/architecture mismatch.** The name implies a different base than the weights indicate.")
        elif t == "PROVENANCE_SCRUBBING":
            out.append("- **Provenance scrubbing.** The chat template denies its true lineage — a deliberate step to obscure origin.")
        elif t == "IDENTITY_OVERRIDE":
            out.append("- **Identity override.** The model is configured to self-report a false identity.")
        else:
            out.append(f"- {f.get('explanation','')}")
    if band == "HIGH":
        out.append("**Recommendation:** avoid for anything provenance-sensitive; treat all lineage and capability claims as unproven until independently verified.")
    elif band == "MODERATE":
        out.append("**Recommendation:** verify the license before use and treat capability claims as unproven — the true base above is what you are actually running.")
    else:
        out.append("**Recommendation:** minor — note the discrepancy and verify license terms.")
    return "\n\n".join(out)


def _audit_trail(result: dict) -> str:
    """DNA-018 (DeepSeek): shareable chain-of-custody — the fingerprint the verdict is derived from."""
    e = result.get("evidence", {})
    cs = e.get("config_signals", {}) or {}
    v = result.get("verdict", {})
    top = (e.get("base_matches") or [{}])[0]
    lines = ["```"]
    lines.append(f"model_id     : {result.get('model_id','')}")
    lines.append(f"scanned_at   : {result.get('scanned_at','')}")
    for k, label in (("model_type", "model_type"), ("vocab_size", "vocab_size"),
                     ("hidden_size", "hidden_size"), ("num_layers", "num_layers"),
                     ("has_mla", "has_mla")):
        if cs.get(k) is not None:
            lines.append(f"{label:<13}: {cs.get(k)}")
    if top:
        lines.append(f"matched_base : {top.get('name')} (score {top.get('score')}, {top.get('confidence')})")
    lines.append(f"risk         : {v.get('risk_score')}/100 {v.get('risk_band','')}")
    lines.append(f"reference    : ModelAtlas ({reference_count()} models)")
    lines.append("engine       : ModelDNA Stage-1 (config-only, no weight download)")
    lines.append("```")
    return "### 🔎 Fingerprint · audit trail\n\n_Copy as evidence — this is exactly what the verdict is derived from._\n\n" + "\n".join(lines)


def format_verdict(result: dict) -> tuple[str, str, str]:
    """DNA-018 verdict-first layout: pane 1 = VERDICT → MOAT → ACTION; pane 2 = audit trail +
    similar models + badge; pane 3 = engine panel + flag detail."""
    if "error" in result:
        return ("❌ Scan Failed", f"**Error**: {result['error']}", "")

    v = result.get("verdict", {})
    e = result.get("evidence", {})
    m = result.get("metadata", {})
    flags = v.get("flags", [])
    base_matches = e.get("base_matches", [])

    # ── Pane 1: the lead. Verdict headline, risk gauge, then WHY-WE-KNOW and WHAT-TO-DO.
    emoji, verb, subtitle = _headline(v, base_matches)
    header = f"# {emoji} {verb}\n**{subtitle}**"
    if "risk_score" in v:
        band = v.get("risk_band", "")
        be = _RISK_EMOJI.get(band, "⚪")
        if band == "UNKNOWN":
            # don't show a reassuring 0/100 for a model we couldn't identify
            header += f"\n\n### {be} Provenance: UNVERIFIED — architecture not recognized"
        else:
            header += f"\n\n### {be} Provenance Risk: {v['risk_score']}/100 · {band}"
    header += f"\n\n*Scanned in {result.get('elapsed_s', '?')}s · Stage 1 (config-only) · "
    header += f"📥 {m.get('downloads',0):,} · 👍 {m.get('likes',0)}*"
    header += "\n\n---\n\n" + _moat_block(v, e, base_matches)
    header += "\n\n---\n\n" + _action_block(v)

    # ── Pane 2: the evidence & the shareable proof.
    details = _audit_trail(result)
    if e.get("modelatlas_similar"):
        details += "\n\n### Similar verified models (ModelAtlas reference)\n"
        for s in e["modelatlas_similar"][:3]:
            details += f"- `{s['model_id']}`\n"
    details += "\n\n---\n\n" + build_badge(result.get("model_id", ""), v)

    # ── Pane 3: the detector engines + flag detail (backup depth).
    flag_text = _fmt_engine_panel(v.get("engines", [])) + _fmt_flags(flags)

    return header, details, flag_text


def build_badge(model_id: str, v: dict) -> tuple:
    """DNA-004: zero-backend shields.io badge + copyable model-card snippet."""
    from urllib.parse import quote
    score = v.get("risk_score"); band = v.get("risk_band", "")
    color = {"CLEAN": "brightgreen", "LOW": "yellowgreen", "MODERATE": "orange",
             "HIGH": "red", "UNKNOWN": "lightgrey"}.get(band, "blue")
    if band == "UNKNOWN":
        msg = "unverified"
    elif score is None:
        msg = "scanned"
    elif band == "CLEAN":
        msg = "clean"
    else:
        msg = f"{band.lower()} risk {score} of 100"
    badge = f"https://img.shields.io/badge/{quote('ModelDNA')}-{quote(msg)}-{color}"
    space = "https://huggingface.co/spaces/RadicalNotionAI/modeldna"
    md = f"[![ModelDNA provenance]({badge})]({space})"
    block = ("### 🔗 Share / embed this result\n\n"
             f"![badge]({badge})\n\n"
             "Add to your model card (Markdown):\n\n"
             f"```\n{md}\n```")
    return block


_GENERIC_TOKENS = {"qwen", "qwen2", "qwen3", "qwen35", "llama", "gemma", "mistral",
                   "phi", "deepseek", "model", "base", "instruct"}

def build_lineage(model_id: str, result: dict) -> str:
    """DNA-002 v1: lineage view — where it came from + the derivative/quant family it spawned.
    Uses the HF API (reachable from the Space) to find same-family models by name."""
    import os, re
    from huggingface_hub import HfApi
    v = result.get("verdict", {})
    org, short = (model_id.split("/", 1) + [""])[:2] if "/" in model_id else ("", model_id)
    came_from = result.get("resolved_source") or (v.get("base_model_confirmed") or "").strip()

    # distinctive search token = first name segment, unless it's a generic base word
    token = re.split(r"[-_.]", short)[0]
    if len(token) < 4 or token.lower() in _GENERIC_TOKENS:
        token = short
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    try:
        found = list(api.list_models(search=token, limit=60))
    except Exception:
        found = []
    groups = {"GGUF": [], "MLX": [], "AWQ/GPTQ": [], "other quant": [], "fine-tune / variant": []}
    for m in found:
        if m.id.lower() == model_id.lower():
            continue
        low = m.id.lower()
        dl = getattr(m, "downloads", 0) or 0
        if "gguf" in low: g = "GGUF"
        elif "mlx" in low: g = "MLX"
        elif "awq" in low or "gptq" in low: g = "AWQ/GPTQ"
        elif any(q in low for q in ("nvfp4", "fp8", "int4", "int8", "-4bit", "-8bit", "exl2")): g = "other quant"
        else: g = "fine-tune / variant"
        groups[g].append((m.id, dl))
    total = sum(len(x) for x in groups.values())
    if total == 0 and not came_from:
        return ("### 🌳 Lineage & Derivatives\n\nNo related models found yet. "
                "As similar models are scanned, the family tree grows here.")
    out = "### 🌳 Lineage & Derivatives\n\n"
    if came_from and came_from not in ("Unknown", ""):
        out += f"**⬆ Descends from:** `{came_from}`\n\n"
    out += f"**⬇ Derivative family** (`{token}` — {total} related models found on HF):\n\n"
    for g, items in groups.items():
        if not items:
            continue
        items.sort(key=lambda x: -x[1])
        out += f"- **{g}** ({len(items)}): "
        out += ", ".join(f"`{i}` ({d:,})" for i, d in items[:4])
        if len(items) > 4:
            out += f", +{len(items)-4} more"
        out += "\n"
    out += ("\n*Downloads in parentheses. Quants inherit the source's provenance — a scrub or "
            "misattribution in the parent travels to every derivative here.*")
    return out


def _fmt_engine_panel(engines: list) -> str:
    if not engines:
        return ""
    t = "### 🔬 Detector Engines\n\n"
    for e in engines:
        t += f"- {e['status']} · **{e['engine']}** — {e['detail']}\n"
    return t + "\n---\n\n"


def _fmt_flags(flags: list) -> str:
    if not flags:
        return "### ✅ No Flags\n\nNo suspicious claims detected in model name or metadata."
    t = f"### ⚠️ {len(flags)} Flag(s) Found\n\n"
    for f in flags:
        sev = f.get("severity", "")
        t += f"**[{f['type']}]**" + (f"  _(severity: {sev})_" if sev else "")
        t += f"\n\n{f['explanation']}\n\n---\n\n"
    return t


def format_gguf_scan(result: dict) -> tuple[str, str, str, str]:
    """Render a GGUF detection: what it is + the optional follow-up offers (as text)."""
    src = result.get("resolved_source")
    header = ("📦 **GGUF quantization detected**\n\n"
              "*A quant is the same weights at lower precision — its provenance equals its source.*")
    details = "### What this is\n" + result.get("detected", "") + "\n\n"
    if src:
        details += f"**Resolved full-weights source:** `{src}`\n\n"
    details += "_Use the buttons below to inspect the GGUF's embedded metadata or scan the full-weights source._"
    disc = ("### 🔍 Derivative Discovery\n\nGGUF quants inherit their source's provenance "
            "(and any identity scrub baked into the chat template). Inspect the metadata or "
            "scan the source for the full picture.")
    return header, details, "", disc


def format_inspection(result: dict) -> tuple[str, str, str, str]:
    if "error" in result:
        return "❌ GGUF inspection failed", f"**Error**: {result['error']}", "", ""
    v = result.get("verdict", {}); ev = result.get("evidence", {})
    header = (f"📦 **GGUF metadata inspection** — {v.get('architecture','')}\n\n"
              "*Read from the GGUF header only — no weights downloaded.*")
    if "risk_score" in v:
        be = {"CLEAN": "🟢", "LOW": "🟡", "MODERATE": "🟠", "HIGH": "🔴"}.get(v.get("risk_band",""), "⚪")
        header += f"\n\n### {be} Provenance Risk: {v['risk_score']}/100 · {v.get('risk_band','')}"
    details = ("### GGUF header\n"
               f"- **name:** {ev.get('gguf_general.name')}\n"
               f"- **architecture:** `{ev.get('gguf_architecture')}`\n"
               f"- **chat template present:** {ev.get('chat_template_present')}\n"
               f"- **file:** `{result.get('gguf_file')}`\n")
    return header, details, _fmt_engine_panel(v.get("engines", [])) + _fmt_flags(v.get("flags", [])), ""


def inspect_action(gguf_id: str):
    """Optional action (offer #1): inspect the GGUF's embedded metadata."""
    return format_inspection(inspect_gguf(gguf_id))


_HIDE = None  # placeholder; gr.update created inline


def run_scan(model_id: str, request: gr.Request = None):
    """Main scan. Returns 8 outputs: 4 markdown panes + GGUF action row/button updates + 2 states."""
    import gradio as _gr
    model_id = model_id.strip()
    hide_row = _gr.update(visible=False); hide_btn = _gr.update(visible=False)
    if not model_id:
        return "Enter a HuggingFace model ID above.", "", "", "", hide_row, hide_btn, "", ""

    if "huggingface.co/" in model_id:
        model_id = model_id.split("huggingface.co/")[-1].strip("/")

    # Normalize + validate: take first line/token, drop URL query/fragment, keep leading
    # <org>/<name> path segments. Rejects pasted blobs/prose so telemetry stays clean (DNA-017).
    model_id = model_id.splitlines()[0].strip().split()[0] if model_id.split() else ""
    model_id = model_id.split("?")[0].split("#")[0].strip("/")
    parts = model_id.split("/")
    if len(parts) >= 2:
        model_id = "/".join(parts[:2])  # spaces/datasets prefixes or trailing paths → org/name
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", model_id):
        msg = ("**Not a valid model ID.** Enter a HuggingFace repo as `org/name` "
               "(e.g. `Qwen/Qwen3.5-27B`) or paste its huggingface.co URL.")
        return msg, "", "", "", hide_row, hide_btn, "", ""

    result = scan(model_id)
    store_scan_result(result)
    # DNA-017: source tag for usage filtering — "ui" for web visitors; our gradio_client test
    # calls set the X-ModelDNA-Source header so they can be excluded from external-usage counts.
    _src = "ui"
    try:
        if request is not None:
            _src = (request.headers.get("x-modeldna-source") or "ui").lower()[:32]
    except Exception:
        _src = "ui"
    log_scan(model_id, result, _src)  # telemetry to HF dataset (no-op without LOG_TOKEN)

    # GGUF: show detection + reveal the optional follow-up buttons
    if str(result.get("format", "")).startswith("GGUF"):
        h, d, fl, disc = format_gguf_scan(result)
        src = result.get("resolved_source") or ""
        src_btn = _gr.update(visible=bool(src), value=f"🔬 Scan source: {src}") if src else hide_btn
        return h, d, fl, disc, _gr.update(visible=True), src_btn, src, model_id

    header, details, flags = format_verdict(result)

    # DNA-002: lineage & derivative family (HF-API-backed, works on the Space)
    try:
        discovery = build_lineage(model_id, result)
    except Exception:
        discovery = "### 🌳 Lineage & Derivatives\n\n(temporarily unavailable)"

    return header, details, flags, discovery, hide_row, hide_btn, "", ""


# ── Gradio UI ──────────────────────────────────────────────────────────────

EXAMPLES = [
    "Qwen/Qwen3.5-27B",
    "Jackrong/Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled",
    "poolside/Laguna-XS.2",
    "deepseek-ai/DeepSeek-R1",
    "mistralai/Mistral-Medium-3.5-128B",
]

CSS = """
.gradio-container { max-width: 900px !important; margin: 0 auto; }
.verdict-header { font-size: 1.2em; }
footer { display: none; }
"""

with gr.Blocks(
    title="ModelDNA — AI Model Provenance",
    theme=gr.themes.Ocean(),
    css=CSS,
) as demo:
    gr.Markdown("""
    # 🧬 ModelDNA
    ### The DNA test for AI models — verify provenance before you download
    *Powered by ModelAtlas · a RadicalNotion product*

    > **Works with:** standard HuggingFace checkpoints (safetensors / PyTorch bin) **and GGUF quants**
    > (header-only metadata inspection + source resolution). Not yet supported: private/gated models.
    > No weight download needed — Stage 1 reads config.json (or the GGUF header) only.
    ---
    """)

    with gr.Row():
        model_input = gr.Textbox(
            label="HuggingFace Model ID or URL",
            placeholder="e.g. Qwen/Qwen3.5-27B  (not GGUF — use the original checkpoint)",
            scale=4,
        )
        scan_btn = gr.Button("🔬 Scan", variant="primary", scale=1)

    gr.Examples(
        examples=EXAMPLES,
        inputs=model_input,
        label="Try these examples",
    )

    gr.Markdown("---")

    with gr.Row():
        header_out = gr.Markdown(label="Verdict")
    with gr.Row():
        with gr.Column():
            details_out = gr.Markdown(label="Evidence")
        with gr.Column():
            flags_out = gr.Markdown(label="Flags")

    # GGUF optional follow-up actions (hidden until a GGUF is scanned)
    source_state = gr.State("")
    gguf_id_state = gr.State("")
    with gr.Row(visible=False) as gguf_actions:
        inspect_btn = gr.Button("🔍 Inspect GGUF metadata (no download)")
        source_btn = gr.Button("🔬 Scan full-weights source", variant="primary")

    gr.Markdown("---")
    discovery_out = gr.Markdown(label="Derivative Discovery")

    gr.Markdown("""
    ---
    *Stage 1 (architecture screening): free, unlimited, no weight download needed.*
    *Stage 2 (weight-level analysis): coming soon — deeper confirmation.*
    *[modeldna.ai](https://modeldna.ai) · [RadicalNotionAI on HF](https://huggingface.co/RadicalNotionAI)*
    """)

    _scan_outputs = [header_out, details_out, flags_out, discovery_out,
                     gguf_actions, source_btn, source_state, gguf_id_state]
    scan_btn.click(fn=run_scan, inputs=[model_input], outputs=_scan_outputs)
    model_input.submit(fn=run_scan, inputs=[model_input], outputs=_scan_outputs)

    # Optional GGUF follow-ups (user-triggered)
    inspect_btn.click(
        fn=inspect_action, inputs=[gguf_id_state],
        outputs=[header_out, details_out, flags_out, discovery_out],
    )
    source_btn.click(  # scan the resolved full-weights source
        fn=run_scan, inputs=[source_state], outputs=_scan_outputs,
    )

if __name__ == "__main__":
    demo.launch()
