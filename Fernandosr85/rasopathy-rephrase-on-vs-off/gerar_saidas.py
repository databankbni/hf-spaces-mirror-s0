"""
Controlled output generation for the RASopathy VUS audit Space.
This module is designed to run inside the GPU-backed Hugging Face Space.
It extracts the local LoRA archives, loads one quantized base model at a time,
generates auditable outputs, unloads the model, and writes one JSON file per
pipeline. It can be imported by app.py or executed from the command line.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable


GENERATOR_API_VERSION = "2.0"

SEED = 42
MAX_NEW_TOKENS = 700
DATASET_SPLIT = "train"
PAIRED_OUTPUT_FILE = "outputs_rephrase_pairs.json"
PAIRING_CONTRACT_VERSION = "paired-shared-prompt-v2.1"

ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class PipelineConfig:
    key: str
    display_name: str
    base_model: str
    original_base_model: str
    model_family: str
    adapter_archive: str
    dataset_repo: str
    output_file: str
    label: str
    rephrase_state: str


PIPELINES: dict[str, PipelineConfig] = {
    "mixtral_on": PipelineConfig(
        key="mixtral_on",
        display_name="Pipeline A — Mixtral / Rephrase ON",
        base_model="ybelkada/Mixtral-8x7B-Instruct-v0.1-bnb-4bit",
        original_base_model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        model_family="mixtral",
        adapter_archive="adaption_mixtral_8x7b_instruc_rasopathy_vus_tier1.tgz",
        dataset_repo="Fernandosr85/adaption-rasopathy-vus-tier1-reports",
        output_file="outputs_mixtral_on.json",
        label="mixtral_rephrase_on",
        rephrase_state="ON",
    ),
    "scout_off": PipelineConfig(
        key="scout_off",
        display_name="Pipeline B — Llama 4 Scout / Rephrase OFF",
        base_model="bnb-community/Llama-4-Scout-17B-16E-Instruct-bnb-4bit",
        original_base_model="meta-llama/Llama-4-Scout-17B-16E-Instruct",
        model_family="llama4",
        adapter_archive="adaption_llama_4_scout_17b_16_rasopathy_vus_tier1.tgz",
        dataset_repo="Fernandosr85/adaption-rasopathy-vus-tier1-reports-v1",
        output_file="outputs_scout_off.json",
        label="scout_rephrase_off",
        rephrase_state="OFF",
    ),
}


RUNTIME_CONTRACT = {
    "transformers": "4.52.4",
    "peft": "0.15.2",
    "huggingface_hub": "0.30.2",
    "bitsandbytes": "0.45.5",
    "accelerate": "1.6.0",
}


def _assert_runtime_contract() -> dict[str, str]:
    """
    Require the library stack used by the original pre-quantized MoE checkpoints.
    The Mixtral and Llama 4 Scout BNB archives store router weights in the
    packed representation expected by Transformers 4.52-era quantization code.
    Transformers 5.x can leave those packed weights attached to ordinary
    ``nn.Linear`` routers, producing the recurring matrix-shape failures.
    """
    installed: dict[str, str] = {}
    mismatches: list[str] = []

    for package, expected in RUNTIME_CONTRACT.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = "missing"
        installed[package] = actual
        if actual != expected:
            mismatches.append(f"{package}: expected {expected}, found {actual}")

    if mismatches:
        raise RuntimeError(
            "Incompatible inference runtime. This Space must use the pinned "
            "Transformers 4.52 stack because both base checkpoints contain "
            "pre-quantized MoE router weights.\n- " + "\n- ".join(mismatches)
        )

    return installed


# -----------------------------------------------------------------------------
# Heuristic review signals — kept aligned with app.py
# -----------------------------------------------------------------------------

import re

FABRICATION_REGEX = {
    "untraceable_cdna": re.compile(r"c\.\d+[ACGT]>[ACGT]", re.IGNORECASE),
    "unresolved_placeholder": re.compile(r"c\.\[[^\]]{0,60}\]", re.IGNORECASE),
    "untraceable_mondo": re.compile(r"MONDO:\d+", re.IGNORECASE),
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

REQUIREMENT_CONTEXT = re.compile(
    r"(required|requirement|before any|are needed|is needed|would be needed|"
    r"one would need|necessary|must be|remains? a vus|to strengthen|"
    r"to confirm|to establish|not (yet )?(been )?"
    r"(established|available|documented|reported)|absence of|lack of|"
    r"no (functional|segregation)|pending|awaiting|in order to|"
    r"additional evidence|for reclassification|could include|can include|"
    r"would include|should include|future studies|further studies)",
    re.IGNORECASE,
)

FORMAT_CONTAMINATION_PATTERNS = {
    "boxed_answer": re.compile(r"\\boxed\s*\{", re.IGNORECASE),
    "math_final_answer": re.compile(r"\bthe final answer is\b", re.IGNORECASE),
    "no_numerical_answer": re.compile(r"\bno numerical answer\b", re.IGNORECASE),
    "stepwise_reasoning": re.compile(
        r"(?mi)^\s*#{0,3}\s*(?:step\s*)?\d+\s*[:.)]"
    ),
    "problem_solving_template": re.compile(
        r"\b(?:understand|determine|solve) the (?:given )?(?:data|problem)\b",
        re.IGNORECASE,
    ),
}

CLINGEN_ABSENCE_PATTERNS = {
    "absence_of_clingen_curation": re.compile(
        r"\b(?:absence|lack)\s+of\s+(?:a\s+)?clingen\s+curation\b",
        re.IGNORECASE,
    ),
    "clingen_not_provided": re.compile(
        r"\bclingen\b.{0,80}\b(?:not provided|not explicitly stated|"
        r"not available|unknown)\b",
        re.IGNORECASE,
    ),
    "relationship_not_established": re.compile(
        r"\bgene[-– ]disease relationship\b.{0,80}\b"
        r"(?:not well established|not established|poorly established|"
        r"insufficiently established)\b",
        re.IGNORECASE,
    ),
    "limited_gene_disease_evidence": re.compile(
        r"\b(?:limited|weak|insufficient)\s+"
        r"(?:gene[-– ]disease|clingen)\s+(?:validity|evidence)\b",
        re.IGNORECASE,
    ),
}

GENCC_ABSENCE_PATTERNS = {
    "gencc_not_provided": re.compile(
        r"\bgencc\b.{0,80}\b(?:not provided|not explicitly stated|"
        r"not available|unknown)\b",
        re.IGNORECASE,
    ),
    "absence_of_gencc_context": re.compile(
        r"\b(?:absence|lack)\s+of\s+(?:a\s+)?gencc\b",
        re.IGNORECASE,
    ),
}

TIER_CONTRADICTION_PATTERNS = {
    "low_investigation_priority": re.compile(
        r"\b(?:low|lowest|minimal)\s+(?:investigation\s+)?priority\b",
        re.IGNORECASE,
    ),
    "not_priority_candidate": re.compile(
        r"\bnot\s+(?:a\s+)?(?:high[- ]priority|priority)\s+candidate\b",
        re.IGNORECASE,
    ),
}

GROUNDING_FIELD_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gene", ("gene",)),
    ("protein_change", ("protein_change", "protein_variant")),
    ("clinvar_id", ("clinvar_id",)),
    ("investigation_tier", ("investigation_tier", "tier_label", "tier")),
    ("investigation_score", ("investigation_score",)),
    (
        "cadd_phred",
        ("cadd_phred", "cadd_score", "cadd", "CADD_PHRED"),
    ),
    (
        "concordant_predictors",
        (
            "concordant_predictors",
            "n_concordant_predictors",
            "predictor_count",
            "concordant_predictor_count",
        ),
    ),
    (
        "clingen_validity",
        ("clingen_validity", "clingen_gene_disease_validity", "clingen_classification"),
    ),
    ("gencc_validity", ("gencc_validity", "gencc_classification")),
    ("primary_condition", ("primary_condition", "condition", "disease")),
    ("clingen_condition", ("clingen_condition", "curated_condition")),
    ("condition_match_type", ("condition_match_type",)),
    ("inheritance_mode", ("inheritance_mode", "mode_of_inheritance", "moi")),
    ("omim_primary", ("omim_primary", "omim_id", "omim")),
    ("protein_domain", ("protein_domain", "domain", "domain_context", "region")),
    ("snapshot_date", ("snapshot_date",)),
)


def _clean_scalar(value: Any) -> str:
    """Convert a scalar dataset value to a stable, readable string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        cleaned = [_clean_scalar(item) for item in value]
        return "; ".join(item for item in cleaned if item)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    value_text = str(value).strip()
    if value_text.lower() in {"", "none", "nan", "null", "n/a", "na"}:
        return ""
    return value_text


