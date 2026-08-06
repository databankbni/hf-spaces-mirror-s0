from pathlib import Path


def test_poster_labels_toy_and_unavailable_evidence():
    poster = Path("poster.html").read_text(encoding="utf-8")
    assert 'fetch("./evidence.json")' in poster
    assert "Toy CPU mechanism audit" in poster
    assert "No 27B training or downstream evaluation was run." in poster
    assert "reproduces Table 4" not in poster
    assert "verified all claims" not in poster.lower()
