"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STR = {
  en: {
    tagline: "Digital Suraksha for every phone",
    heroTitle: "Got a suspicious message or call?",
    heroSub: "Paste it below — DHAAL explains in seconds whether it's a scam, and exactly why.",
    placeholder: "Paste the SMS / WhatsApp / email text here…",
    scan: "🛡️ Scan message",
    clear: "Clear",
    scanning: "Analysing…",
    anatomy: "Scam anatomy — the manipulation in their own words",
    tactics: "Manipulation tactics detected",
    why: "Why this verdict",
    authority: "What official sources say",
    actions: "What to do now",
    report: "Draft 1930 complaint",
    share: "Share warning with family",
    copied: "Copied!",
    tryReal: "Try a real documented scam script:",
    trust: "<b>Privacy first:</b> messages are analysed in memory and not stored. DHAAL is an awareness aid, not legal advice — for real incidents call <b>1930</b> or visit <b>cybercrime.gov.in</b>.",
    apiDown: "Analysis service unreachable. Please try again in a minute.",
    complaintTitle: "Pre-filled complaint draft (copy into cybercrime.gov.in or read to 1930):",
  },
  hi: {
    tagline: "हर फ़ोन के लिए डिजिटल सुरक्षा",
    heroTitle: "कोई संदिग्ध मैसेज या कॉल आया है?",
    heroSub: "नीचे पेस्ट करें — DHAAL सेकंडों में बताएगा कि यह धोखाधड़ी है या नहीं, और क्यों।",
    placeholder: "SMS / WhatsApp / ईमेल का टेक्स्ट यहाँ पेस्ट करें…",
    scan: "🛡️ मैसेज जाँचें",
    clear: "हटाएँ",
    scanning: "जाँच हो रही है…",
    anatomy: "धोखे की बनावट — उन्हीं के शब्दों में",
    tactics: "पकड़ी गई मनोवैज्ञानिक चालें",
    why: "यह नतीजा क्यों",
    authority: "आधिकारिक स्रोत क्या कहते हैं",
    actions: "अभी क्या करें",
    report: "1930 शिकायत ड्राफ्ट करें",
    share: "परिवार को चेतावनी भेजें",
    copied: "कॉपी हो गया!",
    tryReal: "असली दर्ज किए गए स्कैम स्क्रिप्ट आज़माएँ:",
    trust: "<b>प्राइवेसी सबसे पहले:</b> मैसेज सेव नहीं किए जाते। DHAAL एक जागरूकता सहायक है, कानूनी सलाह नहीं — असली घटना पर <b>1930</b> पर कॉल करें या <b>cybercrime.gov.in</b> पर जाएँ।",
    apiDown: "सेवा उपलब्ध नहीं है। कृपया एक मिनट में फिर कोशिश करें।",
    complaintTitle: "तैयार शिकायत ड्राफ्ट (cybercrime.gov.in पर पेस्ट करें या 1930 पर पढ़ें):",
  },
};

const SAMPLES = [
  {
    label: "FedEx digital arrest",
    text: "This is FedEx. Your parcel containing illegal items has been seized by Customs. Mumbai Police have issued an arrest warrant. Transfer funds to the RBI verification account immediately and do not tell your family.",
  },
  {
    label: "Electricity disconnection",
    text: "Dear Consumer, Your electricity will be disconnected tonight 9:30 PM due to non-update of your previous month bill. Please immediately contact our officer http://bses-update.online/pay -BSES",
  },
  {
    label: "KYC suspension",
    text: "HDFC ALERT: Your net banking will be deactivated. Complete re-KYC in 24 hours or account will be frozen. Verify now: hdfc-rekyc.xyz. Share OTP with our executive.",
  },
  {
    label: "Task scam (Telegram)",
    text: "Earn Rs 3000-5000 daily by liking YouTube videos. No investment for first task. Join our Telegram group to start earning today! Registration deposit Rs 500 refundable.",
  },
  {
    label: "Genuine bank alert (SAFE)",
    text: "Dear Customer, Rs 4,500.00 is debited from A/c XX1234 on 04-Jul-26 at AMAZON PAY. Avl Bal: Rs 32,110.50. If not done by you, call 1800 1111 09 (SBI).",
  },
];

function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlight(text, tactics) {
  const spans = [];
  for (const arr of Object.values(tactics || {})) for (const s of arr) spans.push(s);
  spans.sort((a, b) => a.start - b.start);
  let out = "", pos = 0;
  for (const s of spans) {
    if (s.start < pos) continue;
    out += esc(text.slice(pos, s.start)) + "<mark>" + esc(text.slice(s.start, s.end)) + "</mark>";
    pos = s.end;
  }
  return out + esc(text.slice(pos));
}

function complaintDraft(text, r) {
  const d = new Date().toLocaleString("en-IN");
  return `COMPLAINT DRAFT — suspected ${String(r.scam_type).replace(/_/g, " ")} fraud
Date/time received: ${d}
Channel: SMS/WhatsApp/Call (select on portal)

I received the following communication which DHAAL analysis flagged as ${r.verdict} (confidence ${Math.round(r.confidence * 100)}%), matching known ${String(r.scam_type).replace(/_/g, " ")} fraud patterns (manipulation tactics: ${Object.keys(r.tactics || {}).join(", ") || "-"}).

Message text:
"${text}"

I have not transferred money / I have transferred Rs ____ (strike out one).
Suspect number/UPI/link: ____________

Reported via: National Cyber Crime Reporting Portal (cybercrime.gov.in) / Helpline 1930.`;
}

