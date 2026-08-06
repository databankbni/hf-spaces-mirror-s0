"""Data layer: pull the moments parquet from the Hub, load it into DuckDB.

The dataset IS the API. This module does nothing clever with it — it downloads
the parquet, materialises one table, and reports which optional columns
(embeddings, transcripts) turned up. Everything downstream keys off that report
so new columns light up new search modes without touching the UI.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from dataclasses import dataclass, field

import duckdb
from huggingface_hub import snapshot_download

log = logging.getLogger(__name__)

DATASET_ID = os.environ.get("MOMENTS_DATASET", "davanstrien/prelinger-moments")
LOCAL_PARQUET = os.environ.get("MOMENTS_PARQUET")  # dev escape hatch

# Films outside this range are treated as undated: the `date` field mixes real
# production dates with Internet Archive upload timestamps, so anything modern
# is a metadata artefact rather than a 21st-century Prelinger film.
YEAR_MIN, YEAR_MAX = 1900, 1995

EMBEDDING_COLUMNS = ("emb_caption", "emb_scene", "emb_events")


@dataclass
class Store:
    con: duckdb.DuckDBPyConnection
    n_moments: int
    n_films: int
    embedding_columns: tuple[str, ...] = ()
    fts: bool = False
    decades: list[str] = field(default_factory=list)


def _snapshot() -> str:
    if LOCAL_PARQUET:
        return LOCAL_PARQUET
    return snapshot_download(
        DATASET_ID,
        repo_type="dataset",
        allow_patterns=["*.parquet"],
        token=os.environ.get("HF_TOKEN"),
    )


def _sources(con: duckdb.DuckDBPyConnection, root: str) -> tuple[str, str | None, tuple[str, ...]]:
    """Find the caption parquet and, if published, the embeddings parquet.

    The dataset ships as two configs — `default` (text) and `embeddings` (id +
    vectors) — which land in sibling directories. They have incompatible
    schemas, so they cannot be globbed together.
    """
    if LOCAL_PARQUET:
        return LOCAL_PARQUET, None, ()

    dirs = sorted({os.path.dirname(p) for p in glob.glob(f"{root}/**/*.parquet", recursive=True)})
    captions: str | None = None
    embeddings: str | None = None
    embeds: tuple[str, ...] = ()
    for d in dirs:
        src = f"{d}/*.parquet"
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{src}')").fetchall()}
        found = tuple(c for c in EMBEDDING_COLUMNS if c in cols)
        if "caption" in cols:
            captions = src
            if found:  # embeddings inline in the same table
                embeds = found
        elif found:
            embeddings, embeds = src, found
    if captions is None:
        raise RuntimeError(f"no parquet with a `caption` column under {root}")
    return captions, embeddings, embeds


def load() -> Store:
    root = _snapshot()
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")

    captions, embeddings, embeds = _sources(con, root)
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{captions}')").fetchall()}

    # The published dataset carries its own unique `id`; the draft does not, so
    # derive the same shape (identifier alone is not unique — one row per chunk).
    key = (
        "id"
        if "id" in cols
        else "identifier || '@' || CAST(CAST(chunk_start AS INT) AS VARCHAR)"
    )
    inline = ", ".join(c for c in embeds if c in cols)
    inline = f", {inline}" if inline else ""

    con.execute(
        f"""
        CREATE TABLE moments AS
        SELECT
            {key} AS moment_id,
            identifier, title, date, licenseurl, ia_url, video_url, thumb_url,
            chunk_start, chunk_end, scene, caption, events,
            CASE
                WHEN TRY_CAST(substr(date, 1, 4) AS INT) BETWEEN {YEAR_MIN} AND {YEAR_MAX}
                THEN TRY_CAST(substr(date, 1, 4) AS INT)
            END AS year
            {inline}
        FROM read_parquet('{captions}')
        WHERE caption IS NOT NULL
        """
    )

    if embeddings:
        joined = ", ".join(f"e.{c}" for c in embeds)
        con.execute(
            f"""
            CREATE TABLE moments_joined AS
            SELECT m.*, {joined}
            FROM moments m LEFT JOIN read_parquet('{embeddings}') e
              ON e.id = m.moment_id
            """
        )
        con.execute("DROP TABLE moments")
        con.execute("ALTER TABLE moments_joined RENAME TO moments")

    con.execute("CREATE UNIQUE INDEX moments_pk ON moments(moment_id)")

    n_moments, n_films = con.execute(
        "SELECT count(*), count(DISTINCT identifier) FROM moments"
    ).fetchone()
    if embeddings:
        embeds = tuple(
            c for c in embeds
            if con.execute(f"SELECT count({c}) FROM moments").fetchone()[0]
        )

    decades = [
        f"{d}s"
        for (d,) in con.execute(
            "SELECT DISTINCT (year/10)*10 AS d FROM moments "
            "WHERE year IS NOT NULL ORDER BY d"
        ).fetchall()
    ]

    fts = _build_fts(con)
    log.info(
        "loaded %s moments / %s films (fts=%s, embeddings=%s)",
        n_moments,
        n_films,
        fts,
        embeds or "none",
    )
    return Store(con, n_moments, n_films, embeds, fts, decades)


def _build_fts(con: duckdb.DuckDBPyConnection) -> bool:
    """BM25 over the caption text. Optional — search falls back to LIKE."""
    try:
        con.execute("INSTALL fts; LOAD fts")
        con.execute(
            "PRAGMA create_fts_index('moments', 'moment_id', 'caption', "
            "stemmer='porter', stopwords='english', overwrite=1)"
        )
        return True
    except Exception as exc:  # network-less or extension-less environment
        log.warning("FTS unavailable, falling back to substring search: %s", exc)
        return False


# --- events -----------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9']+")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "you", "your", "her", "his", "its", "into", "over", "under", "out", "off",
    "who", "what", "when", "where", "how", "why", "some", "any", "all", "one",
    "two", "has", "have", "had", "not", "but", "can", "will", "they", "them",
    "there", "then", "than", "about", "show", "showing", "shows", "video",
    "footage", "clip", "scene", "film",
}


def parse_events(raw: str | None) -> list[dict]:
    """`events` is a JSON string of {start, end, text} in global film seconds."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    out = []
    for e in parsed:
        if not isinstance(e, dict) or not e.get("text"):
            continue
        try:
            start = float(e.get("start", 0.0))
        except (TypeError, ValueError):
            continue
        try:
            end = float(e.get("end", start))
        except (TypeError, ValueError):
            end = start
        out.append({"start": start, "end": end, "text": str(e["text"]).strip()})
    return out


def query_terms(query: str) -> list[str]:
    return [t for t in _WORD.findall(query.lower()) if len(t) > 2 and t not in _STOP]


def _term_hits(term: str, words: list[str]) -> bool:
    """Loose stem match: 'washing' should find 'washes'.

    A shared five-character prefix in either direction is a cheap stand-in for
    the porter stemmer FTS uses on the retrieval side. It over-matches a little
    ('planting'/'plants'), which is the right way to be wrong for highlighting.
    """
    head = term[:5]
    return any(
        w.startswith(head) or (len(w) >= 4 and term.startswith(w[:5]))
        for w in words
    )


def rank_events(events: list[dict], terms: list[str]) -> list[dict]:
    """Events that actually mention the query words, best first.

    A moment can legitimately match on its scene description alone, so an empty
    result here is meaningful — the caller falls back to the opening events
    rather than pretending the query landed on a specific second.
    """
    if not terms:
        return []
    scored = []
    for e in events:
        words = _WORD.findall(e["text"].lower())
        hits = sum(1 for t in terms if _term_hits(t, words))
        if hits:
            scored.append((hits, -e["start"], e))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [e for _, _, e in scored]
