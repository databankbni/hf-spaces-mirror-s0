"""
RASopathy VUS Output Audit
==========================

GPU-integrated Gradio Space for controlled generation and side-by-side review.
When the two audit JSON files are absent, the owner can explicitly start a
sequential GPU generation run using the local LoRA archives. The completed JSON
files are committed back to the Space repository, causing a rebuild. On later
starts, the app opens directly as a lightweight audit viewer.

Expected output files:
    outputs_mixtral_on.json
    outputs_scout_off.json
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import shutil
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

import gradio as gr
from huggingface_hub import CommitOperationAdd, HfApi

try:
    from gerar_saidas import (
        GENERATOR_API_VERSION,
        PIPELINES,
        generate_all_outputs,
    )
except ImportError as exc:
    raise RuntimeError(
        "Incompatible gerar_saidas.py. Replace app.py and gerar_saidas.py "
        "from the same release bundle. Expected generator API v2.0 with "
        "PIPELINES and generate_all_outputs."
    ) from exc

if GENERATOR_API_VERSION != "2.0":
    raise RuntimeError(
        f"Unsupported generator API: {GENERATOR_API_VERSION!r}. Expected '2.0'."
    )


# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

# Prefer an attached persistent volume for the Hugging Face cache. When no
# volume is attached, the cache remains ephemeral and must fit on local disk.
RUNTIME_STORAGE = Path("/data") if Path("/data").is_dir() else BASE_DIR
HF_CACHE_ROOT = Path(
    os.getenv("HF_HOME", str(RUNTIME_STORAGE / ".huggingface-cache"))
).resolve()
HF_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(HF_CACHE_ROOT))
os.environ.setdefault("HF_HUB_CACHE", str(HF_CACHE_ROOT / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_CACHE_ROOT / "transformers"))

SPACE_REPO_ID = os.getenv(
    "SPACE_ID",
    "Fernandosr85/rasopathy-rephrase-on-vs-off",
)
GENERATION_CONFIRMATION = "GENERATE OUTPUTS"

PIPELINE_A_NAME = os.getenv(
    "PIPELINE_A_NAME",
    "Mixtral 8×7B · Rephrase ON",
)
PIPELINE_B_NAME = os.getenv(
    "PIPELINE_B_NAME",
    "Llama 4 Scout · Rephrase OFF",
)

PIPELINE_A_CANDIDATES = [
    "outputs_mixtral_on.json",
    "saidas_mixtral_on.json",
    "mixtral_rephrase_on.json",
    "outputs_mixtral_rephrase_on.json",
]
PIPELINE_B_CANDIDATES = [
    "outputs_scout_off.json",
    "saidas_scout_off.json",
    "scout_rephrase_off.json",
    "outputs_scout_rephrase_off.json",
]


# =============================================================================
# Heuristic review signals
# =============================================================================

FLAG_META = {
    "untraceable_cdna": {
        "regex": re.compile(r"c\.\d+[ACGT]>[ACGT]", re.IGNORECASE),
        "label": "cDNA not traceable to input",
        "short_label": "Untraceable cDNA",
        "color": "#fee2e2",
        "border": "#ef4444",
        "explanation": (
            "HGVS-c notation appears in the generated output, but the audited "
            "input schema provides protein-level notation only. The value may be "
            "correct, but it is not traceable to the supplied input."
        ),
    },
    "unresolved_placeholder": {
        "regex": re.compile(r"c\.\[[^\]]{0,60}\]", re.IGNORECASE),
        "label": "Unresolved template placeholder",
        "short_label": "Placeholder",
        "color": "#fef3c7",
        "border": "#f59e0b",
        "explanation": (
            "A literal template placeholder, such as c.[Variant], remained in "
            "the final output."
        ),
    },
    "untraceable_mondo": {
        "regex": re.compile(r"MONDO:\d+", re.IGNORECASE),
        "label": "MONDO ID not traceable to input",
        "short_label": "Untraceable MONDO",
        "color": "#ede9fe",
        "border": "#8b5cf6",
        "explanation": (
            "A specific MONDO identifier appears in the output even though the "
            "audited input schema contains OMIM fields but no MONDO field."
        ),
    },
}

UNSUPPORTED_EVIDENCE_PHRASES = [
    "de novo",
    "segregat",
    "robust evidence",
    "strong genetic evidence",
    "functional studies demonstrating",
    "clinical phenotypes typically",
    "particularly high risk",
    "well-established in vitro",
    "established literature indicates",
    "literature indicates that",
]

# Evidence terms are not flagged when they appear in nearby requirement,
# uncertainty, absence, or negation language. This avoids marking legitimate
# safety disclaimers as unsupported factual claims.
REQUIREMENT_CONTEXT = re.compile(
    r"(required|before any|are needed|is needed|would be needed|necessary|"
    r"must be|remains? a vus|to strengthen|to confirm|to establish|"
    r"not (yet )?(been )?(established|available|documented|reported)|"
    r"absence of|lack of|no (functional|segregation)|pending|awaiting|"
    r"in order to)",
    re.IGNORECASE,
)

ALL_FLAG_META = {
    **FLAG_META,
    "potentially_unsupported_evidence": {
        "label": "Potentially unsupported evidence claim",
        "short_label": "Unsupported evidence",
        "color": "#fce7f3",
        "border": "#ec4899",
        "explanation": (
            "The text may assert clinical, functional, or segregation evidence "
            "that is not represented in the audited input fields. This is a "
            "review signal, not an automatic factual-error determination."
        ),
    },
}


def find_evidence_signals(text: str) -> list[tuple[int, int, str]]:
    """Return unsupported-evidence phrase spans after context filtering."""
    lower = text.lower()
    hits: list[tuple[int, int, str]] = []

    for phrase in UNSUPPORTED_EVIDENCE_PHRASES:
        for match in re.finditer(re.escape(phrase), lower):
            window = lower[max(0, match.start() - 80): match.end() + 80]
            if REQUIREMENT_CONTEXT.search(window):
                continue
            hits.append((match.start(), match.end(), phrase))

    return hits


def collect_flags(text: Any) -> tuple[list[tuple[int, int, str]], dict[str, int]]:
    """Collect highlight spans and counts for all heuristic categories."""
    if not isinstance(text, str) or not text.strip():
        return [], {key: 0 for key in ALL_FLAG_META}

    spans: list[tuple[int, int, str]] = []
    counts: dict[str, int] = {}

    for key, config in FLAG_META.items():
        matches = list(config["regex"].finditer(text))
        counts[key] = len(matches)
        spans.extend((match.start(), match.end(), key) for match in matches)

    evidence_hits = find_evidence_signals(text)
    counts["potentially_unsupported_evidence"] = len(evidence_hits)
    spans.extend(
        (start, end, "potentially_unsupported_evidence")
        for start, end, _phrase in evidence_hits
    )

    return spans, counts


# =============================================================================
# JSON loading and pairing
# =============================================================================


def resolve_json_path(env_name: str, candidates: list[str]) -> Path | None:
    """Resolve an explicit environment path or the first existing candidate."""
    explicit = os.getenv(env_name, "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    for filename in candidates:
        path = BASE_DIR / filename
        if path.exists():
            return path

    return None


def load_payload(path: Path, fallback_label: str) -> dict[str, Any]:
    """Load and validate one controlled-inference JSON payload."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path.name}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object at the top level.")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError(f"{path.name} must contain a 'results' list.")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        meta = {}

    meta = dict(meta)
    meta.setdefault("label", fallback_label)
    meta["source_file"] = path.name

    return {"meta": meta, "results": results}


