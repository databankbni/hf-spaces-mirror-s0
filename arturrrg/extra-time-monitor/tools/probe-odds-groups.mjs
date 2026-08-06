// One-shot: dump the match-odds groups 1win sends for a live match, with each
// group's leg statuses and how stale the last price delta is. Answers "why is
// market X not counted as an open 'other market'".
//
// Run: node tools/probe-odds-groups.mjs            (match nearest 90')
//      node tools/probe-odds-groups.mjs arsenal    (match whose name contains "arsenal")

const PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e";
const LANG = "en-001";
const LOCATION = "MD";
const NAME_FILTER = (process.argv[2] || "").toLowerCase();

const API_HEADERS = {
  accept: "application/json",
  "content-type": "application/json",
  referer: "https://1wlgk.com/",
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
  "x-external-partner-id": PARTNER_ID,
  "x-lang": LANG,
  "x-user-location": LOCATION
};

const minuteOf = ms => (Number.isFinite(Number(ms)) && Number(ms) > 0 ? Math.floor(Number(ms) / 60000) : null);

async function postJson(url, body) {
  const res = await fetch(url, { method: "POST", headers: API_HEADERS, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

async function listLive() {
  const json = await postJson("https://api-gateway.top-parser.com/matches/get-many", {
    service: "live", sportId: 18, excludeSportType: "polybet", limit: 100
  });
  return (json.result?.items || []).map(m => ({
    id: m.id,
    home: m.homeTeam?.name || m.competitors?.find(c => c.position === 1)?.name || "?",
    away: m.awayTeam?.name || m.competitors?.find(c => c.position === 2)?.name || "?",
    minute: minuteOf(m.matchTime)
  }));
}

// Subscribe to match-odds exactly like the server (isBaseOddsGroups:false), merge
// snapshot + deltas, stamp each leg with arrival time, listen ~15s.
function grabOdds(id, listenMs = 15000) {
  const url = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(LANG)}&externalPartnerId=${encodeURIComponent(PARTNER_ID)}&EIO=4&transport=websocket`;
  const groups = new Map(); // key -> {id,name,legs:Map(oddKey->{outcome,status,cf,seenAt})}
  return new Promise(resolve => {
    let done = false;
    const ws = new WebSocket(url);
    const finish = () => { if (done) return; done = true; clearTimeout(t); try { ws.close(); } catch {} resolve(groups); };
    const t = setTimeout(finish, listenMs);
    ws.onerror = finish;
    ws.onclose = finish;
    ws.onmessage = ev => {
      const text = String(ev.data || "");
      if (text === "2") { try { ws.send("3"); } catch {} return; }
      if (text.startsWith("0")) { try { ws.send("40"); } catch {} return; }
      if (text.startsWith("40")) {
        try { ws.send(`42["subscribe",{"messageType":"subscribe-match-odds","data":{"matchIds":[${Number(id)}],"isBaseOddsGroups":false}}]`); } catch { finish(); }
        return;
      }
      if (!text.startsWith("42")) return;
      let payload; try { payload = JSON.parse(text.slice(2)); } catch { return; }
      const msg = payload?.[1];
      if (!msg) return;
      const datas = Array.isArray(msg.data) ? msg.data : [msg.data || {}];
      const now = Date.now();
      for (const d of datas) {
        const gs = d.oddsGroups || d.groups || (d.oddsGroup ? [d.oddsGroup] : (d.group ? [d.group] : (d.name && d.oddsList ? [d] : [])));
        for (const g of gs) {
          const key = String(g.id ?? g.groupId ?? g.oddsGroupId ?? g.marketId ?? g.name ?? "");
          if (!key) continue;
          let rec = groups.get(key);
          if (!rec) { rec = { id: g.id ?? key, name: g.name || "", legs: new Map() }; groups.set(key, rec); }
          if (g.name) rec.name = g.name;
          for (const odd of (g.oddsList || g.odds || g.outcomes || [])) {
            const ok = String(odd.id ?? odd.oddId ?? odd.outcomeId ?? `${odd.outcome || odd.name || ""}:${odd.value ?? odd.line ?? ""}`);
            rec.legs.set(ok, { outcome: odd.outcome || odd.name || "", status: odd.status, cf: odd.cf ?? odd.value, seenAt: now });
          }
        }
      }
    };
  });
}

(async () => {
  const live = await listLive();
  const sorted = live.slice().sort((a, b) => (b.minute || 0) - (a.minute || 0));
  let target = NAME_FILTER
    ? sorted.find(m => `${m.home} ${m.away}`.toLowerCase().includes(NAME_FILTER))
    : sorted[0];
  if (!target) { console.log(`No live match matching "${NAME_FILTER}". Live now:`); sorted.slice(0, 15).forEach(m => console.log(`  [${m.minute}'] ${m.home} vs ${m.away} id=${m.id}`)); process.exit(0); }

  console.log(`\nTarget: [${target.minute}'] ${target.home} vs ${target.away}  id=${target.id}`);
  console.log(`Subscribing to match-odds (isBaseOddsGroups:false) for ~15s...\n`);
  const groups = await grabOdds(target.id);
  const end = Date.now();
  if (groups.size === 0) { console.log("NO odds groups received at all."); process.exit(0); }

  console.log(`Groups received: ${groups.size}\n`);
  for (const [key, rec] of groups) {
    const legs = [...rec.legs.values()];
    const open = legs.filter(l => Number(l.status) === 1).length;
    const newestDelta = Math.max(...legs.map(l => l.seenAt));
    const ageMs = end - newestDelta;
    console.log(`GROUP id=${rec.id} name="${rec.name}"`);
    console.log(`   legs=${legs.length} open(status=1)=${open}  newestDeltaAge=${(ageMs / 1000).toFixed(1)}s  (fresh<90s? ${ageMs < 90000})`);
    for (const l of legs) console.log(`     - "${l.outcome}" status=${l.status} cf=${l.cf} age=${((end - l.seenAt) / 1000).toFixed(1)}s`);
  }
  console.log(`\nNOTE: legs whose price never changed during the 15s window keep their snapshot-arrival age (~window length).`);
  process.exit(0);
})().catch(e => { console.error("PROBE FAILED:", e); process.exit(1); });
