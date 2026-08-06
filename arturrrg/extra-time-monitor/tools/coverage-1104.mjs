// Coverage check: of all live soccer matches, how many expose a tracker (=> can
// have event 1104 from the API), and of those past 45', how many actually have a
// 1104 board announcement. Answers "do we get injury time from the API no matter what".

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
  let total = 0, withTracker = 0, past45 = 0, past45WithH1 = 0, noTrackerList = [];
  for (const m of items) {
    total++;
    const d = snaps.get(String(m.id));
    const mt = Number(d?.matchTime); const min = Number.isFinite(mt) ? Math.floor(mt / 60000) : null;
    const tracker = d?.liveTracker?.url || "";
    if (!tracker) { noTrackerList.push(`${m.homeTeam?.name} vs ${m.awayTeam?.name} (${min ?? "?"}', ${d?.status || "?"})`); continue; }
    withTracker++;
    if ((min || 0) < 46) continue;
    past45++;
    let has = false;
    try { const meta = await sc(`/ma/sportscast/actrans?fonid=${fon(tracker)}&lang=eng`); const code = (meta.items || []).find(e => e?.code)?.code; if (code) { const ev = await sc(`/ma/sportscast/events?code=${code}&lastid=0`); has = (ev.events || []).some(e => Number(e.type) === 1104); } } catch {}
    if (has) past45WithH1++; else console.log(`  past-45 tracker match WITHOUT 1104: ${m.homeTeam?.name} vs ${m.awayTeam?.name} (${min}')`);
  }
  console.log(`\nTotal live soccer: ${total}`);
  console.log(`With liveTracker (=> sportcast/1104 possible): ${withTracker} (${Math.round(withTracker / total * 100)}%)`);
  console.log(`Without any tracker (=> NO API injury time): ${total - withTracker}`);
  console.log(`Past 45' with tracker: ${past45}  | of those with >=1 1104: ${past45WithH1} (${past45 ? Math.round(past45WithH1 / past45 * 100) : 0}%)`);
  if (noTrackerList.length) { console.log(`\nNo-tracker matches:`); noTrackerList.forEach(s => console.log(`  - ${s}`)); }
  process.exit(0);
})().catch(e => { console.error("FAIL", e); process.exit(1); });