def clean_id(value: Any) -> str:
    """Normalize identifiers while avoiding literal None/nan values."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "null"}:
        return ""
    return text


def sha256_text(text: Any) -> str:
    """Create a stable SHA-256 hash for text-like values."""
    value = text if isinstance(text, str) else ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def candidate_pair_keys(record: dict[str, Any]) -> list[tuple[str, ...]]:
    """Build pairing keys from most specific to least specific."""
    record_id = clean_id(record.get("record_id"))
    clinvar_id = clean_id(record.get("clinvar_id"))
    protein_change = clean_id(record.get("protein_change"))
    instruction_hash = clean_id(record.get("instruction_hash")) or sha256_text(
        record.get("instruction", "")
    )

    keys: list[tuple[str, ...]] = []
    if record_id:
        keys.append(("record_id", record_id))
    if clinvar_id and instruction_hash:
        keys.append(("clinvar_instruction", clinvar_id, instruction_hash))
    if clinvar_id and protein_change:
        keys.append(("clinvar_protein", clinvar_id, protein_change))
    if clinvar_id:
        keys.append(("clinvar_id", clinvar_id))

    return keys


def get_generated_output(record: dict[str, Any]) -> str:
    """Read the generated output using the new field, with safe fallbacks."""
    for field in ("generated_output", "enhanced_completion", "output"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def pair_results(
    left_results: list[dict[str, Any]],
    right_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Greedily pair records using increasingly permissive auditable keys."""
    right_indexes: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, record in enumerate(right_results):
        if not isinstance(record, dict):
            continue
        for key in candidate_pair_keys(record):
            right_indexes[key].append(index)

    used_right: set[int] = set()
    pairs: list[dict[str, Any]] = []
    match_counts: dict[str, int] = defaultdict(int)

    for left_index, left_record in enumerate(left_results):
        if not isinstance(left_record, dict):
            continue

        matched_index: int | None = None
        matched_key: tuple[str, ...] | None = None

        for key in candidate_pair_keys(left_record):
            for candidate_index in right_indexes.get(key, []):
                if candidate_index not in used_right:
                    matched_index = candidate_index
                    matched_key = key
                    break
            if matched_index is not None:
                break

        if matched_index is None:
            continue

        used_right.add(matched_index)
        right_record = right_results[matched_index]
        left_output = get_generated_output(left_record)
        right_output = get_generated_output(right_record)
        left_spans, left_flags = collect_flags(left_output)
        right_spans, right_flags = collect_flags(right_output)

        match_method = matched_key[0] if matched_key else "unknown"
        match_counts[match_method] += 1

        pair_id = f"pair-{len(pairs):04d}"
        pairs.append(
            {
                "pair_id": pair_id,
                "match_method": match_method,
                "left": left_record,
                "right": right_record,
                "left_output": left_output,
                "right_output": right_output,
                "left_spans": left_spans,
                "right_spans": right_spans,
                "left_flags": left_flags,
                "right_flags": right_flags,
                "left_total": sum(left_flags.values()),
                "right_total": sum(right_flags.values()),
            }
        )

    stats = {
        "left_total": len(left_results),
        "right_total": len(right_results),
        "paired": len(pairs),
        "left_unpaired": max(0, len(left_results) - len(pairs)),
        "right_unpaired": max(0, len(right_results) - len(used_right)),
        **{f"match_{key}": value for key, value in match_counts.items()},
    }
    return pairs, stats


