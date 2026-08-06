from pathlib import Path

from underdog_lab.data.audit import load, normalize, summarize


def test_checked_in_splits_are_disjoint_and_diverse():
    root = Path(__file__).resolve().parents[2]
    splits = {
        name: load(root / "data" / "scenarios" / f"{name}.jsonl")
        for name in ("train", "validation", "test")
    }
    normalized = {
        name: {normalize(row["text"]) for row in rows}
        for name, rows in splits.items()
    }
    assert normalized["train"].isdisjoint(normalized["validation"])
    assert normalized["train"].isdisjoint(normalized["test"])
    assert normalized["validation"].isdisjoint(normalized["test"])

    for rows in splits.values():
        summary = summarize(rows)
        assert summary["unique_texts"] == summary["rows"]
        assert summary["multi_factor"] > 0
        assert summary["unsupported"] > 0
        assert summary["ambiguous"] > 0
