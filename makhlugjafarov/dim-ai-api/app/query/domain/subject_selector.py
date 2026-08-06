from dataclasses import dataclass
from typing import Any

# Canonical subject identifiers — must match `data/books/manifest.yaml` `subject:`
# and the `chunks.subject` column in Supabase. Mirrors
# `app.ingestion.application.subject_pipeline.SUBJECT_*` (kept as a local literal map so
# the query context does not import the ingestion context).
_CANONICAL_SUBJECTS = {
    "azerbaycan_tarixi",
    "biology",
    "chemistry",
    "geography",
    "literature",
    "mathematics",
    "physics",
    "umumi_tarix",
}

# Maps the many subject aliases that reach the API (frontend select values,
# eval-set labels, Azerbaijani names) onto the canonical id. This is used ONLY to
# pick the prompt policy — retrieval keeps the raw request value so its filter
# behaviour (and the GRO-28 retrieval eval gate) is unchanged.
_SUBJECT_ALIASES = {
    # Mathematics
    "math": "mathematics",
    "maths": "mathematics",
    "riyaziyyat": "mathematics",
    "mathematics": "mathematics",
    # History (Azerbaijani history)
    "history": "azerbaycan_tarixi",
    "tarix": "azerbaycan_tarixi",
    "azerbaycan_tarixi": "azerbaycan_tarixi",
    "azərbaycan_tarixi": "azerbaycan_tarixi",
    # Geography
    "geography": "geography",
    "cografiya": "geography",
    "coğrafiya": "geography",
    # Broader corpus subjects. Prompt policy falls back to the default prose
    # tutor until each subject earns a specialised policy, but retrieval should
    # still filter on the canonical stored subject id.
    "biology": "biology",
    "biologiya": "biology",
    "chemistry": "chemistry",
    "kimya": "chemistry",
    "literature": "literature",
    "adabiyyat": "literature",
    "ədəbiyyat": "literature",
    "physics": "physics",
    "fizika": "physics",
    "umumi tarix": "umumi_tarix",
    "umumi_tarix": "umumi_tarix",
}


def canonical_subject(raw: str | None) -> str | None:
    """Normalise a request subject value to its canonical id for policy selection.

    Returns the canonical subject id (matching ``chunks.subject``) when the input
    is a known alias, the value unchanged when it is already canonical, and
    ``None`` when the input is ``None`` or unrecognised.

    Unrecognised subjects deliberately return ``None`` so the prompt registry falls
    back to the default prose policy rather than guessing.
    """
    if raw is None:
        return None
    key = raw.strip().lower()
    if key in _SUBJECT_ALIASES:
        return _SUBJECT_ALIASES[key]
    if key in _CANONICAL_SUBJECTS:
        return key
    return None


def retrieval_subject(raw: str | None) -> str | None:
    """Canonical subject id used to FILTER chunks in the DB.

    ``chunks.subject`` stores canonical ingestion ids. A request may arrive with an alias
    (``riyaziyyat``, ``math``, ``tarix`` …); map those onto the canonical id so
    the ``c.subject = %s`` filter still matches the stored rows. Any value
    without an explicit alias entry is passed through unchanged so subjects
    lacking an alias still filter on their own id. ``None`` stays ``None``
    (coach mode: no subject filter).

    This is the GRO-146 fix: once the corpus was re-ingested under the canonical
    ``mathematics`` id, the previous raw-subject filter silently matched zero
    rows for an incoming ``riyaziyyat`` request.
    """
    return canonical_subject(raw) or raw


# History questions frequently span two distant pages (e.g. Gülüstan p.166-167
# AND Türkmənçay p.179-182 in one multi-hop question). A larger candidate window
# ensures both pages appear in the top results. Other subjects keep the standard
# default; math retrieval improvement is gated on GRO-91, not top_k tuning.
_TOP_K_OVERRIDES: dict[str, int] = {
    "azerbaycan_tarixi": 10,
}
_DEFAULT_TOP_K = 8


def retrieval_top_k(subject: str | None) -> int:
    """Return the retrieval top_k for the given subject.

    Accepts raw aliases or canonical ids — normalises via ``canonical_subject``
    before the lookup so callers do not need to pre-canonicalise.
    Returns ``_DEFAULT_TOP_K`` for unknown or ``None`` subjects.
    """
    return _TOP_K_OVERRIDES.get(canonical_subject(subject) or "", _DEFAULT_TOP_K)


@dataclass
class SubjectSelection:
    subject: str | None
    grade: int | None

class SubjectSelector:
    @staticmethod
    def from_request(top_level: str | None, filters: Any | None) -> SubjectSelection:
        subject = top_level or (filters.subject if filters else None)
        grade = filters.grade if filters else None
        return SubjectSelection(subject=subject, grade=grade)
