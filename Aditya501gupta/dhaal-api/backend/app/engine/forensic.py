"""DHAAL Forensic Agent — live URL threat intelligence (Layer 2).

This is the "look at the *link*, not just the words" layer. Text-only scam
detection misses a message whose wording is bland but whose link is a known
phishing kit. The Forensic Agent checks every URL in a message against
authoritative, free threat-intelligence feeds and a set of offline heuristics.

SECURITY (this is the important part):
- The message is UNTRUSTED. Its links are treated as *strings to look up*, never
  as endpoints to visit. This module NEVER fetches, resolves, or opens a URL
  found in a message — doing so would be a server-side request forgery (SSRF)
  hole (a scammer could point the link at an internal address and make our
  server hit it). We only ask trusted, hard-coded threat databases *about* the
  URL string.
- Extracted hosts that are IP literals in private / loopback / reserved ranges,
  or names like `localhost`, are flagged and are never sent to any feed.

PRIVACY:
- Query strings and fragments frequently carry victim PII (phone numbers,
  session tokens, tracking ids). They are stripped before a URL is sent to any
  third-party feed — only scheme + host + path leaves the box. URLhaus receives
  only the bare host.

FEEDS (all free, all optional — a missing key or no network simply skips that
feed and the agent degrades to offline heuristics):
  * heuristics            — no network, always on
  * Google Safe Browsing  — env GOOGLE_SAFE_BROWSING_KEY (v4 threatMatches.find)
  * URLhaus (abuse.ch)    — env ABUSECH_AUTH_KEY (free at https://auth.abuse.ch)

Per-URL verdict:  MALICIOUS  (an external feed confirmed it)
                > SUSPICIOUS (offline heuristics only)
                > CLEAN.
Only a feed can produce MALICIOUS. Heuristics alone cap at SUSPICIOUS, so the
offline path can advise caution but can never *falsely condemn* a link — that
is what keeps the whole system's false-positive rate at zero when feeds are off.
"""
from __future__ import annotations

import ipaddress
import os
import re
import time
from urllib.parse import urlsplit, urlunsplit  # urlsplit cleanly separates path/query

try:
    import requests
except ImportError:  # pragma: no cover - requests is in requirements.txt
    requests = None

# ------------------------------------------------------------------ config ---
SB_KEY = os.environ.get("GOOGLE_SAFE_BROWSING_KEY", "")
ABUSECH_KEY = os.environ.get("ABUSECH_AUTH_KEY", "")
TIMEOUT = 8                 # feeds must be fast; a slow feed must not stall a verdict
MAX_URLS = 10               # per message — bound work on adversarial input
CACHE_TTL = 6 * 3600        # seconds; feed answers are stable enough for a demo/session
SUSPICIOUS_URL_T = 1.5      # heuristic score at/above which a link is "suspicious"

SB_ENDPOINT = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
URLHAUS_HOST_ENDPOINT = "https://urlhaus-api.abuse.ch/v1/host/"

# ------------------------------------------------------------- known lists ---
OFFICIAL_DOMAINS = {
    "sbi.co.in", "onlinesbi.sbi", "hdfcbank.com", "icicibank.com", "axisbank.com",
    "amazon.in", "flipkart.com", "bsesdelhi.com", "tatapower.com", "adanielectricity.com",
    "irctc.co.in", "indiapost.gov.in", "incometax.gov.in", "uidai.gov.in", "epfindia.gov.in",
    "pmkisan.gov.in", "cybercrime.gov.in", "sancharsaathi.gov.in", "myvi.in", "jio.com",
    "airtel.in", "fedex.com", "bluedart.com", "google.com", "npci.org.in", "rbi.org.in",
}
BRAND_WORDS = [
    "sbi", "yono", "hdfc", "icici", "axis", "paytm", "phonepe", "gpay", "bses", "adani",
    "tatapower", "indiapost", "bluedart", "fedex", "amazon", "flipkart", "incometax",
    "pmkisan", "irctc", "epfo", "uidai", "netbanking",
]
RISKY_TLDS = (".xyz", ".top", ".online", ".site", ".live", ".click", ".link", ".icu",
              ".buzz", ".rest", ".shop", ".tk", ".work", ".fit", ".gq", ".cf", ".ml")
SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "t.co", "is.gd", "rb.gy", "shorturl.at",
              "t.ly", "rebrand.ly"}
