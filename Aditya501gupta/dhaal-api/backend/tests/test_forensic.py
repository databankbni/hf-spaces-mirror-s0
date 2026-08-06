"""Forensic Agent tests — feeds are mocked, so this runs offline in CI.

    python3 backend/tests/test_forensic.py

Covers: offline heuristics, feed-confirmed escalation, and the two guarantees
that matter most — PII is stripped before a URL leaves the box, and internal /
private hosts are never sent to any feed (SSRF defence)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine import forensic as F  # noqa: E402

PHISH = "Your SBI KYC is pending. Update now at hxxp://sbi-kyc-verify[.]xyz/login to avoid block."
OFFICIAL = "Pay your electricity bill at https://bsesdelhi.com/pay before the due date."
PII = "Track your parcel: https://track-now.shop/status?phone=9876543210&otp=552310"
INTERNAL = "Urgent: verify at http://127.0.0.1:8080/admin and http://10.0.0.5/reset now."


def test_no_url_is_clean():
    r = F.analyze("Lunch at 1 PM tomorrow? Book the corner table.", use_cache=False)
    assert r["urls_found"] == 0 and r["worst_verdict"] == "CLEAN"


def test_official_domain_clean():
    r = F.analyze(OFFICIAL, use_cache=False)
    assert r["worst_verdict"] == "CLEAN" and r["details"][0]["host"] == "bsesdelhi.com"


def test_defanged_url_is_extracted():
    r = F.analyze(PHISH, use_cache=False)
    assert r["urls_found"] == 1 and r["details"][0]["host"] == "sbi-kyc-verify.xyz"


def test_heuristics_cap_at_suspicious():
    # No feed configured -> a nasty-looking link can be SUSPICIOUS but NEVER MALICIOUS.
    r = F.analyze(PHISH, sb_fn=lambda urls: {}, urlhaus_fn=lambda h: None, use_cache=False)
    assert r["worst_verdict"] == "SUSPICIOUS"


def test_safe_browsing_confirmed_is_malicious():
    def sb(urls):
        return {urls[0]: "SOCIAL_ENGINEERING"}
    r = F.analyze(PHISH, sb_fn=sb, urlhaus_fn=lambda h: None, use_cache=False)
    assert r["worst_verdict"] == "MALICIOUS" and r["max_score"] >= 9.0
    top = r["details"][0]["findings"][0]
    assert top["source"] == "google_safe_browsing" and top["severity"] == "critical"


def test_urlhaus_confirmed_is_malicious():
    def uh(host):
        return {"listed": True, "online": True, "threat": "malware_download",
                "tags": ["phishing"], "date_added": "2026-07-02"}
    r = F.analyze(PHISH, sb_fn=lambda urls: {}, urlhaus_fn=uh, use_cache=False)
    assert r["worst_verdict"] == "MALICIOUS"
    assert any(f["source"] == "urlhaus" for f in r["details"][0]["findings"])


def test_pii_is_stripped_before_feed():
    """The phone number and OTP in the query string must never reach a feed."""
    captured = []

    def sb(urls):
        captured.extend(urls)
        return {}
    F.analyze(PII, sb_fn=sb, urlhaus_fn=lambda h: None, use_cache=False)
    assert captured, "Safe Browsing should have been called with the URL"
    joined = " ".join(captured)
    assert "9876543210" not in joined and "otp=" not in joined and "?" not in joined
    assert captured[0] == "https://track-now.shop/status"


def test_internal_hosts_never_sent_to_feeds():
    """SSRF defence: private/loopback hosts are flagged but never contacted."""
    sent_urls, sent_hosts = [], []

    def sb(urls):
        sent_urls.extend(urls)
        return {}

    def uh(host):
        sent_hosts.append(host)
        return None
    r = F.analyze(INTERNAL, sb_fn=sb, urlhaus_fn=uh, use_cache=False)
    assert "127.0.0.1" not in sent_hosts and "10.0.0.5" not in sent_hosts
    assert all("127.0.0.1" not in u and "10.0.0.5" not in u for u in sent_urls)
    # …yet they are still surfaced to the user as suspicious.
    assert r["worst_verdict"] == "SUSPICIOUS"


def test_feed_exception_falls_back_to_heuristics():
    """A throwing feed must degrade gracefully, not crash the verdict."""
    def boom(*a, **k):
        raise RuntimeError("feed down")
    r = F.analyze(PHISH, sb_fn=boom, urlhaus_fn=boom, use_cache=False)
    assert r["worst_verdict"] == "SUSPICIOUS"  # heuristics still produced a verdict


def test_at_trick_uses_real_host():
    r = F.analyze("Login https://sbi.co.in@evil-login.top/otp now", use_cache=False)
    assert r["details"][0]["host"] == "evil-login.top"


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
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
    sys.exit(1 if failed else 0)