def _first_available(row: Any, keys: tuple[str, ...]) -> str:
    """Return the first non-empty value among equivalent dataset columns."""
    for key in keys:
        try:
            value = row.get(key)
        except AttributeError:
            value = None
        cleaned = _clean_scalar(value)
        if cleaned:
            return cleaned
    return ""


def _collect_grounding_fields(row: Any) -> dict[str, str]:
    """
    Collect only explicit structured values present in the dataset row.

    The reference output is intentionally excluded to prevent answer leakage.
    """
    fields: dict[str, str] = {}

    for canonical_name, candidate_keys in GROUNDING_FIELD_SPECS:
        value = _first_available(row, candidate_keys)
        if value:
            fields[canonical_name] = value

    try:
        row_items = row.items()
    except AttributeError:
        row_items = []

    for key, value in row_items:
        key_text = str(key)
        key_lower = key_text.lower()
        if key_text in fields:
            continue
        if not (
            key_lower.startswith("clingen_")
            or key_lower.startswith("gencc_")
        ):
            continue
        cleaned = _clean_scalar(value)
        if cleaned:
            fields.setdefault(key_text, cleaned)

    return fields


def build_grounded_instruction(
    row: Any,
) -> tuple[str, str, dict[str, str]]:
    """
    Preserve the original task and append explicit structured ground truth.
    """
    original_instruction = _clean_scalar(row.get("instruction"))
    if not original_instruction:
        raise ValueError("Dataset row has an empty instruction.")

    grounding_fields = _collect_grounding_fields(row)

    label_map = {
        "gene": "Gene",
        "protein_change": "Protein variant",
        "clinvar_id": "ClinVar ID",
        "investigation_tier": "Investigation tier",
        "investigation_score": "Investigation score",
        "cadd_phred": "CADD PHRED",
        "concordant_predictors": "Concordant predictors",
        "clingen_validity": "ClinGen validity",
        "gencc_validity": "GenCC validity",
        "primary_condition": "Primary condition",
        "clingen_condition": "ClinGen curated condition",
        "condition_match_type": "Condition match type",
        "inheritance_mode": "Mode of inheritance",
        "omim_primary": "OMIM",
        "protein_domain": "Protein domain/context",
        "snapshot_date": "Evidence snapshot date",
    }

    context_lines: list[str] = []
    for key, value in grounding_fields.items():
        label = label_map.get(key, key.replace("_", " ").strip().title())
        context_lines.append(f"- {label}: {value}")

    if not context_lines:
        context_lines.append(
            "- No additional structured evidence fields were available for this row."
        )

    requirements = [
        "- Use only facts explicitly present in the original task or the structured context below.",
        "- Never infer that ClinGen or GenCC curation is absent merely because a requested field is missing.",
        "- If a requested value is not supplied, state only that it is not available in the supplied record.",
        "- Distinguish research prioritization from ACMG/AMP clinical classification.",
        "- Do not claim that computational prediction alone is sufficient for pathogenic or benign reclassification.",
        "- Write a concise clinical-research summary without hidden or step-by-step reasoning.",
        "- Do not use mathematics-contest language, numbered solution steps, 'the final answer is', or boxed answers.",
    ]

    tier_value = grounding_fields.get("investigation_tier", "")
    if tier_value or re.search(r"\btier\s*1\b", original_instruction, re.I):
        requirements.append(
            "- Preserve the Tier 1 investigation-priority framing explicitly, "
            "while stating that Tier 1 is not an ACMG/AMP classification."
        )

    clingen_value = grounding_fields.get("clingen_validity", "")
    if clingen_value:
        requirements.append(
            f"- Preserve the exact ClinGen validity level: {clingen_value}."
        )

    gencc_value = grounding_fields.get("gencc_validity", "")
    if gencc_value:
        requirements.append(
            f"- Preserve the exact GenCC validity level: {gencc_value}."
        )

    grounded_instruction = (
        "ORIGINAL TASK\n"
        f"{original_instruction}\n\n"
        "STRUCTURED GROUND-TRUTH CONTEXT\n"
        + "\n".join(context_lines)
        + "\n\nOUTPUT CONTRACT\n"
        + "\n".join(requirements)
    )

    return original_instruction, grounded_instruction, grounding_fields


def detect_review_signals(
    text: str,
    instruction: str = "",
) -> dict[str, int]:
    """Count legacy heuristic signals while respecting requirement context."""
    counts = {
        key: len(regex.findall(text))
        for key, regex in FABRICATION_REGEX.items()
    }

    lower = text.lower()
    instruction_lower = instruction.lower()
    evidence_count = 0

    for phrase in UNSUPPORTED_EVIDENCE_PHRASES:
        for match in re.finditer(re.escape(phrase), lower):
            window = lower[
                max(0, match.start() - 180):
                min(len(lower), match.end() + 180)
            ]
            if REQUIREMENT_CONTEXT.search(window):
                continue
            if phrase in instruction_lower and REQUIREMENT_CONTEXT.search(
                instruction_lower
            ):
                continue
            evidence_count += 1

    counts["potentially_unsupported_evidence"] = evidence_count
    return counts


