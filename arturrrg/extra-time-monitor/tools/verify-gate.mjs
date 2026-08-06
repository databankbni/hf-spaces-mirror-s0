// Verify the hardened real-football gate against the LIVE 1win list.
// Replicates the exact isNonRealFootballMatch logic from server.js (normalizeText +
// hyphen collapse + patterns) and classifies every live soccer match, printing
// REAL vs FAKE with the deciding tournament slug, so we can confirm:
//   - all confirmed fakes (esportsbattle / h2h-gg-league / short-football /
//     ehighlights / vi-highlights / world-cup-penalty-shootout / (V) / (replays)) -> FAKE
//   - all real leagues (aff-championship, liga-bantu, queensland-premier-league-2,
//     universities-championship, women-national-teams-*) -> REAL

const H = { accept: "application/json", "content-type": "application/json", referer: "https://1wlgk.com/", "user-agent": "Mozilla/5.0", "x-external-partner-id": "44ba10e5-7df2-47ab-a44d-dc93803c7a6e", "x-lang": "en-001", "x-user-location": "MD" };

// ---- verbatim copy of server.js logic ----
const NON_REAL_FOOTBALL_PATTERNS = [
  /\bcyberfifa\b/i, /\besportsbattle\b/i, /\bh2h\s+gg\s+league\b/i, /\bgg\s+league\b/i,
  /\bereplays?\b/i, /\breplays?\b/i, /\behighlights?\b/i, /\bhighlights?\b/i,
  /\bpenalty\s+shootout\b/i, /\bshort\s+football\b/i, /\bshort\s+football\s+3x3\b/i,
  /\b2x3\s*min/i, /\b2x4\s*min/i, /\b2x5\s*min/i, /\bvirtual\b/i, /\befootball\b/i,
  /\be\s*football\b/i, /\besoccer\b/i, /\be\s*soccer\b/i, /\besports?\b/i
];
const normalizeText = t => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9\s\-]/g, "").trim();
function isNonRealFootballMatch({ league = "", home = "", away = "", slug = "", tournamentSlug = "" } = {}) {
  const teamText = `${home} ${away}`;
  if (/\((?:v|replays?)\)/i.test(teamText)) return true;
  const text = normalizeText(`${league} ${slug} ${tournamentSlug}`).replace(/[-_]+/g, " ").replace(/\s+/g, " ");
  return NON_REAL_FOOTBALL_PATTERNS.some(p => p.test(text));
}
// ---- end copy ----

(async () => {
  const r = await fetch("https://api-gateway.top-parser.com/matches/get-many", { method: "POST", headers: H, body: JSON.stringify({ service: "live", sportId: 18, excludeSportType: "polybet", limit: 100 }) });
  const items = (await r.json()).result?.items || [];
  let real = 0, fake = 0;
  const realRows = [], fakeRows = [];
  for (const m of items) {
    const home = m.homeTeam?.name || "?";
    const away = m.awayTeam?.name || "?";
    const tslug = m.tournament?.slug || "";
    const isFake = isNonRealFootballMatch({ league: tslug, home, away, slug: m.slug || "", tournamentSlug: tslug });
    const row = `  ${(home + " vs " + away).slice(0, 42).padEnd(44)} | ${tslug}`;
    if (isFake) { fake++; fakeRows.push(row); } else { real++; realRows.push(row); }
  }
  console.log(`=== FAKE (gated out, no injury time) : ${fake} ===`);
  fakeRows.forEach(s => console.log(s));
  console.log(`\n=== REAL (kept, eligible for injury time) : ${real} ===`);
  realRows.forEach(s => console.log(s));
  console.log(`\nTotal ${items.length}  |  real ${real}  |  fake ${fake}`);
  process.exit(0);
})().catch(e => { console.error("FAIL", e); process.exit(1); });
