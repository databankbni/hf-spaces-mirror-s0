"""Theme clustering over the 606 embedded review chunks.

Strategy (with graceful fallback):
  Primary  — Groq/Llama LLM clustering: batch the chunk texts, ask the model to
             assign each to one of 6-8 themes it discovers, then aggregate.
  Fallback — pure TF-IDF + KMeans (no extra deps beyond sklearn which sentence-
             transformers already pulls in transitively).

BERTopic is NOT used: it requires pytorch + umap-learn + hdbscan which
creates dependency conflicts in this environment (ADR-024).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _insecure_http_client() -> httpx.Client:
    """httpx client with TLS verification disabled.

    Mirrors the project's existing posture (HF_HUB_DISABLE_SSL_VERIFICATION=1,
    ADR-022) for this machine's TLS-inspecting proxy whose root CA is absent
    from certifi's bundle.
    """
    return httpx.Client(verify=False)

CHUNKS_PATH = Path("data/output/chunks.jsonl")
THEMES_PATH = Path("data/output/themes.json")

# Groq call settings (mirrors Phase 2 conservative settings)
_GROQ_MODEL = "llama-3.3-70b-versatile"
_BATCH_SIZE = 40          # chunks per Groq call
_BATCH_DELAY = 4.0        # seconds between calls
_TARGET_THEMES = 6        # ask the LLM to find 5-6 insight-rich themes
_DISCOVERY_SAMPLE_SIZE = 60  # chunks sampled across the corpus for theme discovery

# Discovery-specific keyword filter. Theme clustering runs ONLY on chunks whose
# text mentions music discovery / recommendation behaviour, so the resulting
# themes are discovery-specific rather than generic app-review categories.
DISCOVERY_KEYWORDS = [
    "discover",
    "recommend",
    "algorithm",
    "repeat",
    "same songs",
    "playlist",
    "suggestion",
    "personali",
]


def _load_chunks() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(CHUNKS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _filter_by_keywords(
    chunks: list[dict[str, Any]], keywords: list[str]
) -> list[dict[str, Any]]:
    """Keep only chunks whose text contains at least one keyword (case-insensitive)."""
    kws = [k.lower() for k in keywords]
    matched = []
    for chunk in chunks:
        text = (chunk.get("text") or "").lower()
        if any(kw in text for kw in kws):
            matched.append(chunk)
    return matched


def _even_sample(chunks: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Evenly spaced sample across the list so discovery sees the full breadth."""
    if len(chunks) <= n:
        return list(chunks)
    step = len(chunks) / n
    return [chunks[int(i * step)] for i in range(n)]