# Words that, inside a host or path, signal a credential-harvest landing page.
CRED_PATH_WORDS = ("login", "signin", "verify", "kyc", "secure", "update", "account",
                   "netbank", "otp", "wallet", "unblock", "reactivate", "confirm", "billdesk")

# In-process cache: key -> (result, expiry_epoch). Persists while the server is
# warm; avoids re-hitting a feed for a repeated URL (quota protection).
_CACHE: dict[str, tuple] = {}


# ---------------------------------------------------------------- extract ---
def _refang(text: str) -> str:
    """Undo common 'defanging' so obfuscated links are still analysed.
    hxxp://sbi[.]xyz  /  sbi(dot)xyz  ->  http://sbi.xyz / sbi.xyz"""
    t = text
    t = re.sub(r"h[x*]{2}ps?", lambda m: "https" if "s" in m.group(0)[-1:] else "http", t, flags=re.I)
    t = t.replace("[.]", ".").replace("(.)", ".").replace("{.}", ".")
    t = re.sub(r"\s*[\[(]?\s*dot\s*[\])]?\s*", ".", t, flags=re.I)
    t = re.sub(r"\s*[\[(]\s*\.\s*[\])]\s*", ".", t)
    return t


# Candidate matcher: an explicit http(s) URL, a bare domain(+path), or a bare
# IPv4(+path). We only *locate* candidates here — the authoritative parsing
# (host / path / query separation, port, userinfo) is done by urlsplit below,
# which is far more reliable than a hand-rolled regex.
_CAND_RE = re.compile(
    r"(https?://[^\s<>\"'\]\)}]+"                                  # explicit URL
    r"|(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+[a-z]{2,24}"          # bare domain
    r"(?::\d{2,5})?(?:/[^\s<>\"'\]\)}]*)?"
    r"|\d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?(?:/[^\s<>\"'\]\)}]*)?)",  # bare IPv4
    re.I,
)


def extract_urls(text: str) -> list[dict]:
    """Return unique {raw, scheme, host, path, safe_url, userinfo} dicts.

    NEVER fetches. Query strings and fragments are dropped from `safe_url` so
    victim PII never leaves the box. IP-literal hosts are matched too (a common
    phishing pattern). Bare email addresses are NOT treated as URLs.
    """
    seen, out = [], []
    for m in _CAND_RE.finditer(_refang(text or "")):
        cand = m.group(0).rstrip(".,);:!?'\"")
        has_scheme = bool(re.match(r"^https?://", cand, re.I))
        parts = urlsplit(cand if has_scheme else "http://" + cand)
        scheme = (parts.scheme or "http").lower()
        host = (parts.hostname or "").lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        path = parts.path or ""
        userinfo = parts.username or None
        if not host:
            continue
        is_ip = _is_ip_literal(host)
        # A bare email (userinfo, no scheme, no real path) is an address, not a link.
        if userinfo and not has_scheme and path in ("", "/"):
            continue
        # A domain must end in an alphabetic TLD; an IP literal is allowed as-is.
        if not is_ip and not re.search(r"\.[a-z]{2,24}$", host):
            continue
        if host in seen:
            continue
        seen.append(host)
        # PII-stripped: scheme + host + path only — query and fragment are dropped.
        safe_url = urlunsplit((scheme, host, path or "/", "", ""))
        out.append({"raw": cand, "scheme": scheme, "host": host,
                    "path": path, "safe_url": safe_url, "userinfo": userinfo})
        if len(out) >= MAX_URLS:
            break
    return out