# =============================================================================
# Rendering helpers
# =============================================================================


def escape(value: Any) -> str:
    return html_lib.escape(clean_id(value))


def format_pipeline_title(meta: dict[str, Any], fallback: str) -> str:
    label = clean_id(meta.get("label"))
    return label.replace("_", " ").title() if label else fallback


def render_pipeline_card(meta: dict[str, Any], display_name: str, side: str) -> str:
    model = escape(meta.get("base_model") or "Not recorded")
    adapter = escape(meta.get("adapter") or "Not recorded")
    seed = escape(meta.get("seed") or "Not recorded")
    decoding = escape(meta.get("decoding") or "Not recorded")
    source = escape(meta.get("source_file") or "Not recorded")
    accent_class = "pipeline-a" if side == "a" else "pipeline-b"

    return f"""
    <div class="pipeline-card {accent_class}">
      <div class="pipeline-kicker">PIPELINE {side.upper()}</div>
      <div class="pipeline-name">{escape(display_name)}</div>
      <div class="pipeline-grid">
        <div><span>Base model</span><strong>{model}</strong></div>
        <div><span>Adapter</span><strong>{adapter}</strong></div>
        <div><span>Decoding</span><strong>{decoding}</strong></div>
        <div><span>Seed</span><strong>{seed}</strong></div>
      </div>
      <div class="source-file">Source: <code>{source}</code></div>
    </div>
    """


def render_highlighted(text: str, spans: list[tuple[int, int, str]]) -> str:
    if not text:
        return '<div class="empty-output">No generated output was recorded.</div>'

    ordered = sorted(spans, key=lambda item: (item[0], item[1]))
    non_overlapping: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, key in ordered:
        if start >= last_end:
            non_overlapping.append((start, end, key))
            last_end = end

    parts: list[str] = []
    cursor = 0
    for start, end, key in non_overlapping:
        parts.append(html_lib.escape(text[cursor:start]))
        meta = ALL_FLAG_META[key]
        snippet = html_lib.escape(text[start:end])
        tooltip = html_lib.escape(f"{meta['label']}: {meta['explanation']}")
        parts.append(
            f'<mark class="flag-mark" style="background:{meta["color"]}; '
            f'border-bottom:2px solid {meta["border"]};" title="{tooltip}">'
            f"{snippet}</mark>"
        )
        cursor = end

    parts.append(html_lib.escape(text[cursor:]))
    body = "".join(parts).replace("\n", "<br>")
    return f'<div class="output-text">{body}</div>'


