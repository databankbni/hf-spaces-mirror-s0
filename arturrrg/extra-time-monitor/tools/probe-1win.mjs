// One-shot diagnostic probe for the 1win added-time question.
//
// Goal: capture REAL payloads from every 1win feed and locate where (or whether)
// the board-announced 2nd-half added time ("+X" shown at 90') actually appears.
//
// It does three things:
//   1) REST  matches/get-many  -> list live soccer, dump full objects for the
//      matches closest to 90' (where added time would be announced).
//   2) WS    match-info feed    -> dump the FULL raw snapshot for those matches and
//      deep-scan every key for anything injury/added/stoppage/extra/period related.
//   3) REST  sportcast events   -> dump EVERY event type code seen (incl. ones the
//      server does not map), so we can spot an "added time announced" event code.
//
// Run: node tools/probe-1win.mjs            (probes all live matches)
//      node tools/probe-1win.mjs 75         (only matches at/after the 75th minute)

const PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e";
const LANG = "en-001";
const LOCATION = "MD";
const MIN_MINUTE = Number.parseInt(process.argv[2] || "0", 10);

const API_HEADERS = {
  accept: "application/json",
  "content-type": "application/json",
  referer: "https://1wlgk.com/",
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
  "x-external-partner-id": PARTNER_ID,
  "x-lang": LANG,
  "x-user-location": LOCATION
};
const SPORTCAST_HOSTS = [
  "https://line-lb61-w.bk6bba-resources.com",
  "https://line-lb54-w.bk6bba-resources.com"
];
const SPORTCAST_HEADERS = {
  accept: "application/json",
  referer: "https://video-translations.top-parser.com/",
  origin: "https://video-translations.top-parser.com",
  "user-agent": API_HEADERS["user-agent"]
};

const KEY_RX = /inj|add|stop|extra|compensat|overtime|period|timer|clock|minute|elapsed|remain|aggreg/i;

// ---- helpers -------------------------------------------------------------

function minuteOf(matchTimeMs) {
  const n = Number(matchTimeMs);
  return Number.isFinite(n) && n > 0 ? Math.floor(n / 60000) : null;
}

// Walk an object and collect every path whose key looks time/added related,
// plus any value that looks like a small "+X" integer next to such a key.
function deepScan(obj, path = "", hits = []) {
  if (obj == null || typeof obj !== "object") return hits;
  for (const [k, v] of Object.entries(obj)) {
    const here = path ? `${path}.${k}` : k;
    if (KEY_RX.test(k)) hits.push({ path: here, value: v && typeof v === "object" ? "[obj]" : v });
    if (v && typeof v === "object") deepScan(v, here, hits);
  }
  return hits;
}

async function postJson(url, body) {
  const res = await fetch(url, { method: "POST", headers: API_HEADERS, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

async function sportcast(pathname) {
  let lastErr;
  for (const host of SPORTCAST_HOSTS) {
    try {
      const res = await fetch(`${host}${pathname}`, { headers: SPORTCAST_HEADERS });
      if (!res.ok) { lastErr = new Error(`${host} -> ${res.status}`); continue; }
      return res.json();
    } catch (e) { lastErr = e; }
  }
  throw lastErr || new Error("sportcast failed");
}

// ---- step 1: list live matches ------------------------------------------

async function listLive() {
  const json = await postJson("https://api-gateway.top-parser.com/matches/get-many", {
    service: "live", sportId: 18, excludeSportType: "polybet", limit: 100
  });
  const items = json.result?.items || [];
  return items.map(m => ({
    id: m.id,
    home: m.homeTeam?.name || m.competitors?.find(c => c.position === 1)?.name || "?",
    away: m.awayTeam?.name || m.competitors?.find(c => c.position === 2)?.name || "?",
    status: m.status,
    matchTime: m.matchTime,
    minute: minuteOf(m.matchTime),
    raw: m
  }));
}

// ---- step 2: match-info websocket snapshot ------------------------------

function grabMatchInfo(ids, timeoutMs = 12000) {
  const url = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(LANG)}&externalPartnerId=${encodeURIComponent(PARTNER_ID)}&EIO=4&transport=websocket`;
  const snaps = new Map();
  return new Promise(resolve => {
    let done = false;
    const ws = new WebSocket(url);
    const finish = () => { if (done) return; done = true; clearTimeout(t); try { ws.close(); } catch {} resolve(snaps); };
    const t = setTimeout(finish, timeoutMs);
    ws.onerror = finish;
    ws.onclose = finish;
    ws.onmessage = ev => {
      const text = String(ev.data || "");
      if (text === "2") { try { ws.send("3"); } catch {} return; }
      if (text.startsWith("0")) { try { ws.send("40"); } catch {} return; }
      if (text.startsWith("40")) {
        try { ws.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`); } catch { finish(); }
        return;
      }
      if (!text.startsWith("42")) return;
      let payload;
      try { payload = JSON.parse(text.slice(2)); } catch { return; }
      const msg = payload?.[1];
      if (!msg || (msg.messageType !== "match-info-snapshot" && msg.messageType !== "match-info")) return;
      const updates = Array.isArray(msg.data) ? msg.data : [msg.data || {}];
      for (const d of updates) {
        const id = String(d.matchId || d.id || "");
        if (id) snaps.set(id, d);
      }
      // keep listening a bit to catch live deltas, but resolve once we have all snapshots
      if (snaps.size >= ids.length) setTimeout(finish, 1500);
    };
  });
}

// ---- step 3: sportcast event-type census --------------------------------