def _normalized_contains(text: str, value: str) -> bool:
    """Case-insensitive containment after normalizing whitespace and dashes."""
    def normalize(item: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            item.lower().replace("–", "-").replace("—", "-"),
        ).strip()

    normalized_value = normalize(value)
    if not normalized_value:
        return True
    return normalized_value in normalize(text)


def detect_semantic_audit(
    text: str,
    original_instruction: str,
    grounded_instruction: str,
    grounding_fields: dict[str, str],
    legacy_flags: dict[str, int],
) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Detect contradictions, omissions, format leakage, and unsupported claims."""
    counts = {
        "factual_contradiction": 0,
        "required_fact_omission": 0,
        "format_contamination": 0,
        "unsupported_assertion": int(
            legacy_flags.get("potentially_unsupported_evidence", 0)
        ),
    }
    details: dict[str, list[str]] = {key: [] for key in counts}

    if counts["unsupported_assertion"]:
        details["unsupported_assertion"].append(
            "Evidence phrase detected outside requirement/limitation context."
        )

    for label, pattern in FORMAT_CONTAMINATION_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            counts["format_contamination"] += len(matches)
            details["format_contamination"].append(
                f"{label}: {len(matches)} occurrence(s)"
            )

    tier_value = grounding_fields.get("investigation_tier", "")
    tier_required = bool(
        tier_value
        or re.search(r"\btier\s*1\b", original_instruction, re.IGNORECASE)
    )
    if tier_required:
        expected_tier = tier_value or "Tier 1"
        if not re.search(r"\btier\s*1\b", text, re.IGNORECASE):
            counts["required_fact_omission"] += 1
            details["required_fact_omission"].append(
                f"Required investigation tier omitted: {expected_tier}"
            )

        for label, pattern in TIER_CONTRADICTION_PATTERNS.items():
            if pattern.search(text):
                counts["factual_contradiction"] += 1
                details["factual_contradiction"].append(
                    f"{label}: contradicts Tier 1/high-priority framing"
                )

    clingen_validity = grounding_fields.get("clingen_validity", "")
    if clingen_validity:
        if not _normalized_contains(text, clingen_validity):
            counts["required_fact_omission"] += 1
            details["required_fact_omission"].append(
                f"ClinGen validity level omitted: {clingen_validity}"
            )

        for label, pattern in CLINGEN_ABSENCE_PATTERNS.items():
            if pattern.search(text):
                counts["factual_contradiction"] += 1
                details["factual_contradiction"].append(
                    f"{label}: conflicts with supplied ClinGen validity "
                    f"'{clingen_validity}'"
                )

        if clingen_validity.lower() in {"definitive", "strong", "moderate"}:
            weak_claim = re.compile(
                r"\b(?:weak|limited|insufficient|uncertain)\b.{0,60}"
                r"\b(?:gene[-– ]disease|clingen)\b|"
                r"\b(?:gene[-– ]disease|clingen)\b.{0,60}"
                r"\b(?:weak|limited|insufficient|uncertain)\b",
                re.IGNORECASE,
            )
            if weak_claim.search(text):
                counts["factual_contradiction"] += 1
                details["factual_contradiction"].append(
                    "Weak/limited validity language conflicts with supplied "
                    f"ClinGen level '{clingen_validity}'"
                )

    gencc_validity = grounding_fields.get("gencc_validity", "")
    if gencc_validity:
        if not _normalized_contains(text, gencc_validity):
            counts["required_fact_omission"] += 1
            details["required_fact_omission"].append(
                f"GenCC validity level omitted: {gencc_validity}"
            )

        for label, pattern in GENCC_ABSENCE_PATTERNS.items():
            if pattern.search(text):
                counts["factual_contradiction"] += 1
                details["factual_contradiction"].append(
                    f"{label}: conflicts with supplied GenCC validity "
                    f"'{gencc_validity}'"
                )

    return counts, details



# -----------------------------------------------------------------------------
# Controlled Rephrase ON × OFF pairing
# -----------------------------------------------------------------------------

PAIRING_CRITICAL_FIELDS = (
    "gene",
    "protein_change",
    "clinvar_id",
    "investigation_tier",
    "investigation_score",
    "cadd_phred",
    "concordant_predictors",
    "clingen_validity",
    "gencc_validity",
    "primary_condition",
    "clingen_condition",
    "condition_match_type",
    "inheritance_mode",
    "omim_primary",
    "protein_domain",
    "snapshot_date",
)


def _normalize_for_comparison(value: Any) -> str:
    """Normalize scalar values for cross-dataset equality checks."""
    return re.sub(
        r"\s+",
        " ",
        _clean_scalar(value)
        .lower()
        .replace("–", "-")
        .replace("—", "-"),
    ).strip()


def _comparison_key(
    row: Any,
    required: bool = True,
) -> str:
    """
    Build a stable variant key.

    ClinVar ID is preferred because transcript versions may differ while still
    referring to the same ClinVar record. When ``required`` is False, malformed
    or metadata-only rows return an empty string so they can be skipped and
    recorded in the pairing audit instead of aborting the full generation.
    """
    clinvar_id = _first_available(row, ("clinvar_id",))
    if clinvar_id:
        return f"clinvar:{clinvar_id}"

    gene = _first_available(row, ("gene",))
    protein_change = _first_available(
        row,
        ("protein_change", "protein_variant"),
    )
    if gene and protein_change:
        return f"variant:{gene}|{protein_change}"

    record_id = _first_available(row, ("record_id",))
    if record_id:
        return f"record:{record_id}"

    if not required:
        return ""

    raise ValueError(
        "Cannot build a comparison key: row has no ClinVar ID, "
        "gene/protein pair, or record_id."
    )


def _index_dataset_rows(
    rows: list[dict[str, Any]],
    condition_key: str,
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Index rows by stable variant key.

    Empty, malformed, or metadata-only rows are skipped and recorded rather
    than terminating the entire controlled comparison.
    """
    index: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    unkeyable_rows: list[dict[str, Any]] = []

    for position, row in enumerate(rows):
        key = _comparison_key(row, required=False)
        if not key:
            nonempty_fields = sorted(
                str(field)
                for field, value in row.items()
                if _clean_scalar(value)
            )
            unkeyable_rows.append(
                {
                    "condition": condition_key,
                    "position": position,
                    "available_nonempty_fields": nonempty_fields[:30],
                    "field_count": len(row),
                    "nonempty_field_count": len(nonempty_fields),
                    "instruction_preview": _clean_scalar(
                        row.get("instruction")
                    )[:240],
                }
            )
            continue

        if key in index:
            duplicates.append(
                {
                    "condition": condition_key,
                    "comparison_key": key,
                    "first_record_id": index[key].get("record_id"),
                    "duplicate_record_id": row.get("record_id"),
                    "duplicate_position": position,
                }
            )
            continue

        index[key] = row

    return index, duplicates, unkeyable_rows


