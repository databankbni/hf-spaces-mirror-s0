// Confirm hypothesis: sportcast event type 1104 = announced added time.
//   i1 = minutes added, i2 = half (1 = first half, 2 = second half).
// Prints every 1104 across all live matches next to the live clock.

const PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e", LANG = "en-001", LOCATION = "MD";
const API_HEADERS = { accept: "application/json", "content-type": "application/json", referer: "https://1wlgk.com/", "user-agent": "Mozilla/5.0", "x-external-partner-id": PARTNER_ID, "x-lang": LANG, "x-user-location": LOCATION };
const HOSTS = ["https://line-lb61-w.bk6bba-resources.com", "https://line-lb54-w.bk6bba-resources.com"];
const SC = { accept: "application/json", referer: "https://video-translations.top-parser.com/", origin: "https://video-translations.top-parser.com", "user-agent": "Mozilla/5.0" };
const post = async (u, b) => { const r = await fetch(u, { method: "POST", headers: API_HEADERS, body: JSON.stringify(b) }); if (!r.ok) throw new Error(r.status); return r.json(); };
const sc = async p => { let e; for (const h of HOSTS) { try { const r = await fetch(h + p, { headers: SC }); if (r.ok) return r.json(); e = r.status; } catch (x) { e = x; } } throw new Error(e); };
const fon = u => { const v = decodeURIComponent(String(u || "")); const m = v.match(/tracker\/get\/(\d+)/i); return m ? m[1] : ""; };
function grab(ids) { const url = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${LANG}&externalPartnerId=${PARTNER_ID}&EIO=4&transport=websocket`; const s = new Map(); return new Promise(res => { let d = 0; const ws = new WebSocket(url); const f = () => { if (d) return; d = 1; clearTimeout(t); try { ws.close(); } catch {} res(s); }; const t = setTimeout(f, 12000); ws.onerror = f; ws.onclose = f; ws.onmessage = e => { const x = String(e.data || ""); if (x === "2") return void ws.send("3"); if (x[0] === "0") return void ws.send("40"); if (x.startsWith("40")) { ws.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`); return; } if (!x.startsWith("42")) return; let p; try { p = JSON.parse(x.slice(2)); } catch { return; } const m = p?.[1]; if (!m || !/match-info/.test(m.messageType)) return; for (const dd of (Array.isArray(m.data) ? m.data : [m.data])) { const id = String(dd.matchId || dd.id || ""); if (id) s.set(id, dd); } if (s.size >= ids.length) setTimeout(f, 1000); }; }); }

(async () => {
  const j = await post("https://api-gateway.top-parser.com/matches/get-many", { service: "live", sportId: 18, excludeSportType: "polybet", limit: 100 });
  const items = j.result?.items || [];
  const snaps = await grab(items.map(m => Number(m.id)));
  const rows = items.map(m => { const d = snaps.get(String(m.id)); const mt = Number(d?.matchTime); return { home: m.homeTeam?.name || "?", away: m.awayTeam?.name || "?", status: d?.status || "?", min: Number.isFinite(mt) ? Math.floor(mt / 60000) : null, tracker: d?.liveTracker?.url || "" }; }).filter(r => r.tracker).sort((a, b) => (b.min || 0) - (a.min || 0));

  console.log(`match | clock | status | 1104 events (i1=mins, i2=half)`);
  console.log(`-----------------------------------------------------------`);
  for (const r of rows) {
    const f = fon(r.tracker); if (!f) continue;
    let code, ev;
    try { const meta = await sc(`/ma/sportscast/actrans?fonid=${f}&lang=eng`); code = (meta.items || []).find(e => e?.code)?.code; if (!code) continue; ev = await sc(`/ma/sportscast/events?code=${code}&lastid=0`); } catch { continue; }
    const e1104 = (ev.events || []).filter(e => Number(e.type) === 1104).map(e => `+${e.i1}'(H${e.i2}@${e.regtime.slice(-8)})`);
    console.log(`${r.home} vs ${r.away} | ${r.min}' | ${r.status} | ${e1104.join("  ") || "(none yet)"}`);
  }
  process.exit(0);
})().catch(e => { console.error("FAIL", e); process.exit(1); });
