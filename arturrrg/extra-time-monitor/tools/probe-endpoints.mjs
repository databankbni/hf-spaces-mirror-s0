// Deep endpoint explorer: hunt for a UNIVERSAL injury-time source on 1win.
//
// 1104 (sportcast) is tracker-gated (~39% of matches) and only fires at 90'.
// This probe looks for anything better:
//   A) full REST match object for a real (non-esports) match
//   B) try sibling REST endpoints on api-gateway (detail / statistics / events / timeline)
//   C) full actrans response (ALL providers/codes, not just the first)
//   D) full match-info WS snapshot, deep-scanned
//
// Run: node tools/probe-endpoints.mjs

const PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e", LANG = "en-001", LOCATION = "MD";
const GW = "https://api-gateway.top-parser.com";
const API_HEADERS = { accept: "application/json", "content-type": "application/json", referer: "https://1wlgk.com/", "user-agent": "Mozilla/5.0", "x-external-partner-id": PARTNER_ID, "x-lang": LANG, "x-user-location": LOCATION };
const HOSTS = ["https://line-lb61-w.bk6bba-resources.com", "https://line-lb54-w.bk6bba-resources.com"];
const SC = { accept: "application/json", referer: "https://video-translations.top-parser.com/", origin: "https://video-translations.top-parser.com", "user-agent": "Mozilla/5.0" };

const post = async (u, b) => { const r = await fetch(u, { method: "POST", headers: API_HEADERS, body: JSON.stringify(b) }); return { ok: r.ok, status: r.status, json: r.ok ? await r.json().catch(() => null) : null }; };
const get = async (u) => { const r = await fetch(u, { headers: API_HEADERS }); return { ok: r.ok, status: r.status, json: r.ok ? await r.json().catch(() => null) : null }; };
const sc = async p => { let e; for (const h of HOSTS) { try { const r = await fetch(h + p, { headers: SC }); if (r.ok) return r.json(); e = r.status; } catch (x) { e = x; } } throw new Error(e); };
const fon = u => { const v = decodeURIComponent(String(u || "")); const m = v.match(/tracker\/get\/(\d+)/i); return m ? m[1] : ""; };

const KEY_RX = /inj|add|stop|extra|compensat|overtime|aggreg|loss|added/i;
function deepScan(obj, path = "", hits = []) {
  if (obj == null || typeof obj !== "object") return hits;
  for (const [k, v] of Object.entries(obj)) {
    const here = path ? `${path}.${k}` : k;
    if (KEY_RX.test(k)) hits.push({ path: here, value: v && typeof v === "object" ? JSON.stringify(v).slice(0, 120) : v });
    if (v && typeof v === "object") deepScan(v, here, hits);
  }
  return hits;
}

function grab(ids) { const url = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${LANG}&externalPartnerId=${PARTNER_ID}&EIO=4&transport=websocket`; const s = new Map(); return new Promise(res => { let d = 0; const ws = new WebSocket(url); const f = () => { if (d) return; d = 1; clearTimeout(t); try { ws.close(); } catch {} res(s); }; const t = setTimeout(f, 12000); ws.onerror = f; ws.onclose = f; ws.onmessage = e => { const x = String(e.data || ""); if (x === "2") return void ws.send("3"); if (x[0] === "0") return void ws.send("40"); if (x.startsWith("40")) { ws.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`); return; } if (!x.startsWith("42")) return; let p; try { p = JSON.parse(x.slice(2)); } catch { return; } const m = p?.[1]; if (!m || !/match-info/.test(m.messageType)) return; for (const dd of (Array.isArray(m.data) ? m.data : [m.data])) { const id = String(dd.matchId || dd.id || ""); if (id) s.set(id, dd); } if (s.size >= ids.length) setTimeout(f, 1000); }; }); }

