"""Fusion-layer tests with a mocked LLM — python3 backend/tests/test_fusion.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine.fusion import analyze_hybrid  # noqa: E402

DA = ("This is CBI. Your parcel has drugs, arrest warrant issued. Transfer Rs 50,000 "
      "for verification now and do not tell your family.")
GRAY = "Your account requires verification. Please respond at the earliest."
BENIGN = "Lunch at 1 PM tomorrow? Book the corner table."


def mock(verdict, conf=0.9, rationale="mock"):
    return lambda text: {"verdict": verdict, "scam_type": "other" if verdict != "SAFE" else "none",
                         "confidence": conf, "tactics": [], "rationale": rationale, "provider": "mock"}


def test_fastpath_skips_llm():
    called = []
    def spy(text):
        called.append(1)
        return mock("SAFE")(text)
    r = analyze_hybrid(DA, llm_fn=spy)
    assert r["verdict"] == "SCAM" and "fast-path" in r["engine"] and not called


def test_agreement_boosts_confidence():
    r = analyze_hybrid(GRAY, llm_fn=mock("SAFE", 0.9))
    assert r["verdict"] == "SAFE" and r["confidence"] >= 0.9 and r["needs_review"] is False


def test_max_disagreement_goes_review():
    r = analyze_hybrid(BENIGN, llm_fn=mock("SCAM", 0.95))
    assert r["verdict"] == "SUSPICIOUS" and r["needs_review"] is True


def test_llm_unavailable_falls_back_to_rules():
    r = analyze_hybrid(BENIGN, llm_fn=None, allow_llm=False)
    assert r["verdict"] == "SAFE" and "llm unavailable" in r["engine"]


def test_one_step_gap_takes_higher_severity():
    r = analyze_hybrid(GRAY, llm_fn=mock("SUSPICIOUS", 0.8))
    assert r["verdict"] == "SUSPICIOUS"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    sys.exit(1 if failed else 0)
