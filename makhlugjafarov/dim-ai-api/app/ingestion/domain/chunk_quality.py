from dataclasses import dataclass

@dataclass(frozen=True)
class ChunkQuality:
    is_low_quality: bool
    verdict: str           # "junk" | "review" | "clean"
    reason: str            # human-readable, e.g. "low_diversity: 2 distinct words"
    distinct_words: int
    total_words: int
    diversity_ratio: float # distinct_words / max(total_words, 1)

def assess_chunk_quality(content: str) -> ChunkQuality:
    n = len(content.strip())
    words = content.lower().split()
    total_words = len(words)
    distinct_words = len(set(words))
    diversity_ratio = distinct_words / max(total_words, 1)

    if n <= 120:
        return ChunkQuality(
            is_low_quality=False,
            verdict="clean",
            reason="short_content",
            distinct_words=distinct_words,
            total_words=total_words,
            diversity_ratio=diversity_ratio
        )

    if distinct_words <= 6 or diversity_ratio < 0.12:
        reason = f"low_diversity: {distinct_words} distinct words, ratio {diversity_ratio:.2f}"
        return ChunkQuality(
            is_low_quality=True,
            verdict="junk",
            reason=reason,
            distinct_words=distinct_words,
            total_words=total_words,
            diversity_ratio=diversity_ratio
        )

    if 7 <= distinct_words <= 12:
        reason = f"borderline_diversity: {distinct_words} distinct words"
        return ChunkQuality(
            is_low_quality=False,
            verdict="review",
            reason=reason,
            distinct_words=distinct_words,
            total_words=total_words,
            diversity_ratio=diversity_ratio
        )

    return ChunkQuality(
        is_low_quality=False,
        verdict="clean",
        reason="clean",
        distinct_words=distinct_words,
        total_words=total_words,
        diversity_ratio=diversity_ratio
    )