def _extract_numeric_from_instruction(
    instruction: str,
    label_pattern: str,
) -> str:
    """Extract a numeric value only as a transparent fallback."""
    match = re.search(
        rf"{label_pattern}\s*:\s*([0-9]+(?:\.[0-9]+)?)",
        instruction,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _build_neutral_pair_instruction(
    canonical_row: dict[str, Any],
    source_instructions: dict[str, str],
) -> str:
    """
    Build one neutral task used identically for Rephrase ON and OFF.

    It intentionally does not copy the wording from either dataset condition.
    """
    fields = _collect_grounding_fields(canonical_row)

    cadd = fields.get("cadd_phred", "")
    predictors = fields.get("concordant_predictors", "")

    # Some historical dataset snapshots embedded these values only in the
    # instruction text. Use the two source instructions only as a traceable
    # numeric fallback; never infer values from the reference completion.
    if not cadd:
        for source_instruction in source_instructions.values():
            cadd = _extract_numeric_from_instruction(
                source_instruction,
                r"CADD\s+PHRED",
            )
            if cadd:
                canonical_row["cadd_phred"] = cadd
                break

    if not predictors:
        for source_instruction in source_instructions.values():
            predictors = _extract_numeric_from_instruction(
                source_instruction,
                r"Concordant\s+predictors",
            )
            if predictors:
                canonical_row["concordant_predictors"] = predictors
                break

    fields = _collect_grounding_fields(canonical_row)

    lines = [
        "Prepare a concise, source-grounded clinical-research summary for "
        "the RASopathy VUS below.",
        "",
        f"Gene: {fields.get('gene', 'not supplied')}",
        f"Protein variant: {fields.get('protein_change', 'not supplied')}",
        f"ClinVar ID: {fields.get('clinvar_id', 'not supplied')}",
        f"Investigation tier: {fields.get('investigation_tier', 'not supplied')}",
        f"Investigation score: {fields.get('investigation_score', 'not supplied')}",
        f"CADD PHRED: {fields.get('cadd_phred', 'not supplied')}",
        "Concordant predictors: "
        f"{fields.get('concordant_predictors', 'not supplied')}",
        "",
        "The summary must:",
        "- describe the computational prioritization evidence without "
        "treating it as proof of pathogenicity;",
        "- report the supplied ClinGen and GenCC gene-disease validity context;",
        "- preserve the condition-specificity or mapping context when supplied;",
        "- distinguish Tier 1 investigation priority from ACMG/AMP classification;",
        "- state whether the supplied evidence is sufficient for formal "
        "ACMG/AMP reclassification;",
        "- identify additional evidence needed when reclassification is not "
        "supported;",
        "- use a professional clinical-research format without step-by-step "
        "reasoning or mathematics-answer conventions.",
    ]
    return "\n".join(lines)


def _merge_paired_rows(
    on_row: dict[str, Any],
    off_row: dict[str, Any],
    comparison_key: str,
    pair_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Merge the two source rows into one canonical inference record.

    Rephrase ON values are used only as the first source; missing values are
    filled from OFF. Any conflicting structured values are recorded explicitly.
    """
    canonical = dict(on_row)
    for key, value in off_row.items():
        if not _clean_scalar(canonical.get(key)) and _clean_scalar(value):
            canonical[key] = value

    on_fields = _collect_grounding_fields(on_row)
    off_fields = _collect_grounding_fields(off_row)

    conflicts: dict[str, dict[str, str]] = {}
    for field in PAIRING_CRITICAL_FIELDS:
        on_value = on_fields.get(field, "")
        off_value = off_fields.get(field, "")
        if (
            on_value
            and off_value
            and _normalize_for_comparison(on_value)
            != _normalize_for_comparison(off_value)
        ):
            conflicts[field] = {
                "rephrase_on": on_value,
                "rephrase_off": off_value,
            }

    source_instructions = {
        "rephrase_on": _clean_scalar(on_row.get("instruction")),
        "rephrase_off": _clean_scalar(off_row.get("instruction")),
    }
    source_outputs = {
        "rephrase_on": _clean_scalar(on_row.get("output")),
        "rephrase_off": _clean_scalar(off_row.get("output")),
    }

    neutral_instruction = _build_neutral_pair_instruction(
        canonical,
        source_instructions,
    )
    canonical["instruction"] = neutral_instruction
    canonical["_comparison_key"] = comparison_key
    canonical["_pair_index"] = pair_index
    canonical["_source_instructions"] = source_instructions
    canonical["_reference_outputs"] = source_outputs
    canonical["_source_grounding_conflicts"] = conflicts

    audit = {
        "comparison_key": comparison_key,
        "pair_index": pair_index,
        "record_id_on": on_row.get("record_id"),
        "record_id_off": off_row.get("record_id"),
        "source_instruction_hashes": {
            key: _sha256_text(value) if value else None
            for key, value in source_instructions.items()
        },
        "source_instructions_identical": (
            _normalize_for_comparison(source_instructions["rephrase_on"])
            == _normalize_for_comparison(source_instructions["rephrase_off"])
        ),
        "grounding_conflicts": conflicts,
    }
    return canonical, audit


def prepare_paired_records(
    token: str,
    limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Select the same variants from both datasets and build one shared prompt.

    Records with conflicting critical structured fields are excluded from the
    controlled pair set rather than silently choosing one value.
    """
    from datasets import load_dataset

    on_config = PIPELINES["mixtral_on"]
    off_config = PIPELINES["scout_off"]

    if progress_callback:
        progress_callback("Loading Rephrase ON dataset for pairing", 0, 1)
    on_dataset = load_dataset(
        on_config.dataset_repo,
        split=DATASET_SPLIT,
        token=token,
    )

    if progress_callback:
        progress_callback("Loading Rephrase OFF dataset for pairing", 0, 1)
    off_dataset = load_dataset(
        off_config.dataset_repo,
        split=DATASET_SPLIT,
        token=token,
    )

    on_rows = [dict(row) for row in on_dataset]
    off_rows = [dict(row) for row in off_dataset]

    (
        on_index,
        on_duplicates,
        on_unkeyable_rows,
    ) = _index_dataset_rows(on_rows, "rephrase_on")
    (
        off_index,
        off_duplicates,
        off_unkeyable_rows,
    ) = _index_dataset_rows(off_rows, "rephrase_off")

    # Python dictionaries preserve insertion order. Iterating over the ON index
    # preserves the ON dataset order without re-evaluating malformed raw rows.
    shared_keys = [
        key
        for key in on_index
        if key in off_index
    ]

    records: list[dict[str, Any]] = []
    pair_audits: list[dict[str, Any]] = []
    excluded_conflicts: list[dict[str, Any]] = []

    for shared_key in shared_keys:
        canonical, audit = _merge_paired_rows(
            on_index[shared_key],
            off_index[shared_key],
            comparison_key=shared_key,
            pair_index=len(records),
        )

        if audit["grounding_conflicts"]:
            excluded_conflicts.append(audit)
            continue

        records.append(canonical)
        pair_audits.append(audit)

        if limit is not None and limit > 0 and len(records) >= limit:
            break

    if not records:
        raise RuntimeError(
            "No valid shared variants were found across the Rephrase ON and "
            "Rephrase OFF datasets after conflict checks. "
            f"ON indexed rows={len(on_index)}, "
            f"OFF indexed rows={len(off_index)}, "
            f"shared keys={len(shared_keys)}, "
            f"excluded conflicts={len(excluded_conflicts)}, "
            f"unkeyable ON rows={len(on_unkeyable_rows)}, "
            f"unkeyable OFF rows={len(off_unkeyable_rows)}."
        )

    same_base = (
        on_config.original_base_model.rstrip("/")
        == off_config.original_base_model.rstrip("/")
    )
    same_family = on_config.model_family == off_config.model_family

    interpretation_boundary = {
        "comparison_type": (
            "controlled_rephrase_ablation"
            if same_base and same_family
            else "paired_end_to_end_pipeline_comparison"
        ),
        "same_variants": True,
        "same_variant_order": True,
        "same_grounded_prompt": True,
        "same_seed": True,
        "same_decoding": True,
        "same_original_base_model": same_base,
        "same_model_family": same_family,
        "same_adapter": (
            on_config.adapter_archive == off_config.adapter_archive
        ),
        "isolates_rephrase_effect": bool(same_base and same_family),
        "confounders": (
            []
            if same_base and same_family
            else [
                "base model differs",
                "model family differs",
                "adapter weights differ",
                "training dataset/rephrase recipe may differ",
            ]
        ),
        "required_for_pure_ablation": (
            "Use the same original base model and model family with two "
            "separately trained adapters whose only recipe difference is "
            "Rephrase ON versus Rephrase OFF."
        ),
    }

    audit = {
        "contract_version": PAIRING_CONTRACT_VERSION,
        "selection_basis": "intersection by ClinVar ID, fallback gene/protein",
        "canonical_prompt_source": "neutral structured template",
        "on_dataset_repo": on_config.dataset_repo,
        "off_dataset_repo": off_config.dataset_repo,
        "on_dataset_rows": len(on_rows),
        "off_dataset_rows": len(off_rows),
        "on_indexed_variant_rows": len(on_index),
        "off_indexed_variant_rows": len(off_index),
        "shared_variant_count_before_conflict_filter": len(shared_keys),
        "selected_pair_count": len(records),
        "duplicate_rows": on_duplicates + off_duplicates,
        "unkeyable_rows": on_unkeyable_rows + off_unkeyable_rows,
        "unkeyable_row_count": (
            len(on_unkeyable_rows) + len(off_unkeyable_rows)
        ),
        "excluded_grounding_conflicts": excluded_conflicts,
        "pair_audits": pair_audits,
        "interpretation_boundary": interpretation_boundary,
    }
    return records, audit


def _text_metrics(text: str) -> dict[str, Any]:
    """Compute simple transparent style metrics for one output."""
    stripped = text.strip()
    words = re.findall(r"\b[\w'-]+\b", stripped)
    paragraphs = [
        part.strip()
        for part in re.split(r"\n\s*\n", stripped)
        if part.strip()
    ]
    return {
        "characters": len(stripped),
        "words": len(words),
        "paragraphs": len(paragraphs),
        "tier_mentions": len(re.findall(r"\btier\s*1\b", stripped, re.I)),
        "clingen_mentions": len(re.findall(r"\bclingen\b", stripped, re.I)),
        "gencc_mentions": len(re.findall(r"\bgencc\b", stripped, re.I)),
        "acmg_mentions": len(re.findall(r"\bacmg/?amp\b", stripped, re.I)),
    }


def _normalized_text_similarity(left: str, right: str) -> float:
    """Return a reproducible normalized character-sequence similarity."""
    normalize = lambda value: re.sub(r"\s+", " ", value.lower()).strip()
    return round(
        SequenceMatcher(
            None,
            normalize(left),
            normalize(right),
        ).ratio(),
        4,
    )


def build_paired_output(
    on_output_path: Path,
    off_output_path: Path,
    paired_output_path: Path,
    pairing_audit: dict[str, Any],
) -> Path:
    """Create a record-aligned Rephrase ON × OFF comparison JSON."""
    on_payload = json.loads(on_output_path.read_text(encoding="utf-8"))
    off_payload = json.loads(off_output_path.read_text(encoding="utf-8"))

    on_results = {
        row["comparison_key"]: row
        for row in on_payload.get("results", [])
    }
    off_results = {
        row["comparison_key"]: row
        for row in off_payload.get("results", [])
    }

    on_keys = list(on_results)
    off_keys = list(off_results)
    if on_keys != off_keys:
        raise RuntimeError(
            "Paired output alignment failed: ON and OFF comparison keys or "
            "ordering differ."
        )

    pairs: list[dict[str, Any]] = []
    for pair_index, key in enumerate(on_keys):
        on_row = on_results[key]
        off_row = off_results[key]

        if on_row["instruction_hash"] != off_row["instruction_hash"]:
            raise RuntimeError(
                f"Shared-prompt contract failed for {key}: instruction hashes differ."
            )

        on_text = on_row.get("generated_output", "")
        off_text = off_row.get("generated_output", "")
        on_metrics = _text_metrics(on_text)
        off_metrics = _text_metrics(off_text)

        pairs.append(
            {
                "pair_index": pair_index,
                "comparison_key": key,
                "clinvar_id": on_row.get("clinvar_id"),
                "gene": on_row.get("gene"),
                "protein_change": on_row.get("protein_change"),
                "shared_instruction_hash": on_row["instruction_hash"],
                "shared_grounded_instruction": on_row.get(
                    "grounded_instruction",
                    on_row.get("instruction", ""),
                ),
                "grounding_fields": on_row.get("grounding_fields", {}),
                "source_instructions": on_row.get("source_instructions", {}),
                "reference_outputs": on_row.get("reference_outputs", {}),
                "rephrase_on": {
                    "pipeline": on_payload["meta"].get("display_name"),
                    "base_model": on_payload["meta"].get("base_model"),
                    "adapter_archive": on_payload["meta"].get("adapter_archive"),
                    "generated_output": on_text,
                    "fabrication_flags": on_row.get("fabrication_flags", {}),
                    "semantic_flags": on_row.get("semantic_flags", {}),
                    "semantic_details": on_row.get("semantic_details", {}),
                    "total_flags": on_row.get("total_flags", 0),
                    "text_metrics": on_metrics,
                },
                "rephrase_off": {
                    "pipeline": off_payload["meta"].get("display_name"),
                    "base_model": off_payload["meta"].get("base_model"),
                    "adapter_archive": off_payload["meta"].get("adapter_archive"),
                    "generated_output": off_text,
                    "fabrication_flags": off_row.get("fabrication_flags", {}),
                    "semantic_flags": off_row.get("semantic_flags", {}),
                    "semantic_details": off_row.get("semantic_details", {}),
                    "total_flags": off_row.get("total_flags", 0),
                    "text_metrics": off_metrics,
                },
                "comparison_metrics": {
                    "exact_match": on_text.strip() == off_text.strip(),
                    "normalized_text_similarity": _normalized_text_similarity(
                        on_text,
                        off_text,
                    ),
                    "character_delta_on_minus_off": (
                        on_metrics["characters"] - off_metrics["characters"]
                    ),
                    "word_delta_on_minus_off": (
                        on_metrics["words"] - off_metrics["words"]
                    ),
                    "paragraph_delta_on_minus_off": (
                        on_metrics["paragraphs"] - off_metrics["paragraphs"]
                    ),
                    "flag_delta_on_minus_off": (
                        int(on_row.get("total_flags", 0))
                        - int(off_row.get("total_flags", 0))
                    ),
                },
            }
        )

    payload = {
        "meta": {
            "status": "complete",
            "label": "rephrase_on_vs_off_paired_comparison",
            "pairing_contract": pairing_audit,
            "n_pairs": len(pairs),
            "on_output_file": on_output_path.name,
            "off_output_file": off_output_path.name,
            "interpretation_boundary": pairing_audit[
                "interpretation_boundary"
            ],
        },
        "pairs": pairs,
    }
    _write_json_atomic(paired_output_path, payload)
    return paired_output_path

# -----------------------------------------------------------------------------
# Archive handling
# -----------------------------------------------------------------------------


def _safe_tar_extract(archive: tarfile.TarFile, destination: Path) -> None:
    """Extract a tar archive while rejecting path traversal entries."""
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"Unsafe archive member: {member.name}") from exc

    try:
        archive.extractall(destination, filter="data")
    except TypeError:
        archive.extractall(destination)


def _extract_zstd_tar(archive_path: Path, destination: Path) -> None:
    """Extract a zstd-compressed tar archive using Python zstandard."""
    try:
        import zstandard as zstd
    except ImportError as exc:
        raise RuntimeError(
            "The adapter archive uses zstd compression, but the zstandard "
            "package is not installed."
        ) from exc

    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as temp_file:
        temp_tar = Path(temp_file.name)

    try:
        decompressor = zstd.ZstdDecompressor()
        with archive_path.open("rb") as source, temp_tar.open("wb") as target:
            decompressor.copy_stream(source, target)
        with tarfile.open(temp_tar, "r:") as archive:
            _safe_tar_extract(archive, destination)
    finally:
        temp_tar.unlink(missing_ok=True)


def find_adapter_directory(root: Path) -> Path:
    """Find the directory containing adapter_config.json and adapter weights."""
    candidates: list[Path] = []
    for config_path in root.rglob("adapter_config.json"):
        parent = config_path.parent
        has_weights = any(
            (parent / filename).is_file()
            for filename in (
                "adapter_model.safetensors",
                "adapter_model.bin",
                "pytorch_model.bin",
            )
        )
        if has_weights:
            candidates.append(parent)

    if not candidates:
        found_configs = list(root.rglob("adapter_config.json"))
        if found_configs:
            raise FileNotFoundError(
                "adapter_config.json was found, but no adapter weight file was "
                f"found beside it. Configs: {[str(path) for path in found_configs]}"
            )
        raise FileNotFoundError(
            f"No PEFT adapter directory was found under {root}. The archive must "
            "contain adapter_config.json and adapter_model.safetensors or .bin."
        )

    candidates.sort(key=lambda path: (len(path.parts), str(path)))
    return candidates[0]


def extract_adapter_archive(
    archive_path: Path,
    extraction_root: Path,
    force: bool = False,
) -> Path:
    """Extract an adapter archive and return its PEFT directory."""
    if not archive_path.is_file():
        raise FileNotFoundError(f"Adapter archive not found: {archive_path}")

    destination = extraction_root / archive_path.name.replace(".tgz", "")
    marker = destination / ".extraction_complete"

    if destination.exists() and marker.exists() and not force:
        return find_adapter_directory(destination)

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    magic = archive_path.read_bytes()[:4]
    try:
        if magic == b"\x28\xb5\x2f\xfd":
            _extract_zstd_tar(archive_path, destination)
        else:
            try:
                with tarfile.open(archive_path, "r:*") as archive:
                    _safe_tar_extract(archive, destination)
            except tarfile.ReadError:
                result = subprocess.run(
                    ["tar", "-xf", str(archive_path), "-C", str(destination)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        "Could not extract adapter archive. "
                        f"tar stderr: {result.stderr.strip()}"
                    )

        adapter_dir = find_adapter_directory(destination)
        marker.write_text(str(adapter_dir), encoding="utf-8")
        return adapter_dir
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


# -----------------------------------------------------------------------------
# Output generation
# -----------------------------------------------------------------------------


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _package_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "unknown"


def _gpu_metadata(torch_module: Any) -> dict[str, Any]:
    if not torch_module.cuda.is_available():
        return {"available": False}

    return {
        "available": True,
        "name": torch_module.cuda.get_device_name(0),
        "count": torch_module.cuda.device_count(),
        "cuda_version": torch_module.version.cuda,
        "capability": list(torch_module.cuda.get_device_capability(0)),
    }


def _input_device(model: Any) -> Any:
    """Return the device hosting the input embedding layer."""
    try:
        return model.get_input_embeddings().weight.device
    except Exception:
        for parameter in model.parameters():
            if getattr(parameter, "device", None) is not None and parameter.device.type != "meta":
                return parameter.device
        raise RuntimeError("Could not determine the model input device.")


def _move_inputs(inputs: Any, device: Any) -> Any:
    if hasattr(inputs, "to"):
        return inputs.to(device)
    return {
        key: value.to(device) if hasattr(value, "to") else value
        for key, value in inputs.items()
    }


def _build_text_prompt(tokenizer_or_processor: Any, instruction: str, family: str) -> str:
    if family == "llama4":
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": instruction}],
            }
        ]
    else:
        messages = [{"role": "user", "content": instruction}]

    try:
        return tokenizer_or_processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        return f"User: {instruction}\nAssistant:"


