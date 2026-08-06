"""Tests for Phase 4 reciprocal rank fusion."""

from src.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_promotes_items_in_both_lists():
    fused = reciprocal_rank_fusion(
        [
            ["a", "b", "c"],
            ["b", "d", "a"],
        ],
        rrf_k=60,
    )
    scores = dict(fused)
    assert scores["b"] > scores["c"]
    assert scores["b"] > scores["d"]
    assert fused[0][0] == "b"


def test_rrf_respects_top_k():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "a"]], top_k=2)
    assert len(fused) == 2