(async () => {
  const list = await post(`${GW}/matches/get-many`, { service: "live", sportId: 18, excludeSportType: "polybet", limit: 100 });
  const items = list.json?.result?.items || [];
  const snaps = await grab(items.map(m => Number(m.id)));

  // pick the latest REAL match (has tracker, highest minute) as our deep target
  const ranked = items.map(m => {
    const d = snaps.get(String(m.id));
    const mt = Number(d?.matchTime);
    return { id: m.id, home: m.homeTeam?.name || "?", away: m.awayTeam?.name || "?", status: d?.status, min: Number.isFinite(mt) ? Math.floor(mt / 60000) : null, tracker: d?.liveTracker?.url || "", snap: d, raw: m };
  }).sort((a, b) => (b.min || 0) - (a.min || 0));

  const real = ranked.find(m => m.tracker && (m.min || 0) >= 45) || ranked.find(m => m.tracker) || ranked[0];
  console.log(`\n=== DEEP TARGET: [${real.min}'] ${real.home} vs ${real.away}  id=${real.id} ===\n`);

  // ---- A) full REST object ----
  console.log(`========== A) REST match object (matches/get-many item) ==========`);
  console.log(JSON.stringify(real.raw, null, 2));
  console.log(`REST injury/added scan: ${JSON.stringify(deepScan(real.raw))}`);

  // ---- B) sibling REST endpoints ----
  console.log(`\n========== B) sibling REST endpoints ==========`);
  const candidates = [
    ["GET", `${GW}/matches/get?id=${real.id}`],
    ["GET", `${GW}/matches/get?matchId=${real.id}`],
    ["GET", `${GW}/match/get?id=${real.id}`],
    ["GET", `${GW}/matches/${real.id}`],
    ["GET", `${GW}/matches/get-statistics?matchId=${real.id}`],
    ["GET", `${GW}/statistics/get?matchId=${real.id}`],
    ["GET", `${GW}/matches/get-events?matchId=${real.id}`],
    ["GET", `${GW}/events/get?matchId=${real.id}`],
    ["GET", `${GW}/matches/get-timeline?matchId=${real.id}`],
    ["GET", `${GW}/timeline/get?matchId=${real.id}`],
    ["POST", `${GW}/matches/get`, { id: Number(real.id) }],
    ["POST", `${GW}/matches/get-statistics`, { matchId: Number(real.id) }],
    ["POST", `${GW}/matches/get-events`, { matchId: Number(real.id) }],
    ["POST", `${GW}/statistics/get-many`, { matchIds: [Number(real.id)] }],
  ];
  for (const [method, url, body] of candidates) {
    try {
      const r = method === "GET" ? await get(url) : await post(url, body);
      const path = url.replace(GW, "");
      if (!r.ok) { console.log(`  ${method} ${path} -> ${r.status}`); continue; }
      const hits = deepScan(r.json);
      const keys = r.json && typeof r.json === "object" ? Object.keys(r.json).join(",") : typeof r.json;
      console.log(`  ${method} ${path} -> 200  topKeys=[${keys}]  injuryHits=${hits.length ? JSON.stringify(hits) : "none"}`);
      if (hits.length) { console.log(`     FULL: ${JSON.stringify(r.json).slice(0, 1500)}`); }
    } catch (e) { console.log(`  ${method} ${url.replace(GW, "")} -> ERR ${e.message}`); }
  }

  // ---- C) full actrans (all providers) ----
  console.log(`\n========== C) full actrans response (all providers/codes) ==========`);
  const fonId = fon(real.tracker);
  console.log(`tracker=${real.tracker}\nfonId=${fonId}`);
  if (fonId) {
    try {
      const meta = await sc(`/ma/sportscast/actrans?fonid=${fonId}&lang=eng`);
      console.log(JSON.stringify(meta, null, 2).slice(0, 2500));
    } catch (e) { console.log(`actrans err: ${e.message}`); }
  }

  // ---- D) full WS snapshot deep scan ----
  console.log(`\n========== D) match-info WS snapshot ==========`);
  console.log(`topKeys=[${Object.keys(real.snap || {}).join(", ")}]`);
  console.log(`injury/added scan: ${JSON.stringify(deepScan(real.snap))}`);
  console.log(`FULL snapshot:\n${JSON.stringify(real.snap, null, 2)}`);

  process.exit(0);
})().catch(e => { console.error("FAIL", e); process.exit(1); });