def _validate_adapter_base(adapter_dir: Path, config: PipelineConfig) -> dict[str, Any]:
    config_path = adapter_dir / "adapter_config.json"
    adapter_config = json.loads(config_path.read_text(encoding="utf-8"))
    recorded_base = str(adapter_config.get("base_model_name_or_path", "")).strip()

    return {
        "adapter_config_path": str(config_path),
        "recorded_base_model": recorded_base,
        "expected_original_base_model": config.original_base_model,
        "base_name_matches": (
            not recorded_base
            or recorded_base.rstrip("/").split("/")[-1].lower()
            == config.original_base_model.rstrip("/").split("/")[-1].lower()
        ),
    }


def generate_pipeline_output(
    config: PipelineConfig,
    base_dir: Path,
    output_path: Path | None = None,
    limit: int | None = None,
    max_new_tokens: int = MAX_NEW_TOKENS,
    token: str | None = None,
    progress_callback: ProgressCallback | None = None,
    overwrite: bool = False,
    cleanup_extracted_adapter: bool = True,
    records: list[dict[str, Any]] | None = None,
    pairing_audit: dict[str, Any] | None = None,
) -> Path:
    """Generate one pipeline JSON using the Space GPU."""
    token = (token or os.getenv("HF_TOKEN", "")).strip()
    if not token:
        raise RuntimeError("HF_TOKEN is not available in the Space environment.")

    runtime_versions = _assert_runtime_contract()

    output_path = output_path or (base_dir / config.output_file)
    if output_path.exists() and not overwrite:
        if records is not None:
            raise RuntimeError(
                f"{output_path.name} already exists. Paired comparison mode "
                "requires overwrite=True so stale unpaired outputs cannot be "
                "mixed with the new shared-prompt contract."
            )
        return output_path

    archive_path = base_dir / config.adapter_archive
    extraction_root = base_dir / ".adapter_runtime"

    if progress_callback:
        progress_callback(f"Extracting {config.display_name} adapter", 0, 1)
    adapter_dir = extract_adapter_archive(archive_path, extraction_root)
    adapter_audit = _validate_adapter_base(adapter_dir, config)

    import torch
    from datasets import load_dataset
    from peft import PeftModel
    from transformers import (
        AutoModelForCausalLM,
        AutoProcessor,
        AutoTokenizer,
        Llama4ForConditionalGeneration,
        set_seed,
    )

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is not available. Select GPU hardware in the Space settings "
            "before starting controlled generation."
        )

    set_seed(SEED)
    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.use_deterministic_algorithms(True, warn_only=True)

    if records is None:
        if progress_callback:
            progress_callback(f"Loading dataset for {config.display_name}", 0, 1)
        dataset = load_dataset(
            config.dataset_repo,
            split=DATASET_SPLIT,
            token=token,
        )
        if limit is not None and limit > 0:
            dataset = dataset.select(range(min(limit, len(dataset))))
        inference_rows = [dict(row) for row in dataset]
    else:
        inference_rows = [dict(row) for row in records]

    base_model = None
    model = None
    tokenizer_or_processor = None
    started_at = time.time()

    try:
        if progress_callback:
            progress_callback(f"Loading {config.base_model}", 0, 1)

        common_model_kwargs = {
            "device_map": "auto",
            "token": token,
            "trust_remote_code": True,
            "low_cpu_mem_usage": True,
        }

        if config.model_family == "llama4":
            tokenizer_or_processor = AutoProcessor.from_pretrained(
                config.base_model,
                token=token,
                trust_remote_code=True,
            )
            base_model = Llama4ForConditionalGeneration.from_pretrained(
                config.base_model,
                torch_dtype=torch.bfloat16,
                **common_model_kwargs,
            )
        else:
            tokenizer_or_processor = AutoTokenizer.from_pretrained(
                config.base_model,
                token=token,
                trust_remote_code=True,
            )
            if tokenizer_or_processor.pad_token is None:
                tokenizer_or_processor.pad_token = tokenizer_or_processor.eos_token
            base_model = AutoModelForCausalLM.from_pretrained(
                config.base_model,
                torch_dtype=torch.bfloat16,
                **common_model_kwargs,
            )

        if progress_callback:
            progress_callback(f"Applying LoRA adapter for {config.display_name}", 0, 1)
        model = PeftModel.from_pretrained(
            base_model,
            str(adapter_dir),
            is_trainable=False,
        )
        model.eval()

        results: list[dict[str, Any]] = []
        total = len(inference_rows)

        for index, row in enumerate(inference_rows):
            (
                original_instruction,
                grounded_instruction,
                grounding_fields,
            ) = build_grounded_instruction(row)

            prompt_text = _build_text_prompt(
                tokenizer_or_processor,
                grounded_instruction,
                config.model_family,
            )

            if config.model_family == "llama4":
                inputs = tokenizer_or_processor(
                    text=prompt_text,
                    return_tensors="pt",
                )
            else:
                inputs = tokenizer_or_processor(
                    prompt_text,
                    return_tensors="pt",
                )

            device = _input_device(model)
            inputs = _move_inputs(inputs, device)
            prompt_length = int(inputs["input_ids"].shape[-1])

            nested_tokenizer = getattr(tokenizer_or_processor, "tokenizer", None)
            pad_token_id = (
                getattr(tokenizer_or_processor, "pad_token_id", None)
                or getattr(nested_tokenizer, "pad_token_id", None)
                or getattr(tokenizer_or_processor, "eos_token_id", None)
                or getattr(nested_tokenizer, "eos_token_id", None)
            )

            generation_kwargs = {
                "max_new_tokens": max_new_tokens,
                "do_sample": False,
                "num_beams": 1,
                "use_cache": True,
            }
            if pad_token_id is not None:
                generation_kwargs["pad_token_id"] = pad_token_id

            with torch.inference_mode():
                generated_ids = model.generate(
                    **inputs,
                    **generation_kwargs,
                )

            completion_ids = generated_ids[:, prompt_length:]
            if config.model_family == "llama4":
                generated = tokenizer_or_processor.batch_decode(
                    completion_ids,
                    skip_special_tokens=True,
                )[0].strip()
            else:
                generated = tokenizer_or_processor.decode(
                    completion_ids[0],
                    skip_special_tokens=True,
                ).strip()

            legacy_flags = detect_review_signals(
                generated,
                grounded_instruction,
            )
            semantic_flags, semantic_details = detect_semantic_audit(
                text=generated,
                original_instruction=original_instruction,
                grounded_instruction=grounded_instruction,
                grounding_fields=grounding_fields,
                legacy_flags=legacy_flags,
            )

            legacy_fabrication_total = sum(
                count
                for name, count in legacy_flags.items()
                if name != "potentially_unsupported_evidence"
            )
            total_flags = (
                legacy_fabrication_total
                + sum(semantic_flags.values())
            )

            results.append(
                {
                    "record_id": row.get("record_id"),
                    "comparison_key": (
                        row.get("_comparison_key")
                        or _comparison_key(row)
                    ),
                    "pair_index": row.get("_pair_index", index),
                    "rephrase_state": config.rephrase_state,
                    "clinvar_id": row.get("clinvar_id"),
                    "gene": row.get("gene"),
                    "protein_change": row.get("protein_change"),
                    "original_instruction": original_instruction,
                    "grounded_instruction": grounded_instruction,
                    "instruction": grounded_instruction,
                    "original_instruction_hash": _sha256_text(
                        original_instruction
                    ),
                    "instruction_hash": _sha256_text(
                        grounded_instruction
                    ),
                    "grounding_fields": grounding_fields,
                    "source_instructions": row.get(
                        "_source_instructions",
                        {config.rephrase_state.lower(): original_instruction},
                    ),
                    "reference_outputs": row.get(
                        "_reference_outputs",
                        {config.rephrase_state.lower(): row.get("output", "")},
                    ),
                    "source_grounding_conflicts": row.get(
                        "_source_grounding_conflicts",
                        {},
                    ),
                    "generated_output": generated,
                    "original_output": row.get("output", ""),
                    "fabrication_flags": legacy_flags,
                    "semantic_flags": semantic_flags,
                    "semantic_details": semantic_details,
                    "total_flags": total_flags,
                    "repro_hash": _sha256_text(
                        f"{SEED}|{config.base_model}|"
                        f"{grounded_instruction}|{generated}"
                    )[:20],
                }
            )

            if progress_callback:
                progress_callback(
                    f"{config.display_name}: generated {index + 1}/{total}",
                    index + 1,
                    total,
                )

            # Write a recoverable partial snapshot after each record.
            partial_payload = {
                "meta": {
                    "status": "partial",
                    "pipeline": asdict(config),
                    "completed": index + 1,
                    "total": total,
                },
                "results": results,
            }
            _write_json_atomic(
                output_path.with_suffix(output_path.suffix + ".partial"),
                partial_payload,
            )

        payload = {
            "meta": {
                "status": "complete",
                "label": config.label,
                "display_name": config.display_name,
                "rephrase_state": config.rephrase_state,
                "base_model": config.base_model,
                "original_base_model": config.original_base_model,
                "adapter_archive": config.adapter_archive,
                "adapter_directory": str(adapter_dir.relative_to(base_dir)),
                "adapter_audit": adapter_audit,
                "runtime_contract": runtime_versions,
                "dataset_repo": config.dataset_repo,
                "dataset_split": DATASET_SPLIT,
                "seed": SEED,
                "max_new_tokens": max_new_tokens,
                "decoding": "greedy (do_sample=False, num_beams=1)",
                "prompt_contract": "grounded-structured-context-v1",
                "pairing_contract": pairing_audit,
                "audit_taxonomy": {
                    "legacy": [
                        "untraceable_cdna",
                        "unresolved_placeholder",
                        "untraceable_mondo",
                        "potentially_unsupported_evidence",
                    ],
                    "semantic": [
                        "factual_contradiction",
                        "required_fact_omission",
                        "format_contamination",
                        "unsupported_assertion",
                    ],
                },
                "n_variants": len(results),
                "n_flagged": sum(row["total_flags"] > 0 for row in results),
                "elapsed_seconds": round(time.time() - started_at, 2),
                "gpu": _gpu_metadata(torch),
                "runtime": {
                    "python": platform.python_version(),
                    "torch": _package_version("torch"),
                    "transformers": _package_version("transformers"),
                    "peft": _package_version("peft"),
                    "accelerate": _package_version("accelerate"),
                    "bitsandbytes": _package_version("bitsandbytes"),
                    "datasets": _package_version("datasets"),
                },
            },
            "results": results,
        }
        _write_json_atomic(output_path, payload)
        output_path.with_suffix(output_path.suffix + ".partial").unlink(missing_ok=True)
        return output_path

    finally:
        if model is not None:
            del model
        if base_model is not None:
            del base_model
        if tokenizer_or_processor is not None:
            del tokenizer_or_processor
        gc.collect()
        if "torch" in locals() and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        if cleanup_extracted_adapter:
            extraction_directory = extraction_root / config.adapter_archive.replace(".tgz", "")
            shutil.rmtree(extraction_directory, ignore_errors=True)


