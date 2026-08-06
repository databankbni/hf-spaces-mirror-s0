"""Unit tests for the rules engine — run with: python3 -m pytest backend/tests -q
(or plain `python3 backend/tests/test_rules.py` — stdlib fallback included)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine.rules import analyze, analyze_urls  # noqa: E402


def test_digital_arrest_is_scam():
    r = analyze("This is CBI. Your parcel has drugs. Arrest warrant issued. "
                "Transfer Rs 50,000 now for verification and do not tell your family.")
    assert r["verdict"] == "SCAM"
    assert r["scam_type"] == "digital_arrest"
    assert "secrecy" in r["tactics"]


def test_benign_otp_with_safety_warning_is_safe():
    r = analyze("Your OTP for HDFC Bank login is 448291. Do not share this OTP with anyone. "
                "Bank never calls to ask OTP.")
    assert r["verdict"] == "SAFE"
    assert "credential_ask" not in r["tactics"]


def test_single_authority_mention_is_safe():
    r = analyze("Police verification for your passport application is scheduled on Monday. "
                "Please be available with original documents.")
    assert r["verdict"] == "SAFE"


def test_collect_request_scam_detected():
    r = analyze("You received a collect request of Rs 4,999. Approve with your UPI PIN "
                "to receive your refund.")
    assert r["verdict"] in ("SCAM", "SUSPICIOUS")


def test_brand_impersonation_url_flagged():
    urls = analyze_urls("Pay at http://sbi-yono-kyc.online/verify now")
    assert urls and urls[0]["risk"] >= 1.5


def test_official_domain_not_flagged():
    urls = analyze_urls("Pay your bill at bsesdelhi.com today")
    assert urls and urls[0]["risk"] == 0.0


def test_latency_under_50ms():
    r = analyze("hello, are we meeting tomorrow?")
    assert r["latency_ms"] < 50
    assert r["verdict"] == "SAFE"


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