function Scanner() {
  const params = useSearchParams();
  const [lang, setLang] = useState("en");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [showComplaint, setShowComplaint] = useState(false);
  const [copied, setCopied] = useState(false);
  const t = STR[lang];

  // PWA share-target: /?text=... lands here from the Android share sheet
  useEffect(() => {
    const shared = [params.get("title"), params.get("text"), params.get("url")]
      .filter(Boolean)
      .join("\n");
    if (shared) {
      setText(shared);
      scan(shared);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function scan(input) {
    const body = (typeof input === "string" ? input : text).trim();
    if (!body) return;
    setBusy(true);
    setErr("");
    setShowComplaint(false);
    try {
      const resp = await fetch(`${API}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: body, channel: "paste" }),
      });
      if (!resp.ok) throw new Error(`API ${resp.status}`);
      setRes({ ...(await resp.json()), _input: body });
    } catch {
      setErr(t.apiDown);
      setRes(null);
    } finally {
      setBusy(false);
    }
  }

  function shareWarning() {
    const msg =
      lang === "hi"
        ? `⚠️ सावधान! यह मैसेज DHAAL जाँच में ${res.verdict} निकला (${Math.round(res.confidence * 100)}% भरोसा) — "${res._input.slice(0, 120)}…" ऐसे मैसेज का जवाब न दें, पैसे न भेजें। शिकायत: 1930`
        : `⚠️ Warning! This message was flagged ${res.verdict} by DHAAL (${Math.round(res.confidence * 100)}% confidence) — "${res._input.slice(0, 120)}…" Do not reply or pay. Report: 1930`;
    if (navigator.share) navigator.share({ text: msg }).catch(() => {});
    else {
      navigator.clipboard.writeText(msg);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }

  function copyComplaint() {
    navigator.clipboard.writeText(complaintDraft(res._input, res));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="wrap">
      <div className="topbar">
        <div className="brand">
          <div className="brand-badge">🛡️</div>
          <h1>
            DHAAL
            <small>{t.tagline}</small>
          </h1>
        </div>
        <button className="lang-toggle" onClick={() => setLang(lang === "en" ? "hi" : "en")}>
          {lang === "en" ? "हिंदी" : "English"}
        </button>
      </div>

      <div className="hero">
        <h2>{t.heroTitle}</h2>
        <p>{t.heroSub}</p>
      </div>

      <div className="input-card">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t.placeholder}
        />
        <div className="input-actions">
          <button className="btn btn-primary" disabled={busy} onClick={() => scan()}>
            {busy ? t.scanning : t.scan}
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => {
              setText("");
              setRes(null);
              setErr("");
            }}
          >
            {t.clear}
          </button>
        </div>
      </div>

      {err && (
        <div className="verdict-card SUSPICIOUS">
          <div className="explain">{err}</div>
        </div>
      )}

      {res && (
        <div className={`verdict-card ${res.verdict}`}>
          <div className="verdict-head">
            <span className="verdict-label">
              {res.verdict === "SCAM" ? "🚨 SCAM" : res.verdict === "SUSPICIOUS" ? "⚠️ SUSPICIOUS" : "✅ SAFE"}
            </span>
            {res.scam_type !== "none" && res.scam_type !== "unknown" && (
              <span className="verdict-type">{res.scam_type.replace(/_/g, " ")}</span>
            )}
            <span className="confidence">
              {Math.round(res.confidence * 100)}% · {res.latency_ms} ms
            </span>
          </div>

          {Object.keys(res.tactics || {}).length > 0 && (
            <>
              <div className="section-label">{t.anatomy}</div>
              <div
                className="anatomy"
                dangerouslySetInnerHTML={{ __html: highlight(res._input, res.tactics) }}
              />
              <div className="section-label">{t.tactics}</div>
              <div className="tags">
                {Object.keys(res.tactics).map((k) => (
                  <span className="tag" key={k}>
                    {k.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </>
          )}

          <div className="section-label">{t.why}</div>
          <div className="explain">{res.explanation}</div>

          {res.citations?.length > 0 && (
            <>
              <div className="section-label">{t.authority}</div>
              {res.citations.map((c, i) => (
                <div className="citation" key={i}>
                  <b>{c.source}:</b> {c.point}
                </div>
              ))}
            </>
          )}

          {res.verdict !== "SAFE" && (
            <>
              <div className="section-label">{t.actions}</div>
              <div className="action-row">
                <button className="btn-action btn-danger" onClick={() => setShowComplaint(!showComplaint)}>
                  {t.report}
                </button>
                <button className="btn-action" onClick={shareWarning}>
                  {copied ? t.copied : t.share}
                </button>
              </div>
              {showComplaint && (
                <div className="complaint-box" onClick={copyComplaint} title="Click to copy">
                  <b>{t.complaintTitle}</b>
                  {"\n\n"}
                  {complaintDraft(res._input, res)}
                </div>
              )}
            </>
          )}

          <div className="meta-line">
            engine {res.engine} · agent trace: intake → forensics → verdict → guardian
          </div>
        </div>
      )}

      <div className="samples">
        <h3>{t.tryReal}</h3>
        {SAMPLES.map((s, i) => (
          <span
            className="chip"
            key={i}
            onClick={() => {
              setText(s.text);
              scan(s.text);
            }}
          >
            {s.label}
          </span>
        ))}
      </div>

      <div className="trust-strip" dangerouslySetInnerHTML={{ __html: t.trust }} />
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Scanner />
    </Suspense>
  );
}