def generate_all_outputs(
    base_dir: Path,
    limit: int | None = None,
    overwrite: bool = False,
    token: str | None = None,
    progress_callback: ProgressCallback | None = None,
    max_new_tokens: int = MAX_NEW_TOKENS,
) -> list[Path]:
    """
    Generate record-aligned Rephrase ON and OFF outputs plus a paired JSON.

    Both conditions receive the same variants, in the same order, with the
    same neutral grounded prompt, seed, decoding settings, and token budget.
    """
    token = (token or os.getenv("HF_TOKEN", "")).strip()
    if not token:
        raise RuntimeError("HF_TOKEN is not available in the Space environment.")

    paired_records, pairing_audit = prepare_paired_records(
        token=token,
        limit=limit,
        progress_callback=progress_callback,
    )

    outputs: list[Path] = []
    for config in (PIPELINES["mixtral_on"], PIPELINES["scout_off"]):
        outputs.append(
            generate_pipeline_output(
                config=config,
                base_dir=base_dir,
                output_path=base_dir / config.output_file,
                limit=None,
                max_new_tokens=max_new_tokens,
                token=token,
                progress_callback=progress_callback,
                overwrite=overwrite,
                records=paired_records,
                pairing_audit=pairing_audit,
            )
        )

    paired_path = build_paired_output(
        on_output_path=outputs[0],
        off_output_path=outputs[1],
        paired_output_path=base_dir / PAIRED_OUTPUT_FILE,
        pairing_audit=pairing_audit,
    )
    outputs.append(paired_path)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pipeline",
        choices=["mixtral_on", "scout_off", "all"],
        default="all",
    )
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=MAX_NEW_TOKENS,
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()

    def progress(message: str, current: int, total: int) -> None:
        suffix = f" [{current}/{total}]" if total else ""
        print(f"{message}{suffix}", flush=True)

    if args.pipeline == "all":
        paths = generate_all_outputs(
            base_dir=base_dir,
            limit=args.limit,
            overwrite=args.overwrite,
            progress_callback=progress,
            max_new_tokens=args.max_new_tokens,
        )
    else:
        token = os.getenv("HF_TOKEN", "").strip()
        if not token:
            raise RuntimeError("HF_TOKEN is not available in the environment.")

        paired_records, pairing_audit = prepare_paired_records(
            token=token,
            limit=args.limit,
            progress_callback=progress,
        )
        config = PIPELINES[args.pipeline]
        paths = [
            generate_pipeline_output(
                config=config,
                base_dir=base_dir,
                limit=None,
                max_new_tokens=args.max_new_tokens,
                token=token,
                overwrite=args.overwrite,
                progress_callback=progress,
                records=paired_records,
                pairing_audit=pairing_audit,
            )
        ]

    for path in paths:
        print(f"Saved: {path}")


if __name__ == "__main__":
    main()