def render_flag_badge(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    if total == 0:
        return '<div class="status-badge clean">✓ No heuristic signals</div>'

    chips = "".join(
        f'<span class="mini-chip">{html_lib.escape(ALL_FLAG_META[key]["short_label"])}: {value}</span>'
        for key, value in counts.items()
        if value
    )
    return (
        f'<div class="status-badge review">⚠ {total} review signal(s)</div>'
        f'<div class="chip-row">{chips}</div>'
    )


def display_value(left: dict[str, Any], right: dict[str, Any], field: str) -> str:
    return clean_id(left.get(field)) or clean_id(right.get(field)) or "Not recorded"


def render_variant_header(pair: dict[str, Any]) -> str:
    left = pair["left"]
    right = pair["right"]
    gene = display_value(left, right, "gene")
    protein = display_value(left, right, "protein_change")
    clinvar = display_value(left, right, "clinvar_id")
    record_id = display_value(left, right, "record_id")
    method = pair["match_method"].replace("_", " ")

    return f"""
    <div class="variant-header">
      <div>
        <div class="variant-eyebrow">PAIRED VARIANT</div>
        <h2>{escape(gene)} <span>{escape(protein)}</span></h2>
      </div>
      <div class="variant-facts">
        <div><span>ClinVar</span><strong>{escape(clinvar)}</strong></div>
        <div><span>Record</span><strong>{escape(record_id)}</strong></div>
        <div><span>Matched by</span><strong>{escape(method)}</strong></div>
      </div>
    </div>
    """


def render_summary(
    pairs: list[dict[str, Any]],
    left_name: str,
    right_name: str,
    pairing_stats: dict[str, int],
) -> str:
    n = len(pairs)
    if n == 0:
        return '<div class="notice error">No paired variants are available.</div>'

    left_flagged = sum(pair["left_total"] > 0 for pair in pairs)
    right_flagged = sum(pair["right_total"] > 0 for pair in pairs)
    left_rate = 100 * left_flagged / n
    right_rate = 100 * right_flagged / n
    delta = right_rate - left_rate

    category_rows = []
    for key, meta in ALL_FLAG_META.items():
        left_count = sum(pair["left_flags"].get(key, 0) > 0 for pair in pairs)
        right_count = sum(pair["right_flags"].get(key, 0) > 0 for pair in pairs)
        left_category_rate = 100 * left_count / n
        right_category_rate = 100 * right_count / n
        category_delta = right_category_rate - left_category_rate
        category_rows.append(
            f"""
            <tr>
              <td><strong>{html_lib.escape(meta['label'])}</strong></td>
              <td>{left_count}/{n} <span class="muted">({left_category_rate:.1f}%)</span></td>
              <td>{right_count}/{n} <span class="muted">({right_category_rate:.1f}%)</span></td>
              <td>{category_delta:+.1f} pp</td>
            </tr>
            """
        )

    return f"""
    <div class="metric-grid">
      <div class="metric-card">
        <span>Paired variants</span>
        <strong>{n}</strong>
        <small>{pairing_stats.get('left_unpaired', 0)} unmatched in A · {pairing_stats.get('right_unpaired', 0)} unmatched in B</small>
      </div>
      <div class="metric-card accent-a">
        <span>{escape(left_name)}</span>
        <strong>{left_flagged}/{n}</strong>
        <small>{left_rate:.1f}% with ≥1 review signal</small>
      </div>
      <div class="metric-card accent-b">
        <span>{escape(right_name)}</span>
        <strong>{right_flagged}/{n}</strong>
        <small>{right_rate:.1f}% with ≥1 review signal</small>
      </div>
      <div class="metric-card">
        <span>Pipeline B − Pipeline A</span>
        <strong>{delta:+.1f} pp</strong>
        <small>Difference in flagged-row rate</small>
      </div>
    </div>

    <div class="table-card">
      <div class="table-title">Signals by category</div>
      <div class="table-scroll">
        <table class="summary-table">
          <thead>
            <tr>
              <th>Heuristic review signal</th>
              <th>{escape(left_name)}</th>
              <th>{escape(right_name)}</th>
              <th>B − A</th>
            </tr>
          </thead>
          <tbody>{''.join(category_rows)}</tbody>
        </table>
      </div>
    </div>
    """


def render_methodology_note() -> str:
    return """
    <div class="method-note">
      <div class="method-icon">i</div>
      <div>
        <strong>Interpretation boundary</strong>
        <p>
          This is a descriptive comparison between two complete pipelines.
          Because the base models differ, the results do not isolate a causal
          effect of the Rephrase setting. Flags are heuristic review signals,
          not automatic proof of hallucination or factual error. The review
          interface reads fixed JSON files. GPU inference runs only through the
          separate, explicitly triggered generation control.
        </p>
      </div>
    </div>
    """


def render_setup_error(message: str) -> str:
    available = sorted(path.name for path in BASE_DIR.glob("*.json"))
    available_text = ", ".join(available) if available else "No JSON files found"
    return f"""
    <div class="setup-panel">
      <div class="setup-icon">!</div>
      <div>
        <h2>Output files are not ready</h2>
        <p>{html_lib.escape(message)}</p>
        <p>The Space has not generated both controlled-output files yet:</p>
        <pre>outputs_mixtral_on.json
outputs_scout_off.json</pre>
        <p>Use the GPU generation panel below. It will extract the local LoRA archives,
        run the two pipelines sequentially, and commit both JSON files back to this Space.</p>
        <p class="muted">JSON files currently detected: {html_lib.escape(available_text)}</p>
      </div>
    </div>
    """


# =============================================================================
# Application state
# =============================================================================

STATE: dict[str, Any] = {
    "error": None,
    "left_payload": None,
    "right_payload": None,
    "pairs": [],
    "pair_map": {},
    "pairing_stats": {},
}


def initialize_state() -> None:
    left_path = resolve_json_path("PIPELINE_A_JSON", PIPELINE_A_CANDIDATES)
    right_path = resolve_json_path("PIPELINE_B_JSON", PIPELINE_B_CANDIDATES)

    if left_path is None or right_path is None:
        missing = []
        if left_path is None:
            missing.append("Pipeline A JSON")
        if right_path is None:
            missing.append("Pipeline B JSON")
        STATE["error"] = f"Missing: {', '.join(missing)}."
        return

    if left_path.resolve() == right_path.resolve():
        STATE["error"] = "Pipeline A and Pipeline B resolve to the same JSON file."
        return

    try:
        left_payload = load_payload(left_path, PIPELINE_A_NAME)
        right_payload = load_payload(right_path, PIPELINE_B_NAME)
        pairs, pairing_stats = pair_results(
            left_payload["results"],
            right_payload["results"],
        )
    except (OSError, ValueError) as exc:
        STATE["error"] = str(exc)
        return

    if not pairs:
        STATE["error"] = (
            "The JSON files loaded successfully, but no records could be paired. "
            "Include record_id when possible, or ensure clinvar_id and instruction "
            "refer to the same variants in both files."
        )
        return

    STATE.update(
        {
            "left_payload": left_payload,
            "right_payload": right_payload,
            "pairs": pairs,
            "pair_map": {pair["pair_id"]: pair for pair in pairs},
            "pairing_stats": pairing_stats,
        }
    )


initialize_state()


def choice_label(pair: dict[str, Any]) -> str:
    left = pair["left"]
    right = pair["right"]
    gene = display_value(left, right, "gene")
    protein = display_value(left, right, "protein_change")
    clinvar = display_value(left, right, "clinvar_id")
    marker = "⚠" if pair["left_total"] or pair["right_total"] else "✓"
    return (
        f"{marker} {gene} {protein} · ClinVar {clinvar} "
        f"[A:{pair['left_total']} | B:{pair['right_total']}]"
    )


def compare_pair(pair_id: str):
    pair = STATE["pair_map"].get(pair_id)
    if pair is None:
        return (
            '<div class="notice error">Variant pair not found.</div>',
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )

    left = pair["left"]
    right = pair["right"]
    left_instruction = left.get("instruction", "")
    right_instruction = right.get("instruction", "")
    if not isinstance(left_instruction, str):
        left_instruction = ""
    if not isinstance(right_instruction, str):
        right_instruction = ""
    left_hash = clean_id(left.get("repro_hash")) or "Not recorded"
    right_hash = clean_id(right.get("repro_hash")) or "Not recorded"

    return (
        render_variant_header(pair),
        render_flag_badge(pair["left_flags"]),
        render_highlighted(pair["left_output"], pair["left_spans"]),
        render_flag_badge(pair["right_flags"]),
        render_highlighted(pair["right_output"], pair["right_spans"]),
        left_instruction,
        right_instruction,
        f"Pipeline A output hash: {left_hash}\nPipeline B output hash: {right_hash}",
    )



# =============================================================================
# Controlled GPU generation and persistence
# =============================================================================


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def generation_environment_html() -> str:
    token_ready = bool(os.getenv("HF_TOKEN", "").strip())
    accelerator = os.getenv("ACCELERATOR", "unknown")
    generation_key_ready = bool(os.getenv("GENERATION_KEY", "").strip())

    try:
        import torch

        gpu_ready = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_ready else "No CUDA device"
        gpu_memory = (
            _format_bytes(torch.cuda.get_device_properties(0).total_memory)
            if gpu_ready
            else "0 B"
        )
    except Exception as exc:
        gpu_ready = False
        gpu_name = f"Torch check failed: {type(exc).__name__}"
        gpu_memory = "Unknown"

    disk = shutil.disk_usage(HF_CACHE_ROOT)
    output_a = (BASE_DIR / "outputs_mixtral_on.json").is_file()
    output_b = (BASE_DIR / "outputs_scout_off.json").is_file()

    def status(value: bool) -> str:
        return "Ready" if value else "Missing"

    return f"""
    <div class="generation-status-grid">
      <div><span>HF_TOKEN</span><strong>{status(token_ready)}</strong></div>
      <div><span>GPU</span><strong>{html_lib.escape(gpu_name)}</strong><small>{html_lib.escape(gpu_memory)} · {html_lib.escape(accelerator)}</small></div>
      <div><span>HF cache</span><strong>{html_lib.escape(str(HF_CACHE_ROOT))}</strong><small>{_format_bytes(disk.free)} free</small></div>
      <div><span>Generation key</span><strong>{'Protected' if generation_key_ready else 'Confirmation phrase only'}</strong></div>
      <div><span>Pipeline A JSON</span><strong>{status(output_a)}</strong></div>
      <div><span>Pipeline B JSON</span><strong>{status(output_b)}</strong></div>
    </div>
    """


def _publish_generated_outputs(paths: list[Path], token: str) -> str:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Generated output files are missing: {missing}")

    api = HfApi(token=token)
    operations = [
        CommitOperationAdd(
            path_in_repo=path.name,
            path_or_fileobj=str(path),
        )
        for path in paths
    ]
    commit = api.create_commit(
        repo_id=SPACE_REPO_ID,
        repo_type="space",
        revision="main",
        operations=operations,
        commit_message="Add controlled RASopathy audit outputs",
        commit_description=(
            "Generated sequentially on the Space GPU using the local LoRA "
            "archives. The review interface uses these fixed JSON outputs."
        ),
    )
    return commit.commit_url


def run_controlled_generation(
    confirmation: str,
    admin_key: str,
    limit_value: float,
    overwrite: bool,
    progress=gr.Progress(),
) -> str:
    """Generate both pipelines sequentially and commit the JSONs to the Space."""
    if (confirmation or "").strip() != GENERATION_CONFIRMATION:
        return (
            '<div class="notice error">Type <code>GENERATE OUTPUTS</code> '
            "exactly before starting the GPU run.</div>"
        )

    required_key = os.getenv("GENERATION_KEY", "").strip()
    if required_key and (admin_key or "").strip() != required_key:
        return '<div class="notice error">Invalid generation key.</div>'

    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        return (
            '<div class="notice error"><strong>HF_TOKEN is missing.</strong> '
            "Add it under Space Settings → Variables and secrets.</div>"
        )

    try:
        import torch

        if not torch.cuda.is_available():
            return (
                '<div class="notice error"><strong>No CUDA GPU detected.</strong> '
                "Select GPU hardware in the Space settings and restart the Space."
                "</div>"
            )

        limit = int(limit_value or 0)
        limit = None if limit <= 0 else limit

        disk = shutil.disk_usage(HF_CACHE_ROOT)
        minimum_free = 70 * 1024**3
        scout_output_exists = (BASE_DIR / PIPELINES["scout_off"].output_file).is_file()
        if disk.free < minimum_free and not scout_output_exists:
            return f"""
            <div class="notice error">
              <strong>Insufficient cache disk for the Scout pipeline.</strong><br>
              Available: {_format_bytes(disk.free)}. Recommended before the first
              Scout download: at least {_format_bytes(minimum_free)}.<br>
              Attach a Storage Bucket or larger volume and set <code>HF_HOME</code>
              to its mount path.
            </div>
            """

        progress(0.01, desc="Preparing controlled generation")

        def callback(message: str, current: int, total: int) -> None:
            lower = message.lower()
            stage_start = 0.03 if ("mixtral" in lower or "pipeline a" in lower) else 0.52
            stage_width = 0.45
            fraction = (current / total) if total else 0.05
            progress(
                min(0.97, stage_start + stage_width * fraction),
                desc=message,
            )

        paths = generate_all_outputs(
            base_dir=BASE_DIR,
            limit=limit,
            overwrite=bool(overwrite),
            token=token,
            progress_callback=callback,
        )

        progress(0.98, desc="Committing generated JSON files to the Space")
        commit_url = _publish_generated_outputs(paths, token)
        progress(1.0, desc="Generation complete")

        generated = "<br>".join(
            f"<code>{html_lib.escape(path.name)}</code> ({_format_bytes(path.stat().st_size)})"
            for path in paths
        )
        return f"""
        <div class="notice success">
          <strong>Controlled generation completed.</strong><br>
          {generated}<br><br>
          Both files were committed to the Space repository.<br>
          <a href="{html_lib.escape(commit_url)}" target="_blank">Open commit</a>.
          The Space will rebuild; refresh after the new revision starts.
        </div>
        """

    except Exception as exc:
        detail = traceback.format_exc()
        token_value = os.getenv("HF_TOKEN", "")
        if token_value:
            detail = detail.replace(token_value, "***HF_TOKEN***")
        detail = detail[-9000:]
        return f"""
        <div class="notice error">
          <strong>Generation failed: {html_lib.escape(type(exc).__name__)}</strong>
          <p>{html_lib.escape(str(exc))}</p>
          <details><summary>Technical traceback</summary>
          <pre>{html_lib.escape(detail)}</pre></details>
        </div>
        """


def add_generation_controls() -> None:
    gr.HTML(generation_environment_html())
    gr.Markdown(
        """
        The two models run **sequentially**, never at the same time. Start with
        `1` variant per pipeline. After validating the adapters and output format,
        run again with `0` to generate the complete datasets. The final JSON files
        are committed to this Space, so they survive the automatic rebuild.
        """
    )
    with gr.Row():
        limit_input = gr.Number(
            value=1,
            precision=0,
            minimum=0,
            label="Variants per pipeline",
            info="Use 1 for the first test. Use 0 for all variants.",
        )
        overwrite_input = gr.Checkbox(
            value=False,
            label="Overwrite existing output JSON files",
        )
    admin_key_input = gr.Textbox(
        type="password",
        label="Generation key",
        placeholder="Required only when GENERATION_KEY is configured",
    )
    confirmation_input = gr.Textbox(
        label="Confirmation phrase",
        placeholder="Type: GENERATE OUTPUTS",
    )
    generate_button = gr.Button(
        "Generate and publish controlled outputs",
        variant="primary",
    )
    generation_result = gr.HTML()
    generate_button.click(
        fn=run_controlled_generation,
        inputs=[
            confirmation_input,
            admin_key_input,
            limit_input,
            overwrite_input,
        ],
        outputs=generation_result,
        concurrency_limit=1,
        concurrency_id="controlled-generation",
    )


# =============================================================================
# Theme and UI
# =============================================================================

CSS = """
:root {
  --ink: #172033;
  --muted: #64748b;
  --line: #e7ebf2;
  --surface: #ffffff;
  --surface-soft: #f7f9fc;
  --a: #2563eb;
  --b: #7c3aed;
}

.gradio-container {
  max-width: 1240px !important;
  margin: 0 auto !important;
  background: #f5f7fb !important;
  color: var(--ink) !important;
}

.main-shell {
  padding-top: 8px;
}

.hero {
  background: linear-gradient(135deg, #ffffff 0%, #f7f8ff 100%);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 28px 30px;
  margin: 8px 0 18px;
  box-shadow: 0 12px 35px rgba(30, 41, 59, 0.06);
}

.hero-badge {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  background: #e0e7ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .06em;
}

.hero h1 {
  margin: 14px 0 8px;
  font-size: clamp(30px, 4vw, 46px);
  line-height: 1.05;
  letter-spacing: -0.04em;
}

.hero p {
  max-width: 850px;
  margin: 0;
  color: var(--muted);
  font-size: 16px;
  line-height: 1.65;
}

.pipeline-card,
.variant-header,
.table-card,
.metric-card,
.method-note,
.setup-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  box-shadow: 0 8px 24px rgba(30, 41, 59, 0.045);
}

.pipeline-card {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  padding: 20px;
  min-height: 210px;
}

.pipeline-card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 4px;
}

.pipeline-card.pipeline-a::before { background: var(--a); }
.pipeline-card.pipeline-b::before { background: var(--b); }

.pipeline-kicker,
.variant-eyebrow {
  color: var(--muted);
  font-size: 11px;
  letter-spacing: .1em;
  font-weight: 800;
}

.pipeline-name {
  margin: 5px 0 16px;
  font-size: 21px;
  font-weight: 750;
  letter-spacing: -0.02em;
}

.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.pipeline-grid div,
.variant-facts div {
  min-width: 0;
}

.pipeline-grid span,
.variant-facts span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-bottom: 3px;
}

.pipeline-grid strong,
.variant-facts strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.35;
}

.source-file {
  margin-top: 16px;
  color: var(--muted);
  font-size: 12px;
}

.variant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border-radius: 18px;
  padding: 18px 22px;
  margin: 14px 0;
}

.variant-header h2 {
  margin: 3px 0 0;
  font-size: 25px;
  letter-spacing: -0.025em;
}

.variant-header h2 span {
  color: var(--muted);
  font-weight: 550;
}

.variant-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(90px, 1fr));
  gap: 18px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 7px 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 750;
}

.status-badge.clean {
  color: #166534;
  background: #dcfce7;
}

.status-badge.review {
  color: #991b1b;
  background: #fee2e2;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 9px 0 0;
}

.mini-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
  font-size: 11px;
  font-weight: 650;
}

.output-text {
  min-height: 320px;
  max-height: 680px;
  overflow: auto;
  margin-top: 12px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fbfcfe;
  color: #263247;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.72;
}

.flag-mark {
  padding: 1px 2px;
  border-radius: 4px;
  color: inherit;
  cursor: help;
}

.empty-output {
  padding: 24px;
  border: 1px dashed #cbd5e1;
  border-radius: 14px;
  color: var(--muted);
  text-align: center;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 4px 0 16px;
}

.metric-card {
  border-radius: 16px;
  padding: 17px;
}

.metric-card span {
  display: block;
  min-height: 36px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
}

.metric-card strong {
  display: block;
  margin: 5px 0;
  font-size: 27px;
  letter-spacing: -0.03em;
}

.metric-card small {
  color: var(--muted);
  line-height: 1.35;
}

.metric-card.accent-a { border-top: 3px solid var(--a); }
.metric-card.accent-b { border-top: 3px solid var(--b); }

.table-card {
  border-radius: 18px;
  overflow: hidden;
}

.table-title {
  padding: 17px 20px;
  border-bottom: 1px solid var(--line);
  font-weight: 750;
}

.table-scroll { overflow-x: auto; }

.summary-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.summary-table th,
.summary-table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}

.summary-table th {
  background: var(--surface-soft);
  color: #475569;
  font-size: 11px;
  letter-spacing: .02em;
}

.summary-table tr:last-child td { border-bottom: none; }

.muted { color: var(--muted); }

.method-note {
  display: flex;
  gap: 13px;
  border-radius: 16px;
  padding: 16px 18px;
  margin: 15px 0 4px;
}

.method-icon,
.setup-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e0e7ff;
  color: #3730a3;
  font-weight: 800;
}

.method-note p {
  margin: 4px 0 0;
  color: var(--muted);
  line-height: 1.55;
  font-size: 13px;
}

.setup-panel {
  display: flex;
  gap: 16px;
  border-radius: 18px;
  padding: 22px;
}

.setup-panel .setup-icon {
  background: #fee2e2;
  color: #991b1b;
}

.generation-status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 18px;
}

.generation-status-grid > div {
  background: #ffffff;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 13px 14px;
}

.generation-status-grid span,
.generation-status-grid small {
  display: block;
  color: var(--muted);
  font-size: 11px;
}

.generation-status-grid strong {
  display: block;
  margin: 3px 0;
  overflow-wrap: anywhere;
  font-size: 13px;
}

.notice.success {
  border: 1px solid #86efac;
  background: #f0fdf4;
  color: #166534;
}

.setup-panel h2 { margin: 0 0 6px; }
.setup-panel p { color: var(--muted); }
.setup-panel pre {
  display: inline-block;
  padding: 12px 14px;
  border-radius: 10px;
  background: #0f172a;
  color: #e2e8f0;
}

footer { display: none !important; }

@media (max-width: 900px) {
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .generation-status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .variant-header { align-items: flex-start; flex-direction: column; }
  .variant-facts { width: 100%; }
}

@media (max-width: 640px) {
  .hero { padding: 22px 20px; border-radius: 18px; }
  .pipeline-grid { grid-template-columns: 1fr; }
  .metric-grid { grid-template-columns: 1fr; }
  .generation-status-grid { grid-template-columns: 1fr; }
  .variant-facts { grid-template-columns: 1fr; gap: 9px; }
}
"""


with gr.Blocks(
    title="RASopathy VUS Output Audit",
    theme=gr.themes.Soft(),
    css=CSS,
) as demo:
    gr.HTML(
        """
        <div class="hero">
          <div class="hero-badge">CONTROLLED OUTPUT REVIEW</div>
          <h1>RASopathy VUS Output Audit</h1>
          <p>
            Side-by-side review of pre-generated outputs from two AutoScientist
            pipelines. Select a paired variant, inspect the unmodified model
            text, and review content that may not be traceable to the supplied
            input fields.
          </p>
        </div>
        """
    )

    if STATE["error"]:
        gr.HTML(render_setup_error(STATE["error"]))
        with gr.Accordion("Generate outputs on this Space GPU", open=True):
            add_generation_controls()
        gr.HTML(render_methodology_note())
    else:
        left_meta = STATE["left_payload"]["meta"]
        right_meta = STATE["right_payload"]["meta"]
        left_name = format_pipeline_title(left_meta, PIPELINE_A_NAME)
        right_name = format_pipeline_title(right_meta, PIPELINE_B_NAME)

        with gr.Row(equal_height=True):
            gr.HTML(render_pipeline_card(left_meta, left_name, "a"))
            gr.HTML(render_pipeline_card(right_meta, right_name, "b"))

        with gr.Tabs():
            with gr.Tab("Variant comparison"):
                choices = [
                    (choice_label(pair), pair["pair_id"])
                    for pair in sorted(
                        STATE["pairs"],
                        key=lambda item: (
                            -(item["left_total"] + item["right_total"]),
                            choice_label(item),
                        ),
                    )
                ]
                initial_pair_id = choices[0][1]
                initial_values = compare_pair(initial_pair_id)

                selector = gr.Dropdown(
                    choices=choices,
                    value=initial_pair_id,
                    label="Choose a paired variant",
                    info="⚠ indicates at least one heuristic review signal in either pipeline.",
                    filterable=True,
                )

                variant_header = gr.HTML(initial_values[0])

                with gr.Row(equal_height=True):
                    with gr.Column():
                        gr.Markdown(f"### Pipeline A · {left_name}")
                        left_badge = gr.HTML(initial_values[1])
                        left_output = gr.HTML(initial_values[2])
                    with gr.Column():
                        gr.Markdown(f"### Pipeline B · {right_name}")
                        right_badge = gr.HTML(initial_values[3])
                        right_output = gr.HTML(initial_values[4])

                with gr.Accordion("Audit context", open=False):
                    gr.Markdown(
                        "The prompts below are shown exactly as recorded in each JSON file. "
                        "Differences in prompts should be considered when interpreting output differences."
                    )
                    with gr.Row():
                        left_instruction = gr.Textbox(
                            value=initial_values[5],
                            label="Pipeline A input instruction",
                            lines=10,
                            interactive=False,
                        )
                        right_instruction = gr.Textbox(
                            value=initial_values[6],
                            label="Pipeline B input instruction",
                            lines=10,
                            interactive=False,
                        )
                    output_hashes = gr.Textbox(
                        value=initial_values[7],
                        label="Recorded output hashes",
                        lines=2,
                        interactive=False,
                    )

                selector.change(
                    fn=compare_pair,
                    inputs=selector,
                    outputs=[
                        variant_header,
                        left_badge,
                        left_output,
                        right_badge,
                        right_output,
                        left_instruction,
                        right_instruction,
                        output_hashes,
                    ],
                )

            with gr.Tab("Aggregate summary"):
                gr.HTML(
                    render_summary(
                        STATE["pairs"],
                        left_name,
                        right_name,
                        STATE["pairing_stats"],
                    )
                )
                gr.HTML(render_methodology_note())

            with gr.Tab("Method and scope"):
                gr.Markdown(
                    """
                    ## What this Space does

                    1. Loads two pre-generated controlled-inference JSON files.
                    2. Pairs records using `record_id` when available, followed by
                       `clinvar_id + instruction hash`, `clinvar_id + protein change`,
                       and finally `clinvar_id`.
                    3. Recomputes the same text heuristics for both pipelines.
                    4. Shows the original generated outputs without rewriting or summarizing them.

                    ## What it does not do

                    - The review tabs do not run either model live. Inference is
                      isolated in the explicit GPU generation tab.
                    - It does not classify a flagged phrase as definitively false.
                    - It does not isolate the causal effect of Rephrase because the
                      compared pipelines use different base models.

                    ## Review categories

                    - **cDNA not traceable to input**
                    - **Unresolved template placeholder**
                    - **MONDO ID not traceable to input**
                    - **Potentially unsupported evidence claim**
                    """
                )
                gr.HTML(render_methodology_note())

            with gr.Tab("GPU generation"):
                gr.Markdown(
                    """## Regenerate or expand the controlled outputs

Use this panel to replace a small test run with the complete dataset, or to regenerate outputs after changing an adapter."""
                )
                add_generation_controls()


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=8, max_size=16).launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", "7860")),
        share=False,
        show_error=True,
    )