async function censusSportcast(fonId) {
  const meta = await sportcast(`/ma/sportscast/actrans?fonid=${encodeURIComponent(fonId)}&lang=eng`);
  const item = Array.isArray(meta.items) ? meta.items.find(e => e?.code) : null;
  if (!item?.code) return { fonId, error: "no code" };
  const ev = await sportcast(`/ma/sportscast/events?code=${encodeURIComponent(item.code)}&lastid=0`);
  const events = Array.isArray(ev.events) ? ev.events : [];
  const byType = {};
  for (const e of events) {
    const ty = e.type;
    (byType[ty] ||= []).push(e);
  }
  return { fonId, code: item.code, total: events.length, byType, sample: events.slice(-12) };
}

function fonFromTracker(url) {
  const v = decodeURIComponent(String(url || ""));
  const m = v.match(/tracker\/get\/(\d+)/i) || v.match(/[?&](?:eventId|fonid|fonId)=(\d+)/i);
  return m ? m[1] : "";
}

// ---- main ----------------------------------------------------------------

(async () => {
  console.log(`\n=== 1WIN ADDED-TIME PROBE (min minute filter: ${MIN_MINUTE}) ===\n`);

  const live = await listLive();
  console.log(`Live soccer matches: ${live.length}`);
  const sorted = live.slice().sort((a, b) => (b.minute || 0) - (a.minute || 0));
  for (const m of sorted.slice(0, 20)) {
    console.log(`  [${m.minute ?? "?"}'] ${m.home} vs ${m.away}  status="${m.status}" id=${m.id}`);
  }

  const targets = sorted.filter(m => (m.minute || 0) >= MIN_MINUTE).slice(0, 8);
  if (targets.length === 0) {
    console.log(`\nNo matches at/after minute ${MIN_MINUTE}. Re-run with a lower threshold or when matches are late.`);
    // still dump one raw REST object so we can see the REST shape
    if (sorted[0]) {
      console.log(`\n--- REST raw object (highest-minute match) ---`);
      console.log(JSON.stringify(sorted[0].raw, null, 2));
    }
    process.exit(0);
  }

  console.log(`\nProbing ${targets.length} match(es): ${targets.map(t => `${t.home}/${t.away}@${t.minute}'`).join(", ")}`);

  // REST raw dump (one, to see full shape incl. any period/timer fields)
  console.log(`\n========== REST raw object: ${targets[0].home} vs ${targets[0].away} ==========`);
  console.log(JSON.stringify(targets[0].raw, null, 2));

  // match-info websocket
  const snaps = await grabMatchInfo(targets.map(t => Number(t.id)));
  console.log(`\n========== match-info WS snapshots captured: ${snaps.size}/${targets.length} ==========`);
  for (const t of targets) {
    const d = snaps.get(String(t.id));
    if (!d) { console.log(`\n[${t.minute}'] ${t.home} vs ${t.away}: NO WS snapshot received`); continue; }
    console.log(`\n----- [${t.minute}'] ${t.home} vs ${t.away} (id=${t.id}) -----`);
    console.log(`top-level keys: ${Object.keys(d).join(", ")}`);
    const hits = deepScan(d);
    if (hits.length) {
      console.log(`time/added-related fields found:`);
      for (const h of hits) console.log(`   ${h.path} = ${JSON.stringify(h.value)}`);
    } else {
      console.log(`time/added-related fields found: NONE`);
    }
    console.log(`FULL raw snapshot:`);
    console.log(JSON.stringify(d, null, 2));
  }

  // sportcast event census for whichever target exposes a tracker fonid.
  // The tracker URL lives in the match-info WS snapshot (liveTracker.url), NOT REST.
  console.log(`\n========== sportcast event-type census ==========`);
  for (const t of targets) {
    const d = snaps.get(String(t.id));
    const trackerUrl = d?.liveTracker?.url || t.raw?.liveTracker?.url || "";
    const fonId = fonFromTracker(trackerUrl);
    if (!fonId) { console.log(`[${t.minute}'] ${t.home} vs ${t.away}: no tracker fonid in REST object`); continue; }
    try {
      const c = await censusSportcast(fonId);
      console.log(`\n[${t.minute}'] ${t.home} vs ${t.away} fonid=${fonId} code=${c.code} totalEvents=${c.total}`);
      console.log(`event type codes seen: ${Object.entries(c.byType || {}).map(([k, v]) => `${k}(x${v.length})`).join(", ")}`);
      // High-frequency telemetry (ball pos, attacks, clock) is noise. The added-time
      // board announcement should be a RARE code with small integer payload. Dump every
      // row for codes occurring <= 5 times so we can eyeball which carries "+X".
      const NOISE = new Set([1106, 1107, 1209, 2681, 1149, 1164]);
      const rare = Object.entries(c.byType || {})
        .filter(([k, v]) => v.length <= 5 && !NOISE.has(Number(k)));
      console.log(`rare/candidate event rows (<=5 occurrences, telemetry excluded):`);
      for (const [k, rows] of rare) {
        console.log(`  type ${k}:`);
        for (const r of rows) console.log(`     ${JSON.stringify(r)}`);
      }
    } catch (e) {
      console.log(`[${t.minute}'] ${t.home} vs ${t.away} fonid=${fonId}: sportcast error ${e.message}`);
    }
  }

  console.log(`\n=== PROBE COMPLETE ===`);
  process.exit(0);
})().catch(e => { console.error("PROBE FAILED:", e); process.exit(1); });
