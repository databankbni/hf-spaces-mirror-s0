// Boundary scanner: find the sportcast event code that carries the announced
// added/injury time. The board "+X" fires near the half boundaries — 45:00
// (~2700s) and 90:00 (~5400s). We pull the FULL event history for late matches
// and print every event whose clock field lands in those windows, plus every
// rare/config-style code, so the "minutes added" event becomes obvious.

const PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e";
const LANG = "en-001";
const LOCATION = "MD";

const API_HEADERS = {
  accept: "application/json", "content-type": "application/json", referer: "https://1wlgk.com/",
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
  "x-external-partner-id": PARTNER_ID, "x-lang": LANG, "x-user-location": LOCATION
};
const SPORTCAST_HOSTS = ["https://line-lb61-w.bk6bba-resources.com", "https://line-lb54-w.bk6bba-resources.com"];
const SPORTCAST_HEADERS = { accept: "application/json", referer: "https://video-translations.top-parser.com/", origin: "https://video-translations.top-parser.com", "user-agent": API_HEADERS["user-agent"] };

// clock windows in seconds: 1st-half stoppage announce, 2nd-half stoppage announce
const WINDOWS = [[2580, 2760], [5280, 5700]];
const inWindow = v => WINDOWS.some(([lo, hi]) => v >= lo && v <= hi);
// codes that are pure telemetry / ball position / attack — ignore as noise
const TELEMETRY = new Set([1106, 1107, 1113, 1149, 1164, 1209, 1210, 1228, 1253, 2681, 2682, 1116, 1117, 1190, 1194, 1195, 1196, 1197, 1198, 1199, 1200, 1201, 1203, 1205]);

async function postJson(url, body) {
  const r = await fetch(url, { method: "POST", headers: API_HEADERS, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${url} ${r.status}`); return r.json();
}
async function sportcast(p) {
  let e; for (const h of SPORTCAST_HOSTS) { try { const r = await fetch(`${h}${p}`, { headers: SPORTCAST_HEADERS }); if (!r.ok) { e = new Error(`${h} ${r.status}`); continue; } return r.json(); } catch (x) { e = x; } }
  throw e;
}
function fon(url) { const v = decodeURIComponent(String(url || "")); const m = v.match(/tracker\/get\/(\d+)/i) || v.match(/[?&](?:eventId|fonid|fonId)=(\d+)/i); return m ? m[1] : ""; }

function grabInfo(ids, ms = 12000) {
  const url = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(LANG)}&externalPartnerId=${encodeURIComponent(PARTNER_ID)}&EIO=4&transport=websocket`;
  const snaps = new Map();
  return new Promise(res => {
    let done = false; const ws = new WebSocket(url);
    const fin = () => { if (done) return; done = true; clearTimeout(t); try { ws.close(); } catch {} res(snaps); };
    const t = setTimeout(fin, ms);
    ws.onerror = fin; ws.onclose = fin;
    ws.onmessage = ev => {
      const x = String(ev.data || "");
      if (x === "2") return void ws.send("3");
      if (x.startsWith("0")) return void ws.send("40");
      if (x.startsWith("40")) { try { ws.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`); } catch { fin(); } return; }
      if (!x.startsWith("42")) return;
      let p; try { p = JSON.parse(x.slice(2)); } catch { return; }
      const m = p?.[1]; if (!m || (m.messageType !== "match-info-snapshot" && m.messageType !== "match-info")) return;
      for (const d of (Array.isArray(m.data) ? m.data : [m.data || {}])) { const id = String(d.matchId || d.id || ""); if (id) snaps.set(id, d); }
      if (snaps.size >= ids.length) setTimeout(fin, 1200);
    };
  });
}

(async () => {
  const j = await postJson("https://api-gateway.top-parser.com/matches/get-many", { service: "live", sportId: 18, excludeSportType: "polybet", limit: 100 });
  const items = j.result?.items || [];
  const ids = items.map(m => Number(m.id));
  const snaps = await grabInfo(ids);

  // rank by matchTime (real clock) desc; keep 2nd-half matches
  const ranked = items.map(m => {
    const d = snaps.get(String(m.id));
    const mt = Number(d?.matchTime);
    return { id: m.id, home: m.homeTeam?.name || "?", away: m.awayTeam?.name || "?", status: d?.status || "?", min: Number.isFinite(mt) ? Math.floor(mt / 60000) : null, tracker: d?.liveTracker?.url || "" };
  }).filter(m => m.tracker).sort((a, b) => (b.min || 0) - (a.min || 0));

  console.log(`Late matches with tracker (top 12):`);
  for (const m of ranked.slice(0, 12)) console.log(`  [${m.min}'] ${m.home} vs ${m.away} status="${m.status}"`);

  // scan the latest 10 for boundary + config events
  for (const m of ranked.slice(0, 10)) {
    const fonId = fon(m.tracker);
    if (!fonId) continue;
    let code;
    try {
      const meta = await sportcast(`/ma/sportscast/actrans?fonid=${encodeURIComponent(fonId)}&lang=eng`);
      code = (Array.isArray(meta.items) ? meta.items.find(e => e?.code) : null)?.code;
    } catch (e) { console.log(`  ${m.home}: actrans err ${e.message}`); continue; }
    if (!code) continue;
    let ev;
    try { ev = await sportcast(`/ma/sportscast/events?code=${encodeURIComponent(code)}&lastid=0`); } catch (e) { console.log(`  ${m.home}: events err ${e.message}`); continue; }
    const events = Array.isArray(ev.events) ? ev.events : [];

    // boundary events: any numeric field in a stoppage-announce window
    const boundary = events.filter(e => !TELEMETRY.has(Number(e.type)) && Object.values(e).some(v => typeof v === "number" && inWindow(v)));
    // config/announce-like: rare non-telemetry codes with tiny payloads (potential "minutes")
    const counts = {}; for (const e of events) counts[e.type] = (counts[e.type] || 0) + 1;
    const tiny = events.filter(e => !TELEMETRY.has(Number(e.type)) && counts[e.type] <= 3 &&
      Object.entries(e).some(([k, v]) => /^i\d$/.test(k) && typeof v === "number" && v >= 1 && v <= 15));

    console.log(`\n===== [${m.min}'] ${m.home} vs ${m.away}  code=${code} total=${events.length} =====`);
    console.log(`-- events with a clock field near 45:00/90:00 stoppage windows --`);
    for (const e of boundary) console.log(`   ${JSON.stringify(e)}`);
    if (!boundary.length) console.log(`   (none)`);
    console.log(`-- rare non-telemetry events carrying a small 1..15 value (minutes-added candidates) --`);
    const seen = new Set();
    for (const e of tiny) { const kk = `${e.type}:${e.i1}:${e.i2}:${e.i3}`; if (seen.has(kk)) continue; seen.add(kk); console.log(`   ${JSON.stringify(e)}`); }
  }
  process.exit(0);
})().catch(e => { console.error("FAIL", e); process.exit(1); });
