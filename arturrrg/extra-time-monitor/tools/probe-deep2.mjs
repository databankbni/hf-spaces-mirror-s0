// Round 2: chase the two live leads.
//  1) full dump of GET matches/get?matchId= (the one endpoint that returned a result)
//  2) sportcast SIBLING endpoints: many betradar-style feeds expose a "match
//     situation / statistics" channel that carries LIVE injurytime continuously,
//     not just the 1104 board pulse. Probe /ma/sportscast/{stat,info,situation,...}
//  3) does the broadcast sportplayer embed expose anything?
//  4) census: across ALL tracker matches, list gateway_code + tracker type, and
//     whether a non-1104 "added time" style event exists.

const PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e", LANG = "en-001", LOCATION = "MD";
const GW = "https://api-gateway.top-parser.com";
const API_HEADERS = { accept: "application/json", "content-type": "application/json", referer: "https://1wlgk.com/", "user-agent": "Mozilla/5.0", "x-external-partner-id": PARTNER_ID, "x-lang": LANG, "x-user-location": LOCATION };
const HOSTS = ["https://line-lb61-w.bk6bba-resources.com", "https://line-lb54-w.bk6bba-resources.com"];
const SC = { accept: "application/json", referer: "https://video-translations.top-parser.com/", origin: "https://video-translations.top-parser.com", "user-agent": "Mozilla/5.0" };

const post = async (u, b) => { const r = await fetch(u, { method: "POST", headers: API_HEADERS, body: JSON.stringify(b) }); return { ok: r.ok, status: r.status, json: r.ok ? await r.json().catch(() => null) : null }; };
const get = async (u) => { const r = await fetch(u, { headers: API_HEADERS }); return { ok: r.ok, status: r.status, json: r.ok ? await r.json().catch(() => null) : null }; };
const scRaw = async (p, host) => { const r = await fetch(host + p, { headers: SC }); return { ok: r.ok, status: r.status, text: await r.text() }; };
const sc = async p => { let e; for (const h of HOSTS) { try { const r = await fetch(h + p, { headers: SC }); if (r.ok) return r.json(); e = r.status; } catch (x) { e = x; } } throw new Error(e); };
const fon = u => { const v = decodeURIComponent(String(u || "")); const m = v.match(/tracker\/get\/(\d+)/i); return m ? m[1] : ""; };

function grab(ids) { const url = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${LANG}&externalPartnerId=${PARTNER_ID}&EIO=4&transport=websocket`; const s = new Map(); return new Promise(res => { let d = 0; const ws = new WebSocket(url); const f = () => { if (d) return; d = 1; clearTimeout(t); try { ws.close(); } catch {} res(s); }; const t = setTimeout(f, 12000); ws.onerror = f; ws.onclose = f; ws.onmessage = e => { const x = String(e.data || ""); if (x === "2") return void ws.send("3"); if (x[0] === "0") return void ws.send("40"); if (x.startsWith("40")) { ws.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`); return; } if (!x.startsWith("42")) return; let p; try { p = JSON.parse(x.slice(2)); } catch { return; } const m = p?.[1]; if (!m || !/match-info/.test(m.messageType)) return; for (const dd of (Array.isArray(m.data) ? m.data : [m.data])) { const id = String(dd.matchId || dd.id || ""); if (id) s.set(id, dd); } if (s.size >= ids.length) setTimeout(f, 1000); }; }); }

(async () => {
  const list = await post(`${GW}/matches/get-many`, { service: "live", sportId: 18, excludeSportType: "polybet", limit: 100 });
  const items = list.json?.result?.items || [];
  const snaps = await grab(items.map(m => Number(m.id)));
  const ranked = items.map(m => { const d = snaps.get(String(m.id)); const mt = Number(d?.matchTime); return { id: m.id, home: m.homeTeam?.name, away: m.awayTeam?.name, status: d?.status, min: Number.isFinite(mt) ? Math.floor(mt / 60000) : null, tracker: d?.liveTracker?.url || "", type: d?.liveTracker?.type || "" }; }).sort((a, b) => (b.min || 0) - (a.min || 0));
  const real = ranked.find(m => m.tracker && (m.min || 0) >= 45) || ranked.find(m => m.tracker);

  // 1) full matches/get result
  console.log(`\n===== 1) GET matches/get?matchId=${real.id} FULL =====`);
  const mg = await get(`${GW}/matches/get?matchId=${real.id}`);
  console.log(JSON.stringify(mg.json, null, 2).slice(0, 4000));

  // 2) sportcast sibling endpoints
  const fonId = fon(real.tracker);
  const meta = await sc(`/ma/sportscast/actrans?fonid=${fonId}&lang=eng`);
  const code = (meta.items || []).find(e => e?.code)?.code;
  console.log(`\n===== 2) sportcast sibling endpoints (fonId=${fonId} code=${code}) =====`);
  const scPaths = [
    `/ma/sportscast/stat?code=${code}&lang=eng`,
    `/ma/sportscast/statistics?code=${code}&lang=eng`,
    `/ma/sportscast/info?code=${code}&lang=eng`,
    `/ma/sportscast/situation?code=${code}&lang=eng`,
    `/ma/sportscast/state?code=${code}&lang=eng`,
    `/ma/sportscast/match?code=${code}&lang=eng`,
    `/ma/sportscast/matchinfo?code=${code}&lang=eng`,
    `/ma/sportscast/timer?code=${code}&lang=eng`,
    `/ma/sportscast/get?code=${code}&lang=eng`,
    `/ma/sportscast/scoreboard?code=${code}&lang=eng`,
    `/ma/sportscast/widget?code=${code}&lang=eng`,
    `/ma/sportscast/events?code=${code}&lastid=0&full=1`,
  ];
  for (const p of scPaths) {
    let got = null;
    for (const h of HOSTS) { try { const r = await scRaw(p, h); if (r.ok) { got = r.text; break; } else got ??= `${r.status}`; } catch (e) { got ??= e.message; } }
    const short = typeof got === "string" && got.length > 300 ? got.slice(0, 300) + "…" : got;
    console.log(`  ${p.split("?")[0]}  -> ${short}`);
  }

  // 3) tracker page itself (bet-broadcast tracker/get) — does the raw widget bootstrap carry injurytime?
  console.log(`\n===== 3) raw tracker bootstrap =====`);
  try {
    const tr = await fetch(real.tracker, { headers: SC });
    const txt = await tr.text();
    console.log(`tracker GET ${tr.status}, len=${txt.length}`);
    const m = txt.match(/.{0,40}(injur|added|stoppage|extratime|compensat).{0,60}/gi);
    console.log(`injury mentions in tracker html/json: ${m ? JSON.stringify(m.slice(0, 8)) : "none"}`);
  } catch (e) { console.log(`tracker err ${e.message}`); }

  // 4) gateway/type census + check for an "added-time" event other than 1104
  console.log(`\n===== 4) tracker census (gateway + 1104 alt scan) =====`);
  for (const m of ranked.filter(r => r.tracker).slice(0, 8)) {
    const f = fon(m.tracker);
    let mt2, c2;
    try { mt2 = await sc(`/ma/sportscast/actrans?fonid=${f}&lang=eng`); c2 = (mt2.items || []).find(e => e?.code); } catch { continue; }
    console.log(`  [${m.min}'] ${m.home} vs ${m.away} | type=${m.type} | gateway=${c2?.gateway_code} | dur=${c2?.extra?.duration} | sport_code=${c2?.sport_code}`);
  }

  process.exit(0);
})().catch(e => { console.error("FAIL", e); process.exit(1); });