# ------------------------------------------------------------- guardrails ---
def _root(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _is_internal(host: str) -> bool:
    """True if the host is an internal / private / loopback target. Never contact these."""
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast
    except ValueError:
        return False


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


# ------------------------------------------------------------- heuristics ---
def heuristics(u: dict) -> tuple[float, list[dict]]:
    """Offline analysis of one extracted URL. Returns (score, findings).
    Findings are human-readable; heuristics never yield a MALICIOUS verdict."""
    host, path = u["host"], (u["path"] or "")
    root = _root(host)
    f: list[dict] = []

    if host in OFFICIAL_DOMAINS or root in OFFICIAL_DOMAINS \
            or host.endswith(".gov.in") or host.endswith(".nic.in"):
        return 0.0, [{"source": "heuristics", "severity": "info",
                      "detail": "Recognised official / government domain."}]

    score = 0.0
    if u.get("userinfo"):
        score += 1.5
        f.append({"source": "heuristics", "severity": "high",
                  "detail": f"URL uses an '@' trick (text before '@' is a decoy; real host is {host})."})
    if _is_internal(host):
        score += 1.5
        f.append({"source": "heuristics", "severity": "high",
                  "detail": "Link points to a private/internal address — never a legitimate public service (not contacted)."})
    elif _is_ip_literal(host):
        score += 2.0
        f.append({"source": "heuristics", "severity": "high",
                  "detail": "Uses a raw IP address instead of a domain name — a common phishing signal."})
    if host.startswith("xn--") or ".xn--" in host or any(ord(c) > 127 for c in host):
        score += 2.0
        f.append({"source": "heuristics", "severity": "high",
                  "detail": "Internationalised / punycode host — possible look-alike (homograph) domain."})
    if root in SHORTENERS or host in SHORTENERS:
        score += 1.0
        f.append({"source": "heuristics", "severity": "medium",
                  "detail": "Link shortener hides the true destination."})
    if any(host.endswith(t) for t in RISKY_TLDS):
        tld = next(t for t in RISKY_TLDS if host.endswith(t))
        score += 1.2
        f.append({"source": "heuristics", "severity": "medium",
                  "detail": f"Cheap/high-abuse top-level domain ({tld})."})
    flat = host.replace("-", "").replace(".", "")
    for b in BRAND_WORDS:
        if b in flat and root not in OFFICIAL_DOMAINS:
            score += 1.8
            f.append({"source": "heuristics", "severity": "high",
                      "detail": f"Imitates the brand '{b}' on an unofficial domain."})
            break
    blob = (host + path).lower()
    hit = [w for w in CRED_PATH_WORDS if w in blob]
    if hit:
        score += 1.0
        f.append({"source": "heuristics", "severity": "medium",
                  "detail": f"URL contains credential/verification keywords ({', '.join(hit[:3])})."})
    if host.count(".") >= 4:
        score += 0.6
        f.append({"source": "heuristics", "severity": "low",
                  "detail": "Unusually deep sub-domain nesting."})
    if host.count("-") >= 3:
        score += 0.5
        f.append({"source": "heuristics", "severity": "low",
                  "detail": "Many hyphens in the host — typical of throwaway phishing domains."})
    if not f:
        f.append({"source": "heuristics", "severity": "info",
                  "detail": "No known-good match and no strong red flag — unrated domain, treat with care."})
    return round(score, 2), f


# ------------------------------------------------------------------ feeds ---
def _cache_get(key: str):
    hit = _CACHE.get(key)
    if hit and hit[1] > time.time():
        return hit[0]
    _CACHE.pop(key, None)
    return None


def _cache_put(key: str, val) -> None:
    _CACHE[key] = (val, time.time() + CACHE_TTL)


def safe_browsing_lookup(safe_urls: list[str], http=None) -> dict:
    """Google Safe Browsing v4 threatMatches.find. Batched. Returns {url: threatType}.
    Sends only PII-stripped URLs. Empty dict when unconfigured or on any error."""
    http = http or requests
    if not (SB_KEY and http and safe_urls):
        return {}
    try:
        resp = http.post(
            SB_ENDPOINT, params={"key": SB_KEY},
            json={
                "client": {"clientId": "dhaal", "clientVersion": "1.0.0"},
                "threatInfo": {
                    "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING",
                                    "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": u} for u in safe_urls],
                },
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {}
        out = {}
        for match in resp.json().get("matches", []):
            u = match.get("threat", {}).get("url")
            if u:
                out[u] = match.get("threatType", "THREAT")
        return out
    except Exception:
        return {}


def urlhaus_host_lookup(host: str, http=None) -> dict | None:
    """URLhaus (abuse.ch) host lookup. Needs a free Auth-Key. Returns a threat dict
    when the host is listed and currently online, else None."""
    http = http or requests
    if not (ABUSECH_KEY and http and host):
        return None
    try:
        resp = http.post(URLHAUS_HOST_ENDPOINT, data={"host": host},
                         headers={"Auth-Key": ABUSECH_KEY}, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("query_status") != "ok":
            return None
        urls = data.get("urls") or []
        online = [x for x in urls if x.get("url_status") == "online"]
        if not urls:
            return None
        sample = (online or urls)[0]
        return {
            "listed": True,
            "online": bool(online),
            "threat": sample.get("threat", "malware"),
            "tags": sample.get("tags") or [],
            "date_added": sample.get("date_added", ""),
            "reference": data.get("urlhaus_reference", ""),
        }
    except Exception:
        return None


# --------------------------------------------------------------- assemble ---
def _verdict_for(score: float, feed_hit: bool) -> str:
    if feed_hit:
        return "MALICIOUS"
    if score >= SUSPICIOUS_URL_T:
        return "SUSPICIOUS"
    return "CLEAN"


def analyze(text: str, sb_fn=None, urlhaus_fn=None, use_cache: bool = True) -> dict:
    """Full forensic pass over every URL in `text`.

    sb_fn / urlhaus_fn are injectable for tests; default to the live feeds
    (which are themselves no-ops unless their API key env var is set).
    """
    t0 = time.perf_counter()
    sb_fn = sb_fn or safe_browsing_lookup
    urlhaus_fn = urlhaus_fn or urlhaus_host_lookup

    urls = extract_urls(text)
    if not urls:
        return {"urls_found": 0, "worst_verdict": "CLEAN", "max_score": 0.0,
                "details": [], "feeds_used": _feeds_used(), "latency_ms": _ms(t0)}

    # Only externally-routable hosts are ever sent to a feed.
    contactable = [u for u in urls if not _is_internal(u["host"])]
    safe_urls = [u["safe_url"] for u in contactable]

    sb_map = {}
    cache_key = "sb:" + "|".join(sorted(safe_urls))
    if use_cache and (cached := _cache_get(cache_key)) is not None:
        sb_map = cached
    elif safe_urls:
        try:                              # a feed must NEVER crash a verdict
            sb_map = sb_fn(safe_urls) or {}
        except Exception:
            sb_map = {}
        if use_cache:
            _cache_put(cache_key, sb_map)

    details, worst_rank, max_score = [], 0, 0.0
    rank = {"CLEAN": 0, "SUSPICIOUS": 1, "MALICIOUS": 2}
    for u in urls:
        score, findings = heuristics(u)
        feed_hit = False

        sb_threat = sb_map.get(u["safe_url"])
        if sb_threat:
            feed_hit = True
            findings.insert(0, {"source": "google_safe_browsing", "severity": "critical",
                                "detail": f"Google Safe Browsing flags this as {sb_threat.replace('_', ' ').title()}."})

        if not _is_internal(u["host"]):
            uh_key = "uh:" + u["host"]
            uh = _cache_get(uh_key) if use_cache else None
            if uh is None:
                try:                      # a feed must NEVER crash a verdict
                    uh = urlhaus_fn(u["host"])
                except Exception:
                    uh = None
                if use_cache and uh is not None:
                    _cache_put(uh_key, uh)
            if uh and uh.get("listed"):
                feed_hit = True
                status = "online" if uh.get("online") else "offline"
                dt = f", first seen {uh['date_added']}" if uh.get("date_added") else ""
                findings.insert(0, {"source": "urlhaus", "severity": "critical",
                                    "detail": f"On URLhaus malware list ({uh.get('threat', 'malware')}, {status}{dt})."})

        verdict = _verdict_for(score, feed_hit)
        if feed_hit:
            score = max(score, 9.0)
        details.append({"url": u["safe_url"], "host": u["host"], "verdict": verdict,
                        "score": round(score, 2), "findings": findings})
        worst_rank = max(worst_rank, rank[verdict])
        max_score = max(max_score, score)

    worst = {0: "CLEAN", 1: "SUSPICIOUS", 2: "MALICIOUS"}[worst_rank]
    return {"urls_found": len(urls), "worst_verdict": worst, "max_score": round(max_score, 2),
            "details": details, "feeds_used": _feeds_used(), "latency_ms": _ms(t0)}


def _feeds_used() -> list[str]:
    feeds = ["heuristics"]
    if SB_KEY:
        feeds.append("google_safe_browsing")
    if ABUSECH_KEY:
        feeds.append("urlhaus")
    return feeds


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


def available() -> dict:
    """Which live feeds are configured (for /health and the demo badge)."""
    return {"safe_browsing": bool(SB_KEY), "urlhaus": bool(ABUSECH_KEY),
            "heuristics": True}


if __name__ == "__main__":
    import json
    import sys
    demo = sys.argv[1] if len(sys.argv) > 1 else \
        "Dear customer, your SBI KYC is pending. Update now at hxxp://sbi-kyc-verify[.]xyz/login to avoid block."
    print(json.dumps(analyze(demo), indent=2, ensure_ascii=False))
