// Empirical test: does 1win's match-info websocket return data for a matchId that is
// NOT in the current REST live-list? This decides whether we can "probe" a match that
// 1win delisted early but is still being played.
//
// Method:
//   1) REST live-list -> current live soccer matchIds.
//   2) Subscribe match-info for a KNOWN-LIVE id (control: must return data).
//   3) Subscribe match-info for ids NOT in the live-list (recently-finished / neighbor
//      ids) and see whether the socket still answers, and with what status.
//
// Run: node tools/test-delisted-probe.mjs

const PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e";
const LANG = "en-001";
const API_HEADERS = {
  accept: "application/json",
  "content-type": "application/json",
  referer: "https://1wlgk.com/",
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
  "x-external-partner-id": PARTNER_ID,
  "x-lang": LANG,
  "x-user-location": "MD"
};

function minuteOf(ms) { const n = Number(ms); return Number.isFinite(n) && n > 0 ? Math.floor(n / 60000) : null; }

async function listLive() {
  const res = await fetch("https://api-gateway.top-parser.com/matches/get-many", {
    method: "POST", headers: API_HEADERS,
    body: JSON.stringify({ service: "live", sportId: 18, excludeSportType: "polybet", limit: 100 })
  });
  if (!res.ok) throw new Error(`live-list ${res.status}`);
  const json = await res.json();
  return (json.result?.items || []).map(m => ({
    id: String(m.id),
    home: m.homeTeam?.name || m.competitors?.find(c => c.position === 1)?.name || "?",
    away: m.awayTeam?.name || m.competitors?.find(c => c.position === 2)?.name || "?",
    status: m.status, minute: minuteOf(m.matchTime)
  }));
}

function probe(ids, timeoutMs = 10000) {
  const url = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(LANG)}&externalPartnerId=${encodeURIComponent(PARTNER_ID)}&EIO=4&transport=websocket`;
  const raw = new Map();
  const merge = (prev, next) => ({ ...prev, ...next, matchScore: next.matchScore || prev.matchScore });
  return new Promise(resolve => {
    let done = false;
    const ws = new WebSocket(url);
    const finish = () => {
      if (done) return; done = true; clearTimeout(t); try { ws.close(); } catch {}
      const out = new Map();
      for (const [id, d] of raw) out.set(id, { status: d.status, matchTime: d.matchTime, minute: minuteOf(d.matchTime), score: `${d.matchScore?.t1 ?? d.score?.t1 ?? "?"}-${d.matchScore?.t2 ?? d.score?.t2 ?? "?"}` });
      resolve(out);
    };
    const t = setTimeout(finish, timeoutMs);
    ws.onerror = finish;
    ws.onclose = finish;
    ws.onmessage = ev => {
      const text = String(ev.data || "");
      if (text === "2") { try { ws.send("3"); } catch {} return; }
      if (text.startsWith("0")) { try { ws.send("40"); } catch {} return; }
      if (text.startsWith("40")) { try { ws.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`); } catch { finish(); } return; }
      if (!text.startsWith("42")) return;
      let payload; try { payload = JSON.parse(text.slice(2)); } catch { return; }
      const msg = payload?.[1];
      if (!msg || (msg.messageType !== "match-info-snapshot" && msg.messageType !== "match-info")) return;
      const updates = Array.isArray(msg.data) ? msg.data : [msg.data || {}];
      for (const d of updates) {
        const id = String(d.matchId || d.id || "");
        if (id) raw.set(id, merge(raw.get(id) || {}, d));
      }
      const allUsable = ids.every(id => { const s = raw.get(String(id)); return s && (s.matchTime != null || s.status != null || s.matchScore != null); });
      if (allUsable) finish();
    };
  });
}

(async () => {
  const live = await listLive();
  console.log(`\nLive soccer matches now: ${live.length}`);
  const sorted = live.slice().sort((a, b) => (b.minute || 0) - (a.minute || 0));
  for (const m of sorted.slice(0, 10)) console.log(`  [${m.minute ?? "?"}'] id=${m.id} ${m.home} vs ${m.away} status="${m.status}"`);

  if (!sorted.length) { console.log("No live matches — re-run when matches are on."); process.exit(0); }

  const liveIds = new Set(live.map(m => m.id));
  const control = sorted[0];                                   // known-live
  const maxId = Math.max(...live.map(m => Number(m.id)));
  // Candidate "not in live-list" ids: neighbors around the live id range. Some of these
  // are likely recently-finished real matches.
  const offLineIds = [];
  for (let d = 1; d <= 60 && offLineIds.length < 12; d++) {
    const cand = String(maxId - d);
    if (!liveIds.has(cand)) offLineIds.push(cand);
  }

  console.log(`\n--- CONTROL: probing known-LIVE id ${control.id} (${control.home}) ---`);
  const ctrl = await probe([Number(control.id)]);
  console.log(ctrl.has(control.id) ? `  OK -> ${JSON.stringify(ctrl.get(control.id))}` : `  NO RESPONSE (socket mechanism itself failing!)`);

  console.log(`\n--- TEST: probing ${offLineIds.length} ids NOT in live-list ---`);
  const off = await probe(offLineIds.map(Number));
  console.log(`  responses received: ${off.size}/${offLineIds.length}`);
  for (const [id, info] of off.entries()) console.log(`   id=${id} -> ${JSON.stringify(info)}`);

  console.log(`\n=== VERDICT ===`);
  if (!ctrl.has(control.id)) {
    console.log("Socket failed even for a live match — inconclusive (network/auth).");
  } else if (off.size > 0) {
    console.log("Socket RETURNS data for matches not in the live-list -> probing a delisted match is VIABLE.");
    console.log("Look above: do any carry a 'finished' status or an ADVANCING minute? That's our ground truth.");
  } else {
    console.log("Socket returned NOTHING for off-list ids -> 1win likely stops serving match-info once delisted.");
    console.log("=> Probing won't help; grace-window fallback is the best we can do.");
  }
  process.exit(0);
})().catch(e => { console.error("TEST FAILED:", e); process.exit(1); });