def _pick_quotes(members: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    """Pick up to n substantive, real quotes (longer text reads as more illustrative)."""
    ranked = sorted(members, key=lambda m: len((m.get("text") or "").strip()), reverse=True)
    picked = [m for m in ranked if len((m.get("text") or "").strip()) >= 60][:n]
    if len(picked) < n:
        for m in ranked:
            if m not in picked:
                picked.append(m)
            if len(picked) >= n:
                break
    return [
        {
            "text": (m.get("text") or "")[:300],
            "source": m.get("source", "unknown"),
            "date": (m.get("date") or "")[:10],
        }
        for m in picked
    ]


# ---------------------------------------------------------------------------
# Primary path: LLM clustering via Groq
# ---------------------------------------------------------------------------

_INSIGHT_DISCOVERY_PROMPT = """You are a senior product researcher analysing Spotify user reviews that specifically mention MUSIC DISCOVERY, RECOMMENDATIONS, the ALGORITHM, or PLAYLISTS.

Below is a representative sample of real review excerpts. Identify the {n} most important RECURRING themes about how users experience discovery and recommendations.

CRITICAL — theme naming rules:
- Each theme name MUST be a specific, insight-rich FINDING that captures a real pain point or behaviour — written as a short headline a researcher would publish.
- GOOD examples (style to imitate): "Discover Weekly loses novelty within weeks", "Algorithm traps users in a loop of the same songs", "Recommendations override and ignore user-built playlists", "Personalisation feels worse after recent updates", "Forced auto-play injects unwanted songs after a playlist ends".
- FORBIDDEN (do NOT output generic category labels like these): "Music Discovery", "Recommendations", "Algorithm", "Playlists", "App Features", "Personalization and Algorithm".
- 6-12 words each, phrased as an insight/claim, not a noun category.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{"themes": ["Insight finding 1", "Insight finding 2", ...]}}
Produce exactly {n} themes."""

_ASSIGNMENT_PROMPT = """You are assigning Spotify review excerpts to a fixed set of discovery insight themes.

Themes (assign each excerpt to the SINGLE best-fitting one; only use "Other" if none genuinely fit):
{themes}

Return ONLY valid JSON (no markdown) in this exact shape:
{{"assignments": {{"1": "<exact theme text>", "2": "<exact theme text>", ...}}}}
Each key is an excerpt number. Each value MUST be copied verbatim from the theme list above, or "Other"."""


def _groq_json(client: Any, prompt: str) -> dict[str, Any] | None:
    """Single Groq JSON call. Returns parsed dict or None on failure/quota."""
    time.sleep(_BATCH_DELAY)
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=_GROQ_MODEL,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = response.choices[0].message.content or "{}"
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        err = str(exc)
        if "429" in err or "rate limit" in err.lower() or "quota" in err.lower():
            logger.warning("Groq quota hit during theme clustering: %s", exc)
            return None
        logger.error("Groq call failed: %s", exc)
        return None


def _discover_insight_themes(
    client: Any, chunks: list[dict[str, Any]], target_themes: int
) -> list[str]:
    """Discover insight-rich theme names from a breadth-spanning sample."""
    sample = _even_sample(chunks, _DISCOVERY_SAMPLE_SIZE)
    numbered = "\n".join(
        f"{i + 1}. {(c.get('text') or '')[:300]}" for i, c in enumerate(sample)
    )
    prompt = (
        _INSIGHT_DISCOVERY_PROMPT.format(n=target_themes)
        + "\n\nExcerpts:\n"
        + numbered
    )
    logger.info("Groq theme discovery — %d-excerpt sample, target %d themes", len(sample), target_themes)
    result = _groq_json(client, prompt)
    if not result:
        return []
    themes = [t.strip() for t in result.get("themes", []) if isinstance(t, str) and t.strip()]
    return themes[:target_themes]


def _groq_cluster(
    chunks: list[dict[str, Any]], target_themes: int = _TARGET_THEMES
) -> list[dict[str, Any]] | None:
    """Cluster chunks into insight-rich themes via Groq LLM.

    Two-stage: (1) discover specific insight themes from a sample spanning the
    whole filtered corpus, then (2) assign every chunk to those themes in
    batches. Returns theme list or None if the Groq quota is exhausted before
    any themes are discovered.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — skipping LLM clustering.")
        return None

    from groq import Groq  # lazy import

    client = Groq(api_key=api_key, http_client=_insecure_http_client())

    global_themes = _discover_insight_themes(client, chunks, target_themes)
    if not global_themes:
        logger.warning("Groq discovered no themes.")
        return None
    logger.info("Discovered %d insight themes: %s", len(global_themes), global_themes)

    themes_block = "\n".join(f"- {t}" for t in global_themes)
    assignments: dict[int, str] = {}
    total_batches = (len(chunks) + _BATCH_SIZE - 1) // _BATCH_SIZE

    for batch_number, start in enumerate(range(0, len(chunks), _BATCH_SIZE), start=1):
        batch = chunks[start : start + _BATCH_SIZE]
        numbered = "\n".join(
            f"{i + 1}. {(c.get('text') or '')[:300]}" for i, c in enumerate(batch)
        )
        prompt = (
            _ASSIGNMENT_PROMPT.format(themes=themes_block) + "\n\nExcerpts:\n" + numbered
        )
        logger.info("Groq theme assignment — batch %d/%d", batch_number, total_batches)
        res = _groq_json(client, prompt)
        if res is None:
            logger.warning("Quota exhausted mid-clustering. Remaining chunks left unassigned.")
            break
        for str_key, theme in res.get("assignments", {}).items():
            try:
                assignments[start + int(str_key) - 1] = theme
            except (ValueError, TypeError):
                pass

    # Aggregate — snap any off-list label to the nearest known theme or "Other".
    theme_chunks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    theme_lookup = {t.lower(): t for t in global_themes}
    for i, chunk in enumerate(chunks):
        raw_theme = assignments.get(i)
        if raw_theme is None:
            continue
        theme = theme_lookup.get(raw_theme.strip().lower(), raw_theme.strip())
        if theme not in global_themes:
            theme = "Other"
        theme_chunks[theme].append(chunk)

    output: list[dict[str, Any]] = []
    for theme_name in global_themes:
        members = theme_chunks.get(theme_name, [])
        if not members:
            continue
        output.append(
            {
                "theme_name": theme_name,
                "count": len(members),
                "top_quotes": _pick_quotes(members, n=3),
            }
        )

    output.sort(key=lambda t: t["count"], reverse=True)
    return output or None


# ---------------------------------------------------------------------------
# Fallback: TF-IDF + KMeans
# ---------------------------------------------------------------------------

def _tfidf_cluster(chunks: list[dict[str, Any]], n_clusters: int = _TARGET_THEMES) -> list[dict[str, Any]]:
    """Sklearn-based fallback clustering. No extra deps beyond what sentence-transformers pulls."""
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts = [chunk.get("text", "") for chunk in chunks]
    vectorizer = TfidfVectorizer(max_features=5000, stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(texts)
    terms = vectorizer.get_feature_names_out()

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    km.fit(matrix)
    labels = km.labels_

    # Name each cluster with its top TF-IDF terms
    order_centroids = km.cluster_centers_.argsort()[:, ::-1]
    theme_names = [
        " / ".join(terms[ind] for ind in order_centroids[c, :4])
        for c in range(n_clusters)
    ]

    theme_chunks: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, label in enumerate(labels):
        theme_chunks[int(label)].append(chunks[i])

    output: list[dict[str, Any]] = []
    for c in range(n_clusters):
        members = theme_chunks[c]
        if not members:
            continue
        output.append(
            {
                "theme_name": theme_names[c],
                "count": len(members),
                "top_quotes": _pick_quotes(members, n=3),
            }
        )

    output.sort(key=lambda t: t["count"], reverse=True)
    return output


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_themes(
    force: bool = False,
    keywords: list[str] | None = None,
    target_themes: int = _TARGET_THEMES,
) -> list[dict[str, Any]]:
    """Cluster discovery-related review chunks into insight-rich themes.

    By default clustering runs ONLY on chunks whose text mentions a discovery
    keyword (``DISCOVERY_KEYWORDS``), so the resulting themes are discovery-
    specific findings rather than generic app-review categories. Pass
    ``keywords=[]`` to cluster all chunks.

    Results are cached to data/output/themes.json. Pass ``force=True`` to
    recompute even when the cache exists.
    """
    if not force and THEMES_PATH.exists():
        logger.info("Loading cached themes from %s", THEMES_PATH)
        with open(THEMES_PATH, encoding="utf-8") as fh:
            cached = json.load(fh)
        # The cache file stores a wrapper {method, chunk_count, themes}.
        # Return just the themes list to match the fresh-compute return type.
        if isinstance(cached, dict) and "themes" in cached:
            return cached["themes"]
        return cached

    all_chunks = _load_chunks()
    active_keywords = DISCOVERY_KEYWORDS if keywords is None else keywords
    if active_keywords:
        chunks = _filter_by_keywords(all_chunks, active_keywords)
        logger.info(
            "Filtered %d/%d chunks on discovery keywords %s",
            len(chunks),
            len(all_chunks),
            active_keywords,
        )
    else:
        chunks = all_chunks

    logger.info("Clustering %d chunks into %d insight themes", len(chunks), target_themes)

    themes = _groq_cluster(chunks, target_themes=target_themes)
    method = "groq-llm-insight"
    if themes is None:
        logger.info("Falling back to TF-IDF + KMeans clustering.")
        themes = _tfidf_cluster(chunks, n_clusters=target_themes)
        method = "tfidf-kmeans"

    THEMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "method": method,
        "chunk_count": len(chunks),
        "source_chunk_count": len(all_chunks),
        "keywords": active_keywords,
        "themes": themes,
    }
    with open(THEMES_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    logger.info(
        "Themes saved to %s | method=%s | theme_count=%d",
        THEMES_PATH,
        method,
        len(themes),
    )
    return themes
