import express from "express";
import cors from "cors";
import webpush from "web-push";
import { WebSocketServer } from "ws"; // browser<->server push (the global WebSocket stays the 1win client)
import { fileURLToPath } from "url";
import path, { dirname } from "path";
import fs from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Persistent data dir for the audit log (passive outcome record so accuracy can be
// checked). On HF Spaces set DATA_DIR to a persistent mount (e.g. /data) so the log
// survives restarts; defaults to the repo dir for local runs.
const DATA_DIR = process.env.DATA_DIR || __dirname;
try { fs.mkdirSync(DATA_DIR, { recursive: true }); } catch { /* best effort */ }

function loadLocalEnvFile() {
  const envPath = path.join(__dirname, ".env");
  if (!fs.existsSync(envPath)) return;

  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const eqIndex = trimmed.indexOf("=");
    if (eqIndex === -1) continue;

    const key = trimmed.slice(0, eqIndex).trim();
    let value = trimmed.slice(eqIndex + 1).trim();
    if (!key || Object.prototype.hasOwnProperty.call(process.env, key)) continue;

    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

loadLocalEnvFile();

const app = express();
app.use(cors());
app.use(express.json({ limit: "16kb" }));

// Disable caching for local assets to ensure dynamic code modifications propagate instantly
app.use(express.static(__dirname, {
  setHeaders: (res, filePath) => {
    res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate, private");
    res.setHeader("Pragma", "no-cache");
    res.setHeader("Expires", "0");
  }
}));

app.get("/favicon.ico", (req, res) => res.redirect(302, "/favicon.svg"));

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    uptime: Math.round(process.uptime()),
    liveMatches: oneWinLiveMatchesCache.size,
    activeMatches: activeAutoMatches.length,
    webSocket: typeof WebSocket,
    liveInfoSocket: oneWinLiveInfoSocket?.readyState ?? null,
    oddsSnapshotEnabled: ONE_WIN_ODDS_SNAPSHOT_ENABLED,
    oddsSnapshotSocket: oneWinOddsSnapshotSocket?.readyState ?? null,
    timestamp: Date.now()
  });
});

const PORT = process.env.PORT || 7860;

// =========================================================================
// MINIMUM MINUTE THRESHOLD FOR TRACKING
// Defaults to late-stage monitoring; override TEMP_MIN_MINUTE for verification runs.
const TEMP_MIN_MINUTE = Number.parseInt(process.env.TEMP_MIN_MINUTE || "62", 10);
// A fixture first DISCOVERED at/after this minute has almost no lead time before the 90' freeze
// (1win surfaced its tracker/timeline very late — typical of low-tier reserve feeds). Such a match
// fails our usefulness rule and is never added to the dashboard (see updateAutoTrackedMatches).
const LATE_APPEARANCE_MINUTE = Number.parseInt(process.env.LATE_APPEARANCE_MINUTE || "85", 10);
// On a fresh restart EVERY live match is rediscovered at once — including ones we were already
// tracking that are now past LATE_APPEARANCE_MINUTE. The late-discovery guard would wrongly drop
// those from the dashboard. So suppress that guard for this grace window after process start; once
// it elapses, genuine late low-tier feeds are skipped as before.
const LATE_APPEARANCE_STARTUP_GRACE_SEC = Number.parseInt(process.env.LATE_APPEARANCE_STARTUP_GRACE_SEC || "300", 10);
// From this minute on, do not retire a card just because FTR/No-Goal briefly disappear.
// Deep endgame markets often suspend/reappear, so the dashboard keeps the card and lets
// the entry signal decide whether the match is actionable.
const MARKET_NARROW_MINUTE = Number.parseInt(process.env.MARKET_NARROW_MINUTE || "88", 10);
// Anti-flicker grace: 1win frequently suspends a market then re-adds it seconds later. A
// market counts as "active" if it was last seen active within this window, so a brief
// suspend/resume blip does not churn the entry signal or blink the displayed odds off and on.
const MARKET_ACTIVE_GRACE_MS = Number.parseInt(process.env.MARKET_ACTIVE_GRACE_MS || "60000", 10);
// Freshness window (anti-zombie, GROUP-level): a market we have NOT seen ANY delta for within
// this window stops counting as active, so a SILENTLY-removed market (1win drops it with no close
// signal — corners vanishing ~90') clears instead of lingering forever. This is the ONLY way to
// detect a silent removal; there is no instant signal to push. Applied per market
// (isOneWinGroupActive), never per leg — 1win's delta feed leaves individual legs quiet for long
// stretches while the market is plainly still open, so per-leg ageing wrongly dropped stable legs.
// Lowered 90s -> 45s so silent removals clear ~2x faster; still well above the gap between
// re-prices on a genuinely-open market, so a quiet-but-open market is not aged out prematurely.
const MARKET_ODD_FRESH_MS = Number.parseInt(process.env.MARKET_ODD_FRESH_MS || "45000", 10);
// Legacy display-hold (no longer referenced): the visible No-Goal / Full Time Result sections used
// to linger for this long after a suspend. They now use the short MARKET_DISPLAY_GRACE_MS instead so
// the board tracks 1win in near-real-time. Kept as a defined env knob for compatibility.
const MARKET_LAPSE_MS = Number.parseInt(process.env.MARKET_LAPSE_MS || "180000", 10);
// DEPRECATED (no longer referenced): the visible No-Goal / Full Time Result odds blocks used to
// linger this long after a suspend to ride out 1win's rapid suspend→resume micro-blips. The display
// now MIRRORS 1win with no hold — it tracks isMarketActive directly, so a suspend hides the odds and
// a resume shows them again in ~100ms (see buildDashboardPayload). Kept as a defined env knob only
// for backwards-compatibility; set it >0 again if the un-buffered mirror ever flickers too much.
const MARKET_DISPLAY_GRACE_MS = Number.parseInt(process.env.MARKET_DISPLAY_GRACE_MS || "0", 10);
// How long a socket-detected full-event suspend keeps suppressing the market ghosts between odds
// deltas. 1win flips every leg of a suspended event to status 2 ("bets temporarily not accepted");
// applyOneWinSocketMarketUpdate stamps suspendedAt on any tick that reads as fully suspended
// (isOneWinEventSuspendedFromGroups) and clears it the moment a market is active again. This grace
// just bridges the gap between deltas so a genuinely-suspended event stays suppressed until the next
// tick, comfortably longer than the delta cadence. No DOM scrape is involved any more.
const ONE_WIN_EVENT_SUSPEND_GRACE_MS = Number.parseInt(process.env.ONEWIN_EVENT_SUSPEND_GRACE_MS || "30000", 10);
// Grace for BOTH tracked markets (Full Time Result + No-Goal) to appear/return before the card is
// dropped. The card is only useful while at least one of the two is priced; if both stay absent for
// this long (while we're otherwise receiving live odds, below 90'), the match is retired.
const BOTH_MARKETS_LAPSE_MS = Number.parseInt(process.env.BOTH_MARKETS_LAPSE_MS || "300000", 10);
// Single canonical reason for every late-goal removal so SYSTEM LOGS stay consistent.
const GOAL_REMOVAL_REASON = "Goal scored after 62nd minute (62'–90')";
// The 4th official's ANNOUNCED 2nd-half added time (sportcast 1104, shown on the dashboard)
// above which we retire the card: an unusually long board (> 5') is a drawn-out, atypical
// finish the user will follow live on 1win directly, so the card no longer adds anything.
const MAX_ANNOUNCED_ADDED_MINUTES = Number.parseInt(process.env.MAX_ANNOUNCED_ADDED_MINUTES || "5", 10);
const LONG_ADDED_TIME_REMOVAL_REASON = `Announced added time over ${MAX_ANNOUNCED_ADDED_MINUTES}m`;

const ONE_WIN_API_PARTNER_ID = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e";
const ONE_WIN_API_LANG = "en-001";
const ONE_WIN_API_LOCATION = "MD";
const ONE_WIN_LIVE_REFRESH_INTERVAL_MS = Number.parseInt(process.env.ONEWIN_LIVE_REFRESH_INTERVAL_MS || "15000", 10);
const ONE_WIN_RATE_LIMIT_BASE_BACKOFF_MS = Number.parseInt(process.env.ONEWIN_RATE_LIMIT_BASE_BACKOFF_MS || "4000", 10);
const ONE_WIN_RATE_LIMIT_MAX_BACKOFF_MS = Number.parseInt(process.env.ONEWIN_RATE_LIMIT_MAX_BACKOFF_MS || "25000", 10);
const ONE_WIN_TOURNAMENT_REFRESH_INTERVAL_MS = Number.parseInt(process.env.ONEWIN_TOURNAMENT_REFRESH_INTERVAL_MS || String(10 * 60 * 1000), 10);
// 1win's REST live-list intermittently omits still-playing matches. A match must be
// absent from this many CONSECUTIVE live-list responses before it is evicted, so a
// single flaky response can never cascade into a false "match completed" exclusion.
const ONE_WIN_LIVE_LIST_MISS_TOLERANCE = Number.parseInt(process.env.ONEWIN_LIVE_LIST_MISS_TOLERANCE || "3", 10);
const ONE_WIN_API_FETCH_TIMEOUT_MS = Number.parseInt(process.env.ONEWIN_API_FETCH_TIMEOUT_MS || "10000", 10);
const ONE_WIN_TIMELINE_API_POLL_INTERVAL_MS = Number.parseInt(process.env.ONEWIN_TIMELINE_API_POLL_INTERVAL_MS || "1500", 10);
// A total line 1win has stopped updating goes stale relative to the freshest odd in the same market.
const ODDS_LINE_STALE_MS = Number.parseInt(process.env.ONEWIN_ODDS_LINE_STALE_MS || "45000", 10);
const ONE_WIN_TIMELINE_API_MAX_MATCHES = Math.max(1, Math.min(30, Number.parseInt(process.env.ONEWIN_TIMELINE_API_MAX_MATCHES || "18", 10) || 18));
const ONE_WIN_TIMELINE_API_CONCURRENCY = Math.max(1, Math.min(6, Number.parseInt(process.env.ONEWIN_TIMELINE_API_CONCURRENCY || "2", 10) || 2));
// Snapshot auditor: the normal match-odds socket is delta-only after subscribe, so a quiet
// market can look stale even while it is still open. This short-lived websocket repeatedly
// resubscribes and uses the initial board snapshot to refresh open markets and quickly confirm
// silent removals. Set ONEWIN_ODDS_SNAPSHOT_INTERVAL_MS=0 to disable.
const ONE_WIN_ODDS_SNAPSHOT_INTERVAL_RAW_MS = Number.parseInt(process.env.ONEWIN_ODDS_SNAPSHOT_INTERVAL_MS || "2000", 10);
const ONE_WIN_ODDS_SNAPSHOT_ENABLED = Number.isFinite(ONE_WIN_ODDS_SNAPSHOT_INTERVAL_RAW_MS) && ONE_WIN_ODDS_SNAPSHOT_INTERVAL_RAW_MS > 0;
const ONE_WIN_ODDS_SNAPSHOT_INTERVAL_MS = ONE_WIN_ODDS_SNAPSHOT_ENABLED
  ? Math.max(500, ONE_WIN_ODDS_SNAPSHOT_INTERVAL_RAW_MS)
  : 0;
const ONE_WIN_ODDS_SNAPSHOT_LISTEN_MS = Math.max(350, Math.min(
  Number.parseInt(process.env.ONEWIN_ODDS_SNAPSHOT_LISTEN_MS || "900", 10) || 900,
  ONE_WIN_ODDS_SNAPSHOT_INTERVAL_MS ? Math.max(350, ONE_WIN_ODDS_SNAPSHOT_INTERVAL_MS - 100) : 900
));
// A group missing from this many consecutive fresh snapshots is treated as gone. Default 2 means
// a 2s snapshot cadence confirms silent removals in roughly 4s while ignoring one bad snapshot.
const ONE_WIN_ODDS_SNAPSHOT_MISS_TOLERANCE = Math.max(1, Math.min(5, Number.parseInt(process.env.ONEWIN_ODDS_SNAPSHOT_MISS_TOLERANCE || "2", 10) || 2));

let isCacheLoopRunning = false;

const oneWinLinksCache = new Map();
const activeOneWinSearches = new Set();
// ── Single source of truth for the 1win odds feed ───────────────────────────
// One per-match state object, fed exclusively by the match-odds websocket and keyed by the
// canonical match key. Every market the API exposes (Full Time Result, No-Goal, and the rest)
// is derived from its `groups` in ONE place (applyOneWinSocketMarketUpdate), so display, the
// bet signal, the both-markets-lapse timer, and the finished check all read the same state.
// Shape: { key, matchId, groups, connectedAt, updatedAt, isFinished,
//          fullTimeResult: { odds, isMarketActive, lastGoodAt },
//          nextGoal:       { odds, isMarketActive, lastGoodAt },
//          otherMarketsLastGoodAt, otherMarketsList, availableMarketsList, isAnyMarketActive,
//          suspendedAt }
const oneWinMarketStateByKey = new Map();
const oneWinLiveMatchesCache = new Map(); // key -> direct live match snapshot from 1win soccer page/API
// key -> { ftrSig, ngSig, suspended } — last-written odds log state per match so duplicate
// socket re-sends of the same prices do NOT produce a second log line.
const oddsLogLastByKey = new Map();

const searchQueue = [];

const matchCache = new Map();
const activeTrackedMatches = new Map(); 
const blacklistedMatches = new Map(); // key -> timestamp of blacklist
const blacklistedMatchIds = new Map(); // stable 1win matchId -> timestamp of blacklist (survives team-name reformatting)
const oneWinKeyByMatchId = new Map(); // stable 1win matchId -> the canonical cache key it was FIRST seen under. Pins a fixture's identity so a mid-match team-name reformat ("Venezuela (Youth)" -> "Venezuela Youth") can't mint a second key and spawn a duplicate queue/dashboard card.

let isOneWinLiveRefreshing = false;
let lastOneWinLiveRefreshAt = 0;
let oneWinLiveBackoffUntil = 0;
let oneWinLiveRateLimitFailures = 0;
let oneWinTournamentCache = { map: new Map(), expiresAt: 0 };
let oneWinLiveInfoSocket = null;
let oneWinLiveInfoSocketSignature = "";
let oneWinLiveInfoSocketReconnectAt = 0;
const oneWinLiveMetaById = new Map();
const oneWinLiveInfoSnapshots = new Map();
const oneWinTimelineApiFeeds = new Map();
let oneWinOddsSocket = null;
let oneWinOddsSocketSignature = "";
let oneWinOddsSocketReconnectAt = 0;
let oneWinOddsSnapshotSocket = null;
let oneWinOddsSnapshotTimer = null;
let oneWinOddsSnapshotCollectTimer = null;
let oneWinOddsSnapshotReady = false;
let oneWinOddsSnapshotCollecting = false;
let oneWinOddsSnapshotReconnectAt = 0;
let oneWinOddsSnapshotFailures = 0;
let oneWinOddsSnapshotEmptyCycles = 0;
let oneWinOddsSnapshotGroupsByMatchId = new Map();
let oneWinOddsSnapshotTargets = new Map();
let isOneWinTimelineApiRefreshing = false;
let oneWinTimelineApiRotationCursor = 0;
let cacheLoopTimer = null;
let isShuttingDown = false;

let activeAutoMatches = []; 
let recentRemovals = []; // Tracks removed matches to serve to frontend toasts + system log
// Server-authoritative retention for the exclusion log. MUST match the client's
// display TTL (20 min in app.js) so every device — no matter when it connects —
// rebuilds the SAME log from the payload. The old 5-min window let late-joining
// devices miss removals the server had already forgotten, so logs diverged
// (desktop showing entries a phone opened minutes later never saw).
const REMOVAL_RETENTION_MS = 20 * 60 * 1000;
const dashboardClients = new Set();      // SSE clients (legacy fallback)
const dashboardWsClients = new Set();     // WebSocket clients (primary, instant push)
let dashboardBroadcastTimer = null;

// ── Web Push (background 90' No-Goal alerts) ─────────────────────────────
// Notifications reach a device even when the tab is closed. VAPID keys and the
// subscription list live in DATA_DIR so they survive restarts (mount /data as
// persistent storage, same requirement as the audit log).
const VAPID_PATH = path.join(DATA_DIR, "vapid.json");
const PUSH_SUBSCRIPTIONS_PATH = path.join(DATA_DIR, "push-subscriptions.json");
// Append-only, human-readable record of EVERY system exclusion, ever. Unlike recentRemovals
// (in-memory, pruned after REMOVAL_RETENTION_MS), this file lives in DATA_DIR so it survives
// restarts and is never auto-pruned — it is the permanent system log the dashboard's export
// button opens. Capped at SYSTEM_LOG_MAX entries only as a runaway safety, not routine cleanup.
const SYSTEM_LOG_PATH = path.join(DATA_DIR, "system-log.json");
// Append-only JSONL capturing every FTR + Next Goal odds change at 90'+ for all tracked matches.
// Record types: "odds" (price/availability changed), "suspend", "resume", "close" (match done).
const ODDS_LOG_PATH = path.join(DATA_DIR, "odds-log.jsonl");
const BLACKLIST_PATH = path.join(DATA_DIR, "blacklist.json");
const MATCH_AUDIT_PATH = path.join(DATA_DIR, "match-audit.jsonl");
const SYSTEM_LOG_MAX = 20000;
let systemLog = []; // chronological (oldest first); served newest-first
const VAPID_SUBJECT = process.env.VAPID_SUBJECT || "mailto:alerts@extratimemonitor.app";
let vapidKeys = null;
let pushSubscriptions = []; // [{ endpoint, keys, mutedNextGoal, createdAt }]
const pushSeenBeforeBoard = new Set(); // mids witnessed live before the 2nd-half added-time board went up
const pushedNextGoalMatches = new Set(); // mids already pushed for the stoppage-time next-goal alert

// Diagnostic memory sets to prevent terminal console log spam
const loggedRejections = new Set();
const loggedPending = new Set();
const loggedNonRealFootballSkips = new Set();
const loggedTrackerWaits = new Set();

const NON_REAL_FOOTBALL_PATTERNS = [
  /\bcyberfifa\b/i,
  /\besportsbattle\b/i,
  /\bh2h\s+gg\s+league\b/i,
  /\bgg\s+league\b/i,
  /\bereplays?\b/i,
  /\breplays?\b/i,
  /\behighlights?\b/i,
  /\bhighlights?\b/i,
  /\bpenalty\s+shootout\b/i,
  /\bshort\s+football\b/i,
  /\bshort\s+football\s+3x3\b/i,
  /\b2x3\s*min/i,
  /\b2x4\s*min/i,
  /\b2x5\s*min/i,
  /\bvirtual\b/i,
  /\befootball\b/i,
  /\be\s*football\b/i,
  /\besoccer\b/i,
  /\be\s*soccer\b/i,
  /\besports?\b/i
];

// True for anything that is NOT real 11-a-side football (esports, virtual, replays,
// highlight reels, penalty-shootout sims, short 3x3/2x4-min formats) — these never
// have a real referee or injury time, so they must never enter the added-time pipeline.
//
// The strongest signal is the 1win `tournament.slug` (e.g. "h2h-gg-league-2x4-min",
// "short-football-3x3-2x5-mins", "world-cup-penalty-shootout", "vi-highlights-…").
// Slugs are hyphenated, so we collapse "-"/"_" to spaces BEFORE testing — otherwise
// space-based patterns like /short\s+football/ silently miss "short-football". The REST
// `isEsport`/`sportType` flags are useless here (false/"default" even for esportsbattle),
// which is why slug + team-name marks ("(V)", "(replays)") are the real discriminators.
function isNonRealFootballMatch({ league = "", home = "", away = "", slug = "", tournamentSlug = "" } = {}) {
  const teamText = `${home} ${away}`;
  if (/\((?:v|replays?)\)/i.test(teamText)) return true;

  const text = normalizeText(`${league} ${slug} ${tournamentSlug}`)
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ");
  return NON_REAL_FOOTBALL_PATTERNS.some(pattern => pattern.test(text));
}

function logNonRealFootballSkip(key, home, away, league) {
  if (loggedNonRealFootballSkips.has(key)) return;
  loggedNonRealFootballSkips.add(key);
}

// Under-age / youth-team fixtures carry a U-number tag (U17/U18/U19/U20/U21/U23, "Under-20")
// in the league, the 1win tournament slug, OR the team names ("Brazil U20" vs "Argentina U20"),
// so all five fields are tested. We collapse "-"/"_" to spaces first (so slug forms like
// "fifa-u20-world-cup" and "under-20" read the same as the spaced variants), then match only the
// U-number forms — broad "Youth"/"Junior"/"Primavera" leagues are intentionally left live.
const UNDER_AGE_PATTERNS = [
  /\bu-?\s?\d{2}\b/i,
  /\bunder[\s-]?\d{2}\b/i
];

function isUnderAgeMatch({ league = "", home = "", away = "", slug = "", tournamentSlug = "" } = {}) {
  const text = normalizeText(`${league} ${slug} ${tournamentSlug} ${home} ${away}`)
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ");
  return UNDER_AGE_PATTERNS.some(pattern => pattern.test(text));
}

const loggedUnderAgeSkips = new Set();
function logUnderAgeSkip(key, home, away, league) {
  if (loggedUnderAgeSkips.has(key)) return;
  loggedUnderAgeSkips.add(key);
  console.log(`[UNDER-AGE SKIP] ${home} vs ${away} (${league || "?"}) — under-age fixture excluded.`);
}

const LOW_TIER_LEAGUE_PATTERNS = [
  /\btercera\b/i,
  /\bcuarta\b/i,
  /\breserve\b/i,
  /\breserves\b/i,
  /\breservas\b/i,
  /\bprimavera\b/i,
  /\bamateur\b/i,
  /\bregional\b/i,
  /\bdistrict\b/i,
  /\blocal\b/i,
  /\bdivision\s+[345]\b/i,
  /\bliga\s+[345]\b/i,
  /\bclass\s+[bcde]\b/i
];

const FRIENDLY_PATTERNS = [
  /\bfriendly\b/i,
  /\bamistoso\b/i,
  /\bexhibition\b/i
];

function isLowTierOrReserve({ league = "", home = "", away = "", slug = "", tournamentSlug = "" } = {}) {
  const leagueText = normalizeText(league).replace(/[-_]+/g, " ");
  const slugText = normalizeText(`${slug} ${tournamentSlug}`).replace(/[-_]+/g, " ");
  const teamText = `${home} ${away}`.toLowerCase();

  // 1. Check if league or slug contains low-tier league words
  const isLowTierLeague = LOW_TIER_LEAGUE_PATTERNS.some(p => p.test(leagueText) || p.test(slugText));
  if (isLowTierLeague) return true;

  // 2. Check if league or slug contains friendly match words
  const isFriendly = FRIENDLY_PATTERNS.some(p => p.test(leagueText) || p.test(slugText));
  if (isFriendly) return true;

  // 3. Check if team names have reserve indicators
  const words = teamText.split(/\s+/);
  const hasReserveTeam = words.some(word => 
    word === "ii" || 
    word === "2" || 
    word === "reserve" || 
    word === "reserves" || 
    word === "reservas"
  );
  if (hasReserveTeam) return true;

  return false;
}

function recordOneWinRateLimit(scope, message = "") {
  oneWinLiveRateLimitFailures += 1;
  const backoffMs = Math.min(
    ONE_WIN_RATE_LIMIT_MAX_BACKOFF_MS,
    ONE_WIN_RATE_LIMIT_BASE_BACKOFF_MS * Math.max(1, oneWinLiveRateLimitFailures)
  );
  oneWinLiveBackoffUntil = Date.now() + backoffMs;
  console.error(`[1win ${scope}] Rate limited${message ? `: ${message}` : ""}. Pausing REST discovery for ${Math.round(backoffMs / 1000)}s while sockets/cache keep running.`);
}

function clearOneWinRateLimit() {
  oneWinLiveRateLimitFailures = 0;
  oneWinLiveBackoffUntil = 0;
}

function trimSetToSize(set, maxSize) {
  while (set.size > maxSize) {
    const first = set.values().next().value;
    if (first === undefined) break;
    set.delete(first);
  }
}

// One-line boot diagnostic: whether DATA_DIR is a persistent mount. Push subscriptions
// and VAPID keys live there, so an ephemeral dir means they reset on restart. There is
// no added-time model or audit log anymore — we act only on the real announced board.
function logPersistenceStatus() {
  const persistent = DATA_DIR !== __dirname;
  console.log(
    `[STORAGE] DATA_DIR=${DATA_DIR} ` +
    `(${persistent ? "persistent" : "EPHEMERAL — push subscriptions reset on restart"})`
  );

  // Initialize match-audit.jsonl if it doesn't exist so the file is visible immediately on boot
  if (!fs.existsSync(MATCH_AUDIT_PATH)) {
    try {
      fs.writeFileSync(MATCH_AUDIT_PATH, "", "utf8");
      console.log(`[STORAGE] Initialized new match-audit.jsonl file.`);
    } catch (err) {
      console.warn(`[STORAGE] Failed to initialize match-audit.jsonl: ${err.message}`);
    }
  }
}

function pruneRuntimeMemory() {
  trimSetToSize(loggedRejections, 1000);
  trimSetToSize(loggedPending, 1000);
  trimSetToSize(loggedNonRealFootballSkips, 1000);
  trimSetToSize(loggedTrackerWaits, 1000);

  const liveKeys = new Set(oneWinLiveMatchesCache.keys());
  const activeKeys = new Set(activeAutoMatches.map(match => match.key));
  for (const key of oneWinLinksCache.keys()) {
    if (!liveKeys.has(key) && !matchCache.has(key) && !activeKeys.has(key)) {
      oneWinLinksCache.delete(key);
    }
  }
  for (const key of oneWinMarketStateByKey.keys()) {
    if (!matchCache.has(key) && !activeKeys.has(key)) {
      oneWinMarketStateByKey.delete(key);
    }
  }
  for (const key of oneWinTimelineApiFeeds.keys()) {
    if (!matchCache.has(key) && !activeKeys.has(key)) {
      oneWinTimelineApiFeeds.delete(key);
    }
  }

  const removalCutoff = Date.now() - REMOVAL_RETENTION_MS;
  recentRemovals = recentRemovals.filter(removal => removal.timestamp > removalCutoff);
}

function saveBlacklist() {
  try {
    fs.writeFileSync(BLACKLIST_PATH, JSON.stringify({
      matches: Array.from(blacklistedMatches.entries()),
      matchIds: Array.from(blacklistedMatchIds.entries())
    }, null, 2), "utf8");
  } catch (err) {
    console.warn(`[BLACKLIST] save failed: ${err.message}`);
  }
}

function loadBlacklist() {
  try {
    if (!fs.existsSync(BLACKLIST_PATH)) return;
    const data = JSON.parse(fs.readFileSync(BLACKLIST_PATH, "utf8"));
    if (Array.isArray(data.matches)) {
      for (const [k, time] of data.matches) {
        blacklistedMatches.set(k, time);
      }
    }
    if (Array.isArray(data.matchIds)) {
      for (const [id, time] of data.matchIds) {
        blacklistedMatchIds.set(id, time);
      }
    }
    console.log(`[BLACKLIST] Loaded ${blacklistedMatches.size} blacklisted keys and ${blacklistedMatchIds.size} blacklisted IDs from ${BLACKLIST_PATH}`);
  } catch (err) {
    console.warn(`[BLACKLIST] load failed: ${err.message}`);
  }
}

function blacklistMatch(key, matchId = null) {
  blacklistedMatches.set(key, Date.now());

  // Also blacklist by the stable 1win matchId so a re-add can't slip past the name-key
  // blacklist when 1win reformats the team names (e.g. "Okzhetpes (w)" vs "Okzhetpes W").
  // Fall back to the cached entry's id — but only when the match is legitimately in cache
  // (a content-based drop). Absence-based drops ("no longer in cache") have no cache entry
  // here, so they intentionally capture no id and stay recoverable from transient feed gaps.
  const id = String(matchId || matchCache.get(key)?.info?.matchId || "").trim();
  if (/^\d+$/.test(id)) blacklistedMatchIds.set(id, Date.now());

  saveBlacklist();

  // Release any identity pin pointing at this key so the fixture can re-key cleanly
  // if it legitimately returns after the blacklist expires.
  for (const [pinnedId, pinnedKey] of oneWinKeyByMatchId.entries()) {
    if (pinnedKey === key) oneWinKeyByMatchId.delete(pinnedId);
  }

  oneWinLinksCache.delete(key);
  oneWinMarketStateByKey.delete(key);
  oneWinLiveMatchesCache.delete(key);
  oneWinTimelineApiFeeds.delete(key);
  matchCache.delete(key); // Instantly purge from cache database to save RAM

  // Instantly strip this key from the pending search queue to avoid useless network lookups
  for (let i = searchQueue.length - 1; i >= 0; i--) {
    if (searchQueue[i].key === key) {
      searchQueue.splice(i, 1);
    }
  }
}

function isBlacklisted(key) {
  const cutoff = Date.now() - 2 * 60 * 60 * 1000; // Auto-expire entries after 2 hours
  let changed = false;
  for (const [k, time] of blacklistedMatches.entries()) {
    if (time < cutoff) {
      blacklistedMatches.delete(k);
      changed = true;
    }
  }
  if (changed) saveBlacklist();
  return blacklistedMatches.has(key);
}

function isBlacklistedById(matchId) {
  const id = String(matchId || "").trim();
  if (!/^\d+$/.test(id)) return false;
  const cutoff = Date.now() - 2 * 60 * 60 * 1000; // Auto-expire entries after 2 hours
  let changed = false;
  for (const [k, time] of blacklistedMatchIds.entries()) {
    if (time < cutoff) {
      blacklistedMatchIds.delete(k);
      changed = true;
    }
  }
  if (changed) saveBlacklist();
  return blacklistedMatchIds.has(id);
}

function isMatchCompleteRemovalReason(reason) {
  const normalized = normalizeText(reason);
  return normalized.includes("match completed") ||
    normalized.includes("no longer in cache") ||
    normalized.includes("finished") ||
    normalized.includes("full time");
}

function isGoalRemovalReason(reason) {
  return normalizeText(reason).includes("goal scored");
}

// The Under market was removed, so removal telemetry no longer carries betting lines.
function getRemovalTelemetryOdds() {
  return [];
}

function cloneMatchInfoForAudit(info = {}) {
  const currentMin = Number(info.currentMin);
  const clockAdded = Number.parseInt(info.secondHalfElapsedAddedTime, 10);
  const officialAdded = Number.parseInt(info.secondHalfInjuryTime, 10);
  const firstHalfAdded = Number.parseInt(info.firstHalfInjuryTime, 10);
  const playedAdded = Number.parseInt(info.secondHalfPlayedAddedTime, 10);

  return {
    score: info.score || "0-0",
    time: info.time || "",
    phase: info.phase || "",
    currentMin: Number.isFinite(currentMin) ? currentMin : getCurrentMinute(info.time),
    secondHalfElapsedAddedTime: Number.isFinite(clockAdded) && clockAdded > 0 ? clockAdded : 0,
    secondHalfInjuryTime: Number.isFinite(officialAdded) && officialAdded > 0 ? officialAdded : 0,
    firstHalfInjuryTime: Number.isFinite(firstHalfAdded) && firstHalfAdded > 0 ? firstHalfAdded : 0,
    // Actual added time played until the full-time whistle (derived from sportcast event
    // timestamps at 1102). getFinalAddedMinutes reports max(this, board) as the "actual".
    secondHalfPlayedAddedTime: Number.isFinite(playedAdded) && playedAdded >= 0 ? playedAdded : undefined,
    // Extra time taints the running clock as an added-time signal — carry the flag so the
    // finaliser refuses to fabricate an "actual" from (currentMin - 90). minute > 105 is an
    // unambiguous ET backstop even if the flag was lost upstream.
    isExtraTime: info.isExtraTime === true || (Number.isFinite(currentMin) && currentMin > 105),
    rawStatus: info.rawStatus || ""
  };
}

function getFinalAddedMinutes(info = {}) {
  // The announced regulation board "+X" (sportcast 1104) is the referee's signalled
  // number and a hard floor. The ACTUAL time played until the full-time whistle
  // (secondHalfPlayedAddedTime, derived from event timestamps at 1102) is what really
  // happened on the pitch — it can exceed the board when the ref plays past it. Report
  // the larger of the two so the audit's "actual" reflects time genuinely played and
  // never dips below the board. Both remain valid even after a match goes to extra time.
  const board = Number.parseInt(info.secondHalfInjuryTime, 10);
  const played = Number.parseInt(info.secondHalfPlayedAddedTime, 10);
  const boardOk = Number.isFinite(board) && board > 0;
  const playedOk = Number.isFinite(played) && played >= 0;
  if (boardOk || playedOk) {
    return Math.max(boardOk ? board : 0, playedOk ? played : 0);
  }

  // In extra time the running clock no longer measures added time, so without a board number we
  // have no trustworthy "actual" — return null ("log nothing") rather than fabricate a +20-ish value.
  if (info.isExtraTime === true) return null;

  const clockAdded = Number.parseInt(info.secondHalfElapsedAddedTime, 10);
  if (Number.isFinite(clockAdded) && clockAdded > 0) return clockAdded;

  const currentMin = Number.isFinite(info.currentMin) ? info.currentMin : getCurrentMinute(info.time);
  // Only derive an "actual" from the clock once the match has genuinely reached full time
  // (currentMin >= 90). Below 90' the match was abandoned / suspended / flaky-dropped mid-play
  // and never played stoppage at all — Math.max(0, currentMin-90) would clamp to a fabricated
  // +0 that poisons the audit (e.g. a 67' drop scored as a full -5 miss vs a +5 board).
  if (Number.isFinite(currentMin) && currentMin >= 90) {
    const derived = currentMin - 90;
    // A real second-half stoppage never exceeds ~12 min; anything larger is an undetected ET
    // clock leaking through. Refuse it instead of polluting the audit/calibration.
    return derived <= 12 ? derived : null;
  }

  return null;
}

// At eviction time the score we log comes from matchCache, which is synced from the
// live list, which is synced from the real-time socket — so it can trail the board the
// user sees by a refresh cycle. When a late goal is what evicted the match, that lag
// means we'd stamp the PRE-goal score (e.g. 0-2 logged for a 0-3 removal). Pull the
// freshest reading across all three caches and keep the highest goal count (goals only
// climb during live play), so the log reflects the goal that actually caused the drop.
function freshestRemovalScore(tracked, cachedInfo) {
  const candidates = [];
  const pushScore = raw => {
    const norm = normalizeOneWinScore(raw);
    if (norm && norm !== "0-0") candidates.push(norm);
  };

  // Real-time socket snapshot (freshest), keyed by matchId.
  const matchId = String(cachedInfo?.info?.matchId || "").trim();
  if (matchId && oneWinLiveInfoSnapshots.has(matchId)) {
    try { pushScore(parseOneWinApiLiveInfo(oneWinLiveInfoSnapshots.get(matchId)).score); }
    catch (_) { /* malformed snapshot — fall through to other sources */ }
  }
  // Live-list cache (synced on each 1win API refresh).
  const live = (tracked && tracked.home && tracked.away)
    ? findOneWinLiveMatchForTeams(tracked.home, tracked.away)
    : null;
  if (live) pushScore(live.score);
  // Synced matchCache score — what the scanner actually detected the goal on.
  pushScore(cachedInfo?.info?.score);

  if (candidates.length === 0) return normalizeOneWinScore(cachedInfo?.info?.score);
  return candidates.reduce((best, s) => getTotalGoals(s) > getTotalGoals(best) ? s : best, candidates[0]);
}

// ── Persistent system log ──────────────────────────────────────────────────────
// Load the durable log at boot so a restart resumes the same file instead of starting blank.
function loadSystemLog() {
  try {
    if (!fs.existsSync(SYSTEM_LOG_PATH)) return [];
    const parsed = JSON.parse(fs.readFileSync(SYSTEM_LOG_PATH, "utf8"));
    const entries = Array.isArray(parsed) ? parsed : (Array.isArray(parsed?.entries) ? parsed.entries : []);
    // File is served newest-first; keep the in-memory copy chronological (oldest first).
    return entries.slice().reverse();
  } catch (err) {
    console.warn(`[SYSTEM LOG] load failed: ${err.message}`);
    return [];
  }
}

// Serialize a well-structured, self-describing document. Entries are newest-first so the file
// reads top-down as a timeline; each carries both an epoch ms and an ISO string for either viewport.
function buildSystemLogDocument() {
  return {
    title: "Extra-Time Monitor — Persistent System Log",
    note: "Append-only record of every system exclusion. Survives restarts; never auto-pruned.",
    generatedAt: new Date().toISOString(),
    count: systemLog.length,
    entries: systemLog.slice().reverse()
  };
}

let systemLogWriteTimer = null;
function writeSystemLog() {
  // Debounce: removals can burst when several matches drop in one monitor loop.
  if (systemLogWriteTimer) return;
  systemLogWriteTimer = setTimeout(() => {
    systemLogWriteTimer = null;
    try {
      fs.writeFileSync(SYSTEM_LOG_PATH, JSON.stringify(buildSystemLogDocument(), null, 2), "utf8");
    } catch (err) {
      console.warn(`[SYSTEM LOG] write failed: ${err.message}`);
    }
  }, 1500);
}

// Append one exclusion to the durable log. Mirrors the recentRemovals entry but flattened into a
// reader-friendly shape with an ISO timestamp.
function appendSystemLog(removal) {
  const t = removal.telemetry || {};
  systemLog.push({
    loggedAt: new Date(removal.timestamp).toISOString(),
    timestamp: removal.timestamp,
    match: removal.name,
    reason: removal.reason,
    score: t.score ?? null,
    time: t.time ?? null,
    actualAddedMinutes: t.actualAddedMinutes ?? null,
    oddsCount: t.oddsCount ?? 0,
    odds: Array.isArray(t.odds) ? t.odds : [],
    oneWinUrl: t.oneWinUrl ?? null,
    key: removal.key,
    matchId: removal.matchId
  });
  if (systemLog.length > SYSTEM_LOG_MAX) systemLog.splice(0, systemLog.length - SYSTEM_LOG_MAX);
  writeSystemLog();
}

// ── Odds log (real-time FTR + Next Goal prices at 90'+) ───────────────────────
// Appends one JSON line per change. Synchronous appendFileSync is fine — records
// are tiny and writes happen at most once per socket delta (~several per second at most).
function appendOddsLog(record) {
  try {
    fs.appendFileSync(ODDS_LOG_PATH, JSON.stringify(record) + "\n", "utf8");
  } catch (err) {
    console.warn(`[ODDS LOG] write failed: ${err.message}`);
  }
}

function appendMatchAuditRow(row) {
  try {
    fs.appendFileSync(MATCH_AUDIT_PATH, JSON.stringify(row) + "\n", "utf8");
  } catch (err) {
    console.warn(`[MATCH AUDIT] write failed: ${err.message}`);
  }
}

// Called from applyOneWinSocketMarketUpdate every time the market state is refreshed.
// Only writes when something actually changed (price, active flag, or suspend state).
function maybeLogOdds(key, nextState, cachedInfo, now) {
  const info = cachedInfo?.info || {};
  const min = getCurrentMinute(info.time);
  if (min === null || min < 90) return; // only log from 90' onward

  const added    = Math.max(0, Number.parseInt(info.secondHalfElapsedAddedTime, 10) || 0);
  const score    = info.score || "?";
  const matchId  = String(nextState.matchId || "");

  const ftr       = nextState.fullTimeResult || {};
  const ng        = nextState.nextGoal || {};
  const suspended = !!nextState.suspendedAt;

  // Compact price snapshot: { outcome -> odds } or null when market is off.
  const ftrSnap = ftr.isMarketActive
    ? Object.fromEntries((ftr.odds || []).map(o => [o.outcome, o.odds]))
    : null;
  // Full Next Goal market: No Goal + both team legs.
  const ngRaw = ng.isMarketActive ? (ng.odds || []) : null;
  let ngSnap = null;
  if (ngRaw) {
    ngSnap = {};
    for (const o of ngRaw) ngSnap[o.outcome] = o.odds;
  }

  const ftrSig = JSON.stringify(ftrSnap) + "|" + (ftr.isMarketActive ? "1" : "0");
  const ngSig  = JSON.stringify(ngSnap)  + "|" + (ng.isMarketActive  ? "1" : "0");
  const last   = oddsLogLastByKey.get(key) || {};

  const suspendChanged = last.suspended !== undefined && last.suspended !== suspended;
  const oddsChanged    = ftrSig !== last.ftrSig || ngSig !== last.ngSig;

  if (!oddsChanged && !suspendChanged) return; // nothing new — skip

  oddsLogLastByKey.set(key, { ftrSig, ngSig, suspended });

  const base = { ts: now, key, matchId, min, added, score };

  if (suspendChanged && suspended) {
    // Market just went suspended — log the last known prices too so the record is self-contained.
    appendOddsLog({ t: "suspend", ...base,
      ftr: ftrSnap ? { ...ftrSnap, active: true  } : { active: false },
      ng:  ngSnap  ? { ...ngSnap,  active: true  } : { active: false } });
    return;
  }
  if (suspendChanged && !suspended) {
    appendOddsLog({ t: "resume", ...base,
      ftr: ftrSnap ? { ...ftrSnap, active: true  } : { active: false },
      ng:  ngSnap  ? { ...ngSnap,  active: true  } : { active: false } });
    return;
  }
  // Normal odds / availability change.
  appendOddsLog({ t: "odds", ...base,
    ftr:       ftrSnap ? { ...ftrSnap, active: true  } : { active: false },
    ng:        ngSnap  ? { ...ngSnap,  active: true  } : { active: false },
    suspended });
}

// Packages exact final state telemetry on backend side at the exact moment of eviction
function recordRemoval(tracked, reason, cachedInfo = null) {
  if (!tracked.hasAppeared) return; // Silent discard for matches that never appeared on the dashboard

  // Compute actual added minutes at the moment of removal (for FT log display)
  const cachedAuditInfo = cloneMatchInfoForAudit(cachedInfo?.info || {});
  const lastSeenAuditInfo = cloneMatchInfoForAudit(tracked.lastSeenMatchInfo || {});
  const cachedFinal = getFinalAddedMinutes(cachedAuditInfo);
  const lastSeenFinalRaw = getFinalAddedMinutes(lastSeenAuditInfo);

  // Scan events for the highest minute > 90 — MUST be declared before lastSeenFinal uses it.
  // Capped at 12 (real stoppage max) so an extra-time event can't inflate the FT-log "+X".
  const maxFromEvents = ((cachedInfo?.events) || [])
    .map(e => Number.parseInt(e.minute, 10))
    .filter(m => Number.isFinite(m) && m > 90 && m - 90 <= 12)
    .reduce((best, m) => Math.max(best, m - 90), 0);

  // Only subtract 1 when clock is exactly 1 min ahead of the last stoppage event.
  const lastSeenFinal = (Number.isFinite(lastSeenFinalRaw) && maxFromEvents > 0 && lastSeenFinalRaw === maxFromEvents + 1)
    ? maxFromEvents
    : lastSeenFinalRaw;

  // Genuine-signal gate: without a board / played-time / at-or-past-90 clock reading or a >90'
  // stoppage event, a sub-90' stop (abandoned / suspended / flaky drop) has NO real added time.
  // Show "—" (null), never a fabricated +0 that the FT log would render as a real stoppage.
  const hasGenuineActual = Number.isFinite(cachedFinal) || Number.isFinite(lastSeenFinal) || maxFromEvents > 0;
  const actualAddedMinutes = hasGenuineActual
    ? Math.max(
        Number.isFinite(cachedFinal) ? cachedFinal : -1,
        Number.isFinite(lastSeenFinal) ? lastSeenFinal : -1,
        maxFromEvents
      )
    : -1;

  // Resolve the 1win link from the SAME source list the dashboard used to show this
  // match (buildDashboardPayload), so the system-log entry always carries the link the
  // card displayed. tracked.url lives on the match object and survives cache eviction,
  // which matters for completed matches removed via the "no longer in cache" path where
  // cachedInfo is null.
  const trackedUrl = (tracked.url && !tracked.url.includes("mid=onewin_")) ? tracked.url : null;
  const oneWinUrl = firstUsableOneWinLink(
    tracked.displayOneWinUrl,
    oneWinLinksCache.get(tracked.key),
    cachedInfo?.info?.oneWinUrl,
    cachedInfo?.info?.liveTrackerUrl,
    trackedUrl
  ) || null;

  let telemetry = null;
  if (cachedInfo) {
    const rawOdds = getRemovalTelemetryOdds(tracked, reason);
    telemetry = {
      score: freshestRemovalScore(tracked, cachedInfo),
      time: cachedInfo.info.time || "00:00",
      oddsCount: rawOdds.length,
      odds: rawOdds.map(o => ({ line: o.line, odds: o.odds })),
      actualAddedMinutes: actualAddedMinutes >= 0 ? actualAddedMinutes : null,
      oneWinUrl
    };
  } else if (isMatchCompleteRemovalReason(reason)) {
    telemetry = {
      score: tracked.scoreAt62 || "0-0",
      time: "FT",
      oddsCount: 0,
      odds: [],
      actualAddedMinutes: actualAddedMinutes >= 0 ? actualAddedMinutes : null,
      oneWinUrl
    };
  }

  const removal = {
    id: `${tracked.key}_${Date.now()}`,
    key: tracked.key,
    // Stable 1win matchId lets a re-add clear this entry even when 1win reformatted the
    // team names (so the fixture returns under a different name-key) — see purge in
    // buildDashboardPayload.
    matchId: String(tracked.matchId || cachedInfo?.info?.matchId || "").trim() || null,
    name: `${tracked.home} vs ${tracked.away}`,
    reason: reason,
    timestamp: Date.now(),
    telemetry: telemetry
  };
  recentRemovals.push(removal);
  const cutoff = Date.now() - REMOVAL_RETENTION_MS;
  recentRemovals = recentRemovals.filter(r => r.timestamp > cutoff);
  // Mirror into the permanent, restart-proof log (recentRemovals above is pruned after 20 min).
  appendSystemLog(removal);

  // Write final record to match-audit.jsonl
  if (isMatchCompleteRemovalReason(reason)) {
    const finalAddedMinutes = actualAddedMinutes >= 0 ? actualAddedMinutes : 0;
    appendMatchAuditRow({
      id: `final:${removal.matchId || removal.key}`,
      type: "final",
      matchAuditId: String(removal.matchId || ""),
      key: removal.key,
      matchId: String(removal.matchId || ""),
      home: tracked.home,
      away: tracked.away,
      league: tracked.league || "",
      reason,
      timestamp: Date.now(),
      score: telemetry?.score || "0-0",
      time: telemetry?.time || "FT",
      finalMinute: telemetry?.time === "FT" ? 90 : null,
      finalAddedMinutes,
      announcedSecondHalfAddedTime: Number.parseInt(cachedAuditInfo.secondHalfInjuryTime, 10) || Number.parseInt(lastSeenAuditInfo.secondHalfInjuryTime, 10) || 0,
      announcedFirstHalfAddedTime: Number.parseInt(cachedAuditInfo.firstHalfInjuryTime, 10) || Number.parseInt(lastSeenAuditInfo.firstHalfInjuryTime, 10) || 0
    });
  }

  // Odds log: write a terminal "close" record so every match's odds history ends cleanly.
  if (oddsLogLastByKey.has(removal.key)) {
    appendOddsLog({ t: "close", ts: removal.timestamp, key: removal.key,
      matchId: removal.matchId || "", reason: removal.reason,
      score: removal.telemetry?.score || "?" });
    oddsLogLastByKey.delete(removal.key);
  }
}


function dropTrackedMatchImmediately(key, reason, cachedInfo = null) {
  const tracked = activeAutoMatches.find(match => match.key === key);
  if (tracked) {
    recordRemoval(tracked, reason, cachedInfo || matchCache.get(key));
    activeAutoMatches = activeAutoMatches.filter(match => match.key !== key);
  }

  activeTrackedMatches.delete(key);
  blacklistMatch(key);
  scheduleDashboardBroadcast(0);
  return Boolean(tracked);
}

const clamp = (x, min, max) => Math.max(min, Math.min(max, x));
const clean = s => String(s || "").replace(/[\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim();

function positiveInt(value, max = Number.POSITIVE_INFINITY) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 && parsed <= max ? parsed : 0;
}

// Strips tournament seeding/group marks (e.g. [1], [10], (2.5)) cleanly from team names
function cleanTeamName(name) {
  if (!name) return "";
  return String(name)
    .replace(/\([\s\d.+-]+\)/g, '')
    .replace(/\[[\s\d.+-]+\]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function makeOneWinSyntheticMid(home, away) {
  const hClean = home.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 10);
  const aClean = away.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 10);
  return `onewin_${hClean}_${aClean}`;
}

function timelineEventBaseKey(e) {
  return `${e.minute}-${e.type}-${e.side || ""}`;
}

function dedupe(events) {
  const seen = new Set();
  const occurrenceCounts = new Map();
  return events.filter(e => {
    if (e.minute < 1 || e.minute > 120 || e.type === "other") return false;

    const baseKey = timelineEventBaseKey(e);
    const explicitOccurrence = Number.isInteger(e.occurrence) && e.occurrence > 0 ? e.occurrence : null;
    const nextOccurrence = explicitOccurrence || ((occurrenceCounts.get(baseKey) || 0) + 1);
    occurrenceCounts.set(baseKey, Math.max(occurrenceCounts.get(baseKey) || 0, nextOccurrence));

    e.occurrence = nextOccurrence;
    const key = `${baseKey}-${nextOccurrence}`;
    
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).sort((a, b) => a.minute - b.minute || (a.occurrence || 1) - (b.occurrence || 1));
}

function currentMinuteFromMatchInfo(matchInfo = {}) {
  if (Number.isFinite(matchInfo.currentMin)) return matchInfo.currentMin;
  return getCurrentMinute(matchInfo.time);
}

function isTimelineEventPlausibleForCurrentClock(event, matchInfo = {}) {
  if (!event || !Number.isFinite(event.minute)) return false;
  if (event.type === "first_half_injury_time" || event.type === "second_half_injury_time") return true;

  const currentMin = currentMinuteFromMatchInfo(matchInfo);
  if (!Number.isFinite(currentMin) || currentMin >= 90) return true;

  return event.minute <= currentMin + 3;
}

function getTotalGoals(scoreStr) {
  if (!scoreStr) return 0;
  const parts = scoreStr.split("-").map(Number);
  if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
    return parts[0] + parts[1];
  }
  return 0;
}

function parseTimelineLine(line, homeTeam, awayTeam) {
  line = clean(String(line || ""))
    .replace(/[´`′]/g, "'")
    .replace(/\s*([~\-–—−:])\s*/g, " $1 ")
    .replace(/\s+/g, " ")
    .trim();
  if (!line) return null;

  const firstHalfScoreMatch = line.match(/score after first half\s*[-:]\s*(\d+\s*[-:]\s*\d+)/i);
  if (firstHalfScoreMatch) {
    return { type: "first_half_score", score: firstHalfScoreMatch[1].replace(/\s*[:\-]\s*/g, "-"), display: line, minute: 45 };
  }

  const fullTimeScoreMatch = line.match(/score after (?:second half|full time)\s*[-:]\s*(\d+\s*[-:]\s*\d+)/i);
  if (fullTimeScoreMatch) {
    return { type: "full_time_score", score: fullTimeScoreMatch[1].replace(/\s*[:\-]\s*/g, "-"), display: line, minute: 90 };
  }

  const lineLower = line.toLowerCase();

  if (lineLower.includes("second half injury time") || lineLower.includes("second half added time") ||
      lineLower.includes("otrā puslaika") || lineLower.includes("otra puslaika")) {
    const match = line.match(/(?:second half injury time|second half added time|otrā puslaika|otra puslaika)\s*:?\s*(\d+)/i) || line.match(/(\d+)\s*min/i);
    return { type: "second_half_injury_time", minutes: match ? parseInt(match[1], 10) : 0, display: line, minute: 90 };
  }

  if (lineLower.includes("first half injury time") || lineLower.includes("first half added time") ||
      lineLower.includes("pirmā puslaika") || lineLower.includes("pirma puslaika")) {
    const match = line.match(/(?:first half injury time|first half added time|pirmā puslaika|pirma puslaika)\s*:?\s*(\d+)/i) || line.match(/(\d+)\s*min/i);
    return { type: "first_half_injury_time", minutes: match ? parseInt(match[1], 10) : 0, display: line, minute: 45 };
  }

  const minMatch = line.match(/^(\d+)(?:\+(\d+))?['’´`′]?/);
  if (!minMatch) return null;

  const baseMin = parseInt(minMatch[1], 10);
  const addedMin = minMatch[2] ? parseInt(minMatch[2], 10) : 0;
  const minute = baseMin + addedMin;
  const minuteDisplay = minMatch[2] ? `${baseMin}+${addedMin}'` : `${baseMin}'`;
  
  let display = line.replace(/^\d+(?:\+\d+)?['’´`′]?\s*[-–—~−:]*\s*/, "").trim();

  let type = "other";

  const isDisallowed = lineLower.includes("disallowed") || 
                       lineLower.includes("cancelled") || 
                       lineLower.includes("atcelts") || 
                       lineLower.includes("atcelti") || 
                       lineLower.includes("no goal") || 
                       lineLower.includes("anulēts") || 
                       lineLower.includes("anulēti");

  const isGoal = (lineLower.includes("goal") || 
                 lineLower.includes("vārti") || 
                 lineLower.includes("varti") || 
                 lineLower.includes("vārty") || 
                 lineLower.includes("vartu") || 
                 lineLower.includes("iesist") || 
                 lineLower.includes("gūti") || 
                 lineLower.includes("guti") || 
                 lineLower.includes("autogol") || 
                 /\b(gol|goles|but|buts|tor|tore|гол|голы|автогол)\b/i.test(lineLower)) && !isDisallowed;

  const isPenaltyMissed = lineLower.includes("penalty missed") || 
                          lineLower.includes("missed penalty") || 
                          lineLower.includes("garām") || 
                          lineLower.includes("garam") || 
                          lineLower.includes("netrāp") || 
                          lineLower.includes("netrap") || 
                          lineLower.includes("nerealizē") || 
                          lineLower.includes("nerealize") ||
                          /\b(missed|miss|penaltı кое-кто)\b/i.test(lineLower);

  const isPenalty = lineLower.includes("penalty") || 
                    lineLower.includes("soda sitiens") || 
                    lineLower.includes("pendele") || 
                    lineLower.includes("penalti") ||
                    /\b(11m|11-m|penal)\b/i.test(lineLower);

  const isYellow = lineLower.includes("yellow card") || 
                   lineLower.includes("yellow-card") || 
                   lineLower.includes("dzeltenā kart") || 
                   lineLower.includes("dzeltena kart") || 
                   lineLower.includes("brīdinā") || 
                   lineLower.includes("bridina") ||
                   /\b(yellow|żółta|gelb|amarilla|jaune|желтая|жк)\b/i.test(lineLower);

  const isRed = lineLower.includes("red card") || 
                lineLower.includes("red-card") || 
                lineLower.includes("sarkanā kart") || 
                lineLower.includes("sarkana kart") || 
                lineLower.includes("noraidī") || 
                lineLower.includes("noraidi") ||
                /\b(red|czerwona|rot|roja|rouge|красная|кк)\b/i.test(lineLower);

  const isSubstitution = lineLower.includes("substitution") || 
                         lineLower.includes("maiņa") || 
                         lineLower.includes("mainas") || 
                         lineLower.includes("maiņas") || 
                         /\b(sub|substitution|wechsel|cambio|remplacement|замена)\b/i.test(lineLower);

  const isVar = /\bvar\b/i.test(lineLower) || 
                lineLower.includes("video assistant referee") || 
                lineLower.includes("video tiesnesis") || 
                lineLower.includes("video asist");

  const isCorner = lineLower.includes("corner") || 
                   lineLower.includes("stūra") || 
                   lineLower.includes("stura") || 
                   lineLower.includes("углов") || 
                   /\b(corner|stūris|sturis|cantos|laukuma stūris|corner kick)\b/i.test(lineLower);

  const isRace = lineLower.includes("race to") && isCorner;

  if (isSubstitution) type = "substitution";
  else if (isYellow) type = "yellow";
  else if (isRed) type = "red";
  else if (isPenaltyMissed) type = "penalty_missed";
  else if (isPenalty) type = "penalty";
  else if (isGoal) type = "goal";
  else if (isVar) type = "var";
  else if (isRace) type = "race";
  else if (isCorner) type = "corner";
  else if (isDisallowed) type = "disallowed_goal";

  let side = "home";
  const hClean = homeTeam.toUpperCase().trim();
  const aClean = awayTeam.toUpperCase().trim();
  const lineUpper = line.toUpperCase();

  const getSignificantWords = (teamName) => teamName.split(/\s+/).filter(w => w.length > 3 && !["TOWN", "CITY", "CLUB", "FC", "UNITED", "WANDERERS", "WOMEN", "(W)"].includes(w));
  const homeWords = getSignificantWords(hClean);
  const awayWords = getSignificantWords(aClean);

  if (lineUpper.includes(aClean) || (awayWords.length > 0 && awayWords.some(w => lineUpper.includes(w)))) side = "away";
  else if (lineUpper.includes(hClean) || (homeWords.length > 0 && homeWords.some(w => lineUpper.includes(w)))) side = "home";

  return { minute, minuteDisplay, type, side, display, text: line };
}

function splitTimelineLines(raw) {
  if (!raw) return [];
  return String(raw)
    .replace(/<br\s*\/?>/ig, "\n")
    .replace(/<\/(li|div|tr|p|h\d)>/ig, "\n")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\u00a0/g, " ")
    .replace(/[´`′]/g, "'")
    .replace(/\s+(?=\d{1,3}(?:\+\d{1,2})?['’]\s*[-~–—−])/g, "\n")
    .replace(/\s+(?=Score After (?:First|Second|Full) (?:Half|Time)\b)/ig, "\n")
    .replace(/\s+(?=(?:First|Second) Half (?:Injury|Added) Time\b)/ig, "\n")
    .split(/\n+/)
    .map(line => clean(line))
    .filter(Boolean);
}

function inferOneWinTrackerType(value) {
  const text = normalizeText(String(value || ""));
  if (!text) return "";

  if (text.includes("added time") || text.includes("injury time") || text.includes("stoppage time")) {
    if (text.includes("second half") || text.includes("2nd half")) return "second_half_injury_time";
    if (text.includes("first half") || text.includes("1st half")) return "first_half_injury_time";
  }

  const hasCard = text.includes("card") || text.includes("booking") || text.includes("sent off");
  if ((text.includes("red") && hasCard) || text.includes("redcard") || text.includes("send off") || text.includes("sent off")) return "red";
  if ((text.includes("yellow") && hasCard) || text.includes("yellowcard") || text.includes("booking")) return "yellow";
  if (text.includes("substitution") || text.includes("substitute") || text.includes("replacement") || /\bsub\b/.test(text)) return "substitution";
  if (text.includes("penalty missed") || text.includes("missed penalty")) return "penalty_missed";
  if (text.includes("penalty")) return "penalty";
  if (text.includes("corner")) return "corner";
  if (text.includes("var") || text.includes("video assistant")) return "var";
  if (text.includes("goal") || text.includes("gooaall") || text.includes("score change") || text.includes("scorechanged")) return "goal";
  return "";
}

function parseOneWinTrackerRecord(record, homeTeam, awayTeam) {
  const eventText = clean([
    record?.text,
    record?.tooltip,
    record?.aria,
    record?.title
  ].filter(Boolean).join(" "))
    .replace(/[´`′]/g, "'")
    .replace(/\s+/g, " ")
    .trim();

  const rawText = clean([eventText, record?.typeHint].filter(Boolean).join(" "));
  if (!rawText) return null;

  const addedTimeMatch =
    rawText.match(/\b(?:second|2nd)\s+half\s+(?:injury|added|stoppage)\s+time\s*:?\s*(\d{1,2})\s*(?:min|minute|minutes)?\b/i) ||
    rawText.match(/\b(?:injury|added|stoppage)\s+time\s+(?:second|2nd)\s+half\s*:?\s*(\d{1,2})\s*(?:min|minute|minutes)?\b/i);
  if (addedTimeMatch) {
    const minutes = Number.parseInt(addedTimeMatch[1], 10);
    if (Number.isFinite(minutes) && minutes >= 1 && minutes <= 15) {
      return {
        minute: 90,
        minuteDisplay: "90'",
        type: "second_half_injury_time",
        side: "",
        minutes,
        display: `Second half added time: ${minutes} min`,
        text: rawText,
        source: "1win-tracker",
        trackerRecordSource: record?.source || "tracker"
      };
    }
  }

  const firstHalfAddedTimeMatch =
    rawText.match(/\b(?:first|1st)\s+half\s+(?:injury|added|stoppage)\s+time\s*:?\s*(\d{1,2})\s*(?:min|minute|minutes)?\b/i) ||
    rawText.match(/\b(?:injury|added|stoppage)\s+time\s+(?:first|1st)\s+half\s*:?\s*(\d{1,2})\s*(?:min|minute|minutes)?\b/i);
  if (firstHalfAddedTimeMatch) {
    const minutes = Number.parseInt(firstHalfAddedTimeMatch[1], 10);
    if (Number.isFinite(minutes) && minutes >= 1 && minutes <= 15) {
      return {
        minute: 45,
        minuteDisplay: "45'",
        type: "first_half_injury_time",
        side: "",
        minutes,
        display: `First half added time: ${minutes} min`,
        text: rawText,
        source: "1win-tracker",
        trackerRecordSource: record?.source || "tracker"
      };
    }
  }

  const minuteMatch =
    eventText.match(/(?:^|\b)(\d{1,3})(?:\s*\+\s*(\d{1,2}))?\s*(?:['’]|\bmin(?:ute)?s?\b)/i) ||
    eventText.match(/\b(\d{1,3})(?:\s*\+\s*(\d{1,2}))?\b(?=.*\b(goal|card|booking|substitution|substitute|yellow|red|penalty|corner|var)\b)/i);

  if (!minuteMatch) return null;

  const baseMinute = parseInt(minuteMatch[1], 10);
  const addedMinute = minuteMatch[2] ? parseInt(minuteMatch[2], 10) : 0;
  const minute = baseMinute + addedMinute;
  if (!Number.isFinite(minute) || minute < 1 || minute > 120) return null;

  const type = inferOneWinTrackerType(rawText);
  if (!type) return null;

  const minuteDisplay = minuteMatch[2] ? `${baseMinute}+${addedMinute}'` : `${baseMinute}'`;
  const labelByType = {
    yellow: "Yellow card",
    red: "Red card",
    substitution: "Substitution",
    penalty_missed: "Penalty missed",
    penalty: "Penalty",
    corner: "Corner",
    var: "VAR",
    goal: "Goal"
  };

  const sideName = record?.sideHint === "away" ? awayTeam : record?.sideHint === "home" ? homeTeam : "";
  const parsed = parseTimelineLine(`${minuteDisplay} ${labelByType[type] || type} ${sideName} ${rawText}`, homeTeam, awayTeam);
  if (!parsed || parsed.type === "other") return null;

  parsed.source = "1win-tracker";
  parsed.trackerRecordSource = record?.source || "tracker";
  parsed.text = rawText;
  parsed.display = clean(`${labelByType[type] || parsed.display}${sideName ? ` - ${sideName}` : ""}`);
  return parsed;
}

function getAnnouncedAddedTime(events = [], type) {
  const values = (Array.isArray(events) ? events : [])
    .filter(event => event.type === type)
    .map(event => Number.parseInt(event.minutes, 10))
    .filter(minutes => Number.isFinite(minutes) && minutes > 0 && minutes <= 15);

  return values.length > 0 ? Math.max(...values) : 0;
}

function mergeOneWinTrackerEvents(key, trackerRecords) {
  const cached = matchCache.get(key);
  if (!cached || !Array.isArray(trackerRecords) || trackerRecords.length === 0) {
    return { added: 0, parsed: 0, total: cached?.events?.length || 0 };
  }

  const rawExistingEvents = Array.isArray(cached.events) ? cached.events : [];
  const existingEvents = dedupe(rawExistingEvents
    .filter(event => isTimelineEventPlausibleForCurrentClock(event, cached.info)));
  if (existingEvents.length !== rawExistingEvents.length) {
    cached.events = existingEvents;
    cached.hasDetailedEvents = existingEvents.length > 0;
    cached.lastUpdated = Date.now();
    scheduleDashboardBroadcast();
  }

  const parsedEvents = trackerRecords
    .map(record => parseOneWinTrackerRecord(record, cached.info.home, cached.info.away))
    .filter(event => isTimelineEventPlausibleForCurrentClock(event, cached.info))
    .filter(Boolean);

  if (parsedEvents.length === 0) {
    return { added: 0, parsed: 0, total: cached.events.length };
  }

  const existingCounts = new Map();
  for (const event of existingEvents) {
    const baseKey = timelineEventBaseKey(event);
    existingCounts.set(baseKey, (existingCounts.get(baseKey) || 0) + 1);
  }

  const incomingGroups = new Map();
  for (const event of parsedEvents) {
    const baseKey = timelineEventBaseKey(event);
    const sourceKey = `${baseKey}::${event.trackerRecordSource || "tracker"}`;
    if (!incomingGroups.has(sourceKey)) incomingGroups.set(sourceKey, { baseKey, events: [] });
    incomingGroups.get(sourceKey).events.push(event);
  }

  const bestIncomingByBase = new Map();
  for (const group of incomingGroups.values()) {
    const current = bestIncomingByBase.get(group.baseKey);
    if (!current || group.events.length > current.events.length) {
      bestIncomingByBase.set(group.baseKey, group);
    }
  }

  const additions = [];
  for (const [baseKey, group] of bestIncomingByBase.entries()) {
    const alreadyHave = existingCounts.get(baseKey) || 0;
    for (let i = alreadyHave; i < group.events.length; i++) {
      const event = { ...group.events[Math.min(i, group.events.length - 1)], occurrence: i + 1 };
      additions.push(event);
    }
  }

  const before = existingEvents.length;
  cached.trackerTimelineReady = true;
  cached.events = dedupe([...existingEvents, ...additions]);
  cached.hasDetailedEvents = cached.hasDetailedEvents || cached.events.length > 0;
  cached.lastUpdated = Date.now();

  if (cached.info) {
    const firstHalfAdded = getAnnouncedAddedTime(cached.events, "first_half_injury_time");
    const secondHalfAdded = getAnnouncedAddedTime(cached.events, "second_half_injury_time");
    if (firstHalfAdded > 0) cached.info.firstHalfInjuryTime = firstHalfAdded;
    if (secondHalfAdded > 0) {
      cached.info.secondHalfInjuryTime = secondHalfAdded;
      // Announced board (incl. the sportcast-1104 record) is authoritative — pin it so
      // the unreliable match-info payload can't overwrite it on the next live refresh.
      cached.info.boardSecondHalfAddedTime = secondHalfAdded;
    }
  }

  if (cached.info && hasRedCardBeforeCutoff(cached.events)) {
    cached.info.hasRedCard = true;
  }

  const added = Math.max(0, cached.events.length - before);
  if (added > 0) scheduleDashboardBroadcast();

  return { added, parsed: parsedEvents.length, total: cached.events.length };
}

function markOneWinTrackerTimelineReady(key) {
  const cached = matchCache.get(key);
  if (!cached) return false;
  if (cached.trackerTimelineReady === true) return true;

  cached.trackerTimelineReady = true;
  cached.lastUpdated = Date.now();
  scheduleDashboardBroadcast();
  return true;
}

function getOneWinLiveTrackerUrl(data = {}) {
  const url = data.liveTracker?.url || data.trackerUrl || data.liveTrackerUrl || data.directTrackerUrl || "";
  return /^https?:\/\//i.test(String(url || "")) ? String(url) : "";
}

// The live-tracker URL (source of the sportcast fonId → added-time feed) comes straight from the
// match-info socket / live-list API. No browser/page is involved.
function getCachedOneWinLiveTrackerUrl(key) {
  return getOneWinLiveTrackerUrl(matchCache.get(key)?.info || {}) ||
    getOneWinLiveTrackerUrl(oneWinLiveMatchesCache.get(key) || {});
}

function firstUsableOneWinLink(...values) {
  return values.find(value => value && value !== "not_found") || null;
}

const ONE_WIN_SPORTCAST_API_HOSTS = [
  "https://line-lb61-w.bk6bba-resources.com",
  "https://line-lb54-w.bk6bba-resources.com"
];

const ONE_WIN_SPORTCAST_EVENT_TYPE_META = new Map([
  [1100, { typeHint: "goal", label: "Goal", fields: "team-period-time" }],
  [1101, { typeHint: "corner", label: "Corner", fields: "team-period-time" }],
  [1108, { typeHint: "yellow", label: "Yellow card", fields: "team-period-time" }],
  [11081, { typeHint: "red", label: "Second yellow card", fields: "team-period-time" }],
  [1109, { typeHint: "red", label: "Red card", fields: "team-period-time" }],
  [1235, { typeHint: "red", label: "Second yellow card", fields: "team-period-time" }],
  [1110, { typeHint: "penalty", label: "Penalty", fields: "team-period-time" }],
  [1111, { typeHint: "substitution", label: "Substitution", fields: "team-period-time" }],
  [1154, { typeHint: "penalty_missed", label: "Penalty missed", fields: "team-time-period" }]
]);

function decodeRepeatedly(value) {
  let output = String(value || "");
  for (let i = 0; i < 3; i++) {
    try {
      const decoded = decodeURIComponent(output);
      if (decoded === output) break;
      output = decoded;
    } catch {
      break;
    }
  }
  return output;
}

function extractOneWinTrackerFonId(url) {
  const value = decodeRepeatedly(url);
  const match =
    value.match(/tracker\/get\/(\d+)/i) ||
    value.match(/[?&]eventId=(\d+)/i) ||
    value.match(/[?&]fonid=(\d+)/i) ||
    value.match(/[?&]fonId=(\d+)/i);
  return match ? match[1] : "";
}

function makeOneWinSportcastHeaders() {
  return {
    "accept": "application/json",
    "referer": "https://video-translations.top-parser.com/",
    "origin": "https://video-translations.top-parser.com",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
  };
}

async function fetchOneWinSportcastJson(pathname, timeoutMs = 6000) {
  let lastError = null;

  for (const host of ONE_WIN_SPORTCAST_API_HOSTS) {
    try {
      const response = await fetchOneWinApi(`${host}${pathname}`, {
        method: "GET",
        headers: makeOneWinSportcastHeaders()
      }, timeoutMs);

      if (!response.ok) {
        lastError = new Error(`sportcast ${response.status}`);
        continue;
      }

      return await response.json();
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error("sportcast fetch failed");
}

function normalizeTeamComparable(value) {
  return normalizeText(cleanTeamName(value))
    .replace(/\b(fc|sc|afc|cf|u\d+|w|women|club|city|united)\b/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function oneWinTeamNamesLookSame(a, b) {
  const left = normalizeTeamComparable(a);
  const right = normalizeTeamComparable(b);
  if (!left || !right) return false;
  if (left === right) return true;
  if (left.length >= 6 && right.includes(left)) return true;
  if (right.length >= 6 && left.includes(right)) return true;

  const leftWords = left.split(/\s+/).filter(word => word.length > 3);
  const rightWords = right.split(/\s+/).filter(word => word.length > 3);
  if (leftWords.length === 0 || rightWords.length === 0) return false;
  const hits = leftWords.filter(word => rightWords.includes(word)).length;
  return hits >= Math.min(2, leftWords.length, rightWords.length);
}

function shouldReverseOneWinSportcastTeams(key, actransItem = {}, extraInfo = {}) {
  const cached = matchCache.get(key);
  const home = cached?.info?.home || "";
  const away = cached?.info?.away || "";
  const providerHome = actransItem.hometeam || actransItem.fon_team1 || "";
  const providerAway = actransItem.awayteam || actransItem.fon_team2 || "";

  if (providerHome && providerAway && home && away) {
    if (oneWinTeamNamesLookSame(providerHome, home) && oneWinTeamNamesLookSame(providerAway, away)) return false;
    if (oneWinTeamNamesLookSame(providerHome, away) && oneWinTeamNamesLookSame(providerAway, home)) return true;
  }

  return extraInfo?.teamsReverse === true;
}

function oneWinSportcastTeamSide(teamNo, reverseTeams = false) {
  const team = Number.parseInt(teamNo, 10);
  if (team === 1) return reverseTeams ? "away" : "home";
  if (team === 2) return reverseTeams ? "home" : "away";
  return "";
}

function formatOneWinSportcastMinute(periodValue, secondsValue, options = {}) {
  const period = Number.parseInt(periodValue, 10);
  const seconds = Math.max(0, Number.parseInt(secondsValue, 10) || 0);
  const secondsPerHalf = 45 * 60;

  if (period === 2) {
    const absoluteSecondHalfEnd = secondsPerHalf * 2;
    if (seconds >= absoluteSecondHalfEnd) {
      const added = Math.floor((seconds - absoluteSecondHalfEnd) / 60) + 1;
      return { minute: 90 + added, minuteDisplay: `90+${added}'` };
    }

    if (seconds >= secondsPerHalf) {
      if (options.secondHalfClockMode === "relative") {
        const added = Math.floor((seconds - secondsPerHalf) / 60) + 1;
        return { minute: 90 + added, minuteDisplay: `90+${added}'` };
      }

      const minute = Math.floor(seconds / 60) + 1;
      return { minute, minuteDisplay: `${minute}'` };
    }

    const minute = 45 + Math.floor(seconds / 60) + 1;
    return { minute, minuteDisplay: `${minute}'` };
  }

  if (period === 1 || !Number.isFinite(period)) {
    if (seconds >= secondsPerHalf) {
      const added = Math.floor((seconds - secondsPerHalf) / 60) + 1;
      return { minute: 45 + added, minuteDisplay: `45+${added}'` };
    }
    const minute = Math.floor(seconds / 60) + 1;
    return { minute, minuteDisplay: `${minute}'` };
  }

  const base = period >= 3 ? 90 + (period - 3) * 15 : 0;
  const minute = base + Math.floor(seconds / 60) + 1;
  return { minute, minuteDisplay: `${minute}'` };
}

function inferOneWinSportcastSecondHalfClockMode(feed, periodValue, secondsValue, key) {
  const period = Number.parseInt(periodValue, 10);
  const seconds = Number.parseInt(secondsValue, 10);
  if (period !== 2 || !Number.isFinite(seconds) || seconds < 0) {
    return feed?.secondHalfClockMode || "";
  }

  const secondsPerHalf = 45 * 60;
  if (seconds < secondsPerHalf) {
    feed.secondHalfClockMode = "relative";
    return feed.secondHalfClockMode;
  }

  if (!feed.secondHalfClockMode && seconds < secondsPerHalf * 2) {
    const cachedMin = currentMinuteFromMatchInfo(matchCache.get(key)?.info || {});
    const absoluteMinute = Math.floor(seconds / 60) + 1;
    if (Number.isFinite(cachedMin) && cachedMin < 90 && absoluteMinute <= cachedMin + 3) {
      feed.secondHalfClockMode = "absolute";
    }
  }

  return feed?.secondHalfClockMode || "";
}

function oneWinSportcastEventClock(event, meta) {
  if (meta.fields === "team-time-period") {
    return { team: event.i1, seconds: event.i2, period: event.i3 };
  }

  return { team: event.i1, period: event.i2, seconds: event.i3 };
}

function oneWinSportcastEventToRecord(event, feed, key) {
  const meta = ONE_WIN_SPORTCAST_EVENT_TYPE_META.get(Number(event?.type));
  if (!meta) return null;

  const { team, period, seconds } = oneWinSportcastEventClock(event, meta);
  const secondHalfClockMode = inferOneWinSportcastSecondHalfClockMode(feed, period, seconds, key);
  const { minute, minuteDisplay } = formatOneWinSportcastMinute(period, seconds, { secondHalfClockMode });
  if (!Number.isFinite(minute) || minute < 1 || minute > 120) return null;

  const sideHint = oneWinSportcastTeamSide(team, feed.reverseTeams === true);
  if (!sideHint) return null;

  const cached = matchCache.get(key);
  const sideName = sideHint === "away" ? cached?.info?.away : cached?.info?.home;
  const teamSuffix = sideName ? ` - ${sideName}` : "";

  return {
    text: `${minuteDisplay} ${meta.label}${teamSuffix}`,
    tooltip: "",
    typeHint: meta.typeHint,
    source: "sportcast-api",
    sideHint,
    providerEventId: event.id || null
  };
}

// Sportcast event type 1104 carries the 4th official's ANNOUNCED added time:
//   i1 = minutes added, i2 = half (1 = first, 2 = second).
// It fires at ~45' and ~90' when the board goes up — the real referee decision,
// not a guess. We mirror it onto match.info (drives the live match clock + audit
// labels) and push an injury-time timeline record so it shows on the board and
// feeds getAnnouncedAddedTime(). The board can be revised, so the latest
// announcement per half (highest event id) wins.
function captureOneWinAddedTimeBoard(targetKey, events, feed) {
  const cached = matchCache.get(targetKey);
  if (!cached?.info || !Array.isArray(events)) return;

  const latest = { 1: null, 2: null };
  for (const e of events) {
    if (Number(e?.type) !== 1104) continue;
    const half = Number(e.i2);
    if (half !== 1 && half !== 2) continue;
    const mins = Number.parseInt(e.i1, 10);
    if (!Number.isFinite(mins) || mins < 0 || mins > 15) continue;
    const id = Number.parseInt(e.id, 10) || 0;
    if (!latest[half] || id >= latest[half].id) latest[half] = { mins, id };
  }

  for (const half of [1, 2]) {
    const ann = latest[half];
    if (!ann) continue;
    const field = half === 1 ? "firstHalfInjuryTime" : "secondHalfInjuryTime";
    if (cached.info[field] !== ann.mins) {
      cached.info[field] = ann.mins;
      cached.lastUpdated = Date.now();
      console.log(`[1win BOARD] ${cached.info.home || "?"} vs ${cached.info.away || "?"}: H${half} added time announced +${ann.mins}' (sportcast 1104).`);
    }
    // Pin the authoritative 2nd-half board separately. The live-list refresh
    // (syncOneWinMatchCacheFromLive) rebuilds info from the 1win match-info payload,
    // whose scavenged "injury time" field is unreliable (match-info has no real board)
    // and would otherwise clobber this referee value — the "+4 flips to +1" glitch.
    if (half === 2) cached.info.boardSecondHalfAddedTime = ann.mins;
    // parseOneWinTrackerRecord only accepts 1..15; a "+0" board has no record but
    // still mirrors onto info above.
    if (ann.mins >= 1 && feed?.recordIds) {
      const recordId = `1104:${half}:${ann.id}`;
      if (!feed.recordIds.has(recordId)) {
        feed.recordIds.add(recordId);
        feed.records.push({
          text: `${half === 1 ? "First" : "Second"} half added time: ${ann.mins} min`,
          tooltip: "",
          typeHint: "",
          source: "sportcast-api",
          providerEventId: recordId
        });
      }
    }
  }
}

// Sportcast event timestamps come as "DD.MM.YYYY HH:MM:SS" (provider local time).
// We only ever subtract two of these from the SAME match, so the (unknown) zone
// cancels — the difference is exact. Returns epoch ms, or null if unparseable.
function parseOneWinSportcastRegtime(regtime) {
  const m = String(regtime || "").match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})$/);
  if (!m) return null;
  const [, dd, mo, yyyy, hh, mi, ss] = m;
  const ms = Date.UTC(+yyyy, +mo - 1, +dd, +hh, +mi, +ss);
  return Number.isFinite(ms) ? ms : null;
}

// Sportcast period markers: event 1118 (i1 = period) STARTS a period, event 1102
// (i1 = period) ENDS it. We confirmed 1102 i1=1 fires at the referee's half-time
// whistle, so 1102 with i1 >= 2 is the end of the second half — the tracker's
// "END OF MATCH" overlay. This is the authoritative, low-latency finish signal:
// it lands the instant the ref blows for full time, instead of waiting for 1win's
// status string to flip to FT or for the match to vanish from the live list (the
// source of past false-FT evictions). For a cup match that goes to extra time this
// is the end of REGULATION, which is exactly where our monitoring window closes.
//
// We also use the whistle here to derive the ACTUAL second-half added time played:
// (1102 i1=2 timestamp) - (1118 i1=2 kickoff timestamp) - 45 min. The event
// timestamps are real wall-clock, immune to 1win's drifting running clock (which
// can read 100' while the half is really at 90' — the bug "currentMin - 90" fell
// for). getFinalAddedMinutes then reports max(played, announced board) so the
// audit's "actual" reflects time genuinely played, never below the ref's board.
function captureOneWinEndOfMatch(targetKey, events) {
  if (!Array.isArray(events)) return false;
  const whistle = events.find(e => Number(e?.type) === 1102 && Number(e?.i1) >= 2);
  if (!whistle) return false;

  const cached = matchCache.get(targetKey);
  // Trust the event, but guard against a garbled early marker: a genuine end of the
  // second half never occurs before ~70'. A null/unknown clock does not block it.
  const minute = cached ? getCurrentMinute(cached.info?.time) : null;
  if (Number.isFinite(minute) && minute < 70) return false;

  // Derive actual added time played in the 2nd half from the whistle vs the captured
  // 2nd-half kickoff (1118 i1=2, recorded onto info when it arrived). Cap at 15 — a
  // larger value means we missed the kickoff marker / it leaked extra time, so we
  // drop the derived number and let the announced board stand alone.
  if (cached?.info) {
    const whistleMs = parseOneWinSportcastRegtime(whistle.regtime);
    const kickoffMs = Number(cached.info.secondHalfKickoffMs);
    if (Number.isFinite(whistleMs) && Number.isFinite(kickoffMs) && kickoffMs > 0) {
      const played = Math.floor((whistleMs - kickoffMs) / 60000) - 45;
      if (played >= 0 && played <= 15) cached.info.secondHalfPlayedAddedTime = played;
    }
  }

  const removed = dropTrackedMatchImmediately(targetKey, "Match completed on 1win", cached);
  if (removed) {
    const at = Number.isFinite(minute) ? `${minute}'` : "unknown";
    const played = Number(cached?.info?.secondHalfPlayedAddedTime);
    const board = Number(cached?.info?.secondHalfInjuryTime);
    const detail = [
      Number.isFinite(played) && played >= 0 ? `played +${played}'` : "",
      Number.isFinite(board) && board > 0 ? `board +${board}'` : ""
    ].filter(Boolean).join(", ");
    console.log(`[1win TRACKER] ${cached?.info?.home || "?"} vs ${cached?.info?.away || "?"}: END OF MATCH (sportcast 1102) at ${at}${detail ? ` (${detail})` : ""}.`);
  }
  return removed;
}

// Record the 2nd-half kickoff wall-clock from event 1118 i1=2 so captureOneWinEndOfMatch
// can measure actual added time at the whistle. Latest marker per match wins (a feed
// reset re-sends it harmlessly with the same timestamp).
function captureOneWinSecondHalfKickoff(targetKey, events) {
  if (!Array.isArray(events)) return;
  const cached = matchCache.get(targetKey);
  if (!cached?.info) return;
  for (const e of events) {
    if (Number(e?.type) !== 1118 || Number(e?.i1) !== 2) continue;
    const ms = parseOneWinSportcastRegtime(e.regtime);
    if (Number.isFinite(ms) && ms > 0) cached.info.secondHalfKickoffMs = ms;
  }
}

function getOneWinTimelineApiFeed(key, fonId) {
  let feed = oneWinTimelineApiFeeds.get(key);
  if (!feed || feed.fonId !== fonId) {
    feed = {
      key,
      fonId,
      code: null,
      records: [],
      recordIds: new Set(),
      lastEventId: 0,
      nextPollAt: 0,
      failCount: 0,
      lastGoodAt: 0,
      lastErrorLogAt: 0,
      hasMergedInitialRecords: false,
      reverseTeams: false,
      secondHalfClockMode: "",
      providerHome: "",
      providerAway: ""
    };
    oneWinTimelineApiFeeds.set(key, feed);
  }
  return feed;
}

async function resolveOneWinTimelineApiFeed(target) {
  const feed = getOneWinTimelineApiFeed(target.key, target.fonId);
  if (feed.code) return feed;

  const json = await fetchOneWinSportcastJson(`/ma/sportscast/actrans?fonid=${encodeURIComponent(target.fonId)}&lang=eng`);
  const item = Array.isArray(json.items) ? json.items.find(entry => entry?.code) : null;
  if (!item?.code) throw new Error("sportcast code missing");

  feed.code = Number.parseInt(item.code, 10);
  feed.providerHome = item.hometeam || item.fon_team1 || "";
  feed.providerAway = item.awayteam || item.fon_team2 || "";
  feed.reverseTeams = shouldReverseOneWinSportcastTeams(target.key, item);
  return feed;
}

function buildOneWinTimelineApiTargets() {
  const targets = [];

  for (const tracked of activeAutoMatches) {
    const cached = matchCache.get(tracked.key);
    if (!cached?.info) continue;
    if (cached.info.phase === "FINISHED") continue;

    const currentMin = getCurrentMinute(cached.info.time);
    if (currentMin === null || currentMin < TEMP_MIN_MINUTE || currentMin > 100) continue;

    const liveTrackerUrl =
      cached.info.liveTrackerUrl ||
      oneWinLiveMatchesCache.get(tracked.key)?.liveTrackerUrl ||
      tracked.liveTrackerUrl ||
      "";
    const fonId = extractOneWinTrackerFonId(liveTrackerUrl);
    if (!fonId) continue;

    const timelineReady = cached.trackerTimelineReady === true || cached.hasDetailedEvents === true;
    targets.push({
      key: tracked.key,
      home: tracked.home || cached.info.home,
      away: tracked.away || cached.info.away,
      fonId,
      liveTrackerUrl,
      hasAppeared: tracked.hasAppeared === true,
      needsTimeline: !timelineReady,
      currentMin,
      enteredCheckzoneAt: tracked.enteredCheckzoneAt || tracked.addedAt || 0
    });
  }

  const shown = targets
    .filter(target => target.hasAppeared)
    .sort((a, b) => b.currentMin - a.currentMin);
  const pending = targets
    .filter(target => !target.hasAppeared && target.needsTimeline)
    .sort((a, b) => a.enteredCheckzoneAt - b.enteredCheckzoneAt || b.currentMin - a.currentMin);
  const ready = targets
    .filter(target => !target.hasAppeared && !target.needsTimeline)
    .sort((a, b) => b.currentMin - a.currentMin);

  if (ready.length > 0) {
    const offset = oneWinTimelineApiRotationCursor % ready.length;
    oneWinTimelineApiRotationCursor += 1;
    ready.push(...ready.splice(0, offset));
  }

  return [...shown, ...pending, ...ready].slice(0, ONE_WIN_TIMELINE_API_MAX_MATCHES);
}

async function refreshOneWinTimelineApiTarget(target) {
  const feed = getOneWinTimelineApiFeed(target.key, target.fonId);
  if (feed.polling) return;
  feed.polling = true;

  try {
    await resolveOneWinTimelineApiFeed(target);
    if (!feed.code) throw new Error("sportcast code unresolved");

    const lastId = Number.isFinite(feed.lastEventId) && feed.lastEventId > 0 ? feed.lastEventId : 0;
    const json = await fetchOneWinSportcastJson(`/ma/sportscast/events?code=${encodeURIComponent(feed.code)}&lastid=${encodeURIComponent(lastId)}`, 7000);
    const events = Array.isArray(json.events) ? json.events.slice().sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0)) : [];
    if (json.extraInfo?.teamsReverse === true) {
      feed.reverseTeams = true;
    }

    if (lastId === 0) {
      feed.records = [];
      feed.recordIds = new Set();
      feed.hasMergedInitialRecords = false;
    }

    let highestEventId = lastId;
    let addedRecords = 0;
    for (const event of events) {
      const eventId = Number.parseInt(event?.id, 10);
      if (Number.isFinite(eventId) && eventId > highestEventId) highestEventId = eventId;

      const record = oneWinSportcastEventToRecord(event, feed, target.key);
      if (!record) continue;

      const recordId = String(record.providerEventId || `${event.type}:${event.i1}:${event.i2}:${event.i3}:${event.i4 || ""}`);
      if (feed.recordIds.has(recordId)) continue;

      feed.recordIds.add(recordId);
      feed.records.push(record);
      addedRecords += 1;
    }

    if (highestEventId > 0) feed.lastEventId = highestEventId;

    // Capture the announced added-time board (sportcast event 1104) into match.info
    // and as an injury-time timeline record before the merge below picks it up.
    captureOneWinAddedTimeBoard(target.key, events, feed);

    // Record the 2nd-half kickoff wall-clock (1118 i1=2) so the whistle below can
    // measure ACTUAL added time played, independent of 1win's drifting clock.
    captureOneWinSecondHalfKickoff(target.key, events);

    // The tracker's "END OF MATCH" overlay (sportcast 1102, end of 2nd half) is the
    // authoritative finish signal — finalise and drop the moment it lands. Nothing
    // left to merge for a match that just ended, so stop processing this batch.
    if (captureOneWinEndOfMatch(target.key, events)) {
      feed.failCount = 0;
      feed.lastGoodAt = Date.now();
      feed.nextPollAt = Date.now() + ONE_WIN_TIMELINE_API_POLL_INTERVAL_MS;
      return;
    }

    if (feed.records.length > 240) {
      feed.records = feed.records.slice(-240);
      feed.recordIds = new Set(feed.records.map(record => String(record.providerEventId || `${record.text}:${record.sideHint}:${record.typeHint}`)));
    }

    if (feed.records.length > 0 && (addedRecords > 0 || !feed.hasMergedInitialRecords)) {
      const merged = mergeOneWinTrackerEvents(target.key, feed.records);
      feed.hasMergedInitialRecords = true;
      if (merged.added > 0) {
        console.log(`[1win TIMELINE API] Added ${merged.added} timeline events from provider feed for ${target.home} vs ${target.away}.`);
      }
    }

    feed.failCount = 0;
    feed.lastGoodAt = Date.now();
    const interval = target.hasAppeared
      ? ONE_WIN_TIMELINE_API_POLL_INTERVAL_MS
      : Math.max(ONE_WIN_TIMELINE_API_POLL_INTERVAL_MS, target.needsTimeline ? 2000 : 3500);
    feed.nextPollAt = Date.now() + interval;
  } catch (err) {
    feed.failCount += 1;
    feed.nextPollAt = Date.now() + Math.min(30000, 3000 + feed.failCount * 3000);

    if (!feed.lastErrorLogAt || Date.now() - feed.lastErrorLogAt > 45000) {
      feed.lastErrorLogAt = Date.now();
      console.warn(`[1win TIMELINE API] ${target.home} vs ${target.away}: provider feed failed (${err.message}).`);
    }
  } finally {
    feed.polling = false;
  }
}

async function refreshOneWinTimelineApiFeeds() {
  if (isOneWinTimelineApiRefreshing) return;
  const now = Date.now();
  const targets = buildOneWinTimelineApiTargets()
    .filter(target => {
      const feed = oneWinTimelineApiFeeds.get(target.key);
      return !feed || !feed.nextPollAt || now >= feed.nextPollAt;
    });

  if (targets.length === 0) return;

  isOneWinTimelineApiRefreshing = true;
  try {
    for (let i = 0; i < targets.length; i += ONE_WIN_TIMELINE_API_CONCURRENCY) {
      const chunk = targets.slice(i, i + ONE_WIN_TIMELINE_API_CONCURRENCY);
      await Promise.allSettled(chunk.map(target => refreshOneWinTimelineApiTarget(target)));
    }
  } finally {
    isOneWinTimelineApiRefreshing = false;
  }
}

function makeOneWinApiHeaders() {
  return {
    "accept": "application/json",
    "content-type": "application/json",
    "referer": "https://1wlgk.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "x-external-partner-id": ONE_WIN_API_PARTNER_ID,
    "x-lang": ONE_WIN_API_LANG,
    "x-user-location": ONE_WIN_API_LOCATION
  };
}

async function fetchOneWinApi(url, options = {}, timeoutMs = ONE_WIN_API_FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal
    });
  } finally {
    clearTimeout(timer);
  }
}

// ── Shared 1win market-name classifiers ─────────────────────────────────────
// One source of truth for "which market is this group?", reused by the Next-goal and
// Full-Time-Result parsers AND by the late-match "only these two markets active" check
// (rule 3). Keeping the patterns here prevents the classifiers from drifting apart.
function normalizeOneWinMarketName(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isOneWinNextGoalGroupName(name) {
  if (!name) return false;
  return name.includes("next goal") ||
    name.includes("next team to score") ||
    name.includes("which team scores next") ||
    name.includes("team to score next");
}

function isOneWinFullTimeResultGroupName(name) {
  if (!name) return false;
  if (/half|1st|2nd|first|second|double|no bet|total|handicap|over|under|corner|card|both teams/.test(name)) return false;
  return name.includes("full time result") ||
    name.includes("fulltime result") ||
    name.includes("match result") ||
    name.includes("match winner") ||
    name.includes("match odds") ||
    name.includes("to win the match") ||
    name === "result" ||
    name === "winner" ||
    name === "1x2" ||
    name === "1 x 2" ||
    name === "1 2" ||
    /\b1 ?x ?2\b/.test(name);
}

function isOneWinPenaltyShootoutGroupName(name) {
  if (!name) return false;
  return /penalt|shoot ?out/.test(name);
}

// "To qualify" / "Qualification" markets (cup ties, knockout legs) — like penalty-shootout
// markets these can sit open alongside FTR + No-Goal late in a match without meaning the board
// is still busy, so they are excluded from the "other markets open" count for the same reason.
function isOneWinToQualifyGroupName(name) {
  if (!name) return false;
  return /qualif/.test(name);
}

// Status gate (no freshness): an outcome is open if it is status===1. 1win's odds socket is
// DELTA-ONLY — after the initial snapshot it re-sends an outcome only when its PRICE changes —
// so a quiet leg keeps its last status/cf and is still open even though no recent delta touched
// it. Per-leg freshness therefore must NOT be used to decide whether an individual leg is open
// (it wrongly drops stable legs); freshness lives at the GROUP level instead (see below).
function isOneWinOddStatusOpen(odd) {
  return Number(odd?.status) === 1;
}

// Most recent delta timestamp across a group's OPEN legs (0 if none ever stamped). Any open leg
// moving price refreshes the whole market's liveness — the right granularity for a delta feed
// where individual legs go quiet while the market stays open. Crucially we count only status-open
// legs: a suspend/close delta flips its leg OUT of status 1 while stamping __seenAt, so counting
// closed legs here would let that suspend traffic keep the group "fresh". Since the merge store
// never prunes legs (a leg keeps its last status forever until 1win explicitly flips it), a stale
// never-closed status===1 orphan leg would then ride that freshness and read as an open market —
// the phantom "1 — Total" the Total carrier group (id 6379, flickered longest by 1win) showed when
// nothing was actually tradeable. Stamping only on open legs ties freshness to genuine open-leg
// activity, so a market 1win is winding down ages out instead of zombie-ing.
function oneWinGroupLastSeenAt(group) {
  let max = 0;
  for (const odd of group?.oddsList || []) {
    if (!isOneWinOddStatusOpen(odd)) continue;
    const seenAt = odd?.__seenAt;
    if (typeof seenAt === "number" && seenAt > max) max = seenAt;
  }
  return max;
}

// A market group is active if it has at least one status-open leg AND one of its OPEN legs was
// touched by a delta within MARKET_ODD_FRESH_MS (group-level anti-zombie: a silently-removed
// market — one 1win stopped sending open-leg deltas for — ages out, but a market where only some
// open legs are quiet stays alive). Freshness counts open legs only so suspend/close traffic on a
// leg can't keep the group warm and prop up a stale orphan leg (see oneWinGroupLastSeenAt). A
// group with no stamps yet (pre-stamping snapshot) is treated as fresh so we never penalise the
// very first read.
function isOneWinGroupActive(group, now = Date.now()) {
  const odds = group?.oddsList || [];
  if (!odds.some(isOneWinOddStatusOpen)) return false;
  const lastSeen = oneWinGroupLastSeenAt(group);
  return lastSeen === 0 || (now - lastSeen) < MARKET_ODD_FRESH_MS;
}

// Full-event suspend, derived from the odds socket ALONE (no DOM). 1win flips every leg of a
// suspended event to status 2 ("bets temporarily not accepted") — distinct from status 1 (open)
// and status 0 (closed/settled). The event is suspended when NO group is currently active (no
// fresh status-open leg anywhere) AND at least one leg is explicitly status 2. Requiring a
// status-2 leg (not merely "nothing active") stops a finished/closed board — every leg at status
// 0 — from reading as suspended. The "all groups inactive" gate debounces the per-market suspend
// flicker that happens constantly in play, since a live event keeps FTR open while one market blinks.
function isOneWinEventSuspendedFromGroups(oddsGroups, now = Date.now()) {
  if (!Array.isArray(oddsGroups) || oddsGroups.length === 0) return false;

  // Fast-path: if BOTH Full Time Result and Next-Goal groups are explicitly suspended
  // (all legs status 2, no active status-1 leg), the event is suspended regardless of
  // what other groups (Handicap, Corners, etc.) show. Partial deltas from 1win often flip
  // FTR + Next-Goal to status 2 without touching the remaining groups, which then retain
  // stale status-1 legs — requiring all groups to be inactive would delay suspension
  // detection by up to MARKET_ODD_FRESH_MS (45s). The two key markets are the canary.
  let ftrSuspended = false, ngSuspended = false;
  let anyActive = false;
  let anyStatus2 = false;

  for (const group of oddsGroups) {
    const name = normalizeOneWinMarketName(group?.name);
    const isFtr = isOneWinFullTimeResultGroupName(name);
    const isNg  = isOneWinNextGoalGroupName(name);

    let hasStatus1 = false, hasStatus2 = false;
    for (const odd of group?.oddsList || []) {
      const s = Number(odd?.status);
      if (s === 1) hasStatus1 = true;
      if (s === 2) hasStatus2 = true;
    }
    if (hasStatus2) anyStatus2 = true;

    if (isFtr && !hasStatus1 && hasStatus2) ftrSuspended = true;
    if (isNg  && !hasStatus1 && hasStatus2) ngSuspended  = true;

    if (isOneWinGroupActive(group, now)) anyActive = true;
  }

  // Both key markets explicitly suspended → event is suspended (even if other groups
  // still look active from a stale delta).
  if (ftrSuspended && ngSuspended) return true;

  // Otherwise fall back to the original rule: ALL groups inactive + at least one
  // status-2 leg anywhere (handles the case where 1win sends a full-board sweep).
  if (!anyActive && anyStatus2) return true;

  return false;
}

// Is this an "other" market by NAME — i.e. neither FTR, Next-goal, penalty/shootout, nor
// To-qualify? This is the name filter only; liveness is applied separately by the two callers
// (each with its own rule).
function isOneWinOtherMarketGroupByName(group) {
  const name = normalizeOneWinMarketName(group?.name);
  if (isOneWinFullTimeResultGroupName(name)) return false;
  if (isOneWinNextGoalGroupName(name)) return false;
  if (isOneWinPenaltyShootoutGroupName(name)) return false;
  if (isOneWinToQualifyGroupName(name)) return false;
  return true;
}

// Unified "other"-market liveness — the SINGLE source of truth for the entry signal and the
// dashboard "markets open" count/tooltip. A market counts as live iff it has
// at least one status-open leg AND the GROUP re-priced within MARKET_ODD_FRESH_MS (group-level,
// never per-leg — see isOneWinGroupActive). This is what makes the count track 1win in real time
// without ever freezing: an explicit suspend takes every leg out of "open" and drops it instantly,
// while a market 1win retires SILENTLY (stops sending any delta, never sends a close — exactly how
// corner markets vanish ~90') ages out of the count instead of lingering as a zombie. The earlier
// "OTHER MARKETS OPEN: 0 while 3 visible" bug was the old PER-LEG ageing that wrongly dropped quiet
// legs of a still-open market; the group-level gate (2026-06-16) fixed that, so the display path no
// longer needs its own gate-less rule — both callers now share this one.
function isOneWinOtherActiveMarketGroup(group, now = Date.now()) {
  if (!isOneWinGroupActive(group, now)) return false;
  return isOneWinOtherMarketGroupByName(group);
}

// The distinct OPEN markets OTHER than FTR / Next-goal / penalty-shootout, as display names.
// Single source of truth for both the dashboard "markets remaining" counter and the hover
// tooltip listing exactly which markets are still open. The original group name (collapsed
// whitespace, trimmed) is kept for display; de-dupe by group id (falling back to its normalized
// name) so the same market split across odds-delta renders isn't listed twice.
function listOtherActiveOneWinMarketNames(oddsGroups, now = Date.now()) {
  if (!Array.isArray(oddsGroups)) return [];
  const seen = new Set();
  const names = [];
  for (const group of oddsGroups) {
    if (!isOneWinOtherActiveMarketGroup(group, now)) continue;
    const dedupeKey = String(group?.id || "") || normalizeOneWinMarketName(group?.name);
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    const display = String(group?.name || "").replace(/\s+/g, " ").trim();
    names.push(display || "Market");
  }
  return names;
}

// The line/handicap value carried on a leg (e.g. the 2.5 in "Total Over 2.5", the -1 in a
// handicap). 1win stashes it under a few different keys depending on the market, so probe them
// in order. Returns a trimmed string or "" when the leg has no line (e.g. Both-Teams-Score Yes/No).
function oneWinOddLineValue(odd = {}) {
  const raw = odd?.vars?.v1 ?? odd?.value ?? odd?.line ?? odd?.param ?? "";
  const s = String(raw).replace(/\s+/g, " ").trim();
  return s;
}

const ONE_WIN_OTHER_MARKET_LEG_CAP = 20; // bound a pathological Total board (40+ legs) per market

// Every OTHER market (not FTR / Next-goal / penalty / qualify) with its live legs, for the card's
// compact "all markets" list. Each entry is { id, name, legs:[{ outcome, line, odds }], suspended }:
//   • a market is INCLUDED while it is group-active (open, repriced within the fresh window) OR
//     explicitly suspended (all legs flipped to status-2). A silently-retired market — no open leg
//     and no status-2, or one that aged past the fresh window — is dropped, giving instant
//     odds-driven removal without waiting on a separate timer.
//   • suspended === true means the market is held (status-2 sweep) but not gone; the card shows it
//     muted rather than yanking the row, so a 1win blip doesn't make the list jump.
// Multi-line markets (Total, Handicap) keep every open line as one labelled leg, so the frontend
// can render them as compact line-chips instead of a block per line. De-duped by group id; legs
// de-duped by outcome+line keeping the best (lowest) price across re-render deltas.
function parseOneWinSocketOtherMarketsDetailed(oddsGroups, now = Date.now()) {
  if (!Array.isArray(oddsGroups)) return [];
  const seen = new Set();
  const out = [];

  for (const group of oddsGroups) {
    if (!isOneWinOtherMarketGroupByName(group)) continue;

    const legMap = new Map();
    for (const odd of group?.oddsList || []) {
      const status = Number(odd?.status);
      if (status !== 1) continue;
      const odds = Number.parseFloat(odd?.cf);
      if (!Number.isFinite(odds)) continue;
      const line = oneWinOddLineValue(odd);
      const outcome = String(odd?.outcome || odd?.name || "").replace(/\s+/g, " ").trim() || "—";
      const legKey = `${outcome.toLowerCase()}|${line}`;
      const prev = legMap.get(legKey);
      if (!prev || odds < prev.odds) legMap.set(legKey, { outcome, line, odds });
    }

    const active = isOneWinGroupActive(group, now);
    // Instant removal: any market that is not currently live (suspended status-2 sweep, silently
    // retired, or aged past the fresh window) is dropped immediately. We deliberately do NOT keep a
    // suspended market with a "SUSP" badge — a lingering row that sits for seconds before 1win clears
    // it reads as stale; yanking it at once is the wanted behaviour.
    if (!active) continue;

    const dedupeKey = String(group?.id || "") || normalizeOneWinMarketName(group?.name);
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    const legs = Array.from(legMap.values())
      .sort((a, b) => {
        const la = Number.parseFloat(a.line), lb = Number.parseFloat(b.line);
        if (Number.isFinite(la) && Number.isFinite(lb) && la !== lb) return la - lb;
        return a.outcome.localeCompare(b.outcome);
      })
      .slice(0, ONE_WIN_OTHER_MARKET_LEG_CAP);

    out.push({
      id: dedupeKey,
      name: String(group?.name || "").replace(/\s+/g, " ").trim() || "Market",
      legs,
      suspended: false   // suspended markets are dropped above, never surfaced — kept for payload shape
    });
  }

  return out;
}

// One-time-per-name log so we can confirm/tune which 1win group actually carries the
// "Next goal" market against live data without spamming the console.
const loggedNextGoalGroupNames = new Set();

// Parse the "Next goal" market and surface ONLY the "No Goal" outcome (the user tracks
// "no further goal" exclusively — team-specific next-scorer outcomes are intentionally
// dropped). 1win sends odds deltas on the same socket as the Total market, so this reads
// the very same merged group store; no extra subscription is needed.
function parseOneWinSocketNextGoalOddsGroups(oddsGroups) {
  if (!Array.isArray(oddsGroups)) return [];

  const normalize = value => String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, " ")
    .trim();

  // The board reads "Next goal" with outcomes like "No Goal", "<Home>", "<Away>".
  // Match defensively by name across the common 1win phrasings (shared classifier).
  const isNextGoalGroup = group => isOneWinNextGoalGroupName(normalize(group?.name));

  const isNoGoalOutcome = odd => {
    const outcome = normalize(odd?.outcome);
    const name = normalize(odd?.name);
    // 1win labels the "no further goal" leg "No Goal" (sometimes suffixed "No Goal 2", or "None").
    return /no goal/.test(outcome) || /no goal/.test(name) || outcome === "none" || name === "none";
  };

  const now = Date.now();
  const out = [];
  let sawGroup = false;
  for (const group of oddsGroups) {
    if (!isNextGoalGroup(group)) continue;
    sawGroup = true;
    // Group-level freshness: only read from a Next-goal market still receiving deltas. Within a
    // live market every status-open leg counts, even one that's been quiet (no per-leg ageing).
    if (!isOneWinGroupActive(group, now)) continue;
    for (const odd of group?.oddsList || []) {
      if (!isOneWinOddStatusOpen(odd)) continue;
      if (!isNoGoalOutcome(odd)) continue;
      const odds = Number.parseFloat(odd?.cf);
      if (!Number.isFinite(odds)) continue;
      out.push({ outcome: "No Goal", odds });
    }
  }

  // Diagnostic: if no "next goal" group matched, log the group names we DID see once each
  // so the name matcher can be tuned against the real live feed.
  if (!sawGroup) {
    for (const group of oddsGroups) {
      const name = normalize(group?.name);
      if (name && /goal|score|scorer/.test(name) && !loggedNextGoalGroupNames.has(name)) {
        loggedNextGoalGroupNames.add(name);
        console.log(`[1win NEXT-GOAL PROBE] Unmatched goal/score market group name: "${group?.name}"`);
      }
    }
  }

  // Keep only the best (lowest) price if 1win duplicates the No Goal leg across renders.
  if (out.length === 0) return [];
  const best = out.reduce((a, b) => (b.odds < a.odds ? b : a));
  return [best];
}

// One-time-per-name log so we can confirm/tune which 1win group actually carries the
// "Full Time Result" (1/X/2) market against live data without spamming the console.
const loggedFullTimeResultGroupNames = new Set();

// Parse the "Full Time Result" (match winner, 1/X/2) market and surface all three legs
// ordered Home / Draw / Away. This reads the same merged group store as the Next-goal and
// Total markets — no extra subscription is needed IF the base group is in the feed (it may
// not be: the socket subscribes with isBaseOddsGroups:false and 1x2 is usually the base
// market — the probe log below confirms this against live data).
function parseOneWinSocketFullTimeResultOddsGroups(oddsGroups) {
  if (!Array.isArray(oddsGroups)) return [];

  const normalize = value => String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, " ")
    .trim();

  // The board reads "Full Time Result" / "1x2" / "Match Result" with outcomes 1 / X / 2.
  // Defensive name match with look-alike exclusions lives in the shared classifier.
  const isFullTimeResultGroup = group => isOneWinFullTimeResultGroupName(normalize(group?.name));

  // Classify a leg as home (1) / draw (X) / away (2) from its outcome/name code.
  const classifyLeg = odd => {
    const code = normalize(odd?.outcome) || normalize(odd?.name);
    if (code === "w1" || code === "1" || code === "home" || code === "p1") return "home";
    if (code === "x" || code === "draw" || code === "tie") return "Draw";
    if (code === "w2" || code === "2" || code === "away" || code === "p2") return "away";
    return null;
  };

  const now = Date.now();
  const legs = {};
  let sawGroup = false;
  for (const group of oddsGroups) {
    if (!isFullTimeResultGroup(group)) continue;
    sawGroup = true;
    // Group-level freshness: read the whole 1/X/2 market only while it is still receiving
    // deltas, then surface ALL status-open legs at their last-known price. A delta usually
    // touches just one leg (e.g. the Draw), so per-leg ageing would collapse the block to that
    // single price — which is exactly the bug being fixed.
    if (!isOneWinGroupActive(group, now)) continue;
    for (const odd of group?.oddsList || []) {
      if (!isOneWinOddStatusOpen(odd)) continue;
      const slot = classifyLeg(odd);
      if (!slot) continue;
      const odds = Number.parseFloat(odd?.cf);
      if (!Number.isFinite(odds)) continue;
      // Keep the best (lowest) price if a leg is duplicated across renders.
      if (!legs[slot] || odds < legs[slot]) legs[slot] = odds;
    }
  }

  // Diagnostic: if no FTR group matched, log the candidate result/winner group names we DID
  // see once each so the matcher (and the base-group subscription question) can be confirmed.
  if (!sawGroup) {
    for (const group of oddsGroups) {
      const name = normalize(group?.name);
      if (name && /result|winner|1.?2|match/.test(name) && !loggedFullTimeResultGroupNames.has(name)) {
        loggedFullTimeResultGroupNames.add(name);
        console.log(`[1win FTR PROBE] Unmatched result/winner market group name: "${group?.name}"`);
      }
    }
  }

  // Emit in fixed 1 / X / 2 order; only the legs that are currently active.
  const out = [];
  if (legs.home != null) out.push({ outcome: "home", odds: legs.home });
  if (legs.Draw != null) out.push({ outcome: "Draw", odds: legs.Draw });
  if (legs.away != null) out.push({ outcome: "away", odds: legs.away });
  return out;
}

function cloneOneWinOddsGroups(groups) {
  return JSON.parse(JSON.stringify(Array.isArray(groups) ? groups : []));
}

function getOneWinOddsGroupKey(group = {}) {
  return String(group.id ?? group.groupId ?? group.oddsGroupId ?? group.marketId ?? group.name ?? "");
}

function getOneWinOddKey(odd = {}) {
  return String(
    odd.id ??
    odd.oddId ??
    odd.outcomeId ??
    `${odd.outcome || odd.name || ""}:${odd.vars?.v1 ?? odd.value ?? odd.line ?? odd.param ?? ""}`
  );
}

function normalizeOneWinOddsPacketGroups(data = {}) {
  const groups =
    data.oddsGroups ||
    data.groups ||
    (data.oddsGroup ? [data.oddsGroup] : null) ||
    (data.group ? [data.group] : null) ||
    (data.name && data.oddsList ? [data] : null);
  return Array.isArray(groups) ? groups : [];
}

function normalizeOneWinOddsPacketOdds(data = {}) {
  const odds =
    data.oddsList ||
    data.odds ||
    data.outcomes ||
    (data.odd ? [data.odd] : null) ||
    (data.outcome || data.cf || data.status ? [data] : null);
  return Array.isArray(odds) ? odds : [];
}

function mergeOneWinOddsGroups(previousGroups, data = {}) {
  const seenAt = Date.now();
  const stampOddsList = list => {
    if (!Array.isArray(list)) return;
    for (const odd of list) {
      if (odd && typeof odd === "object") odd.__seenAt = seenAt;
    }
  };
  const markGroupPresent = group => {
    if (!group || typeof group !== "object") return;
    group.__snapshotMissingCount = 0;
    delete group.__snapshotMissingAt;
  };

  const groups = cloneOneWinOddsGroups(previousGroups);
  const groupMap = new Map();
  for (const group of groups) {
    const key = getOneWinOddsGroupKey(group);
    if (key) groupMap.set(key, group);
  }

  for (const incomingGroup of normalizeOneWinOddsPacketGroups(data)) {
    const key = getOneWinOddsGroupKey(incomingGroup);
    const existingGroup = key ? groupMap.get(key) : null;
    if (!existingGroup) {
      const cloned = cloneOneWinOddsGroups([incomingGroup])[0];
      stampOddsList(cloned.oddsList);
      markGroupPresent(cloned);
      groups.push(cloned);
      if (key) groupMap.set(key, cloned);
      continue;
    }

    const incomingOdds = normalizeOneWinOddsPacketOdds(incomingGroup);
    const existingOdds = Array.isArray(existingGroup.oddsList) ? existingGroup.oddsList : [];
    const oddsMap = new Map(existingOdds.map(odd => [getOneWinOddKey(odd), odd]));

    Object.assign(existingGroup, incomingGroup);
    existingGroup.oddsList = existingOdds;
    markGroupPresent(existingGroup);

    for (const incomingOdd of incomingOdds) {
      const oddKey = getOneWinOddKey(incomingOdd);
      const existingOdd = oddsMap.get(oddKey);
      if (existingOdd) {
        Object.assign(existingOdd, incomingOdd);
        existingOdd.__seenAt = seenAt;
      } else {
        existingOdds.push({ ...incomingOdd, __seenAt: seenAt });
      }
    }
  }

  const looseOdds = normalizeOneWinOddsPacketGroups(data).length === 0 ? normalizeOneWinOddsPacketOdds(data) : [];
  for (const incomingOdd of looseOdds) {
    const groupKey = String(incomingOdd.groupId ?? incomingOdd.oddsGroupId ?? incomingOdd.marketId ?? data.groupId ?? data.oddsGroupId ?? "");
    let targetGroup = groupKey ? groupMap.get(groupKey) : null;

    if (!targetGroup && (groupKey === "6379" || normalizeText(data.name) === "total")) {
      targetGroup = {
        id: groupKey || "6379",
        name: data.name || "Total",
        renderType: data.renderType || "total-2",
        oddsList: []
      };
      groups.push(targetGroup);
      if (groupKey) groupMap.set(groupKey, targetGroup);
    }

    if (!targetGroup) {
      for (const group of groups) {
        const existingOdds = Array.isArray(group.oddsList) ? group.oddsList : [];
        if (existingOdds.some(odd => getOneWinOddKey(odd) === getOneWinOddKey(incomingOdd))) {
          targetGroup = group;
          break;
        }
      }
    }

    if (!targetGroup) continue;
    if (!Array.isArray(targetGroup.oddsList)) targetGroup.oddsList = [];
    markGroupPresent(targetGroup);
    const existingOdd = targetGroup.oddsList.find(odd => getOneWinOddKey(odd) === getOneWinOddKey(incomingOdd));
    if (existingOdd) {
      Object.assign(existingOdd, incomingOdd);
      existingOdd.__seenAt = seenAt;
    } else {
      targetGroup.oddsList.push({ ...incomingOdd, __seenAt: seenAt });
    }
  }

  return groups;
}

function mergeOneWinOddsSnapshotGroups(previousGroups, snapshotGroups, now = Date.now()) {
  const incomingGroups = Array.isArray(snapshotGroups) ? snapshotGroups : [];
  const incomingKeys = new Set(
    incomingGroups
      .map(group => getOneWinOddsGroupKey(group))
      .filter(Boolean)
  );

  const merged = mergeOneWinOddsGroups(previousGroups, { oddsGroups: incomingGroups });
  const kept = [];

  for (const group of merged) {
    const key = getOneWinOddsGroupKey(group);
    if (!key) {
      kept.push(group);
      continue;
    }

    if (incomingKeys.has(key)) {
      group.__snapshotSeenAt = now;
      group.__snapshotMissingCount = 0;
      delete group.__snapshotMissingAt;
      kept.push(group);
      continue;
    }

    // Group is absent from this board. An EMPTY/failed board carries no signal (the gateway
    // returned nothing this cycle), so keep the group untouched and wait for the next board —
    // never let a dud board wipe the whole market state.
    if (incomingKeys.size === 0) {
      kept.push(group);
      continue;
    }

    // A NON-EMPTY board that omits the group means 1win genuinely dropped it. Remove it on the
    // FIRST such board (≈ one snapshot interval, ~realtime) so a silently-retired FTR/market
    // disappears from the card almost immediately rather than lingering for several boards.
    // (Explicit status-2/0 closes are already instant via the live group read; this only governs
    // the silent-removal case, where the full board is the only available signal.) The group is
    // simply not carried into `kept`. Stamp the miss for diagnostics.
    group.__snapshotMissingCount = (Number.parseInt(group.__snapshotMissingCount, 10) || 0) + 1;
    group.__snapshotMissingAt = now;
  }

  return kept;
}

function nextGoalOddsSignature(odds) {
  return (odds || [])
    .map(item => `${item.outcome}:${Number.parseFloat(item.odds).toFixed(3)}`)
    .join("|");
}

// Build a tracked-market entry ({ odds, isMarketActive, lastGoodAt }) from the latest parsed odds
// for FTR or No-Goal. Retains the last-known odds through a suspend so the displayed price doesn't
// blink to a placeholder during a blip; the read-side grace (isOneWinMarketActiveWithGrace and the
// display grace) decides when the market is truly gone and the retained odds stop being shown.
function makeOneWinTrackedMarketEntry(previous = {}, odds = [], now = Date.now()) {
  const nextOdds = Array.isArray(odds) ? odds : [];
  const previousOdds = Array.isArray(previous.odds) ? previous.odds : [];
  const isMarketActive = nextOdds.length > 0;
  return {
    odds: isMarketActive ? nextOdds : previousOdds,
    isMarketActive,
    lastGoodAt: isMarketActive ? now : (previous.lastGoodAt || null)
  };
}

// Every distinct OPEN market on the fixture, as display names — the complete board the 1win API
// exposes (Full Time Result + No-Goal + everything else). De-duped by group id (falling back to
// the normalized name). Drives the dashboard's real-time reactivity to ANY market opening/closing.
function listActiveOneWinMarketNames(oddsGroups, now = Date.now()) {
  if (!Array.isArray(oddsGroups)) return [];
  const seen = new Set();
  const names = [];
  for (const group of oddsGroups) {
    if (!isOneWinGroupActive(group, now)) continue;
    const dedupeKey = String(group?.id || "") || normalizeOneWinMarketName(group?.name);
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    const display = String(group?.name || "").replace(/\s+/g, " ").trim();
    names.push(display || "Market");
  }
  return names;
}

function listOtherOneWinMarketNamesByName(names) {
  if (!Array.isArray(names)) return [];
  const seen = new Set();
  const out = [];
  for (const raw of names) {
    const display = String(raw || "").replace(/\s+/g, " ").trim();
    if (!display) continue;
    const norm = normalizeOneWinMarketName(display);
    if (!norm || seen.has(norm)) continue;
    seen.add(norm);
    if (!isOneWinOtherMarketGroupByName({ name: display })) continue;
    out.push(display);
  }
  return out;
}

// Display-relevant fingerprint of a match's market state: changes exactly when something the
// dashboard shows would change — FTR price/availability, No-Goal price/availability, the list of
// other open markets, or the full board of available markets. A delta that moves nothing visible
// produces the same signature and skips the broadcast.
// Fingerprint the detailed other-markets list: every market name + its legs' prices + suspend
// flag, so a price move on ANY tracked market changes the signature and triggers a broadcast.
function otherMarketsDetailedSignature(list) {
  return (list || [])
    .map(m => `${m.id}:${m.suspended ? "s" : "o"}:` +
      (m.legs || []).map(l => `${l.outcome}@${l.line}=${Number.parseFloat(l.odds).toFixed(3)}`).join(","))
    .join("|");
}

function oneWinMarketStateSignature(state) {
  if (!state) return "";
  const ftr = state.fullTimeResult || {};
  const ng = state.nextGoal || {};
  return [
    ftr.isMarketActive === true ? "ftr:on" : "ftr:off",
    nextGoalOddsSignature(ftr.odds || []),
    ng.isMarketActive === true ? "ng:on" : "ng:off",
    nextGoalOddsSignature(ng.odds || []),
    `other:${otherMarketsDetailedSignature(state.otherMarketsDetailed)}`,
    `all:${(state.availableMarketsList || []).join("|")}`,
    `susp:${state.suspendedAt ? "1" : "0"}`
  ].join(";");
}

// SINGLE write path for the 1win odds feed (the one match-odds socket is the only source). Given a
// fixture's freshly-merged odds groups, derive every market we care about in ONE place and store it
// as the canonical per-match state:
//   • Full Time Result (1/X/2) and No-Goal odds — the only two surfaced with prices,
//   • the list of OTHER open markets — hidden, surfaced only as the hover text, and
//   • the full board of available markets — keeps the dashboard reacting to any market change.
// Retains last-known FTR/No-Goal odds through a suspend (makeOneWinTrackedMarketEntry) and only ever
// stamps otherMarketsLastGoodAt on activity (the read side ages it out via the grace window, so a
// brief suspend can't prematurely fire the bet signal). Broadcasts only when the display-relevant
// signature changes.
function applyOneWinSocketMarketUpdate({ key, matchId, groups }) {
  if (!key) return;

  const now = Date.now();
  const previous = oneWinMarketStateByKey.get(key) || {};
  const oddsGroups = Array.isArray(groups) ? groups : [];

  const fullTimeOdds = parseOneWinSocketFullTimeResultOddsGroups(oddsGroups);
  const nextGoalOdds = parseOneWinSocketNextGoalOddsGroups(oddsGroups);
  const otherMarketsList = listOtherActiveOneWinMarketNames(oddsGroups, now);
  const otherMarketsDetailed = parseOneWinSocketOtherMarketsDetailed(oddsGroups, now);
  const availableMarketsList = listActiveOneWinMarketNames(oddsGroups, now);

  const nextState = {
    key,
    matchId: String(matchId || previous.matchId || ""),
    groups: oddsGroups,
    connectedAt: previous.connectedAt || now,
    updatedAt: now,
    isFinished: matchCache.get(key)?.info?.phase === "FINISHED",
    fullTimeResult: makeOneWinTrackedMarketEntry(previous.fullTimeResult, fullTimeOdds, now),
    nextGoal: makeOneWinTrackedMarketEntry(previous.nextGoal, nextGoalOdds, now),
    otherMarketsLastGoodAt: otherMarketsList.length > 0 ? now : (previous.otherMarketsLastGoodAt || null),
    otherMarketsList,
    otherMarketsDetailed,
    availableMarketsList,
    isAnyMarketActive: availableMarketsList.length > 0,
    // Full-event suspend is derived from the socket itself (all legs flip to status 2). Refresh the
    // timestamp every suspended tick so the read-side grace bridges gaps between deltas; clear it the
    // moment any market is active again. No DOM scrape is involved.
    suspendedAt: isOneWinEventSuspendedFromGroups(oddsGroups, now) ? now : null
  };

  oneWinMarketStateByKey.set(key, nextState);

  // Odds log: capture every FTR/NG change for matches at 90'+.
  const _oddsLogCached = matchCache.get(key);
  if (_oddsLogCached) maybeLogOdds(key, nextState, _oddsLogCached, now);

  if (oneWinMarketStateSignature(previous) !== oneWinMarketStateSignature(nextState)) {
    scheduleDashboardBroadcast(50);
  }
}

// A full-event suspend ("bets on the event are temporarily not accepted") is detected via the odds
// socket (status-2 sweep) AND via the periodic monitor tick (testmonEvaluate checks groups directly
// so a silent socket during a real suspension is caught within one loop). applyOneWinSocketMarketUpdate
// stamps suspendedAt on a delta, and tickTestMonitor stamps it when the groups-based check fires — the
// read side suppresses ghost markets and holds the bet signal without any DOM scrape.
// A market counts as active if a delta showed it active this tick OR it was last seen active
// within the grace window (debounces 1win's suspend→resume flicker). Both Next-goal and FTR
// caches carry { isMarketActive, lastGoodAt } so this works for either.
function isOneWinMarketActiveWithGrace(entry, now = Date.now()) {
  if (!entry) return false;
  if (entry.isMarketActive === true) return true;
  return !!(entry.lastGoodAt && now - entry.lastGoodAt < MARKET_ACTIVE_GRACE_MS);
}

function closeOneWinOddsSocket() {
  const socket = oneWinOddsSocket;
  oneWinOddsSocket = null;
  if (!socket) return;
  socket.onclose = null;
  socket.onerror = null;
  socket.onmessage = null;
  try {
    if (socket.readyState <= 1) socket.close();
  } catch {
    // Ignore socket close races.
  }
}

function buildOneWinOddsSocketTargets() {
  const targets = new Map();

  for (const tracked of activeAutoMatches) {
    const cached = matchCache.get(tracked.key);
    if (!cached?.info) continue;
    if (cached.info.phase === "FINISHED") continue;

    const currentMin = getCurrentMinute(cached.info.time);
    if (currentMin === null || currentMin < TEMP_MIN_MINUTE || currentMin >= 99) continue;

    const matchId = Number.parseInt(cached.info.matchId || tracked.matchId, 10);
    if (!Number.isFinite(matchId) || matchId <= 0) continue;

    targets.set(String(matchId), {
      key: tracked.key,
      home: tracked.home || cached.info.home,
      away: tracked.away || cached.info.away
    });
  }

  return targets;
}

function connectOneWinOddsSocket(targets, signature) {
  if (!signature || typeof WebSocket !== "function") return;
  if (Date.now() < oneWinOddsSocketReconnectAt) return;

  const ids = Array.from(targets.keys()).map(id => Number.parseInt(id, 10));
  const socketUrl = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(ONE_WIN_API_LANG)}&externalPartnerId=${encodeURIComponent(ONE_WIN_API_PARTNER_ID)}&EIO=4&transport=websocket`;

  let socket;
  try {
    socket = new WebSocket(socketUrl, {
      headers: {
        "origin": "https://1wlgk.com",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
      }
    });
  } catch (err) {
    oneWinOddsSocketReconnectAt = Date.now() + 5000;
    console.error(`[1win ODDS SOCKET] Connect failed: ${err.message}`);
    return;
  }

  oneWinOddsSocket = socket;
  oneWinOddsSocketSignature = signature;

  socket.onmessage = event => {
    const message = String(event.data || "");
    if (message === "2") {
      try { socket.send("3"); } catch {}
      return;
    }

    if (message.startsWith("0")) {
      try { socket.send("40"); } catch {}
      return;
    }

    if (message.startsWith("40")) {
      try {
        socket.send(`42["subscribe",{"messageType":"subscribe-match-odds","data":{"matchIds":${JSON.stringify(ids)},"isBaseOddsGroups":false}}]`);
        console.log(`[1win ODDS SOCKET] Subscribed to ${ids.length} active match odds feeds.`);
      } catch {
        closeOneWinOddsSocket();
      }
      return;
    }

    if (!message.startsWith("42")) return;

    try {
      const packet = JSON.parse(message.slice(2));
      const payload = packet?.[1] || {};
      const messageType = String(payload.messageType || "");
      if (!messageType.includes("match-odds")) return;

      const updates = Array.isArray(payload.data) ? payload.data : [payload.data || {}];
      for (const data of updates) {
        const firstOdd = normalizeOneWinOddsPacketOdds(data)[0] || {};
        const matchId = String(data.matchId || data.id || data.match?.id || firstOdd.matchId || firstOdd.eventId || "");
        const target = targets.get(matchId);
        if (!target) continue;

        // Merge this delta into the fixture's running groups (the canonical per-key state holds
        // them), then hand off to the single write path that derives FTR, No-Goal, the other-market
        // list and the full board in one place and broadcasts if anything visible changed.
        const previousGroups = oneWinMarketStateByKey.get(target.key)?.groups || [];
        const oddsGroups = mergeOneWinOddsGroups(previousGroups, data);
        if (oddsGroups.length === 0) continue;

        applyOneWinSocketMarketUpdate({ key: target.key, matchId, groups: oddsGroups });
      }
    } catch {
      // Ignore non-JSON socket.io packets.
    }
  };

  socket.onerror = () => {
    oneWinOddsSocketReconnectAt = Date.now() + 5000;
    closeOneWinOddsSocket();
  };

  socket.onclose = () => {
    if (oneWinOddsSocket === socket) {
      oneWinOddsSocket = null;
      oneWinOddsSocketReconnectAt = Date.now() + 5000;
    }
  };
}

function refreshOneWinOddsSocketSubscriptions() {
  const targets = buildOneWinOddsSocketTargets();
  const signature = Array.from(targets.keys()).sort((a, b) => Number(a) - Number(b)).join(",");
  // NOTE: we deliberately do NOT evict oneWinMarketStateByKey here. State eviction is owned by
  // pruneRuntimeMemory / blacklistMatch / refreshOneWinMatchCache (keyed on the match leaving the
  // cache or the tracked set). Dropping it on every subscription change would wipe a still-tracked
  // fixture's FTR/No-Goal odds the moment it falls outside the socket window (e.g. deep stoppage at
  // >=99'), where the display should instead ride the last-known price out via the display grace.

  if (!signature) {
    oneWinOddsSocketSignature = "";
    closeOneWinOddsSocket();
    return;
  }

  const shouldReconnect =
    !oneWinOddsSocket ||
    oneWinOddsSocket.readyState > 1 ||
    oneWinOddsSocketSignature !== signature;

  if (!shouldReconnect) return;

  closeOneWinOddsSocket();
  connectOneWinOddsSocket(targets, signature);
}

function closeOneWinOddsSnapshotSocket() {
  const socket = oneWinOddsSnapshotSocket;
  oneWinOddsSnapshotSocket = null;
  oneWinOddsSnapshotReady = false;
  oneWinOddsSnapshotCollecting = false;
  if (oneWinOddsSnapshotCollectTimer) {
    clearTimeout(oneWinOddsSnapshotCollectTimer);
    oneWinOddsSnapshotCollectTimer = null;
  }
  if (!socket) return;
  socket.onclose = null;
  socket.onerror = null;
  socket.onmessage = null;
  try {
    if (socket.readyState <= 1) socket.close();
  } catch {
    // Ignore socket close races.
  }
}

function oneWinOddsSnapshotBackoffMs() {
  const exp = Math.min(oneWinOddsSnapshotFailures, 4);
  return Math.min(30000, 3000 * (2 ** exp));
}

// Keep ONE long-lived auditor socket open instead of churning a fresh connection per cycle:
// re-sending the subscribe frame on a held socket makes the gateway re-push the full board
// snapshot, which is what we need to confirm silent removals — without ~30 handshakes/min from
// a single IP (a connection-rate pattern that looks like abuse). Opens on demand, backs off on
// failure, and self-heals via a forced reconnect if a re-subscribe ever yields no board.
function ensureOneWinOddsSnapshotSocket() {
  if (!ONE_WIN_ODDS_SNAPSHOT_ENABLED || isShuttingDown || typeof WebSocket !== "function") return;
  if (oneWinOddsSnapshotSocket && oneWinOddsSnapshotSocket.readyState <= 1) return;
  if (Date.now() < oneWinOddsSnapshotReconnectAt) return;

  const socketUrl = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(ONE_WIN_API_LANG)}&externalPartnerId=${encodeURIComponent(ONE_WIN_API_PARTNER_ID)}&EIO=4&transport=websocket`;

  let socket;
  try {
    socket = new WebSocket(socketUrl, {
      headers: {
        "origin": "https://1wlgk.com",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
      }
    });
  } catch (err) {
    oneWinOddsSnapshotFailures += 1;
    oneWinOddsSnapshotReconnectAt = Date.now() + oneWinOddsSnapshotBackoffMs();
    console.warn(`[1win ODDS SNAPSHOT] Connect failed: ${err.message}`);
    return;
  }

  oneWinOddsSnapshotSocket = socket;
  oneWinOddsSnapshotReady = false;

  socket.onmessage = event => {
    const message = String(event.data || "");
    if (message === "2") {
      try { socket.send("3"); } catch {}
      return;
    }

    if (message.startsWith("0")) {
      try { socket.send("40"); } catch {}
      return;
    }

    if (message.startsWith("40")) {
      oneWinOddsSnapshotReady = true;
      oneWinOddsSnapshotFailures = 0;
      // Namespace is live — pull the first board immediately rather than waiting a full interval.
      runOneWinOddsSnapshotCycle();
      return;
    }

    if (!message.startsWith("42")) return;
    // Only accumulate odds while a board-pull window is open; between cycles the gateway keeps
    // streaming deltas that the main odds socket already owns, so we ignore them here.
    if (!oneWinOddsSnapshotCollecting) return;

    try {
      const packet = JSON.parse(message.slice(2));
      const payload = packet?.[1] || {};
      const messageType = String(payload.messageType || "");
      if (!messageType.includes("match-odds")) return;

      const updates = Array.isArray(payload.data) ? payload.data : [payload.data || {}];
      for (const data of updates) {
        const firstOdd = normalizeOneWinOddsPacketOdds(data)[0] || {};
        const matchId = String(data.matchId || data.id || data.match?.id || firstOdd.matchId || firstOdd.eventId || "");
        if (!oneWinOddsSnapshotTargets.has(matchId)) continue;

        const previousSnapshotGroups = oneWinOddsSnapshotGroupsByMatchId.get(matchId) || [];
        oneWinOddsSnapshotGroupsByMatchId.set(matchId, mergeOneWinOddsGroups(previousSnapshotGroups, data));
      }
    } catch {
      // Ignore non-JSON socket.io packets.
    }
  };

  socket.onerror = () => {
    oneWinOddsSnapshotFailures += 1;
    oneWinOddsSnapshotReconnectAt = Date.now() + oneWinOddsSnapshotBackoffMs();
    closeOneWinOddsSnapshotSocket();
  };

  socket.onclose = () => {
    if (oneWinOddsSnapshotSocket === socket) {
      oneWinOddsSnapshotFailures += 1;
      oneWinOddsSnapshotReconnectAt = Date.now() + oneWinOddsSnapshotBackoffMs();
      closeOneWinOddsSnapshotSocket();
    }
  };
}

// Open a board-pull window: snapshot the current targets, re-send the subscribe frame, and let
// the message handler collect the re-pushed board for ONE_WIN_ODDS_SNAPSHOT_LISTEN_MS.
function runOneWinOddsSnapshotCycle() {
  if (!ONE_WIN_ODDS_SNAPSHOT_ENABLED || isShuttingDown) return;
  const socket = oneWinOddsSnapshotSocket;
  if (!socket || socket.readyState !== 1 || !oneWinOddsSnapshotReady) return;
  if (oneWinOddsSnapshotCollecting) return;

  const targets = buildOneWinOddsSocketTargets();
  if (targets.size === 0) return;

  const ids = Array.from(targets.keys()).map(id => Number.parseInt(id, 10));
  oneWinOddsSnapshotTargets = targets;
  oneWinOddsSnapshotGroupsByMatchId = new Map();
  oneWinOddsSnapshotCollecting = true;

  try {
    socket.send(`42["subscribe",{"messageType":"subscribe-match-odds","data":{"matchIds":${JSON.stringify(ids)},"isBaseOddsGroups":false}}]`);
  } catch {
    oneWinOddsSnapshotCollecting = false;
    closeOneWinOddsSnapshotSocket();
    return;
  }

  oneWinOddsSnapshotCollectTimer = setTimeout(finishOneWinOddsSnapshotCycle, ONE_WIN_ODDS_SNAPSHOT_LISTEN_MS);
}

function finishOneWinOddsSnapshotCycle() {
  oneWinOddsSnapshotCollectTimer = null;
  if (!oneWinOddsSnapshotCollecting) return;
  oneWinOddsSnapshotCollecting = false;

  const now = Date.now();
  const targets = oneWinOddsSnapshotTargets;
  let applied = 0;
  for (const [matchId, snapshotGroups] of oneWinOddsSnapshotGroupsByMatchId.entries()) {
    const target = targets.get(String(matchId));
    if (!target) continue;
    const previousGroups = oneWinMarketStateByKey.get(target.key)?.groups || [];
    const reconciledGroups = mergeOneWinOddsSnapshotGroups(previousGroups, snapshotGroups, now);
    applyOneWinSocketMarketUpdate({ key: target.key, matchId, groups: reconciledGroups });
    applied += 1;
  }

  // Self-heal: if a re-subscribe pulled no board while we had live targets, the gateway may be
  // ignoring duplicate subscribes on a held socket. After two empty cycles force one fresh
  // reconnect, which guarantees an initial snapshot on the new connection's first subscribe.
  if (applied === 0 && targets.size > 0) {
    oneWinOddsSnapshotEmptyCycles += 1;
    if (oneWinOddsSnapshotEmptyCycles >= 2) {
      oneWinOddsSnapshotEmptyCycles = 0;
      console.warn("[1win ODDS SNAPSHOT] Re-subscribe yielded no board twice; forcing reconnect.");
      closeOneWinOddsSnapshotSocket();
    }
  } else {
    oneWinOddsSnapshotEmptyCycles = 0;
  }
}

function startOneWinOddsSnapshotLoop() {
  if (!ONE_WIN_ODDS_SNAPSHOT_ENABLED || oneWinOddsSnapshotTimer) return;

  console.log(
    `[1win ODDS SNAPSHOT] Held-socket board audit every ${ONE_WIN_ODDS_SNAPSHOT_INTERVAL_MS}ms ` +
    `(listen ${ONE_WIN_ODDS_SNAPSHOT_LISTEN_MS}ms, drop a group on the first non-empty board that omits it).`
  );

  const loop = () => {
    oneWinOddsSnapshotTimer = null;
    if (isShuttingDown) return;
    // Make sure the long-lived socket is up (re-opens after backoff/close), then pull a board.
    // A freshly-opened socket pulls its first board from the "40" handler, so this is a no-op
    // until the namespace is ready.
    ensureOneWinOddsSnapshotSocket();
    runOneWinOddsSnapshotCycle();
    oneWinOddsSnapshotTimer = setTimeout(loop, ONE_WIN_ODDS_SNAPSHOT_INTERVAL_MS);
  };

  oneWinOddsSnapshotTimer = setTimeout(loop, Math.min(1000, ONE_WIN_ODDS_SNAPSHOT_INTERVAL_MS));
}

function makeOneWinLooseKey(home, away) {
  const h = normalizeText(home).replace(/\s+/g, "");
  const a = normalizeText(away).replace(/\s+/g, "");
  return `${h}_${a}`;
}

function makeOneWinLiveUrl(match) {
  if (!match || !match.id || !match.slug) return null;
  return `https://1wlgk.com/betting/match/sport/${match.slug}-${match.id}`;
}

function isOneWinFinishedStatus(status) {
  const normalized = String(status || "").toLowerCase().replace(/\s+/g, " ").trim();
  if (!normalized) return false;

  return normalized === "ft" ||
    normalized === "fro" ||
    normalized === "aet" ||
    normalized === "pen" ||
    normalized === "pens" ||
    normalized === "final" ||
    normalized === "ended" ||
    normalized === "completed" ||
    normalized.includes("finished") ||
    normalized.includes("full-time") ||
    normalized.includes("full time") ||
    normalized.includes("match ended") ||
    normalized.includes("event finished") ||
    normalized.includes("game ended") ||
    normalized.includes("end of match") ||
    // Penalty shootout = regulation (and any extra time) is already over. We don't
    // monitor shootouts, so this is terminal for us: route it through the normal FT
    // drop path. The injury time already added during the match is preserved by the
    // removal/audit logic (recordRemoval takes the max of cached / lastSeen / events).
    // 1win status comes back in English ("Penalties" / "Penalty shoot-out"); a penalty
    // *kick* in open play is an event, never a match-level status, so this is safe.
    normalized.includes("penalt") ||
    normalized.includes("shootout") ||
    normalized.includes("shoot-out") ||
    normalized.includes("shoot out");
}

// True while a match is in EXTRA TIME (overtime) — a knockout/cup match that ended 90'
// level and is now playing two 15-min ET halves (clock runs 91'→120'). Our Under strategy
// keys on the SECOND-HALF added-time board that is settled by 90', so once a match crosses
// into ET it is terminal for us: we route it through the same FINISHED drop path. Critically,
// the 1win running clock keeps counting (e.g. 119'), so WITHOUT this detection the parser
// mistakes the ET minute for second-half stoppage (119-90 = a fake "+29") — see the ET branch
// in parseOneWinApiLiveInfo. Bare "et"/"aet" are deliberately NOT matched here: "aet" means
// "after extra time" (already finished, handled by isOneWinFinishedStatus) and a lone "et" is
// too ambiguous. The minute>105 fallback in the parser backs this up if the status text differs.
function isOneWinExtraTimeStatus(status) {
  const normalized = String(status || "").toLowerCase().replace(/\s+/g, " ").trim();
  if (!normalized) return false;
  if (isOneWinFinishedStatus(normalized)) return false; // AET / penalties are finished, not live ET

  return normalized.includes("extra time") ||
    normalized.includes("extra-time") ||
    normalized.includes("extratime") ||
    normalized.includes("overtime") ||
    normalized.includes("1st extra") ||
    normalized.includes("2nd extra") ||
    normalized.includes("first extra") ||
    normalized.includes("second extra") ||
    normalized.includes(" e.t.") ||
    normalized === "et1" ||
    normalized === "et2";
}

function pickAddedTimeFromObject(obj = {}, keys = []) {
  if (!obj || typeof obj !== "object") return 0;
  for (const key of keys) {
    const value = obj[key];
    const parsed = positiveInt(value, 30);
    if (parsed > 0) return parsed;
  }
  return 0;
}

function extractOneWinSecondHalfInjuryTime(data = {}) {
  const direct = pickAddedTimeFromObject(data, [
    "secondHalfInjuryTime",
    "secondHalfAddedTime",
    "secondHalfStoppageTime",
    "secondHalfAdditionalTime",
    "injuryTime2",
    "addedTime2",
    "stoppageTime2",
    "additionalTime2",
    "extraTime2"
  ]);
  if (direct > 0) return direct;

  const periodCandidates = [
    data.periods?.[1],
    data.periodsScore?.[1],
    data.periodInfo?.[1],
    data.timer?.periods?.[1],
    data.clock?.periods?.[1]
  ];
  for (const period of periodCandidates) {
    const parsed = pickAddedTimeFromObject(period, [
      "injuryTime",
      "addedTime",
      "stoppageTime",
      "additionalTime",
      "extraTime"
    ]);
    if (parsed > 0) return parsed;
  }

  return 0;
}

function findOneWinLiveMatchForTeams(home, away) {
  const directKey = `${String(home || "").toLowerCase()}_${String(away || "").toLowerCase()}`;
  const direct = oneWinLiveMatchesCache.get(directKey);
  if (direct) return direct;

  const targetLooseKey = makeOneWinLooseKey(home, away);
  for (const item of oneWinLiveMatchesCache.values()) {
    if (makeOneWinLooseKey(item.home, item.away) === targetLooseKey) return item;
  }

  const homeWords = getUniqueKeywords(home).map(normalizeText);
  const awayWords = getUniqueKeywords(away).map(normalizeText);
  const inputHome = normalizeText(home);
  const inputAway = normalizeText(away);
  for (const item of oneWinLiveMatchesCache.values()) {
    const liveHome = normalizeText(item.home);
    const liveAway = normalizeText(item.away);
    const liveHomeWords = getUniqueKeywords(item.home).map(normalizeText);
    const liveAwayWords = getUniqueKeywords(item.away).map(normalizeText);
    const homeHit =
      (homeWords.length > 0 && homeWords.some(word => word.length > 2 && liveHome.includes(word))) ||
      (liveHomeWords.length > 0 && liveHomeWords.some(word => word.length > 2 && inputHome.includes(word)));
    const awayHit =
      (awayWords.length > 0 && awayWords.some(word => word.length > 2 && liveAway.includes(word))) ||
      (liveAwayWords.length > 0 && liveAwayWords.some(word => word.length > 2 && inputAway.includes(word)));
    if (homeHit && awayHit) return item;
  }

  return null;
}

function parseOneWinApiLiveInfo(data = {}) {
  const status = clean(data.status || "API live match").replace(/[Â´`â€²]/g, "'");
  const statusLower = status.toLowerCase();
  const liveTrackerUrl = getOneWinLiveTrackerUrl(data);
  const matchTimeMs = Number(data.matchTime);
  const minute = Number.isFinite(matchTimeMs) && matchTimeMs > 0
    ? Math.max(1, Math.floor(matchTimeMs / 60000))
    : null;
  // Extra time (overtime): a cup match level at 90' now playing two 15-min ET halves, so the
  // running clock counts 91'→120'. We must detect this BEFORE deriving second-half stoppage,
  // otherwise the ET minute (e.g. 119') is misread as a fake "+29" board. Trust the status text
  // first; fall back to minute > 105 — real second-half stoppage never reaches +16, so anything
  // past 105' is unambiguously extra time even if 1win's status wording is unfamiliar.
  const isExtraTime = isOneWinExtraTimeStatus(statusLower) ||
    (Number.isFinite(minute) && minute > 105);
  // In ET the clock no longer represents added time, so suppress the derived stoppage entirely.
  const secondHalfElapsedAddedTime = !isExtraTime && Number.isFinite(minute) && minute > 90 && minute <= 120
    ? minute - 90
    : 0;
  const secondHalfInjuryTime = extractOneWinSecondHalfInjuryTime(data);

  const scoreHome = data.matchScore?.t1 ?? data.score?.t1 ?? "0";
  const scoreAway = data.matchScore?.t2 ?? data.score?.t2 ?? "0";
  const score = `${scoreHome}-${scoreAway}`;
  const periodScore = period => {
    if (!period) return null;
    return `${period.t1 ?? 0}-${period.t2 ?? 0}`;
  };

  if (isOneWinFinishedStatus(statusLower)) {
    return {
      score,
      time: "FT",
      phase: "FINISHED",
      currentMin: minute || 90,
      matchTimeMs: Number.isFinite(matchTimeMs) ? matchTimeMs : null,
      secondHalfElapsedAddedTime,
      secondHalfInjuryTime,
      isExtraTime,
      rawStatus: status,
      firstHalfScore: periodScore(data.periodsScore?.[0]),
      secondHalfScore: periodScore(data.periodsScore?.[1]),
      liveTrackerUrl
    };
  }

  // Extra time reached → terminal for our purposes. Route through the FINISHED drop path so the
  // match leaves monitoring (our monitoring window closes at 90'). phase "FINISHED" triggers
  // the existing immediate-drop logic; secondHalfElapsedAddedTime is already 0 so no fake clock
  // shows; secondHalfInjuryTime (the announced regulation board "+X", if captured) is preserved
  // for the audit, and isExtraTime tells the finaliser to never derive an "actual" from the clock.
  if (isExtraTime) {
    return {
      score,
      time: "FT",
      phase: "FINISHED",
      currentMin: minute,
      matchTimeMs: Number.isFinite(matchTimeMs) ? matchTimeMs : null,
      secondHalfElapsedAddedTime: 0,
      secondHalfInjuryTime,
      isExtraTime: true,
      rawStatus: status,
      firstHalfScore: periodScore(data.periodsScore?.[0]),
      secondHalfScore: periodScore(data.periodsScore?.[1]),
      liveTrackerUrl
    };
  }

  if (statusLower.includes("about to start")) {
    return {
      score,
      time: "NS",
      phase: "SCHEDULED",
      currentMin: null,
      matchTimeMs: Number.isFinite(matchTimeMs) ? matchTimeMs : null,
      secondHalfElapsedAddedTime: 0,
      secondHalfInjuryTime,
      rawStatus: status,
      firstHalfScore: periodScore(data.periodsScore?.[0]),
      secondHalfScore: periodScore(data.periodsScore?.[1]),
      liveTrackerUrl
    };
  }

  if (statusLower.includes("half-time") || statusLower.includes("half time") || statusLower === "ht") {
    return {
      score,
      time: "HT",
      phase: "HALF TIME",
      currentMin: minute || 45,
      matchTimeMs: Number.isFinite(matchTimeMs) ? matchTimeMs : null,
      secondHalfElapsedAddedTime: 0,
      secondHalfInjuryTime,
      rawStatus: status,
      firstHalfScore: periodScore(data.periodsScore?.[0]),
      secondHalfScore: periodScore(data.periodsScore?.[1]),
      liveTrackerUrl
    };
  }

  return {
    score,
    time: minute ? `${minute}'` : "LIVE",
    phase: status || "LIVE",
    currentMin: minute,
    matchTimeMs: Number.isFinite(matchTimeMs) ? matchTimeMs : null,
    secondHalfElapsedAddedTime,
    secondHalfInjuryTime,
    isExtraTime,
    rawStatus: status,
    firstHalfScore: periodScore(data.periodsScore?.[0]),
    secondHalfScore: periodScore(data.periodsScore?.[1]),
    liveTrackerUrl
  };
}

function mergeOneWinLiveInfoSnapshot(previous = {}, next = {}) {
  return {
    ...previous,
    ...next,
    matchScore: next.matchScore
      ? { ...(previous.matchScore || {}), ...next.matchScore }
      : previous.matchScore,
    score: next.score || previous.score,
    periodsScore: next.periodsScore || previous.periodsScore,
    broadcast: next.broadcast || previous.broadcast,
    liveTracker: next.liveTracker || previous.liveTracker
  };
}

async function fetchOneWinTournamentMap(headers) {
  const now = Date.now();
  if (oneWinTournamentCache.expiresAt > now && oneWinTournamentCache.map.size > 0) {
    return oneWinTournamentCache.map;
  }

  try {
    const response = await fetchOneWinApi("https://api-gateway.top-parser.com/tournaments/get-many", {
      method: "POST",
      headers,
      body: JSON.stringify({ service: "live", sportId: 18, include: { category: true } })
    });

    if (!response.ok) throw new Error(`1win tournaments API returned ${response.status}`);

    const json = await response.json();
    const tournamentMap = new Map();
    for (const item of json.result?.items || []) {
      const tournament = item.tournament || {};
      const category = item.category || {};
      if (!tournament.id) continue;
      const leagueParts = [category.name, tournament.name].filter(Boolean);
      tournamentMap.set(tournament.id, leagueParts.join(". ") || tournament.name || "");
    }

    oneWinTournamentCache = {
      map: tournamentMap,
      expiresAt: Date.now() + ONE_WIN_TOURNAMENT_REFRESH_INTERVAL_MS
    };
    return tournamentMap;
  } catch (err) {
    if (oneWinTournamentCache.map.size > 0) {
      if (/\b429\b/.test(err.message || "")) {
        console.warn(`[1win TOURNAMENT API] Rate limited while refreshing static league metadata. Reusing cached map.`);
      } else {
        console.warn(`[1win TOURNAMENT API] Using cached tournament map after refresh failed: ${err.message}`);
      }
      oneWinTournamentCache.expiresAt = Date.now() + Math.min(5 * 60 * 1000, ONE_WIN_TOURNAMENT_REFRESH_INTERVAL_MS);
      return oneWinTournamentCache.map;
    }
    throw err;
  }
}

async function fetchOneWinLiveInfoSnapshotsViaSocket(matchIds, timeoutMs = 8000) {
  const ids = Array.from(new Set((matchIds || [])
    .map(id => Number.parseInt(id, 10))
    .filter(id => Number.isFinite(id) && id > 0)));
  const snapshots = new Map();
  if (ids.length === 0 || typeof WebSocket !== "function") return snapshots;

  const socketUrl = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(ONE_WIN_API_LANG)}&externalPartnerId=${encodeURIComponent(ONE_WIN_API_PARTNER_ID)}&EIO=4&transport=websocket`;

  return await new Promise(resolve => {
    let settled = false;
    let ws = null;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        if (ws && ws.readyState <= 1) ws.close();
      } catch {
        // Ignore websocket close races.
      }
      resolve(snapshots);
    };

    const timer = setTimeout(finish, timeoutMs);

    try {
      ws = new WebSocket(socketUrl);
    } catch {
      finish();
      return;
    }

    ws.onerror = () => finish();
    ws.onclose = () => finish();
    ws.onmessage = event => {
      const text = String(event.data || "");
      if (text === "2") {
        try { ws.send("3"); } catch {}
        return;
      }

      if (text.startsWith("0")) {
        try { ws.send("40"); } catch {}
        return;
      }

      if (text.startsWith("40")) {
        try {
          ws.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`);
        } catch {
          finish();
        }
        return;
      }

      if (!text.startsWith("42")) return;

      let payload;
      try {
        payload = JSON.parse(text.slice(2));
      } catch {
        return;
      }

      const message = payload?.[1];
      if (!message || (message.messageType !== "match-info-snapshot" && message.messageType !== "match-info")) return;

      // match-info can arrive as a single object or an array, and the first frame is often a
      // partial delta (no matchTime/status yet). Merge frames per id and only resolve once
      // every requested id has a usable snapshot, so the caller never sees a half-filled one.
      const updates = Array.isArray(message.data) ? message.data : [message.data || {}];
      for (const d of updates) {
        const matchId = Number.parseInt(d.matchId || d.id, 10);
        if (!Number.isFinite(matchId)) continue;
        const key = String(matchId);
        snapshots.set(key, mergeOneWinLiveInfoSnapshot(snapshots.get(key) || {}, d));
      }

      const allUsable = ids.every(id => {
        const s = snapshots.get(String(id));
        return s && (s.matchTime != null || s.status != null || s.matchScore != null);
      });
      if (allUsable) finish();
    };
  });
}

function applyOneWinLiveInfoUpdate(matchId, data = {}) {
  const id = String(matchId || data.matchId || data.id || "");
  if (!id) return;

  const mergedData = mergeOneWinLiveInfoSnapshot(oneWinLiveInfoSnapshots.get(id) || {}, data);
  oneWinLiveInfoSnapshots.set(id, mergedData);
  const meta = oneWinLiveMetaById.get(id);
  if (!meta) return;

  // Resolve through the identity pin: after a team-name reformat the live entry stays
  // under its original (canonical) key, so rebuilding the key from meta's current names
  // would miss the cache and silently drop this real-time socket update.
  const key = oneWinKeyByMatchId.get(id) || `${meta.home.toLowerCase()}_${meta.away.toLowerCase()}`;
  const cached = oneWinLiveMatchesCache.get(key);
  if (!cached) return;

  const liveInfo = parseOneWinApiLiveInfo(mergedData);
  const updatedLive = {
    ...cached,
    score: liveInfo.score,
    time: liveInfo.time,
    phase: liveInfo.phase,
    currentMin: liveInfo.currentMin,
    matchTimeMs: liveInfo.matchTimeMs,
    secondHalfElapsedAddedTime: liveInfo.secondHalfElapsedAddedTime,
    secondHalfInjuryTime: liveInfo.secondHalfInjuryTime,
    isExtraTime: liveInfo.isExtraTime === true,
    rawStatus: liveInfo.rawStatus,
    firstHalfScore: liveInfo.firstHalfScore,
    secondHalfScore: liveInfo.secondHalfScore,
    liveTrackerUrl: liveInfo.liveTrackerUrl || cached.liveTrackerUrl || "",
    lastUpdated: Date.now()
  };
  oneWinLiveMatchesCache.set(key, updatedLive);

  const changed = syncOneWinMatchCacheFromLive(updatedLive);
  if (liveInfo.phase === "FINISHED") {
    const removed = dropTrackedMatchImmediately(key, "Match completed on 1win", matchCache.get(key));
    if (removed) {
      console.log(`[SCANNER DROP] ${meta.home} vs ${meta.away}: Match completed on 1win API socket.`);
    }
    return;
  }

  if (changed) {
    scheduleDashboardBroadcast(50);
    // Evaluate the 78' push the instant fresh live data arrives over the socket,
    // instead of waiting for the next ~3s cache loop. This is the low-latency path.
    try {
      evaluatePushTriggers(buildDashboardPayload());
    } catch (err) {
      console.warn("[PUSH] socket-trigger eval failed:", err.message);
    }
  }
}

function closeOneWinLiveInfoSocket() {
  const socket = oneWinLiveInfoSocket;
  oneWinLiveInfoSocket = null;
  if (!socket) return;
  socket.onclose = null;
  socket.onerror = null;
  socket.onmessage = null;
  try {
    if (socket.readyState <= 1) socket.close();
  } catch {
    // Ignore socket close races.
  }
}

function connectOneWinLiveInfoSocket(ids, signature) {
  if (!signature || typeof WebSocket !== "function") return;
  if (Date.now() < oneWinLiveInfoSocketReconnectAt) return;

  const socketUrl = `wss://api-gateway.top-parser.com/push-server-v2/?Language=${encodeURIComponent(ONE_WIN_API_LANG)}&externalPartnerId=${encodeURIComponent(ONE_WIN_API_PARTNER_ID)}&EIO=4&transport=websocket`;

  let socket;
  try {
    socket = new WebSocket(socketUrl);
  } catch (err) {
    oneWinLiveInfoSocketReconnectAt = Date.now() + 5000;
    console.error(`[1win INFO SOCKET] Connect failed: ${err.message}`);
    return;
  }

  oneWinLiveInfoSocket = socket;
  oneWinLiveInfoSocketSignature = signature;

  socket.onmessage = event => {
    const text = String(event.data || "");
    if (text === "2") {
      try { socket.send("3"); } catch {}
      return;
    }

    if (text.startsWith("0")) {
      try { socket.send("40"); } catch {}
      return;
    }

    if (text.startsWith("40")) {
      try {
        socket.send(`42["subscribe",{"messageType":"subscribe-match-info","data":{"matchIds":${JSON.stringify(ids)}}}]`);
        console.log(`[1win INFO SOCKET] Subscribed to ${ids.length} live match info feeds.`);
      } catch {
        closeOneWinLiveInfoSocket();
      }
      return;
    }

    if (!text.startsWith("42")) return;

    try {
      const packet = JSON.parse(text.slice(2));
      const payload = packet?.[1] || {};
      const messageType = String(payload.messageType || "");
      if (messageType !== "match-info-snapshot" && messageType !== "match-info") return;

      const updates = Array.isArray(payload.data) ? payload.data : [payload.data || {}];
      for (const data of updates) {
        const matchId = data.matchId || data.id;
        applyOneWinLiveInfoUpdate(matchId, data);
      }
    } catch {
      // Ignore non-JSON socket.io packets.
    }
  };

  socket.onerror = () => {
    oneWinLiveInfoSocketReconnectAt = Date.now() + 5000;
    closeOneWinLiveInfoSocket();
  };

  socket.onclose = () => {
    if (oneWinLiveInfoSocket === socket) {
      oneWinLiveInfoSocket = null;
      oneWinLiveInfoSocketReconnectAt = Date.now() + 5000;
    }
  };
}

function refreshOneWinLiveInfoSocketSubscriptions(matchIds) {
  const ids = Array.from(new Set((matchIds || [])
    .map(id => Number.parseInt(id, 10))
    .filter(id => Number.isFinite(id) && id > 0)));
  const signature = ids.slice().sort((a, b) => a - b).join(",");

  if (!signature) {
    oneWinLiveInfoSocketSignature = "";
    closeOneWinLiveInfoSocket();
    return;
  }

  const shouldReconnect =
    !oneWinLiveInfoSocket ||
    oneWinLiveInfoSocket.readyState > 1 ||
    oneWinLiveInfoSocketSignature !== signature;

  if (!shouldReconnect) return;

  closeOneWinLiveInfoSocket();
  connectOneWinLiveInfoSocket(ids, signature);
}

async function fetchOneWinLiveApiMetadata() {
  const headers = makeOneWinApiHeaders();

  const matchesResponse = await fetchOneWinApi("https://api-gateway.top-parser.com/matches/get-many", {
    method: "POST",
    headers,
    body: JSON.stringify({ service: "live", sportId: 18, excludeSportType: "polybet", limit: 100 })
  });

  if (!matchesResponse.ok) throw new Error(`1win matches API returned ${matchesResponse.status}`);

  const matchesJson = await matchesResponse.json();
  const tournamentMap = await fetchOneWinTournamentMap(headers);

  const byLooseKey = new Map();
  const byId = new Map();
  for (const match of matchesJson.result?.items || []) {
    const home = match.homeTeam?.name || match.competitors?.find(c => c.position === 1)?.name || "";
    const away = match.awayTeam?.name || match.competitors?.find(c => c.position === 2)?.name || "";
    if (!home || !away || !match.id) continue;

    const league = tournamentMap.get(match.tournamentId) || match.tournament?.slug || "";
    const tournamentSlug = match.tournament?.slug || "";
    if (isNonRealFootballMatch({ league, home, away, slug: match.slug || "", tournamentSlug })) {
      logNonRealFootballSkip(`${home.toLowerCase()}_${away.toLowerCase()}`, home, away, league);
      continue;
    }
    if (isUnderAgeMatch({ league, home, away, slug: match.slug || "", tournamentSlug })) {
      logUnderAgeSkip(`${home.toLowerCase()}_${away.toLowerCase()}`, home, away, league);
      continue;
    }

    const meta = {
      matchId: String(match.id),
      home,
      away,
      league,
      url: makeOneWinLiveUrl(match),
      slug: match.slug || "",
      tournamentSlug
    };
    byLooseKey.set(makeOneWinLooseKey(home, away), meta);
    byId.set(String(match.id), meta);
  }

  return { byLooseKey, byId, items: Array.from(byId.values()), count: byId.size };
}

// Resolve the cache key for a live-list fixture, pinned to its stable 1win matchId.
// 1win intermittently reformats team names mid-match ("Venezuela (Youth)" ->
// "Venezuela Youth"), and a purely name-derived key would mint a SECOND entry for the
// same fixture — duplicate queue rows, a duplicate dashboard card the odds socket can't
// feed (matchId->key is last-write-wins), and a false "no longer in cache" removal when
// the old-name key ages out. Pinning each matchId to the first key it was seen under
// keeps the entry stable: a reformat resolves back to the same key and updates in place.
function resolveCanonicalOneWinKey(meta) {
  const nameKey = `${String(meta.home || "").toLowerCase()}_${String(meta.away || "").toLowerCase()}`;
  const id = String(meta.matchId || "").trim();
  if (!/^\d+$/.test(id)) return nameKey;

  const pinned = oneWinKeyByMatchId.get(id);
  if (pinned && pinned !== nameKey && !isBlacklisted(pinned)) {
    // Same fixture, reformatted name — keep the original key.
    return pinned;
  }
  oneWinKeyByMatchId.set(id, nameKey);
  return nameKey;
}

async function refreshOneWinLiveCache() {
  const now = Date.now();
  if (oneWinLiveBackoffUntil && now < oneWinLiveBackoffUntil) return;
  if (isOneWinLiveRefreshing || now - lastOneWinLiveRefreshAt < ONE_WIN_LIVE_REFRESH_INTERVAL_MS) return;
  isOneWinLiveRefreshing = true;

  try {
    const apiMeta = await fetchOneWinLiveApiMetadata();
    clearOneWinRateLimit();
    oneWinLiveMetaById.clear();
    const currentMatchIds = new Set((apiMeta.items || []).map(item => String(item.matchId)).filter(Boolean));
    for (const id of oneWinLiveInfoSnapshots.keys()) {
      if (!currentMatchIds.has(id)) oneWinLiveInfoSnapshots.delete(id);
    }
    for (const meta of apiMeta.items || []) {
      if (meta.matchId) oneWinLiveMetaById.set(String(meta.matchId), meta);
    }
    refreshOneWinLiveInfoSocketSubscriptions((apiMeta.items || []).map(item => item.matchId));

    const updatedKeys = new Set();
    for (const meta of apiMeta.items || []) {
      const key = resolveCanonicalOneWinKey(meta);
      if (isNonRealFootballMatch({ league: meta.league, home: meta.home, away: meta.away, slug: meta.slug || "", tournamentSlug: meta.tournamentSlug || "" })) {
        logNonRealFootballSkip(key, meta.home, meta.away, meta.league);
        blacklistMatch(key);
        continue;
      }
      if (isUnderAgeMatch({ league: meta.league, home: meta.home, away: meta.away, slug: meta.slug || "", tournamentSlug: meta.tournamentSlug || "" })) {
        logUnderAgeSkip(key, meta.home, meta.away, meta.league);
        blacklistMatch(key);
        continue;
      }

      const previousLive = oneWinLiveMatchesCache.get(key);
      const snapshot = oneWinLiveInfoSnapshots.get(String(meta.matchId));
      const liveInfo = snapshot
        ? parseOneWinApiLiveInfo(snapshot)
        : {
            score: previousLive?.score || "0-0",
            time: previousLive?.time || "LIVE",
            phase: previousLive?.phase || "LIVE",
            currentMin: previousLive?.currentMin ?? null,
            matchTimeMs: previousLive?.matchTimeMs ?? null,
            secondHalfElapsedAddedTime: previousLive?.secondHalfElapsedAddedTime ?? 0,
            secondHalfInjuryTime: previousLive?.secondHalfInjuryTime ?? 0,
            rawStatus: previousLive?.rawStatus || "API live match",
            firstHalfScore: previousLive?.firstHalfScore || null,
            secondHalfScore: previousLive?.secondHalfScore || null,
            liveTrackerUrl: previousLive?.liveTrackerUrl || ""
          };
      updatedKeys.add(key);
      oneWinLiveMatchesCache.set(key, {
        key,
        home: meta.home,
        away: meta.away,
        league: meta.league || "1WIN LIVE SOCCER",
        tournamentSlug: meta.tournamentSlug || "",
        matchId: meta.matchId || "",
        oneWinUrl: meta.url || null,
        score: liveInfo.score,
        time: liveInfo.time,
        phase: liveInfo.phase,
        currentMin: liveInfo.currentMin,
        matchTimeMs: liveInfo.matchTimeMs,
        secondHalfElapsedAddedTime: liveInfo.secondHalfElapsedAddedTime,
        secondHalfInjuryTime: liveInfo.secondHalfInjuryTime,
        isExtraTime: liveInfo.isExtraTime === true,
        rawStatus: liveInfo.rawStatus,
        firstHalfScore: liveInfo.firstHalfScore,
        secondHalfScore: liveInfo.secondHalfScore,
        liveTrackerUrl: liveInfo.liveTrackerUrl || previousLive?.liveTrackerUrl || "",
        source: "1win-api",
        lastUpdated: Date.now()
      });

      if (meta.url) {
        oneWinLinksCache.set(key, meta.url);
      }
    }

    if (apiMeta.count > 0) {
      for (const [key, live] of oneWinLiveMatchesCache.entries()) {
        if (updatedKeys.has(key)) {
          if (live) live.liveListMissCount = 0;
          continue;
        }
        // Tolerate transient omissions: 1win's live-list drops still-playing matches
        // from individual responses. Only evict after several consecutive misses so a
        // single flaky response cannot cascade into a false "completed" exclusion.
        const misses = ((live && live.liveListMissCount) || 0) + 1;
        if (live) live.liveListMissCount = misses;
        if (misses >= ONE_WIN_LIVE_LIST_MISS_TOLERANCE) {
          oneWinLiveMatchesCache.delete(key);
          // The fixture has truly left the live list — release its identity pin so a
          // legitimate future re-list can key cleanly from its current name.
          const evictedId = String(live?.matchId || "").trim();
          if (/^\d+$/.test(evictedId) && oneWinKeyByMatchId.get(evictedId) === key) {
            oneWinKeyByMatchId.delete(evictedId);
          }
        }
      }
    }
  } catch (err) {
    const isRateLimited = /\b429\b/.test(err.message || "");
    if (isRateLimited) {
      recordOneWinRateLimit("LIVE API", err.message);
      return;
    }

    console.error(`[1win LIVE] Refresh failed: ${err.message}`);
  } finally {
    lastOneWinLiveRefreshAt = Date.now();
    isOneWinLiveRefreshing = false;
  }
}

function normalizeOneWinScore(score) {
  const match = String(score || "").match(/(\d+)\s*[-:]\s*(\d+)/);
  return match ? `${match[1]}-${match[2]}` : "0-0";
}

function derivePeriodScores(events, currentScore) {
  const goals = (events || [])
    .filter(event => event.type === "goal")
    .sort((a, b) => a.minute - b.minute);

  let firstHalfScore = "0-0";
  for (const goal of goals) {
    const scoreMatch = String(goal.text || goal.display || "").match(/\((\d+)\s*[-:]\s*(\d+)\)/);
    if (scoreMatch && goal.minute <= 45) {
      firstHalfScore = `${scoreMatch[1]}-${scoreMatch[2]}`;
    }
  }

  return {
    firstHalfScore,
    secondHalfScore: normalizeOneWinScore(currentScore)
  };
}

function syncOneWinMatchCacheFromLive(live) {
  if (!live || !live.home || !live.away || !live.key) return false;
  if (isBlacklisted(live.key) || isBlacklistedById(live.matchId)) return false;
  if (isNonRealFootballMatch({ league: live.league, home: live.home, away: live.away, slug: live.slug || "", tournamentSlug: live.tournamentSlug || "" })) {
    logNonRealFootballSkip(live.key, live.home, live.away, live.league);
    blacklistMatch(live.key);
    return false;
  }

  const existing = matchCache.get(live.key) || {};
  const existingInfo = existing.info || {};
  const previousSignature = `${existingInfo.score || ""}|${existingInfo.time || ""}|${existingInfo.phase || ""}|${existingInfo.currentMin ?? ""}|${existingInfo.secondHalfElapsedAddedTime ?? ""}|${existingInfo.secondHalfInjuryTime ?? ""}|${existingInfo.firstHalfScore || ""}|${existingInfo.secondHalfScore || ""}|${existingInfo.liveTrackerUrl || ""}`;
  const events = dedupe(existing.events || []);
  const liveHasClock = live.currentMin !== null || (live.time && live.time !== "LIVE");
  const score = normalizeOneWinScore(live.score || existingInfo.score);
  const liveTrackerUrl = getOneWinLiveTrackerUrl(live) || existingInfo.liveTrackerUrl || "";
  let time = liveHasClock ? live.time : (existingInfo.time || live.time || "LIVE");
  const phase = liveHasClock ? (live.phase || "LIVE") : (existingInfo.phase || live.phase || "LIVE");
  let currentMin = live.currentMin ?? getCurrentMinute(time) ?? existingInfo.currentMin ?? null;
  if (currentMin === null && phase === "LIVE" && TEMP_MIN_MINUTE <= 1) {
    currentMin = 1;
    time = "1'";
  }
  const periodScores = derivePeriodScores(events, score);

  if (live.oneWinUrl) {
    oneWinLinksCache.set(live.key, live.oneWinUrl);
  }

  matchCache.set(live.key, {
    info: {
      home: live.home,
      away: live.away,
      league: live.league || existing.info?.league || "1WIN LIVE SOCCER",
      tournamentSlug: live.tournamentSlug || existing.info?.tournamentSlug || "",
      score,
      phase,
      time,
      currentMin,
      matchTimeMs: live.matchTimeMs ?? existing.info?.matchTimeMs ?? null,
      secondHalfElapsedAddedTime: Number.isFinite(live.secondHalfElapsedAddedTime)
        ? live.secondHalfElapsedAddedTime
        : (existing.info?.secondHalfElapsedAddedTime || 0),
      // Board-first: the pinned sportcast-1104 referee value wins over the unreliable
      // match-info payload, so a stray payload "+1" can never overwrite the real "+4".
      // Payload is only a fallback for matches with no board (e.g. no sportcast tracker).
      secondHalfInjuryTime: positiveInt(existing.info?.boardSecondHalfAddedTime, 30) || positiveInt(live.secondHalfInjuryTime, 30) || existing.info?.secondHalfInjuryTime || 0,
      boardSecondHalfAddedTime: positiveInt(existing.info?.boardSecondHalfAddedTime, 30) || undefined,
      // Sticky: once a match has entered extra time it stays flagged even if a later partial
      // frame omits the status, so the finaliser never derives an "actual" from the ET clock.
      isExtraTime: live.isExtraTime === true || existing.info?.isExtraTime === true,
      matchId: live.matchId || "",
      matchPath: live.matchId ? `onewin/${live.matchId}` : "",
      oneWinUrl: firstUsableOneWinLink(live.oneWinUrl, oneWinLinksCache.get(live.key)),
      liveTrackerUrl,
      firstHalfScore: live.firstHalfScore || existing.info?.firstHalfScore || periodScores.firstHalfScore,
      secondHalfScore: live.secondHalfScore || periodScores.secondHalfScore,
      firstHalfInjuryTime: existing.info?.firstHalfInjuryTime || 0,
      hasRedCard: existing.info?.hasRedCard || hasRedCardBeforeCutoff(events)
    },
    events,
    hasDetailedEvents: existing.hasDetailedEvents === true || events.length > 0,
    trackerTimelineReady: existing.trackerTimelineReady === true,
    lastUpdated: Date.now(),
    missingFromListCount: 0
  });

  const nextInfo = matchCache.get(live.key)?.info || {};
  const nextSignature = `${nextInfo.score || ""}|${nextInfo.time || ""}|${nextInfo.phase || ""}|${nextInfo.currentMin ?? ""}|${nextInfo.secondHalfElapsedAddedTime ?? ""}|${nextInfo.secondHalfInjuryTime ?? ""}|${nextInfo.firstHalfScore || ""}|${nextInfo.secondHalfScore || ""}|${nextInfo.liveTrackerUrl || ""}`;
  return previousSignature !== nextSignature;
}

async function refreshOneWinMatchCache() {
  const updatedKeys = new Set();

  for (const live of oneWinLiveMatchesCache.values()) {
    if (!live || !live.home || !live.away || !live.key) continue;
    if (isBlacklisted(live.key) || isBlacklistedById(live.matchId)) continue;

    updatedKeys.add(live.key);
    syncOneWinMatchCacheFromLive(live);
  }

  for (const [key, cached] of matchCache.entries()) {
    if (updatedKeys.has(key)) continue;
    const count = (cached.missingFromListCount || 0) + 1;
    cached.missingFromListCount = count;
    if (count >= 2) {
      matchCache.delete(key);
      oneWinLinksCache.delete(key);
      oneWinMarketStateByKey.delete(key);
    }
  }

  for (const [key, lastRequestedTime] of activeTrackedMatches.entries()) {
    if (Date.now() - lastRequestedTime > 40000) {
      activeTrackedMatches.delete(key);
    }
  }
  scheduleDashboardBroadcast(250);
}

function startOneWinMonitorLoop() {
  if (isCacheLoopRunning) return;
  isCacheLoopRunning = true;
  isShuttingDown = false;
  console.log("[SYSTEM] Starting 1win-only API monitor loops (browserless)...");

  const updateLoop = async () => {
    if (isShuttingDown) return;
    try {
      await refreshOneWinLiveCache();
      await refreshOneWinMatchCache();
      updateAutoTrackedMatches();
      tickTestMonitor(); // TEMPORARY: drives the /backtest virtual backtest (safe to remove with its block)
      refreshOneWinOddsSocketSubscriptions();
      await refreshOneWinTimelineApiFeeds();
      pruneRuntimeMemory();
      try {
        evaluatePushTriggers(buildDashboardPayload());
      } catch (pushErr) {
        console.warn("[PUSH] trigger evaluation failed:", pushErr.message);
      }
    } catch (err) {
      console.error("[CACHE LOOP SYSTEM EXCEPTION]:", err.message);
    } finally {
      if (!isShuttingDown) {
        cacheLoopTimer = setTimeout(updateLoop, 3000);
      }
    }
  };
  updateLoop();
  startOneWinOddsSnapshotLoop();
}

function getScoreDifference(score = "0-0") {
  const parts = String(score || "").split("-").map(value => Number.parseInt(value, 10));
  if (parts.length !== 2 || parts.some(value => !Number.isFinite(value))) return 0;
  return Math.abs(parts[0] - parts[1]);
}

function hasRedCardBeforeCutoff(events = [], cutoffMinute = 90) {
  return (Array.isArray(events) ? events : []).some(event => {
    const minute = Number.parseInt(event.minute, 10);
    return event.type === "red" && Number.isFinite(minute) && minute < cutoffMinute;
  });
}

function getMinuteWindows(events = [], maxGapMinutes = 1) {
  const minutes = Array.from(new Set((Array.isArray(events) ? events : [])
    .map(event => Number.parseInt(event.minute, 10))
    .filter(Number.isFinite)))
    .sort((a, b) => a - b);

  const windows = [];
  for (const minute of minutes) {
    const lastWindow = windows[windows.length - 1];
    if (lastWindow && minute - lastWindow.end <= maxGapMinutes) {
      lastWindow.end = minute;
      lastWindow.minutes.push(minute);
      continue;
    }

    windows.push({ start: minute, end: minute, minutes: [minute] });
  }

  return windows;
}

function countUniqueMinuteWindows(events = [], maxGapMinutes = 1) {
  return getMinuteWindows(events, maxGapMinutes).length;
}

function isTopLeague(leagueStr = "") {
  const normalized = String(leagueStr).toUpperCase();
  const topLeagues = [
    "PREMIER LEAGUE", "PRIMERA DIVISION", "LA LIGA", "SERIE A", "BUNDESLIGA", "LIGUE 1",
    "CHAMPIONS LEAGUE", "EUROPA LEAGUE", "CONFERENCE LEAGUE", "WORLD CUP", "EURO ",
    "COPA AMERICA", "COPA LIBERTADORES", "EREDIVISIE", "PRIMEIRA LIGA", "SUPER LIG",
    "MLS", "MAJOR LEAGUE SOCCER", "A-LEAGUE"
  ];
  if (
    normalized.includes("WOMEN") || normalized.includes("YOUTH") || normalized.includes("U19") ||
    normalized.includes("U20") || normalized.includes("U21") || normalized.includes("U17") ||
    normalized.includes("U18") || normalized.includes("RESERVE") || normalized.includes("AMATEUR") ||
    normalized.includes("CUP") || normalized.includes("2. BUNDESLIGA") || normalized.includes("CHAMPIONSHIP") ||
    normalized.includes("LEAGUE ONE") || normalized.includes("LEAGUE TWO")
  ) {
    return false;
  }
  return topLeagues.some(tl => normalized.includes(tl));
}

function normalizeText(text) {
  return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9\s\-]/g, "").trim();
}

// Global exception and rejection handlers to prevent background loops from crashing the Node.js process
process.on("unhandledRejection", (reason, promise) => {
  console.error("[SYSTEM WARNING] Unhandled Promise Rejection at:", promise, "reason:", reason);
});

process.on("uncaughtException", (err) => {
  console.error("[SYSTEM WARNING] Uncaught Exception thrown:", err);
});

function getUniqueKeywords(name) {
  const words = normalizeText(name).split(/\s+/).filter(w => w.length > 3 && !["town", "city", "club", "united", "fc", "fk", "il", "fotball", "football", "women", "youth", "athletics", "athletic", "atletico", "deportivo", "sport", "sporting", "racing", "association", "wanderers", "rovers", "albion", "hotspur", "county", "real", "saint", "sports", "sporting", "university", "varsity", "montevideo"].includes(w));
  return words.length === 0 ? normalizeText(name).split(/\s+/).filter(w => w.length > 1) : words;
}

function getCurrentMinute(timeStr) {
  if (!timeStr) return null;
  const cleanTime = String(timeStr).trim().toUpperCase();
  if (cleanTime === "HT") return 45;
  if (cleanTime === "FT") return 90;
  const match = cleanTime.match(/^(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

function passesFilters(matchInfo, events) {
  if (!matchInfo) return { passed: true };
  const currentMin = getCurrentMinute(matchInfo.time);

  const redBeforeCutoff = hasRedCardBeforeCutoff(events);
  const unknownRedBeforeCutoff = matchInfo.hasRedCard === true &&
    (!Array.isArray(events) || events.length === 0) &&
    (currentMin === null || currentMin < 90);
  if (redBeforeCutoff || unknownRedBeforeCutoff) {
    return { passed: false, reason: "Red card detected" };
  }
  if (currentMin === null && matchInfo.phase === "FINISHED") return { passed: false, reason: "Match completed" };
  if (currentMin === null) return { passed: true };

  // Drop on any goal scored in the 62'–90' window (inclusive of 90', which also covers
  // stoppage time since the clock caps at 90). [3]
  const hasLateGoal = (events || []).some(e => e.type === "goal" && e.minute >= 62 && e.minute <= 90);
  if (hasLateGoal) return { passed: false, reason: GOAL_REMOVAL_REASON };

  return { passed: true };
}

function getCandidates() {
  const candidates = [];
  for (const [key, match] of matchCache.entries()) {
    const info = match.info;
    const currentMin = getCurrentMinute(info.time);

    if (isBlacklisted(key) || isBlacklistedById(info.matchId)) continue;
    if (isNonRealFootballMatch({ league: info.league, home: info.home, away: info.away, tournamentSlug: info.tournamentSlug || "" })) {
      logNonRealFootballSkip(key, info.home, info.away, info.league);
      blacklistMatch(key);
      continue;
    }
    if (isLowTierOrReserve({ league: info.league, home: info.home, away: info.away, tournamentSlug: info.tournamentSlug || "" })) {
      console.log(`[SCANNER FILTER REJECT] ${info.home} vs ${info.away}: Skipped - Low-tier division or reserve team.`);
      blacklistMatch(key);
      continue;
    }

    if (currentMin === null || info.phase === "FINISHED") continue;

    const timeUpper = (info.time || "").toUpperCase().trim();
    if (timeUpper === "FT" || timeUpper === "FRO" || timeUpper === "FINISHED") continue;

    if (currentMin < TEMP_MIN_MINUTE || currentMin >= 99) continue; 

    // No timeline events yet -> require a real live tracker (not just a betting-market
    // link). Low-tier matches (e.g. Angola Liga Bantu) have a 1win page but no tracker, so
    // they can never be analyzed — keep them out of active tracking instead of letting them
    // occupy a slot and scrape forever. A match that ALREADY has detailed events necessarily
    // has a working tracker, so it skips this gate.
    if (!match.hasDetailedEvents) {
      if (!getCachedOneWinLiveTrackerUrl(key)) {
        // Eligible by minute (>=62') but held out solely because 1win hasn't exposed a
        // live tracker / timeline yet. Low-tier feeds (reserve leagues, etc.) often surface
        // this late, which is why such matches appear in the checkzone at 85'+ instead of 62'.
        // Log once per match so a late appearance is explainable at a glance without spam.
        if (!loggedTrackerWaits.has(key)) {
          loggedTrackerWaits.add(key);
          console.log(`[CANDIDATE WAIT] ${info.home} vs ${info.away} (${currentMin}'): eligible but no 1win live tracker/timeline yet — not tracking until feed appears.`);
        }
        continue;
      }
    }

    const filterCheck = passesFilters(info, match.events);
    if (!filterCheck.passed) {
      const rejectKey = `${key}_${filterCheck.reason}`;
      if (!loggedRejections.has(rejectKey)) {
        loggedRejections.add(rejectKey);
        console.log(`[SCANNER FILTER REJECT] ${info.home} vs ${info.away} (${currentMin}'): Skipped - ${filterCheck.reason}`);
      }
      
      // AUTO-BLACKLIST ON DEVIATING CANDIDATES: Write directly to blacklist to prevent reprocessing [2]
      blacklistMatch(key); 
      continue;
    }

    candidates.push({ key, info, events: match.events, currentMin });
  }
  return candidates;
}

function updateAutoTrackedMatches() {
  const updatedList = [];
  
  for (const tracked of activeAutoMatches) {
    const cached = matchCache.get(tracked.key);
    if (!cached) {
      // 1win removed this match from its live page (gone from cache) -> drop it immediately.
      // No grace window and no delisted-match probing: once it leaves the live list it's done.
      const lastSeenMin = Number(tracked.lastSeenMatchInfo?.currentMin);
      const minLabel = Number.isFinite(lastSeenMin) ? `${lastSeenMin}'` : "unknown";
      // Same user-facing diagnostic as the FT/FINISHED path below — a match leaving 1win's live
      // list and a match flagged FT are the SAME outcome (it finished), so the exclusion log
      // shows one criterion. The distinct console line (+ no matchId blacklist, see blacklistMatch)
      // preserves the internal absence-vs-content distinction for recovery from transient gaps.
      recordRemoval(tracked, "Match completed on 1win");
      console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: No longer in 1win cache (last seen ${minLabel}).`);
      blacklistMatch(tracked.key);
      continue;
    }

    const nextAuditInfo = cloneMatchInfoForAudit(cached.info);
    const finishedAuditInfo = cached.info.phase === "FINISHED" ||
      isOneWinFinishedStatus(cached.info.phase) ||
      isOneWinFinishedStatus(cached.info.rawStatus) ||
      String(cached.info.time || "").toUpperCase().trim() === "FT";
    if (!finishedAuditInfo || nextAuditInfo.secondHalfElapsedAddedTime > 0 || nextAuditInfo.currentMin > 90) {
      tracked.lastSeenMatchInfo = nextAuditInfo;
    }

    const currentMin = getCurrentMinute(cached.info.time);
    const oneWinLive = findOneWinLiveMatchForTeams(tracked.home, tracked.away);
    const realFootballArgs = {
      league: tracked.league || cached.info.league || oneWinLive?.league,
      home: cached.info.home || tracked.home,
      away: cached.info.away || tracked.away,
      tournamentSlug: cached.info.tournamentSlug || oneWinLive?.tournamentSlug || ""
    };
    if (isNonRealFootballMatch(realFootballArgs)) {
      blacklistMatch(tracked.key);
      continue;
    }
    if (isUnderAgeMatch(realFootballArgs)) {
      logUnderAgeSkip(tracked.key, realFootballArgs.home, realFootballArgs.away, realFootballArgs.league);
      blacklistMatch(tracked.key);
      continue;
    }

    if (oneWinLive) {
      if (!tracked.league && oneWinLive.league) tracked.league = oneWinLive.league.toUpperCase();
      if (oneWinLive.oneWinUrl && !firstUsableOneWinLink(oneWinLinksCache.get(tracked.key))) oneWinLinksCache.set(tracked.key, oneWinLive.oneWinUrl);
    }
    
    // Check if match is finished on 1win
    const timeUpper = (cached.info.time || "").toUpperCase().trim();
    const isFT = cached.info.phase === "FINISHED" ||
      isOneWinFinishedStatus(cached.info.phase) ||
      isOneWinFinishedStatus(cached.info.rawStatus) ||
      ["FT", "FRO", "FINISHED", "AET", "PEN"].includes(timeUpper);
    if (isFT) {
      console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Match completed on 1win.`);
      recordRemoval(tracked, "Match completed on 1win", cached);
      blacklistMatch(tracked.key);
      continue;
    }

    // High-performance real-time clock check: drop instantly if the 1win browser tab flags "Finished"
    const finishState = oneWinMarketStateByKey.get(tracked.key);
    if (finishState && finishState.isFinished === true) {
      console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Match completed on 1win.`);
      recordRemoval(tracked, "Match completed on 1win", cached);
      blacklistMatch(tracked.key);
      continue;
    }

    if (currentMin !== null && currentMin < TEMP_MIN_MINUTE) {
      recordRemoval(tracked, `Match time fell below ${TEMP_MIN_MINUTE} minutes`, cached);
      console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Time dropped below ${TEMP_MIN_MINUTE}'.`);
      continue;
    }

    // Long-added-time retire: once the referee's announced 2nd-half board (sportcast 1104,
    // mirrored to secondHalfInjuryTime and shown on the dashboard) reads above the threshold,
    // the finish is atypically long — drop + blacklist so the card retires instead of lingering.
    const announcedAdded = Number.parseInt(cached.info.secondHalfInjuryTime, 10);
    if (Number.isFinite(announcedAdded) && announcedAdded > MAX_ANNOUNCED_ADDED_MINUTES) {
      console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Announced 2nd-half added time +${announcedAdded}' exceeds ${MAX_ANNOUNCED_ADDED_MINUTES}'.`);
      recordRemoval(tracked, LONG_ADDED_TIME_REMOVAL_REASON, cached);
      blacklistMatch(tracked.key);
      continue;
    }

    if (!tracked.scoreAt62) {
      tracked.scoreAt62 = cached.info.score || "0-0";
    }
    const initialGoals = getTotalGoals(tracked.scoreAt62);
    const currentGoals = getTotalGoals(cached.info.score);

    // Goal detection active across the 62'–90' window (90' inclusive covers stoppage time,
    // since the clock caps at 90). [3]
    if (currentMin >= 62 && currentMin <= 90 && currentGoals > initialGoals) {
      const updatedScore = cached.info.score || "0-0";
      console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Dropped instantly because score updated from ${tracked.scoreAt62} to ${updatedScore} (late goal).`);
      recordRemoval(tracked, GOAL_REMOVAL_REASON, cached);
      blacklistMatch(tracked.key);
      continue;
    }

    const filterResult = passesFilters(cached.info, cached.events);
    if (!filterResult.passed) {
      console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Failed active filters - ${filterResult.reason}`);
      recordRemoval(tracked, filterResult.reason, cached);
      
      // AUTO-BLACKLIST ON ACTIVE REMOVALS: Write directly to blacklist to prevent reprocessing [2]
      blacklistMatch(tracked.key); 
      continue;
    }

    if (cached.info.home) tracked.home = cached.info.home;
    if (cached.info.away) tracked.away = cached.info.away;

    if (currentMin >= 62) {
      if (!tracked.enteredCheckzoneAt) {
        tracked.enteredCheckzoneAt = Date.now();
        tracked.scoreAt62 = cached.info.score || "0-0";
        console.log(`[CHECKZONE] Match ${tracked.home} entered checkzone (${currentMin}'). Base score: ${tracked.scoreAt62}`);
      }

      const oneWinUrl = firstUsableOneWinLink(oneWinLinksCache.get(tracked.key), cached.info.oneWinUrl, cached.info.liveTrackerUrl);
      const elapsedInCheckzone = Date.now() - tracked.enteredCheckzoneAt;

      if (oneWinUrl === "not_found") {
        console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: No 1win betting market link found.`);
        recordRemoval(tracked, "No 1win link available", cached);
        blacklistMatch(tracked.key); 
        continue; 
      }

      const CHECKZONE_TIMEOUT = 5 * 60 * 1000; 
      if (elapsedInCheckzone > CHECKZONE_TIMEOUT && !oneWinUrl) {
        console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Timed out waiting for 1win link.`);
        recordRemoval(tracked, "No 1win link found within timeout", cached);
        blacklistMatch(tracked.key); 
        continue; 
      }

      if (!oneWinUrl && !activeOneWinSearches.has(tracked.key) && !searchQueue.some(item => item.key === tracked.key)) {
        console.log(`[CHECKZONE MATCH] Queueing link search for ${tracked.home} vs ${tracked.away} (${currentMin}').`);
        queue1winSearch(tracked.key, tracked.home, tracked.away);
      }

      if (oneWinUrl && oneWinUrl !== "not_found") {
        const marketStateForCheck = oneWinMarketStateByKey.get(tracked.key);
        const nextGoalDataForCheck = marketStateForCheck?.nextGoal;
        const ftrDataForCheck = marketStateForCheck?.fullTimeResult;

        // ── BOTH-MARKETS presence (62'-88' window) ──
        // The card is only useful while at least one of the two tracked markets is priced:
        // Full Time Result (1/X/2) or Next-goal "No Goal". It stays as long as EITHER is present.
        // Only when BOTH are absent for the 5-minute grace — while we are connected to the odds feed
        // (even if the board is empty) — is the match dropped + blacklisted. This gives both markets
        // up to 5 minutes to appear/return; if neither does, the card is retired. The window upper
        // bound is 88' (the user-watches-live endgame); never having connected to the feed at all
        // (true data gap) never penalizes it.
        let bothMarketsLapsed = false;
        // "Connected" = we have processed at least one odds-socket message for this fixture
        // (applyOneWinSocketMarketUpdate stamps connectedAt even when ZERO markets are open).
        // We deliberately do NOT require isAnyMarketActive here: low-tier matches (e.g. Cameroon
        // Elite Two) often never serve a "Total" group at all, so gating the lapse on a live market
        // meant the timer never started — a card with BOTH legs gone just sat there forever. As long
        // as we are connected to the feed, an empty board must still count toward the lapse.
        const oddsFeedConnected = !!marketStateForCheck?.connectedAt;
        // Grace-debounced: a brief suspend keeps a market "present" (no cooldown start); only a
        // sustained absence of BOTH (beyond the grace) lets the lapse timer run. Uses the same
        // helper as the dashboard so display, signal, and drop logic agree.
        const hasNoGoalMarket = isOneWinMarketActiveWithGrace(nextGoalDataForCheck);
        const hasFtrMarket = isOneWinMarketActiveWithGrace(ftrDataForCheck);
        const hasEitherMarket = hasNoGoalMarket || hasFtrMarket;

        // Stop counting absence once the clock reaches the narrow endgame window (MARKET_NARROW_MINUTE,
        // 88') or whenever the minute is unknown: from 88' on, 1win routinely suspends then re-adds the
        // end-of-match markets, and the user is already watching live on 1win — it's "user's eyes only",
        // so an absence there must never retire the card. BEFORE 88', a sustained both-legs-gone (beyond
        // the 5-min lapse) means the card has no usable signal and is dropped.
        if (!(Number.isFinite(currentMin) && currentMin < MARKET_NARROW_MINUTE)) {
          tracked.bothMarketsAbsentStartedAt = null;
        } else if (hasEitherMarket) {
          tracked.bothMarketsAbsentStartedAt = null;
        } else if (oddsFeedConnected) {
          // Connected to the odds feed but neither FTR nor No-Goal leg is priced → run the cooldown.
          if (!tracked.bothMarketsAbsentStartedAt) {
            tracked.bothMarketsAbsentStartedAt = Date.now();
          }
          if (Date.now() - tracked.bothMarketsAbsentStartedAt > BOTH_MARKETS_LAPSE_MS) {
            bothMarketsLapsed = true;
          }
        } else {
          // Never connected to this match's odds feed — don't penalize a genuine data gap.
          tracked.bothMarketsAbsentStartedAt = null;
        }
        tracked.nextGoalEligible = !bothMarketsLapsed;

        if (bothMarketsLapsed) {
          console.log(`[SCANNER DROP] ${tracked.home} vs ${tracked.away}: Dropped — no Full Time Result / No-Goal market for 5m.`);
          recordRemoval(tracked, "No FTR / Next-goal market for 5m", cached);
          blacklistMatch(tracked.key);
          continue;
        }
      }
    }

    // Write snapshot record to match-audit.jsonl (including live odds!)
    try {
      const ms = oneWinMarketStateByKey.get(tracked.key);
      const noGoalOdd = testmonNoGoalOdd(ms?.groups || [], Date.now());
      const teamOdds = testmonTeamNextGoalOdds(ms?.groups || [], Date.now());
      const fullTimeOdds = parseOneWinSocketFullTimeResultOddsGroups(ms?.groups || []);

      const eventCounts = { goal: 0, corner: 0, yellow: 0, red: 0, substitution: 0 };
      if (cached && Array.isArray(cached.events)) {
        for (const e of cached.events) {
          if (e.type === "goal") eventCounts.goal++;
          else if (e.type === "corner") eventCounts.corner++;
          else if (e.type === "yellow") eventCounts.yellow++;
          else if (e.type === "red") eventCounts.red++;
          else if (e.type === "substitution") eventCounts.substitution++;
        }
      }

      appendMatchAuditRow({
        id: `snapshot:${tracked.matchId || tracked.key}:${Date.now()}`,
        type: "snapshot",
        matchAuditId: String(tracked.matchId || ""),
        key: tracked.key,
        matchId: String(tracked.matchId || ""),
        home: tracked.home,
        away: tracked.away,
        league: tracked.league || "",
        timestamp: Date.now(),
        minute: currentMin,
        time: cached.info.time || "",
        score: cached.info.score || "0-0",
        eventCount: (cached.events || []).length,
        eventCounts,
        officialAddedTime: Number.parseInt(cached.info.secondHalfInjuryTime, 10) || 0,
        firstHalfAddedTime: Number.parseInt(cached.info.firstHalfInjuryTime, 10) || 0,
        clockAddedTime: Number.parseInt(cached.info.secondHalfElapsedAddedTime, 10) || 0,
        noGoalOdd,
        teamOdds,
        fullTimeOdds,
        activeMarketsCount: ms ? (ms.availableMarketsList || []).length : 0,
        activeMarkets: ms ? (ms.availableMarketsList || []) : []
      });
    } catch (err) {
      console.warn(`[MATCH AUDIT] Snapshot write failed for ${tracked.home} vs ${tracked.away}: ${err.message}`);
    }

    updatedList.push(tracked);
  }
  
  activeAutoMatches = updatedList;

  const activeAutoKeys = new Set(activeAutoMatches.map(m => m.key));
  for (let i = searchQueue.length - 1; i >= 0; i--) {
    if (!activeAutoKeys.has(searchQueue[i].key)) {
      searchQueue.splice(i, 1);
    }
  }

  const candidates = getCandidates();
  const isAlreadyTracked = (key) => activeAutoMatches.some(m => m.key === key);
  // Guard the dashboard against same-fixture duplicates: if a 1win rename briefly left a
  // stale name-key in matchCache, its candidate must not be promoted as a SECOND card for
  // a matchId already tracked — that second card is the one the odds socket can't feed
  // (matchId->key routing is last-write-wins).
  const trackedMatchIds = new Set(
    activeAutoMatches.map(m => String(m.matchId || "")).filter(id => /^\d+$/.test(id))
  );

  for (const cand of candidates) {
    if (activeAutoMatches.length >= 30) break;
    if (isAlreadyTracked(cand.key)) continue;
    const candMatchId = String(cand.info.matchId || "");
    if (/^\d+$/.test(candMatchId) && trackedMatchIds.has(candMatchId)) continue;

    // Discovered too late to be useful: a fixture first seen at/after LATE_APPEARANCE_MINUTE leaves
    // almost no lead time before the 90' freeze (typically a low-tier feed 1win surfaced very late).
    // It fails our usefulness rule, so it never reaches the dashboard. Blacklist (2h TTL ≈ rest of
    // this match) so it isn't reconsidered every monitor cycle. Matches already tracked from earlier
    // are unaffected — the isAlreadyTracked guard above means only freshly-discovered candidates
    // reach this check, so a legitimately-tracked match passing 85' is never dropped here.
    // Skip the late-discovery guard for the startup grace window so a restart re-adopts matches that
    // were already live (and past LATE_APPEARANCE_MINUTE) instead of blacklisting them off the board.
    if (process.uptime() >= LATE_APPEARANCE_STARTUP_GRACE_SEC &&
        Number.isFinite(cand.currentMin) && cand.currentMin >= LATE_APPEARANCE_MINUTE) {
      console.log(`[POOL SKIP] ${cand.info.home} vs ${cand.info.away} (${cand.currentMin}'): discovered too late (>=${LATE_APPEARANCE_MINUTE}') — not added to dashboard.`);
      blacklistMatch(cand.key, candMatchId);
      continue;
    }

    console.log(`[POOL ALLOCATION] Adding active match: ${cand.info.home} vs ${cand.info.away} (${cand.currentMin}')`);
    const oneWinLive = findOneWinLiveMatchForTeams(cand.info.home, cand.info.away);
    if (oneWinLive && oneWinLive.oneWinUrl) {
      oneWinLinksCache.set(cand.key, oneWinLive.oneWinUrl);
    }

    activeAutoMatches.push({
      key: cand.key,
      home: cand.info.home,
      away: cand.info.away,
      matchId: cand.info.matchId,
      matchPath: cand.info.matchPath || `match_live/${cand.info.matchId}`,
      addedAt: Date.now(),
      enteredCheckzoneAt: null,
      scoreAt62: cand.info.score || "0-0",
      league: oneWinLive && oneWinLive.league ? oneWinLive.league.toUpperCase() : (cand.info.league ? cand.info.league.toUpperCase() : null),
      url: firstUsableOneWinLink(cand.info.oneWinUrl, oneWinLinksCache.get(cand.key)) || `https://1wlgk.com/betting/live/soccer-18?mid=${makeOneWinSyntheticMid(cand.info.home, cand.info.away)}`
    });
    if (/^\d+$/.test(candMatchId)) trackedMatchIds.add(candMatchId);
  }

  for (const m of activeAutoMatches) activeTrackedMatches.set(m.key, Date.now());

  scheduleDashboardBroadcast(250);
}

// 1win match links come exclusively from the live API list now (the browser search that used to
// scrape the site for a link is gone). If the API doesn't already carry a link for this fixture
// there is nothing else to try, so resolve it immediately rather than queueing a lookup.
function queue1winSearch(key, home, away) {
  if (firstUsableOneWinLink(oneWinLinksCache.get(key))) return;

  const liveMatch = findOneWinLiveMatchForTeams(home, away);
  if (liveMatch && liveMatch.oneWinUrl && !isNonRealFootballMatch({ league: liveMatch.league, home: liveMatch.home, away: liveMatch.away, tournamentSlug: liveMatch.tournamentSlug || "" })) {
    oneWinLinksCache.set(key, liveMatch.oneWinUrl);
    console.log(`[1win SEARCH] Fast-linked from live API: ${home} vs ${away}`);
    scheduleDashboardBroadcast();
    return;
  }

  oneWinLinksCache.set(key, "not_found");
  if (!loggedPending.has(key)) {
    loggedPending.add(key);
    console.log(`[1win SEARCH] No API link for ${home} vs ${away}.`);
  }
}

// ── Web Push helpers ─────────────────────────────────────────────────────
function loadVapidKeys() {
  try {
    if (fs.existsSync(VAPID_PATH)) {
      const parsed = JSON.parse(fs.readFileSync(VAPID_PATH, "utf8"));
      if (parsed.publicKey && parsed.privateKey) return parsed;
    }
  } catch (err) {
    console.warn("[PUSH] Failed reading VAPID keys, regenerating:", err.message);
  }
  const generated = webpush.generateVAPIDKeys();
  try {
    fs.writeFileSync(VAPID_PATH, JSON.stringify(generated), "utf8");
  } catch (err) {
    console.warn("[PUSH] Could not persist VAPID keys (subscriptions won't survive restart):", err.message);
  }
  return generated;
}

function loadPushSubscriptions() {
  try {
    if (fs.existsSync(PUSH_SUBSCRIPTIONS_PATH)) {
      const parsed = JSON.parse(fs.readFileSync(PUSH_SUBSCRIPTIONS_PATH, "utf8"));
      if (Array.isArray(parsed)) return parsed.map(migratePushSubscriptionRecord);
    }
  } catch (err) {
    console.warn("[PUSH] Failed reading subscriptions:", err.message);
  }
  return [];
}

// Older records carried a single `muted` flag (and, before the Under market was removed,
// a `mutedUnder` flag). The 90' No-Goal alert is now the only push, gated by mutedNextGoal.
function migratePushSubscriptionRecord(rec) {
  if (!rec || typeof rec !== "object") return rec;
  if (rec.mutedNextGoal === undefined) rec.mutedNextGoal = rec.muted === true;
  delete rec.muted;
  delete rec.mutedUnder;
  return rec;
}

function savePushSubscriptions() {
  try {
    fs.writeFileSync(PUSH_SUBSCRIPTIONS_PATH, JSON.stringify(pushSubscriptions), "utf8");
  } catch (err) {
    console.warn("[PUSH] Could not persist subscriptions:", err.message);
  }
}

function initWebPush() {
  vapidKeys = loadVapidKeys();
  pushSubscriptions = loadPushSubscriptions();
  webpush.setVapidDetails(VAPID_SUBJECT, vapidKeys.publicKey, vapidKeys.privateKey);
  console.log(`[PUSH] Web Push ready | ${pushSubscriptions.length} subscription(s) loaded`);
}

// `mutes` carries the per-type flags to apply. Any flag left undefined is
// preserved from the existing record (or defaults to muted for a brand-new one).
function upsertPushSubscription(subscription, mutes = {}) {
  if (!subscription || !subscription.endpoint) return false;
  const idx = pushSubscriptions.findIndex(s => s.endpoint === subscription.endpoint);
  const prev = idx >= 0 ? pushSubscriptions[idx] : null;
  const pick = (val, prevVal) => val === undefined ? (prevVal !== undefined ? prevVal : true) : val === true;
  const record = {
    endpoint: subscription.endpoint,
    keys: subscription.keys || {},
    mutedNextGoal: pick(mutes.mutedNextGoal, prev && prev.mutedNextGoal),
    createdAt: prev ? prev.createdAt : Date.now()
  };
  if (idx >= 0) pushSubscriptions[idx] = record;
  else pushSubscriptions.push(record);
  savePushSubscriptions();
  return true;
}

function removePushSubscription(endpoint) {
  const before = pushSubscriptions.length;
  pushSubscriptions = pushSubscriptions.filter(s => s.endpoint !== endpoint);
  if (pushSubscriptions.length !== before) savePushSubscriptions();
}

function setPushSubscriptionMuted(endpoint, mutes = {}) {
  const sub = pushSubscriptions.find(s => s.endpoint === endpoint);
  if (!sub) return false;
  if (mutes.mutedNextGoal !== undefined) sub.mutedNextGoal = mutes.mutedNextGoal === true;
  savePushSubscriptions();
  return true;
}

// `mutedField` selects which per-type flag gates this push (only "mutedNextGoal" now).
async function sendPushToAll(payloadObj, mutedField = "mutedNextGoal") {
  if (pushSubscriptions.length === 0) return;
  const payload = JSON.stringify(payloadObj);
  const targets = pushSubscriptions.filter(s => s[mutedField] !== true);
  if (targets.length === 0) return;

  const dead = [];
  await Promise.all(targets.map(async sub => {
    try {
      // urgency:"high" tells FCM/APNs to wake the device NOW instead of batching
      // for power-saving — without it, Android (FCM, esp. MIUI/Redmi) delays delivery
      // by minutes while iOS (APNs) stays instant. TTL caps how long a push may sit
      // queued: a 78' alert is useless if it lands at 95', so drop it after 10 min.
      await webpush.sendNotification(
        { endpoint: sub.endpoint, keys: sub.keys },
        payload,
        { urgency: "high", TTL: 600 }
      );
    } catch (err) {
      // 404/410 = subscription expired or was revoked by the browser.
      if (err.statusCode === 404 || err.statusCode === 410) dead.push(sub.endpoint);
      else console.warn("[PUSH] Send failed:", err.statusCode || err.message);
    }
  }));

  if (dead.length > 0) {
    pushSubscriptions = pushSubscriptions.filter(s => !dead.includes(s.endpoint));
    savePushSubscriptions();
    console.log(`[PUSH] Pruned ${dead.length} expired subscription(s)`);
  }
}

// Fired every cache loop (every ~3s, even with zero page viewers): detect the
// moment a tracked live match crosses PUSH_ALERT_MINUTE and push once per match.
function evaluatePushTriggers(payload) {
  if (!payload || !Array.isArray(payload.matches)) return;

  const anyArmed = field => pushSubscriptions.some(s => s[field] !== true);
  const liveMids = new Set();

  for (const match of payload.matches) {
    const info = match.matchInfo || {};
    const phaseUpper = String(info.phase || "").toUpperCase();
    const isFinished = phaseUpper.includes("FINISHED") || phaseUpper.includes("FT") || phaseUpper.includes("FRO");
    const isScheduled = phaseUpper.includes("SCHEDULED") || phaseUpper.includes("WAITING") || phaseUpper.includes("AM") || phaseUpper.includes("PM");
    if (isFinished || isScheduled) continue;

    const currentMin = Number.isFinite(info.currentMin) ? info.currentMin : getCurrentMinute(info.time);
    if (!Number.isFinite(currentMin)) continue;

    const mid = match.mid;
    liveMids.add(mid);
    const home = match.home || info.home || "Home";
    const away = match.away || info.away || "Away";
    const score = info.score || "";

    // ── Next-goal "No Goal" alert ── fire the moment sportcast announces the 2nd-half
    // added-time board (event 1104 → boardSecondHalfAddedTime), not at a fixed 90'. Only
    // while the next-goal market is live, and only for matches we saw live BEFORE the board
    // went up (so a match picked up already in announced stoppage time doesn't alert late).
    const bothMarketsActive = match.fullTimeState === "active" && match.nextGoalState === "active";
    const board = positiveInt(info.boardSecondHalfAddedTime, 15) || positiveInt(info.secondHalfInjuryTime, 15);
    // An announced board over the threshold (> 5') is an atypically long finish — the scanner
    // retires that card (LONG_ADDED_TIME_REMOVAL_REASON), so suppress the alert here too rather
    // than fire on the same tick the long board appears, before the drop lands.
    if (!board) {
      pushSeenBeforeBoard.add(mid);
    } else if (board <= MAX_ANNOUNCED_ADDED_MINUTES && bothMarketsActive && !pushedNextGoalMatches.has(mid) && pushSeenBeforeBoard.has(mid) && anyArmed("mutedNextGoal")) {
      pushedNextGoalMatches.add(mid);
      console.log(`[PUSH] +${board}' stoppage time announced: ${home} vs ${away} — notifying Next-goal subscribers`);
      sendPushToAll({
        title: `+${board}' Stoppage Time — ${home} vs ${away}`,
        body: score ? `Score ${score}. Next-goal "No Goal" window.` : `Next-goal "No Goal" window.`,
        tag: `stoppage-${mid}`,
        url: "/"
      }, "mutedNextGoal").catch(err => console.warn("[PUSH] dispatch error:", err.message));
    }
  }

  // Forget matches that have left the dashboard so memory stays bounded and a
  // future match reusing the id can re-arm.
  for (const mid of [...pushSeenBeforeBoard]) if (!liveMids.has(mid)) pushSeenBeforeBoard.delete(mid);
  for (const mid of [...pushedNextGoalMatches]) if (!liveMids.has(mid)) pushedNextGoalMatches.delete(mid);
}

// Matches that are live and real-football but haven't yet reached the analysis
// window (below TEMP_MIN_MINUTE). They run through every standard filter the
// analyzer uses — blacklist, non-real-football, finished, red card, and the
// "match tracker must be available" gate — EXCEPT the 62'–90' late-goal window,
// which can never apply below 62' anyway.
function buildAwaitingQueue() {
  const awaiting = [];

  for (const [key, match] of matchCache.entries()) {
    const info = match.info;
    if (!info) continue;

    if (isBlacklisted(key)) continue;
    if (isNonRealFootballMatch({ league: info.league, home: info.home, away: info.away, tournamentSlug: info.tournamentSlug || "" })) continue;
    if (info.phase === "FINISHED") continue;

    const timeUpper = (info.time || "").toUpperCase().trim();
    if (timeUpper === "FT" || timeUpper === "FRO" || timeUpper === "FINISHED") continue;

    const currentMin = getCurrentMinute(info.time);
    // Only live matches that are below the analysis window belong in the queue.
    if (currentMin === null || currentMin < 1 || currentMin >= TEMP_MIN_MINUTE) continue;

    // Match-tracker gate: the match must expose a real live tracker — the same feed
    // the analyzer needs for timeline events. A betting-market link alone is NOT enough:
    // low-tier matches (e.g. Angola Liga Bantu) have a 1win page but no tracker, so they
    // can never be analyzed and must stay out of the queue.
    const liveTrackerUrl = getCachedOneWinLiveTrackerUrl(key);
    if (!liveTrackerUrl) continue;

    // Display link for the 1W button (the tracker URL itself is a fine fallback).
    const oneWinUrl = firstUsableOneWinLink(oneWinLinksCache.get(key), info.oneWinUrl, liveTrackerUrl);
    if (!oneWinUrl || oneWinUrl === "not_found") continue;

    // Red-card detection + every other standard filter. The late-goal window
    // inside passesFilters short-circuits below 62', so it never fires here.
    const filterCheck = passesFilters(info, match.events, null);
    if (!filterCheck.passed) continue;

    awaiting.push({
      mid: key.replace(/[^a-z0-9]/g, "_"),
      matchId: String(info.matchId || ""),
      home: info.home,
      away: info.away,
      league: info.league || null,
      score: info.score || "0-0",
      time: info.time || "",
      currentMin,
      minutesUntilAnalysis: Math.max(0, TEMP_MIN_MINUTE - currentMin),
      oneWinUrl
    });
  }

  // Closest to the analysis window first.
  awaiting.sort((a, b) => b.currentMin - a.currentMin);

  // Collapse any residual same-fixture duplicates: during a 1win team-name reformat a
  // stale name-key can briefly co-exist with the canonical key before it ages out of
  // matchCache. Keep one row per stable matchId (the highest minute survives the sort).
  const seenMatchIds = new Set();
  const deduped = [];
  for (const entry of awaiting) {
    if (/^\d+$/.test(entry.matchId)) {
      if (seenMatchIds.has(entry.matchId)) continue;
      seenMatchIds.add(entry.matchId);
    }
    deduped.push(entry);
  }
  return deduped;
}

function buildDashboardPayload() {
  const matches = [];
  // Keys/matchIds of fixtures live on the dashboard this build, used to evict their stale
  // exclusion-log entries below: a match that was dropped (e.g. "No FTR / Next-goal market")
  // and then came back alive once its markets reappeared must not keep showing as removed.
  const liveKeys = new Set();
  const liveMatchIds = new Set();

  for (const m of activeAutoMatches) {
    const cached = matchCache.get(m.key);
    if (!cached) continue;
    const dashboardLink =
      firstUsableOneWinLink(oneWinLinksCache.get(m.key)) ||
      cached.info?.oneWinUrl ||
      cached.info?.liveTrackerUrl ||
      (m.url && !m.url.includes("mid=onewin_") ? m.url : null);

    const timelineReady = cached.trackerTimelineReady === true || cached.hasDetailedEvents === true;
    if (!timelineReady) continue;

    const filterResult = passesFilters(cached.info, cached.events);
    if (!filterResult.passed) {
      // A match that has never appeared is filtered out silently — it simply never shows
      // (no card, so no removal toast is wanted), and we must not flash it on the board.
      //
      // But once a card is LIVE on the board, do NOT drop it here. This builder runs on every
      // broadcast — including 50ms-debounced odds-socket ticks — far faster than the 3s monitor
      // loop. The removal REASON is only ever recorded by recordRemoval() in that monitor loop
      // (updateAutoTrackedMatches), so dropping the card here strands its disappearance ahead of
      // its reason: the user sees the card vanish, then waits seconds for the toast explaining why.
      // Leaving an appeared-but-now-failing card visible until the monitor loop drops it (≤3s,
      // applying the identical passesFilters) means the card-removal and its toast ship in the SAME
      // payload — the reason shows the instant the card leaves.
      if (!m.hasAppeared) continue;
    }

    // Persist the resolved display link on the tracked object so a later removal
    // (where caches may be evicted) can still report the exact link the card showed.
    if (dashboardLink && dashboardLink !== "not_found" && !dashboardLink.includes("mid=onewin_")) {
      m.displayOneWinUrl = dashboardLink;
    }

    if (!m.hasAppeared) {
      const oneWinUrl = dashboardLink;
      const hasUrl = oneWinUrl && oneWinUrl !== "not_found";
      const displayLeague = m.league || cached.info?.league || "";
      const hasLeague = typeof displayLeague === "string" && displayLeague.trim().length > 0;

      if (hasUrl && hasLeague) {
        m.hasAppeared = true;
        console.log(`[DASHBOARD SHOW] ${cached.info.home || m.home} vs ${cached.info.away || m.away}: timeline ready, filters passed.`);
      } else {
        continue;
      }
    }

    const marketNow = Date.now();
    const oneWinUrl = dashboardLink;
    const nextGoalMin = getCurrentMinute(cached.info.time);
    const nextGoalInWindow = nextGoalMin !== null && nextGoalMin >= TEMP_MIN_MINUTE;

    // The main dashboard intentionally uses the same per-match odds evaluator as /backtest.
    // That keeps displayed FTR, displayed No Goal, the other-market count, and the entry glow
    // on one source of truth instead of a parallel dashboard-only interpretation of 1win deltas.
    const dashboardBoardSeen = Math.max(
      testMonitor.boardSeen.get(m.key) || 0,
      Number.parseInt(cached.info.secondHalfInjuryTime, 10) || 0
    );
    if (dashboardBoardSeen > 0) testMonitor.boardSeen.set(m.key, dashboardBoardSeen);
    const noGoalEntry = testmonEvaluate(m, cached, marketNow, dashboardBoardSeen);
    // A full-event suspend hides BOTH market rows (the card shows only the suspend banner). FTR
    // odds are already empty from the evaluator when suspended; gate the states here too so intent
    // is explicit and Next-goal is covered as well.
    const suspended = noGoalEntry.eventSuspended === true;

    const fullTimeOdds = (!suspended && Array.isArray(noGoalEntry.fullTimeOdds) && noGoalEntry.fullTimeOdds.length)
      ? noGoalEntry.fullTimeOdds
      : null;
    const fullTimeState = (!suspended && nextGoalInWindow && fullTimeOdds) ? "active" : "off";

    // Next-goal: shown as three inline badges like FTR — [home scores next · No Goal · away scores
    // next] — while the MARKET is live (No-Goal OR team legs present). Display-only; the bet gate
    // (noGoalEntry.gates.noGoal) still reads the live No-Goal odd, so the visual can't fire a bet.
    const nextGoalThree = orderNextGoalThree(
      noGoalEntry.noGoalOdd, noGoalEntry.teamOdds, cached.info.home || m.home, cached.info.away || m.away
    );
    const nextGoalOdds = (!suspended && noGoalEntry.nextGoalMarketActive && nextGoalThree.length)
      ? nextGoalThree
      : null;
    const nextGoalState = (!suspended && nextGoalInWindow && noGoalEntry.nextGoalMarketActive && nextGoalThree.length) ? "active" : "off";
    // Suspend + open-market count come straight from the evaluator, which checks both the
    // socket-stamped suspendedAt AND the stored groups directly (so a silent socket during a
    // real suspension is caught within one monitor loop). No DOM/page scrape is involved.
    const otherMarketsList = noGoalEntry.otherMarketsList;
    // On a full-event suspend the other markets are frozen, not gone — show the count as 0 rather
    // than nulling it (which dropped the row from the card entirely). Entry stays blocked via the
    // separate eventSuspended gate (dashboardGates.twoMarkets already requires !eventSuspended), so
    // this is display-only.
    const otherMarketsRemaining = noGoalEntry.eventSuspended ? 0 : otherMarketsList.length;
    // Every other market with its live legs/odds, for the card's compact all-markets list. Already
    // [] when the event is suspended (the evaluator freezes it), so the card shows only the banner.
    const otherMarkets = noGoalEntry.otherMarketsDetailed || [];
    const dashboardGates = { ...noGoalEntry.gates };
    const betSignal = dashboardGates.board && dashboardGates.twoMarkets && dashboardGates.noGoal && dashboardGates.teams && dashboardGates.teamBalance && dashboardGates.timing;

    matches.push({
      mid: m.key.replace(/[^a-z0-9]/g, "_"),
      home: cached.info.home || m.home,
      away: cached.info.away || m.away,
      matchInfo: cached.info,
      events: cached.events || [],
      nextGoalOdds,
      nextGoalState,
      // Eligibility (gates the stoppage-time alert) tracks the in-window clock, NOT the section's
      // display state — so an in-window match whose market is temporarily hidden still alerts when
      // its added-time board is announced.
      nextGoalEligible: nextGoalInWindow,
      fullTimeOdds,
      fullTimeState,
      eventSuspended: suspended,
      betSignal,
      noGoalEntrySignal: betSignal,
      noGoalEntryGates: dashboardGates,
      noGoalEntryBoard: noGoalEntry.board,
      noGoalEntryNoGoalOdd: noGoalEntry.noGoalOdd,
      noGoalEntryTeamOdds: noGoalEntry.teamOdds,
      otherMarketsRemaining,
      otherMarketsList,
      otherMarkets,
      oneWinUrl,
      hasDetailedEvents: cached.hasDetailedEvents === true,
      trackerTimelineReady: timelineReady,
      timelinePending: false,
      league: m.league || cached.info?.league || null
    });

    liveKeys.add(m.key);
    const liveMatchId = String(cached.info?.matchId || m.matchId || "").trim();
    if (/^\d+$/.test(liveMatchId)) liveMatchIds.add(liveMatchId);
  }

  // A re-listed match invalidates its own earlier removal: clear any exclusion-log entry
  // for a fixture that is once again showing as a live card (matched by key, or by stable
  // matchId in case 1win reformatted the team names while it was gone).
  if (recentRemovals.length) {
    recentRemovals = recentRemovals.filter(
      r => !(liveKeys.has(r.key) || (r.matchId && liveMatchIds.has(r.matchId)))
    );
  }

  return { matches, recentRemovals, awaiting: buildAwaitingQueue(), serverTime: Date.now() };
}

function writeDashboardEvent(res, payload = buildDashboardPayload()) {
  res.write(`event: dashboard\ndata: ${JSON.stringify(payload)}\n\n`);
}

function broadcastDashboardNow() {
  if (dashboardClients.size === 0 && dashboardWsClients.size === 0) return;
  let payload;
  try {
    payload = buildDashboardPayload();
  } catch (err) {
    console.error("[STREAM ERROR] Failed building dashboard payload:", err.message);
    return;
  }

  for (const res of dashboardClients) {
    try {
      writeDashboardEvent(res, payload);
    } catch {
      dashboardClients.delete(res);
    }
  }

  // Primary path: push the same payload to every WebSocket client instantly. The state was already
  // updated in real time by the 1win odds socket, and scheduleDashboardBroadcast fires this within
  // ~50ms of a change, so the browser sees it in ~100ms — no 1.5s poll wait.
  if (dashboardWsClients.size > 0) {
    const json = JSON.stringify(payload);
    for (const ws of dashboardWsClients) {
      if (ws.readyState !== ws.OPEN) { dashboardWsClients.delete(ws); continue; }
      try { ws.send(json); } catch { dashboardWsClients.delete(ws); }
    }
  }
}

function scheduleDashboardBroadcast(delay = 150) {
  if (dashboardBroadcastTimer) return;
  dashboardBroadcastTimer = setTimeout(() => {
    dashboardBroadcastTimer = null;
    broadcastDashboardNow();
  }, delay);
}

app.get("/api/auto-matches", (req, res) => {
  try {
    res.json(buildDashboardPayload());
  } catch (err) {
    console.error("[API ERROR] Failed returning dashboard sync:", err.message);
    res.status(500).json({ error: "Sync failed" });
  }
});

// The permanent system log — opened by the dashboard's export button. Pretty-printed so it reads
// well in a browser tab or a downloaded file; never cached so a reload always shows the latest.
app.get("/api/system-log.json", (req, res) => {
  try {
    res.set("Cache-Control", "no-store, max-age=0");
    res.set("Content-Type", "application/json; charset=utf-8");
    res.send(JSON.stringify(buildSystemLogDocument(), null, 2));
  } catch (err) {
    console.error("[API ERROR] Failed returning system log:", err.message);
    res.status(500).json({ error: "System log unavailable" });
  }
});

// Odds log — raw JSONL download. One JSON record per line; newest entries at end of file.
// Useful for post-match inspection: filter by key or matchId, group by minute.
app.get("/api/odds-log.jsonl", (req, res) => {
  try {
    res.set("Cache-Control", "no-store, max-age=0");
    res.set("Content-Type", "application/x-ndjson; charset=utf-8");
    if (!fs.existsSync(ODDS_LOG_PATH)) return res.status(404).json({ error: "No odds log yet" });
    res.sendFile(ODDS_LOG_PATH);
  } catch (err) {
    console.error("[API ERROR] Failed returning odds log:", err.message);
    res.status(500).json({ error: "Odds log unavailable" });
  }
});

// Match audit log — raw JSONL download containing snapshots and outcomes.
app.get("/api/match-audit.jsonl", (req, res) => {
  try {
    res.set("Cache-Control", "no-store, max-age=0");
    res.set("Content-Type", "application/x-ndjson; charset=utf-8");
    if (!fs.existsSync(MATCH_AUDIT_PATH)) return res.status(404).json({ error: "No match audit log yet" });
    res.sendFile(MATCH_AUDIT_PATH);
  } catch (err) {
    console.error("[API ERROR] Failed returning match audit log:", err.message);
    res.status(500).json({ error: "Match audit log unavailable" });
  }
});

app.get("/api/push/public-key", (req, res) => {
  if (!vapidKeys) return res.status(503).json({ error: "Push not initialized" });
  res.json({ publicKey: vapidKeys.publicKey });
});

// Accepts the No-Goal mute flag. For backwards compat a single `muted` boolean
// (and the legacy `mutedUnder`) still map onto it.
function resolveMuteFlags(body) {
  const mutes = {};
  if (body.mutedNextGoal !== undefined) mutes.mutedNextGoal = body.mutedNextGoal === true;
  if (mutes.mutedNextGoal === undefined && body.muted !== undefined) {
    mutes.mutedNextGoal = body.muted === true;
  }
  return mutes;
}

app.post("/api/push/subscribe", (req, res) => {
  const body = req.body || {};
  const { subscription, oldEndpoint } = body;
  if (!subscription || !subscription.endpoint) {
    return res.status(400).json({ error: "Invalid subscription" });
  }
  let mutes = resolveMuteFlags(body);
  // Endpoint rotation (pushsubscriptionchange on MIUI/FCM): carry the previous
  // mute flags onto the new record and drop the dead one, so the device keeps its
  // armed/muted state across the rotation instead of resetting.
  if (oldEndpoint && oldEndpoint !== subscription.endpoint) {
    const old = pushSubscriptions.find(s => s.endpoint === oldEndpoint);
    if (old) {
      if (mutes.mutedNextGoal === undefined) mutes.mutedNextGoal = old.mutedNextGoal;
    }
    removePushSubscription(oldEndpoint);
  }
  if (!upsertPushSubscription(subscription, mutes)) {
    return res.status(400).json({ error: "Invalid subscription" });
  }
  res.json({ ok: true });
});

app.post("/api/push/mute", (req, res) => {
  const body = req.body || {};
  const { subscription, endpoint } = body;
  const mutes = resolveMuteFlags(body);
  // Prefer the full subscription so a toggle can RE-CREATE a record whose
  // endpoint rotated out from under the server — otherwise the lookup-by-endpoint
  // below silently no-ops and the device stays muted forever. Fall back to
  // endpoint-only for older clients that don't send the subscription.
  if (subscription && subscription.endpoint) {
    upsertPushSubscription(subscription, mutes);
    return res.json({ ok: true });
  }
  if (!endpoint) return res.status(400).json({ error: "Missing endpoint" });
  const updated = setPushSubscriptionMuted(endpoint, mutes);
  res.json({ ok: updated });
});

app.post("/api/push/unsubscribe", (req, res) => {
  const { endpoint } = req.body || {};
  if (endpoint) removePushSubscription(endpoint);
  res.json({ ok: true });
});

app.get("/api/dashboard-stream", (req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no"
  });
  res.write(": connected\n\n");
  dashboardClients.add(res);

  try {
    writeDashboardEvent(res);
  } catch {
    dashboardClients.delete(res);
  }

  const heartbeat = setInterval(() => {
    try {
      res.write(": heartbeat\n\n");
    } catch {
      clearInterval(heartbeat);
      dashboardClients.delete(res);
    }
  }, 15000);

  req.on("close", () => {
    clearInterval(heartbeat);
    dashboardClients.delete(res);
  });
});

app.get("/api/onewin-live-matches", (req, res) => {
  try {
    const matches = Array.from(oneWinLiveMatchesCache.values())
      .sort((a, b) => (b.currentMin || 0) - (a.currentMin || 0))
      .map(item => ({
        key: item.key,
        home: item.home,
        away: item.away,
        league: item.league,
        score: item.score,
        time: item.time,
        phase: item.phase,
        currentMin: item.currentMin,
        matchTimeMs: item.matchTimeMs,
        secondHalfElapsedAddedTime: item.secondHalfElapsedAddedTime,
        secondHalfInjuryTime: item.secondHalfInjuryTime,
        oneWinUrl: item.oneWinUrl,
        matchId: item.matchId,
        rawStatus: item.rawStatus,
        source: item.source,
        lastUpdated: item.lastUpdated
      }));

    res.json({
      count: matches.length,
      lastRefreshAt: lastOneWinLiveRefreshAt,
      matches
    });
  } catch (err) {
    console.error("[API ERROR] Failed returning 1win live matches:", err.message);
    res.status(500).json({ error: "1win live sync failed" });
  }
});

const cleanupAllPools = async () => {
  isShuttingDown = true;
  isCacheLoopRunning = false;
  if (cacheLoopTimer) {
    clearTimeout(cacheLoopTimer);
    cacheLoopTimer = null;
  }
  if (dashboardBroadcastTimer) {
    clearTimeout(dashboardBroadcastTimer);
    dashboardBroadcastTimer = null;
  }
  if (oneWinOddsSnapshotTimer) {
    clearTimeout(oneWinOddsSnapshotTimer);
    oneWinOddsSnapshotTimer = null;
  }
  closeOneWinLiveInfoSocket();
  oneWinLiveInfoSocketSignature = "";
  closeOneWinOddsSocket();
  oneWinOddsSocketSignature = "";
  closeOneWinOddsSnapshotSocket();
};

process.on("SIGINT", async () => { await cleanupAllPools(); process.exit(0); });
process.on("SIGTERM", async () => { await cleanupAllPools(); process.exit(0); });

// ───────────────────────────────────────────────────────────────────────────────────────────
// TEMPORARY  /backtest  — virtual all-in "No Goal" backtest monitor.
//
// One self-contained block: engine + 3 routes + page. To remove it entirely, delete from here to
// the marker below AND delete the single `tickTestMonitor();` call inside startOneWinMonitorLoop's
// updateLoop. Nothing else in the server references it.
//
// Strategy being simulated (user-defined, locked 2026-06-21):
//   1. A pre-filtered late-game match (the dashboard already applies every entry filter) has an
//      announced added-time board.
//   2. The 1win board has narrowed to EXACTLY two open markets — Full Time Result + Next Goal —
//      with NO other market active and the event NOT suspended.
//   3. In that two-markets-only state:  No Goal odd >= 1.05  AND  BOTH teams' next-goal odds >= 9.
//      In the board's last two added minutes a tighter No-Goal band applies: the earlier minute
//      (board-3) needs >= 1.07; the last minute (board-2) needs 1.05-1.07.
//   4. -> ENTER all-in on "No Goal". A ~3.5s entry delay (1win's real placement lag) is applied:
//      the settlement odd is RE-READ after the delay, so a price move inside that window is the
//      one that counts (matches the real "count to 3-4s" behaviour).
//   5. SETTLE AT FINISH: hold until the match is FINISHED; WIN if the final score == the entry
//      score (no further goal), otherwise LOSE.
//   6. Bankroll starts at 1000, every bet is all-in, one bet is active at a time, and a single
//      loss busts the bankroll to 0 (Reset starts a fresh run).
// ───────────────────────────────────────────────────────────────────────────────────────────
const TESTMON_START_BANKROLL = Number.parseFloat(process.env.TESTMON_START_BANKROLL || "1000");
const TESTMON_ENTRY_DELAY_MS = Number.parseInt(process.env.TESTMON_ENTRY_DELAY_MS || "3500", 10);
const TESTMON_NO_GOAL_MIN    = Number.parseFloat(process.env.TESTMON_NO_GOAL_MIN || "1.05");
const TESTMON_NO_GOAL_HIGH   = Number.parseFloat(process.env.TESTMON_NO_GOAL_HIGH || "1.07"); // last-two-minutes band ceiling
const TESTMON_TEAM_MIN       = Number.parseFloat(process.env.TESTMON_TEAM_MIN || "9");        // both teams' next-goal odds floor
const TESTMON_WATCH_MINUTE   = Number.parseInt(process.env.TESTMON_WATCH_MINUTE || "62", 10); // show run-up from here

const testMonitor = {
  bankroll: TESTMON_START_BANKROLL,
  peak: TESTMON_START_BANKROLL,
  startedAt: Date.now(),
  bets: [],            // chronological: pending -> open -> won/lost/void
  byKey: new Map(),    // key -> currently-active (pending|open) bet, one at most
  everBet: new Set(),  // keys already bet once this run (never re-enter the same fixture)
  watch: new Map(),    // key -> latest watched snapshot of a NOT-yet-bet match (for skip logging)
  skips: [],           // watched matches that finished WITHOUT a bet + why (backtest history)
  boardSeen: new Map(),// key -> highest added-time board ever shown this match (a board is never
                       //        "un-announced", so we keep the max — mirrors the main injury-time logic)
  seq: 0
};

// Persist the run to DATA_DIR so bankroll + bet/skip history survive restarts (same mechanism as the
// audit log: needs HF Persistent Storage mounted at /data, else /data is ephemeral). Only the durable
// fields are written — byKey/watch are rebuilt on load. Debounced so frequent score updates coalesce.
const TESTMON_STATE_PATH = path.join(DATA_DIR, "testmonitor-state.json");
let testMonSaveTimer = null;
function saveTestMonitor() {
  if (testMonSaveTimer) return;
  testMonSaveTimer = setTimeout(() => {
    testMonSaveTimer = null;
    try {
      fs.writeFileSync(TESTMON_STATE_PATH, JSON.stringify({
        bankroll: testMonitor.bankroll,
        peak: testMonitor.peak,
        startedAt: testMonitor.startedAt,
        bets: testMonitor.bets,
        skips: testMonitor.skips,
        everBet: Array.from(testMonitor.everBet),
        seq: testMonitor.seq
      }), "utf8");
    } catch (err) {
      console.warn(`[TESTMON] save failed: ${err.message}`);
    }
  }, 1000);
}
function loadTestMonitor() {
  if (!fs.existsSync(TESTMON_STATE_PATH)) return;
  try {
    const data = JSON.parse(fs.readFileSync(TESTMON_STATE_PATH, "utf8"));
    if (typeof data.bankroll === "number") testMonitor.bankroll = data.bankroll;
    testMonitor.peak = typeof data.peak === "number" ? data.peak : testMonitor.bankroll;
    testMonitor.startedAt = data.startedAt || testMonitor.startedAt;
    testMonitor.bets = Array.isArray(data.bets) ? data.bets : [];
    testMonitor.skips = Array.isArray(data.skips) ? data.skips : [];
    testMonitor.everBet = new Set(Array.isArray(data.everBet) ? data.everBet : []);
    testMonitor.seq = typeof data.seq === "number" ? data.seq : (testMonitor.bets.length + testMonitor.skips.length);
    // Rebuild the live tracking. A 'pending' bet never locked (no stake escrowed) and its delay timer
    // is gone -> void it. An 'open' bet had its stake escrowed; re-track it so the tick settles it at
    // finish (or immediately if the match ended during the downtime).
    for (const bet of testMonitor.bets) {
      if (bet.status === "pending") {
        bet.status = "void"; bet.result = "void";
        bet.reason = "Voided — server restarted before entry locked";
        bet.settledAt = bet.settledAt || Date.now();
      } else if (bet.status === "open") {
        testMonitor.byKey.set(bet.key, bet);
      }
    }
    console.log(`[TESTMON] Restored run from disk: ${testMonitor.bets.length} bets, ${testMonitor.skips.length} skips, bankroll ${testMonitor.bankroll.toFixed(2)}.`);
  } catch (err) {
    console.warn(`[TESTMON] load failed: ${err.message}`);
  }
}

// One-line "why it wasn't bet" from a diagnostic snapshot — lists exactly which gate(s) failed,
// or notes a fully-qualified match that was blocked because the all-in bankroll was already on
// another bet. Drives the SKIP rows in the settled history.
function testmonSkipReason(diag) {
  if (!diag) return "Left before a watch snapshot was recorded";
  const g = diag.gates;
  const fails = [];
  if (!g.board) fails.push("no added-time board announced");
  if (!g.twoMarkets) {
    if (diag.eventSuspended) fails.push("event suspended");
    else {
      const parts = [];
      if (!diag.ftrActive) parts.push("no FTR");
      if (!diag.ngActive) parts.push("no Next Goal");
      if (diag.otherMarketsRemaining > 0) parts.push(`${diag.otherMarketsRemaining} extra market${diag.otherMarketsRemaining > 1 ? "s" : ""} open`);
      fails.push(`not 2 markets (${parts.join(", ") || "—"})`);
    }
  }
  if (!g.noGoal) fails.push(`No-Goal ${diag.noGoalOdd != null ? diag.noGoalOdd.toFixed(2) + " < " + TESTMON_NO_GOAL_MIN.toFixed(2) : "n/a"}`);
  if (!g.teams) fails.push(`teams ${diag.teamOdds.length ? diag.teamOdds.map(t => t.odds.toFixed(2)).join("/") + " < " + TESTMON_TEAM_MIN : "none"}`);
  if (!g.teamBalance) fails.push(`equal team odds at NoGoal floor (${diag.teamOdds.length >= 2 ? diag.teamOdds.map(t => t.odds.toFixed(2)).join("=") : "n/a"} — requires imbalance when NoGoal = ${TESTMON_NO_GOAL_MIN.toFixed(2)})`);
  if (g.board && !g.timing) fails.push(`too early (+${diag.addedNow} < +${diag.minAddedForEntry} for +${diag.board} board)`);
  if (fails.length === 0) return "Qualified, but the all-in bankroll was already on another bet";
  return fails.join("; ");
}

function testmonHasActiveBet() {
  for (const b of testMonitor.byKey.values()) {
    if (b.status === "pending" || b.status === "open") return true;
  }
  return false;
}

// The No-Goal price, parsed from the LIVE odds groups — NOT from the retained market state, which
// keeps the last-known No-Goal odds across a suspend/close (so it would report a stale price like
// "1.86" long after the Next-goal market has actually closed). Reading from the groups with the same
// isOneWinGroupActive gate the team-leg parser uses means No-Goal and the team legs share one source
// of truth: when the Next-goal market isn't currently open (e.g. only Total + Handicap remain) this
// returns null and the gate reads "n/a" instead of contradicting "both teams: none".
function testmonNoGoalOdd(groups, now = Date.now()) {
  if (!Array.isArray(groups)) return null;
  const norm = v => String(v || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  let best = null;
  for (const group of groups) {
    if (!isOneWinNextGoalGroupName(norm(group?.name))) continue;
    if (!isOneWinGroupActive(group, now)) continue;
    for (const odd of group?.oddsList || []) {
      if (!isOneWinOddStatusOpen(odd)) continue;
      const oc = norm(odd?.outcome), nm = norm(odd?.name);
      if (!(/no goal/.test(oc) || /no goal/.test(nm) || oc === "none" || nm === "none")) continue;
      const v = Number.parseFloat(odd?.cf);
      if (!Number.isFinite(v)) continue;
      if (best === null || v < best) best = v; // keep best (lowest) if duplicated across renders
    }
  }
  return best;
}

// Team next-goal legs (everything in the Next-goal market that ISN'T "No Goal"). The canonical
// market state intentionally drops these, so read them straight from the stored raw groups using
// the same open/active gates the core parser uses.
function testmonTeamNextGoalOdds(groups, now = Date.now()) {
  if (!Array.isArray(groups)) return [];
  const norm = v => String(v || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  const out = [];
  for (const group of groups) {
    if (!isOneWinNextGoalGroupName(norm(group?.name))) continue;
    if (!isOneWinGroupActive(group, now)) continue;
    for (const odd of group?.oddsList || []) {
      if (!isOneWinOddStatusOpen(odd)) continue;
      const oc = norm(odd?.outcome), nm = norm(odd?.name);
      if (/no goal/.test(oc) || /no goal/.test(nm) || oc === "none" || nm === "none") continue;
      const v = Number.parseFloat(odd?.cf);
      if (!Number.isFinite(v)) continue;
      const label = String(odd?.outcome || odd?.name || "Team").replace(/\s+/g, " ").trim();
      out.push({ label, odds: v });
    }
  }
  // De-dupe identical labels across delta renders, keeping the best (lowest) price.
  const byLabel = new Map();
  for (const t of out) {
    const ex = byLabel.get(t.label);
    if (!ex || t.odds < ex.odds) byLabel.set(t.label, t);
  }
  return Array.from(byLabel.values());
}

// Order the Next-goal market like 1/X/2 for display: [home-scores-next, No Goal, away-scores-next].
// Team legs arrive as {label, odds}; map them to home/away by fuzzy name match, falling back to feed
// order. Display-only — the bet gates still read noGoalOdd / teamOdds separately.
function orderNextGoalThree(noGoalOdd, teamOdds, home, away) {
  const norm = s => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  const teams = Array.isArray(teamOdds) ? teamOdds.slice() : [];
  const pick = name => {
    const t = norm(name);
    if (!t) return null;
    const idx = teams.findIndex(o => { const l = norm(o.label); return l && (l === t || l.includes(t) || t.includes(l)); });
    return idx === -1 ? null : teams.splice(idx, 1)[0];
  };
  let h = pick(home);
  let a = pick(away);
  if (!h && teams.length) h = teams.shift();   // fallback: remaining legs in feed order
  if (!a && teams.length) a = teams.shift();
  const out = [];
  if (h) out.push({ outcome: "home", odds: h.odds });
  if (noGoalOdd !== null && noGoalOdd !== undefined) out.push({ outcome: "No Goal", odds: noGoalOdd });
  if (a) out.push({ outcome: "away", odds: a.odds });
  return out;
}

// Stoppage-aware minute label: "90+3" in second-half stoppage, otherwise "84'". Used to stamp the
// minute a goal was actually scored (the live clock caps at 90, so we add the running stoppage).
function testmonMinuteLabel(info) {
  const m = getCurrentMinute(info?.time);
  if (m === null) return "?";
  const added = Number.parseInt(info?.secondHalfElapsedAddedTime, 10);
  if (m >= 90 && Number.isFinite(added) && added > 0) return `90+${added}`;
  return `${m}'`;
}

// Full per-match diagnostic — every value + every gate, so the page can show exactly WHERE a
// would-be entry passes or fails (the whole point of the backtest view).
function testmonEvaluate(tracked, cached, now = Date.now(), boardSeen = 0) {
  const info = cached?.info || {};
  const minute = getCurrentMinute(info.time);
  const score = info.score || "0-0";
  // Board = the HIGHEST added-time the 4th official has shown this match, not just the current frame.
  // 1win's secondHalfInjuryTime can blank out (frame gap, market reshuffle) or appear only moments
  // before the fixture drops off the live list — taking the max across the window means a board that
  // was genuinely announced (e.g. Colchagua's +7) is never mis-logged as "no board announced".
  const board = Math.max(Number.parseInt(info.secondHalfInjuryTime, 10) || 0, boardSeen || 0);
  const ms = oneWinMarketStateByKey.get(tracked.key);

  const ftrActive = isOneWinMarketActiveWithGrace(ms?.fullTimeResult, now);
  const ngActive  = isOneWinMarketActiveWithGrace(ms?.nextGoal, now);
  // Event suspension is normally stamped by applyOneWinSocketMarketUpdate on a status-2 sweep
  // from the odds socket. But the socket can go silent during a real suspension (1win stops
  // sending deltas for a suspended match), so we also evaluate directly from the stored groups
  // on every tick. The grace (ONE_WIN_EVENT_SUSPEND_GRACE_MS) still bridges brief gaps between
  // socket deltas; the direct check catches the silent-socket case within one monitor loop (~3s).
  const socketSuspended = !!(ms?.suspendedAt && now - ms.suspendedAt < ONE_WIN_EVENT_SUSPEND_GRACE_MS);
  const groupsSuspended = isOneWinEventSuspendedFromGroups(ms?.groups || [], now);
  const eventSuspended = socketSuspended || groupsSuspended;
  const otherList = eventSuspended ? [] : listOtherActiveOneWinMarketNames(ms?.groups || [], now);
  // Detailed odds for every other market — for the card's compact all-markets list. Frozen to []
  // on a full-event suspend (the card shows the suspend banner instead of stale market rows).
  const otherMarketsDetailed = eventSuspended ? [] : parseOneWinSocketOtherMarketsDetailed(ms?.groups || [], now);
  const noGoalOdd = testmonNoGoalOdd(ms?.groups || [], now);
  const teamOdds = testmonTeamNextGoalOdds(ms?.groups || [], now);
  // The Next-goal MARKET is live if ANY of its legs is — the No-Goal leg OR a team-to-score-next
  // leg. We only surface No Goal with a price, but the section must stay on the card while the
  // market is open on 1win even if the No-Goal leg alone momentarily drops (don't vanish the row).
  const nextGoalMarketActive = noGoalOdd !== null || teamOdds.length > 0;
  // Full Time Result (1/X/2) tracker — read LIVE from the current groups so it drops the instant
  // the FTR group has no open leg (explicit status-2/0 close = same tick; silent removal = next
  // board via the snapshot auditor). No retained-odds + 60s grace, which used to ghost a closed
  // FTR for ~60s. Hidden entirely while the event is suspended. The gate still uses ftrActive
  // (grace) so a brief blip can't yank a pending entry — display and gate are intentionally split.
  const fullTimeOddsLive = parseOneWinSocketFullTimeResultOddsGroups(ms?.groups || []);
  const fullTimeOdds = (!eventSuspended && fullTimeOddsLive.length) ? fullTimeOddsLive : [];

  // Live elapsed stoppage (running clock minus 90). The display clock caps at 90, so this — not
  // `minute` — is the real "+X" the match is currently at.
  const addedNow = Math.max(0, Number.parseInt(info.secondHalfElapsedAddedTime, 10) || 0);
  // Entry window = the announced board's LAST TWO added minutes, applied to EVERY board:
  //   • earlier minute (board-3): enter only if the No-Goal odd is HIGH (>= 1.07).
  //   • last minute    (board-2): enter if the No-Goal odd sits in [1.05, 1.07].
  //   • past the last minute: the standard >= 1.05 rule still applies (e.g. +5 at 94'+).
  // Examples: +5 -> 92'(>=1.07)/93'([1.05,1.07]); +4 -> 91'/92'; +3 -> 90'/91'.
  const earlyAdded = board - 3;
  const lastAdded  = board - 2;
  const minAddedForEntry = Math.max(0, earlyAdded); // earliest qualifying added minute (for diagnostics)

  const gateBoard     = board > 0; // the 4th official's added-time board must have been announced
  // gateTwoMarkets: FTR must be both grace-active (ftrActive, for blip-stability of a pending
  // entry) AND have live odds in the current groups (fullTimeOdds.length > 0, same source as the
  // FTR display row). This closes the split-brain where ftrActive stayed true for up to 60s after
  // FTR closed (via lastGoodAt grace) while the card no longer showed an FTR row — causing the
  // glow to fire even with no Full Time Result visually present.
  const gateTwoMarkets = ftrActive && fullTimeOdds.length > 0 && ngActive && otherList.length === 0 && !eventSuspended;

  let gateNoGoal = false;
  let gateTiming = false;

  if (board > 0 && addedNow === earlyAdded) {
    // earlier of the last two minutes: enter only on a high No-Goal odd
    gateTiming = gateBoard;
    gateNoGoal = noGoalOdd !== null && noGoalOdd >= TESTMON_NO_GOAL_HIGH;
  } else if (board > 0 && addedNow === lastAdded) {
    // last minute: No-Goal odd must be >= 1.05 (no upper ceiling — a tough match can price higher)
    gateTiming = gateBoard;
    gateNoGoal = noGoalOdd !== null && noGoalOdd >= TESTMON_NO_GOAL_MIN;
  } else {
    // before the window: blocked by timing; after it: standard >= 1.05
    gateTiming = gateBoard && addedNow >= minAddedForEntry;
    gateNoGoal = noGoalOdd !== null && noGoalOdd >= TESTMON_NO_GOAL_MIN;
  }

  // Both next-goal team legs must be long shots (>= 9): a short team price means a goal is
  // genuinely likely, so the No-Goal bet is not safe even with the band satisfied.
  const gateTeams     = teamOdds.length >= 2 && teamOdds.every(t => t.odds >= TESTMON_TEAM_MIN);

  // Team-balance gate: when No-Goal is at the floor (TESTMON_NO_GOAL_MIN), both team legs
  // must NOT be exactly equal. Empirical observation from 20-bet HF run: every bet where NoGoal
  // was at the floor AND team odds were identical (e.g. 11/11) resulted in a LOSS — all 6 wins at the floor
  // had clearly unequal team odds. Equal team odds at minimum NoGoal signals that the market sees
  // a perfectly 50/50 chance for either team, meaning higher real goal risk despite the low NoGoal
  // price. At NoGoal > TESTMON_NO_GOAL_MIN this extra constraint does not apply (the higher safety margin
  // already compensates).
  const teamOddsBalanced = teamOdds.length >= 2
    ? teamOdds[0].odds !== teamOdds[1].odds
    : true; // if somehow only 1 team leg, no imbalance to check — gateTeams handles count
  const gateTeamBalance = noGoalOdd === null || noGoalOdd > TESTMON_NO_GOAL_MIN || teamOddsBalanced;

  const enterSignal   = gateBoard && gateTwoMarkets && gateNoGoal && gateTeams && gateTeamBalance && gateTiming;

  return {
    key: tracked.key,
    home: info.home || tracked.home,
    away: info.away || tracked.away,
    league: tracked.league || info.league || "",
    minute, minuteDisplay: minute === null ? "—" : `${minute}'`,
    score, board,
    hasMarket: !!ms,
    ftrActive, ngActive, eventSuspended,
    otherMarketsRemaining: otherList.length,
    otherMarketsList: otherList,
    otherMarketsDetailed,
    noGoalOdd, teamOdds, fullTimeOdds, nextGoalMarketActive,
    addedNow, minAddedForEntry,
    gates: { board: gateBoard, twoMarkets: gateTwoMarkets, noGoal: gateNoGoal, teams: gateTeams, teamBalance: gateTeamBalance, timing: gateTiming },
    teamOddsBalanced, enterSignal
  };
}

// Record a SIGNAL (pending bet). The actual stake/odd lock happens after the entry delay.
function testmonPlace(diag, now) {
  testMonitor.seq += 1;
  const bet = {
    id: testMonitor.seq,
    key: diag.key, home: diag.home, away: diag.away, league: diag.league,
    status: "pending",
    signalAt: now, lockAt: null, settledAt: null,
    entryScore: diag.score, entryMinute: diag.minute,
    noGoalOddAtSignal: diag.noGoalOdd,
    teamOddsAtSignal: diag.teamOdds.map(t => ({ ...t })),
    otherMarketsAtSignal: diag.otherMarketsRemaining,
    lockedOdd: null, oddChangedDuringDelay: false,
    stake: 0, payout: 0, bankrollBefore: testMonitor.bankroll,
    lastScore: diag.score, lastMinute: diag.minute,
    board: diag.board, goalMinute: null, goalScore: null,
    finalScore: null, result: null, reason: null
  };
  testMonitor.bets.push(bet);
  testMonitor.byKey.set(bet.key, bet);
  console.log(`[TESTMON] SIGNAL ${bet.home} vs ${bet.away} @${bet.entryMinute}' score ${bet.entryScore} NoGoal ${bet.noGoalOddAtSignal} teams ${bet.teamOddsAtSignal.map(t => t.odds).join("/")}`);
  saveTestMonitor();
  setTimeout(() => testmonLock(bet.id), TESTMON_ENTRY_DELAY_MS);
}

// After the entry delay: re-read the No-Goal price (capturing any move inside the window), commit
// the all-in stake and escrow the bankroll.
function testmonLock(betId) {
  const bet = testMonitor.bets.find(b => b.id === betId);
  if (!bet || bet.status !== "pending") return; // settled/voided/reset in the meantime
  const now = Date.now();
  const reread = testmonNoGoalOdd(oneWinMarketStateByKey.get(bet.key)?.groups || [], now);
  const lockedOdd = reread !== null ? reread : bet.noGoalOddAtSignal;
  if (testMonitor.bankroll <= 0 || !Number.isFinite(lockedOdd)) {
    bet.status = "void"; bet.result = "void"; bet.settledAt = now;
    bet.reason = testMonitor.bankroll <= 0 ? "No bankroll at lock (busted)" : "No No-Goal price at lock";
    testMonitor.byKey.delete(bet.key);
    saveTestMonitor();
    return;
  }
  bet.lockAt = now;
  bet.lockedOdd = lockedOdd;
  bet.oddChangedDuringDelay = reread !== null && bet.noGoalOddAtSignal !== null && reread !== bet.noGoalOddAtSignal;
  bet.stake = testMonitor.bankroll;   // all-in
  testMonitor.bankroll = 0;            // escrow until settle
  bet.status = "open";
  console.log(`[TESTMON] ENTER ${bet.home} vs ${bet.away} stake ${bet.stake.toFixed(2)} @ ${lockedOdd}${bet.oddChangedDuringDelay ? ` (moved from ${bet.noGoalOddAtSignal})` : ""}`);
  saveTestMonitor();
}

// Settle at finish: win if no further goal since entry.
function testmonSettle(bet, finalScore, now, reason) {
  bet.finalScore = finalScore;
  bet.settledAt = now;
  if (bet.status === "pending") {
    // Match ended inside the entry delay — the bet never actually went on, nothing was staked.
    bet.status = "void"; bet.result = "void";
    bet.reason = reason || "Match ended before entry locked";
    testMonitor.byKey.delete(bet.key);
    saveTestMonitor();
    return;
  }
  const entryGoals = getTotalGoals(bet.entryScore);
  const finalGoals = getTotalGoals(finalScore);
  if (!Number.isFinite(entryGoals) || !Number.isFinite(finalGoals)) {
    bet.status = "void"; bet.result = "void"; bet.reason = "Unreadable score — stake refunded";
    testMonitor.bankroll += bet.stake;
  } else if (finalGoals <= entryGoals) {
    bet.status = "won"; bet.result = "won";
    bet.payout = bet.stake * bet.lockedOdd;
    testMonitor.bankroll += bet.payout;
    bet.reason = reason ? `${reason} — no further goal` : `No further goal (${bet.entryScore} → ${finalScore})`;
  } else {
    bet.status = "lost"; bet.result = "lost"; bet.payout = 0;
    bet.reason = `Goal after entry (${bet.entryScore} → ${finalScore})`;
  }
  bet.bankrollAfter = testMonitor.bankroll;
  if (testMonitor.bankroll > testMonitor.peak) testMonitor.peak = testMonitor.bankroll;
  testMonitor.byKey.delete(bet.key);
  console.log(`[TESTMON] SETTLE ${bet.home} vs ${bet.away} ${bet.status.toUpperCase()} (${bet.entryScore} → ${finalScore}) bankroll ${testMonitor.bankroll.toFixed(2)}`);
  saveTestMonitor();
}

// Driven once per monitor loop (~3s). Detects entries and settles finished/delisted matches.
function tickTestMonitor() {
  const now = Date.now();
  const liveKeys = new Set();
  for (const tracked of activeAutoMatches) {
    const cached = matchCache.get(tracked.key);
    if (!cached?.info) continue;
    liveKeys.add(tracked.key);
    // Remember the highest board this match has ever shown, then evaluate against that max so a
    // board that flickers off (or lands just before the fixture drops) still counts as announced.
    const liveBoard = Number.parseInt(cached.info.secondHalfInjuryTime, 10) || 0;
    const boardSeen = Math.max(testMonitor.boardSeen.get(tracked.key) || 0, liveBoard);
    if (boardSeen > 0) testMonitor.boardSeen.set(tracked.key, boardSeen);
    const diag = testmonEvaluate(tracked, cached, now, boardSeen);
    // If testmonEvaluate detected an event suspension from the stored groups (not from a
    // pre-stamped suspendedAt — the socket may have gone silent), stamp it on the market
    // state so the grace bridge works and applyOneWinSocketMarketUpdate can clear it the
    // moment a market becomes active again.
    if (diag.eventSuspended) {
      const ms = oneWinMarketStateByKey.get(tracked.key);
      if (ms && !ms.suspendedAt) {
        ms.suspendedAt = now;
      }
    }
    const active = testMonitor.byKey.get(tracked.key);
    if (active) {
      active.lastScore = diag.score; active.lastMinute = diag.minute; active.board = diag.board;
      // First goal after entry = the one that loses the No-Goal bet; stamp the minute it landed.
      if (active.status === "open" && active.goalMinute === null &&
          getTotalGoals(diag.score) > getTotalGoals(active.entryScore)) {
        active.goalMinute = testmonMinuteLabel(cached.info);
        active.goalScore = diag.score;
      }
      // Keep the open bet's last-seen score/board fresh on disk so a restart settles it correctly
      // even if the match vanishes during the downtime (debounced — at most one write/sec).
      saveTestMonitor();
    }
    // Remember the watched snapshot of any match we haven't bet, so when it finishes without a
    // bet we can log WHY it was skipped — and whether/when a goal arrived (would the No-Goal bet
    // have won?). Preserve the reference score + goal stamp across ticks; refresh the rest.
    const watchable = diag.minute !== null && diag.minute >= TESTMON_WATCH_MINUTE;
    if (watchable && !testMonitor.everBet.has(tracked.key)) {
      let w = testMonitor.watch.get(tracked.key);
      if (!w) {
        w = { home: diag.home, away: diag.away, league: diag.league,
              refScore: diag.score, qualified: false, qualifyMinute: null,
              goalMinute: null, goalScore: null };
        testMonitor.watch.set(tracked.key, w);
      }
      w.lastDiag = diag; w.lastScore = diag.score; w.lastMinute = diag.minute; w.board = diag.board;
      // The "would the No-Goal bet have won?" reference is the score at the moment the match would
      // actually be BET (all gates pass) — NOT the score at 90'. A real bet only goes on once the
      // enter signal fires, so a goal scored before the match qualifies could never beat it. Until
      // the signal fires keep the reference tracking the live score (pre-bet goals never count);
      // freeze it the first time the match qualifies, then stamp any goal after that.
      if (!w.qualified) {
        if (diag.enterSignal) {
          w.qualified = true;
          w.refScore = diag.score;
          w.qualifyMinute = testmonMinuteLabel(cached.info);
        } else {
          w.refScore = diag.score; // not yet bettable — reference stays current
        }
      }
      if (w.qualified && w.goalMinute === null && getTotalGoals(diag.score) > getTotalGoals(w.refScore)) {
        w.goalMinute = testmonMinuteLabel(cached.info);
        w.goalScore = diag.score;
      }
    }
    // Enter: signal met, fixture not already bet this run, funds available, and (all-in) no other
    // bet currently active.
    if (diag.enterSignal && !testMonitor.byKey.has(tracked.key) && !testMonitor.everBet.has(tracked.key) &&
        testMonitor.bankroll > 0 && !testmonHasActiveBet()) {
      testMonitor.everBet.add(tracked.key);
      testMonitor.watch.delete(tracked.key); // it became a bet, not a skip
      testmonPlace(diag, now);
    }
  }
  // Settle any active bet whose match has finished or dropped off the live list (snapshot the map
  // first — testmonSettle mutates it).
  for (const bet of Array.from(testMonitor.byKey.values())) {
    const cached = matchCache.get(bet.key);
    const gone = !cached || !liveKeys.has(bet.key);
    const finished = gone ||
      cached.info?.phase === "FINISHED" ||
      isOneWinFinishedStatus(cached.info?.phase) ||
      isOneWinFinishedStatus(cached.info?.rawStatus) ||
      String(cached.info?.time || "").toUpperCase().trim() === "FT";
    if (!finished) continue;
    const finalScore = (cached?.info?.score) || bet.lastScore || bet.entryScore;
    testmonSettle(bet, finalScore, now, gone ? "Match left 1win live list" : null);
  }
  // Log SKIPS: any watched match that finished/left the list without ever becoming a bet, with
  // the reason (the gate that failed) from its last watched snapshot.
  for (const [key, w] of Array.from(testMonitor.watch.entries())) {
    if (testMonitor.everBet.has(key)) { testMonitor.watch.delete(key); continue; } // it was bet — handled above
    const cached = matchCache.get(key);
    const gone = !cached || !liveKeys.has(key);
    const finished = gone ||
      cached.info?.phase === "FINISHED" ||
      isOneWinFinishedStatus(cached.info?.phase) ||
      isOneWinFinishedStatus(cached.info?.rawStatus) ||
      String(cached.info?.time || "").toUpperCase().trim() === "FT";
    if (!finished) continue;
    const finalScore = (cached?.info?.score) || w.lastScore || "?";
    const reason = testmonSkipReason(w.lastDiag);
    testMonitor.seq += 1;
    // Snapshot the last-known odds from the diagnostic so the settled card can show them.
    const skipDiag = w.lastDiag || {};
    testMonitor.skips.push({
      id: testMonitor.seq, key, status: "skipped",
      home: w.home, away: w.away, league: w.league,
      entryScore: w.lastScore, finalScore, lastMinute: w.lastMinute,
      board: w.board || 0, goalMinute: w.goalMinute, goalScore: w.goalScore,
      // Last-seen odds — null/undefined when market was closed/suspended at the moment of logging
      noGoalOdd: skipDiag.noGoalOdd ?? null,
      teamOdds: Array.isArray(skipDiag.teamOdds) ? skipDiag.teamOdds : [],
      fullTimeOdds: Array.isArray(skipDiag.fullTimeOdds) ? skipDiag.fullTimeOdds : [],
      reason, settledAt: now
    });
    console.log(`[TESTMON] SKIP ${w.home} vs ${w.away} (${finalScore}) — ${reason}`);
    testMonitor.watch.delete(key);
    saveTestMonitor();
  }
  // Drop the board-max memory for matches that are gone and not held by an active bet (its board is
  // already stamped on the bet/skip record) so the map can't grow across a long run.
  for (const key of Array.from(testMonitor.boardSeen.keys())) {
    if (!liveKeys.has(key) && !testMonitor.byKey.has(key)) testMonitor.boardSeen.delete(key);
  }
}

function testmonStats() {
  let won = 0, lost = 0, voided = 0;
  for (const b of testMonitor.bets) {
    if (b.status === "won") won++;
    else if (b.status === "lost") lost++;
    else if (b.status === "void") voided++;
  }
  const decided = won + lost;
  return {
    total: testMonitor.bets.length,
    won, lost, void: voided, decided,
    skipped: testMonitor.skips.length,
    winRate: decided ? won / decided : 0,
    netProfit: testMonitor.bankroll - TESTMON_START_BANKROLL
  };
}

function testmonBetView(bet, now = Date.now()) {
  const v = { ...bet };
  if (bet.status === "open") {
    v.potentialPayout = bet.stake * bet.lockedOdd;
    v.entryGoals = getTotalGoals(bet.entryScore);
    v.currentGoals = getTotalGoals(bet.lastScore);
    v.goalAfterEntry = Number.isFinite(v.currentGoals) && Number.isFinite(v.entryGoals) && v.currentGoals > v.entryGoals;
  } else if (bet.status === "pending") {
    v.delayRemainingMs = Math.max(0, TESTMON_ENTRY_DELAY_MS - (now - bet.signalAt));
  }
  return v;
}

app.get("/api/backtest", (req, res) => {
  try {
    res.set("Cache-Control", "no-store, max-age=0");
    const now = Date.now();
    const watching = [];
    for (const tracked of activeAutoMatches) {
      const cached = matchCache.get(tracked.key);
      if (!cached?.info) continue;
      const minute = getCurrentMinute(cached.info.time);
      const lateEnough = minute !== null && minute >= TESTMON_WATCH_MINUTE;
      if (!lateEnough && !testMonitor.byKey.has(tracked.key)) continue;
      const diag = testmonEvaluate(tracked, cached, now, testMonitor.boardSeen.get(tracked.key) || 0);
      const bet = testMonitor.byKey.get(tracked.key);
      diag.bet = bet ? testmonBetView(bet, now) : null;
      watching.push(diag);
    }
    watching.sort((a, b) => (b.minute || 0) - (a.minute || 0));

    const activeBets = Array.from(testMonitor.byKey.values()).map(b => testmonBetView(b, now));
    // Settled history = real settled bets + skipped watched matches, newest first, so a backtest
    // shows BOTH the bets that ran and the matches that were passed over (and why).
    const settledBets = testMonitor.bets
      .filter(b => b.status === "won" || b.status === "lost" || b.status === "void")
      .map(b => testmonBetView(b, now));
    const settled = settledBets.concat(testMonitor.skips.map(s => ({ ...s })))
      .sort((a, b) => (b.settledAt || 0) - (a.settledAt || 0));

    res.json({
      bankroll: testMonitor.bankroll,
      startBankroll: TESTMON_START_BANKROLL,
      peak: testMonitor.peak,
      busted: testMonitor.bankroll <= 0 && !testmonHasActiveBet(),
      config: {
        watchMinute: TESTMON_WATCH_MINUTE,
        noGoalMin: TESTMON_NO_GOAL_MIN,
        teamMin: TESTMON_TEAM_MIN,
        entryDelayMs: TESTMON_ENTRY_DELAY_MS
      },
      stats: testmonStats(),
      activeBets, watching, settled, now
    });
  } catch (err) {
    console.error("[TESTMON] API error:", err.message);
    res.status(500).json({ error: "backtest failed" });
  }
});

app.post("/api/backtest/reset", (req, res) => {
  testMonitor.bankroll = TESTMON_START_BANKROLL;
  testMonitor.peak = TESTMON_START_BANKROLL;
  testMonitor.startedAt = Date.now();
  testMonitor.bets.length = 0;
  testMonitor.byKey.clear();
  testMonitor.everBet.clear();
  testMonitor.watch.clear();
  testMonitor.boardSeen.clear();
  testMonitor.skips.length = 0;
  testMonitor.seq = 0;
  saveTestMonitor();
  console.log("[TESTMON] Reset to fresh bankroll.");
  res.json({ ok: true });
});

app.get("/backtest", (req, res) => {
  res.set("Cache-Control", "no-store, max-age=0");
  res.type("html").send(TESTMONITOR_PAGE_HTML);
});

const TESTMONITOR_PAGE_HTML = `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backtest — No-Goal Simulation</title>
<style>
  :root{
    color-scheme:dark;
    --bg:#000; --surface:#0a0a0a; --card:#020202;
    --border:#161616; --border2:#222;
    --txt:#fff; --mut:#8c8c8c; --mut2:#4d4d4d;
    --amb:#f5a623; --amb-soft:rgba(245,166,35,.13); --amb-bd:rgba(245,166,35,.5);
    --grn:#2fbf71; --grn-soft:rgba(47,191,113,.11); --grn-bd:rgba(47,191,113,.45);
    --red:#ef4444; --red-soft:rgba(239,68,68,.11); --red-bd:rgba(239,68,68,.45);
  }
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  html{scrollbar-width:none}
  html::-webkit-scrollbar{display:none}
  body{background:var(--bg);color:var(--txt);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
    min-height:100vh;padding:clamp(12px,2.4vw,26px);position:relative;overflow-x:hidden}
  /* ambient aurora haze + corner vignette, mirrored from the main dashboard */
  body::after{content:"";position:fixed;inset:-25%;z-index:-4;pointer-events:none;filter:blur(50px);
    background:
      radial-gradient(38% 38% at 22% 30%,rgba(255,255,255,.05),transparent 70%),
      radial-gradient(34% 34% at 80% 68%,rgba(200,210,225,.038),transparent 70%),
      radial-gradient(30% 30% at 58% 18%,rgba(245,166,35,.05),transparent 70%),
      radial-gradient(40% 40% at 40% 85%,rgba(170,180,195,.032),transparent 70%);
    animation:aurora 34s ease-in-out infinite alternate}
  .bg-fx{position:fixed;inset:0;z-index:-1;pointer-events:none;
    background:radial-gradient(circle at center,rgba(0,0,0,.06) 20%,rgba(0,0,0,.88) 100%)}
  @keyframes aurora{0%{transform:translate3d(-3%,-2%,0) scale(1.05) rotate(0)}50%{transform:translate3d(2%,3%,0) scale(1.12) rotate(4deg)}100%{transform:translate3d(3%,-3%,0) scale(1.05) rotate(-3deg)}}
  @media(prefers-reduced-motion:reduce){body::after{animation:none}}
  .wrap{max-width:1140px;margin:0 auto;position:relative}

  /* topbar */
  .topbar{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:22px}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--red);box-shadow:0 0 8px 1px rgba(239,68,68,.7);animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  h1{font-size:13px;font-weight:800;letter-spacing:.22em;text-transform:uppercase;margin:0}
  .tag{font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--amb);
    border:1px solid var(--amb-bd);background:var(--amb-soft);padding:4px 9px;border-radius:999px}
  .spacer{flex:1}
  .ago{color:var(--mut2);font-size:11px;font-variant-numeric:tabular-nums}
  button{font:inherit;font-weight:700;cursor:pointer;border-radius:9px;border:1px solid var(--border2);
    background:var(--surface);color:var(--txt);padding:8px 15px;transition:.15s;letter-spacing:.02em}
  button:hover{border-color:#333;background:#111}
  button.danger{border-color:var(--red-bd);color:var(--red);background:var(--red-soft)}
  button.danger:hover{background:rgba(239,68,68,.18)}

  /* hero */
  .hero{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:12px;margin-bottom:16px}
  .hcard{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px;position:relative;overflow:hidden}
  .hcard .l{font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut2);margin-bottom:8px}
  .hcard .v{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1;letter-spacing:-.02em}
  .hcard.big .v{font-size:40px;color:var(--amb)}
  .hcard .sub{font-size:11px;color:var(--mut);margin-top:7px;font-variant-numeric:tabular-nums}
  .pos{color:var(--grn)} .neg{color:var(--red)} .neu{color:var(--mut)}
  .hcard .shine{position:absolute;inset:0;background:linear-gradient(120deg,transparent 30%,rgba(255,255,255,.06) 50%,transparent 70%);
    transform:translateX(-100%);transition:.6s}
  .hcard.flash .shine{transform:translateX(100%)}

  .bust{display:none;align-items:center;gap:10px;background:var(--red-soft);border:1px solid var(--red-bd);
    color:#ffd7dc;border-radius:12px;padding:13px 16px;margin-bottom:16px;font-weight:700}
  .bust.on{display:flex}

  .legend{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:8px;font-size:11px;color:var(--mut)}
  .legend .pill{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:5px 10px}
  .legend b{color:var(--txt)}

  h2{font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--mut);margin:26px 0 12px;
    display:flex;align-items:center;gap:9px}
  h2 .count{color:var(--mut2);font-weight:600;letter-spacing:.08em}

  /* responsive card grid — shared by active / watch / settled, so nothing ever needs a scrollbar */
  .grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(290px,1fr))}
  .card{background:var(--card);border:1px solid var(--border);border-radius:13px;padding:15px}
  .teams{font-weight:800;font-size:14.5px;letter-spacing:.01em}
  .teams .neu{color:var(--mut2);font-weight:600}
  .lg{font-size:11px;color:var(--mut);margin-top:2px}

  /* active bet */
  .betcard.pending{border-color:var(--amb-bd);box-shadow:0 0 0 1px var(--amb-soft) inset}
  .betcard.open{border-color:var(--grn-bd)}
  .betcard.open.danger{border-color:var(--red-bd);animation:glowR 1.4s ease-in-out infinite}
  @keyframes glowR{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0)}50%{box-shadow:0 0 16px -2px rgba(239,68,68,.4)}}
  .statusrow{display:flex;align-items:center;gap:7px;margin-bottom:11px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:9px 14px;margin-top:12px}
  .kv .k{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut2)}
  .kv .vv{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:1px}
  .badge{font-size:9px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;padding:4px 9px;border-radius:999px}
  .b-pending{background:var(--amb-soft);color:var(--amb);border:1px solid var(--amb-bd)}
  .b-open{background:var(--grn-soft);color:var(--grn);border:1px solid var(--grn-bd)}
  .b-won{background:var(--grn-soft);color:var(--grn);border:1px solid var(--grn-bd)}
  .b-lost{background:var(--red-soft);color:var(--red);border:1px solid var(--red-bd)}
  .b-void{background:#141414;color:var(--mut);border:1px solid var(--border2)}
  .b-skip{background:var(--amb-soft);color:var(--amb);border:1px solid var(--amb-bd)}
  .odmove{font-size:11px;color:var(--amb);font-weight:700;margin-top:8px;font-variant-numeric:tabular-nums}
  .bar{height:4px;border-radius:4px;background:#161616;overflow:hidden;margin-top:10px}
  .bar > i{display:block;height:100%;background:var(--amb);transition:width .25s linear}

  /* watching */
  .wcard.enter{border-color:var(--grn-bd);box-shadow:0 0 0 1px var(--grn-soft) inset,0 0 18px -6px rgba(47,191,113,.5)}
  .wcard.holding{border-color:var(--amb-bd)}
  .whead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:5px}
  .wmin{text-align:right;font-weight:800;font-variant-numeric:tabular-nums;font-size:16px;flex:none}
  .wmin small{display:block;font-size:9px;color:var(--mut2);font-weight:600;letter-spacing:.05em}
  .wscore{font-size:12px;color:var(--mut);margin-bottom:11px}
  .wscore b{color:var(--txt);font-variant-numeric:tabular-nums}
  .verdict{font-size:9.5px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;
    padding:4px 9px;border-radius:7px;display:inline-block;margin-bottom:11px}
  .v-enter{background:var(--grn-soft);color:var(--grn);border:1px solid var(--grn-bd)}
  .v-skip{background:#141414;color:var(--mut);border:1px solid var(--border2)}
  .v-bet{background:var(--amb-soft);color:var(--amb);border:1px solid var(--amb-bd)}
  .gates{display:flex;flex-direction:column;gap:7px}
  .gate{display:flex;align-items:center;gap:8px;font-size:12px}
  .gate .ic{width:15px;height:15px;border-radius:50%;flex:none;display:grid;place-items:center;font-size:10px;font-weight:900}
  .gate.ok .ic{background:var(--grn-soft);color:var(--grn)}
  .gate.no .ic{background:var(--red-soft);color:var(--red)}
  .gate .lbl{color:var(--mut)}
  .gate .det{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:700;color:var(--txt)}
  .gate.no .det{color:var(--red)}
  .track{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:9px;
    padding-top:9px;border-top:1px dashed var(--border2);font-size:12px}
  .track .tlbl{color:var(--mut2);text-transform:uppercase;letter-spacing:.1em;font-size:9px;font-weight:700;flex:none}
  .track .tval{font-variant-numeric:tabular-nums;font-weight:700;letter-spacing:.02em;text-align:right}
  .track .tval.off{color:var(--mut2);font-weight:600}
  .susp{margin-top:9px;font-size:11px;color:var(--amb);font-weight:700}
  .mkts{margin-top:8px;font-size:11px;color:var(--mut)}
  .mkts span{display:inline-block;background:#111;border:1px solid var(--border2);border-radius:6px;
    padding:1px 7px;margin:3px 3px 0 0}

  /* settled cards — a card per result, so the log never needs a horizontal scrollbar */
  .scard{border-left:3px solid var(--border2)}
  .scard.won{border-left-color:var(--grn)} .scard.lost{border-left-color:var(--red)}
  .scard.void{border-left-color:var(--mut2)} .scard.skipped{border-left-color:var(--amb)}
  .shead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
  .swhen{font-size:10px;color:var(--mut2);font-variant-numeric:tabular-nums;letter-spacing:.03em;margin-top:4px;display:flex;align-items:center;gap:5px}
  .swhen .cal{opacity:.7;font-size:10px}
  .sgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px 12px;margin-top:13px}
  .sgrid4{grid-template-columns:repeat(4,1fr)}
  .sgrid .k{font-size:8.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut2)}
  .sgrid .vv{font-size:13.5px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px}
  /* inline odds strip below the skip/bet grid */
  .sodds{display:flex;align-items:center;flex-wrap:wrap;gap:5px 12px;margin-top:10px;
    padding:8px 10px;background:#0d0d0d;border:1px solid var(--border);border-radius:9px;font-size:11.5px}
  .sodlbl{font-size:8.5px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;
    color:var(--mut2);white-space:nowrap}
  .sod{font-variant-numeric:tabular-nums;color:var(--txt);font-weight:600}
  .sod b{color:var(--amb);font-weight:800}
  .sod-na{color:var(--mut2);font-style:italic;font-size:11px}
  .swhy{margin-top:10px;padding-top:11px;border-top:1px solid var(--border);font-size:11.5px;color:var(--mut);line-height:1.45}
  .empty{color:var(--mut2);padding:30px 12px;text-align:center;font-size:13px;grid-column:1/-1;
    border:1px dashed var(--border2);border-radius:12px}
  .foot{color:var(--mut2);font-size:11px;margin-top:24px;line-height:1.6}
  @media(max-width:720px){
    .hero{grid-template-columns:1fr 1fr}
    .hcard.big{grid-column:span 2}
  }
</style></head>
<body>
<div class="bg-fx" aria-hidden="true"></div>
<div class="wrap">
  <div class="topbar">
    <span class="dot"></span>
    <h1>Backtest</h1>
    <span class="tag">No-Goal all-in backtest</span>
    <span class="spacer"></span>
    <span id="clock" class="ago"></span>
    <button class="danger" id="reset">Reset run</button>
  </div>

  <div id="bust" class="bust">💥 <span><b>Bankroll busted.</b> An all-in bet lost — the run is over. Hit Reset run to start fresh from 1000.</span></div>

  <div class="hero">
    <div class="hcard big" id="hc-bank"><div class="shine"></div><div class="l">Bankroll</div><div class="v" id="bankroll">—</div><div class="sub" id="bankrollSub">&nbsp;</div></div>
    <div class="hcard"><div class="l">Net profit</div><div class="v" id="net">—</div><div class="sub" id="roi">&nbsp;</div></div>
    <div class="hcard"><div class="l">Win rate</div><div class="v" id="winrate">—</div><div class="sub" id="record">&nbsp;</div></div>
    <div class="hcard"><div class="l">Peak</div><div class="v" id="peak">—</div><div class="sub" id="bets">&nbsp;</div></div>
  </div>

  <div class="legend" id="legend"></div>

  <h2>Active bet <span class="count" id="activeCount"></span></h2>
  <div class="grid" id="active"></div>

  <h2>Watching <span class="count" id="watchCount"></span></h2>
  <div class="grid" id="watch"></div>

  <h2>Settled history <span class="count" id="settledCount"></span></h2>
  <div class="grid" id="settled"></div>

  <p class="foot">Temporary endpoint. Engine ticks with the 3s monitor loop; entry delay re-reads the No-Goal price after ~3.5s, settles at full-time on the live score. Times shown in your local timezone.</p>
</div>

<script>
const $ = s => document.querySelector(s);
const money = n => (n==null||isNaN(n)) ? "—" : Number(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const odd = n => (n==null||isNaN(n)) ? "—" : Number(n).toFixed(2);
let prevBankroll = null, prevSettled = 0, cfg = {watchMinute:62,noGoalMin:1.05,teamMin:9};
const numOr = (v,fallback) => { const n=Number(v); return Number.isFinite(n) ? n : fallback; };
function normalizeConfig(c){
  c = c || {};
  return {
    watchMinute: numOr(c.watchMinute, cfg.watchMinute),
    noGoalMin: numOr(c.noGoalMin, cfg.noGoalMin),
    teamMin: numOr(c.teamMin, cfg.teamMin),
    entryDelayMs: numOr(c.entryDelayMs, 3500)
  };
}

function ago(ts,now){ if(!ts) return ""; const s=Math.max(0,Math.round((now-ts)/1000));
  if(s<60) return s+"s ago"; const m=Math.floor(s/60); if(m<60) return m+"m ago"; return Math.floor(m/60)+"h ago"; }

// Day + hour stamp for the settled log, in the viewer's local timezone, e.g. "Jun 22 · 14:35".
function stamp(ts){ if(!ts) return "—"; const d=new Date(ts);
  const day=d.toLocaleDateString(undefined,{month:"short",day:"numeric"});
  const tm=d.toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit"});
  return day+" · "+tm; }

function gateRow(ok,label,detail){
  return '<div class="gate '+(ok?"ok":"no")+'"><span class="ic">'+(ok?"✓":"✕")+'</span>'+
    '<span class="lbl">'+label+'</span><span class="det">'+detail+'</span></div>';
}

function render(d){
  const now = d.now || Date.now();
  cfg = normalizeConfig(d.config);
  // hero
  const bk = d.bankroll;
  $("#bankroll").textContent = money(bk);
  if(prevBankroll!==null && Math.abs(bk-prevBankroll)>0.005){
    const c=$("#hc-bank"); c.classList.remove("flash"); void c.offsetWidth; c.classList.add("flash");
  }
  prevBankroll = bk;
  $("#bankrollSub").textContent = "start "+money(d.startBankroll);
  const net = d.stats.netProfit;
  $("#net").textContent = (net>=0?"+":"")+money(net);
  $("#net").className = "v "+(net>0?"pos":net<0?"neg":"neu");
  const roi = d.startBankroll? (net/d.startBankroll*100):0;
  $("#roi").textContent = (roi>=0?"+":"")+roi.toFixed(1)+"% ROI";
  $("#winrate").textContent = d.stats.decided ? Math.round(d.stats.winRate*100)+"%" : "—";
  $("#record").textContent = d.stats.won+"W · "+d.stats.lost+"L"+(d.stats.void?" · "+d.stats.void+" void":"");
  $("#peak").textContent = money(d.peak);
  $("#bets").textContent = d.stats.total+" bets"+(d.stats.skipped?" · "+d.stats.skipped+" skipped":"");
  $("#bust").classList.toggle("on", d.busted);

  // legend
  $("#legend").innerHTML =
    '<span class="pill">Enter when <b>all</b> hold:</span>'+
    '<span class="pill">1. added-time <b>board</b></span>'+
    '<span class="pill">2. only <b>2 markets</b></span>'+
    '<span class="pill">3. No&nbsp;Goal &gt;= <b>'+cfg.noGoalMin.toFixed(2)+'</b> (last 2 min: early &gt;=1.07, last '+cfg.noGoalMin.toFixed(2)+'-1.07)</span>'+
    '<span class="pill">4. both teams &gt;= <b>'+cfg.teamMin+'</b>; if NoGoal='+cfg.noGoalMin.toFixed(2)+' → teams must be <b>unequal</b></span>'+
    '<span class="pill">delay <b>'+(cfg.entryDelayMs/1000)+'s</b> · all-in · settle at FT</span>';

  // active
  $("#activeCount").textContent = d.activeBets.length?("· "+d.activeBets.length):"";
  $("#active").innerHTML = d.activeBets.length ? d.activeBets.map(b=>activeCard(b,now)).join("")
    : '<div class="empty">No active bet. Waiting for a qualifying match.</div>';

  // watching
  $("#watchCount").textContent = d.watching.length?("· "+d.watching.length):"";
  $("#watch").innerHTML = d.watching.length ? d.watching.map(w=>watchCard(w,now)).join("")
    : '<div class="empty">No watched matches in the '+cfg.watchMinute+"'+ run-up right now.</div>";

  // settled
  $("#settledCount").textContent = d.settled.length?("· "+d.settled.length):"";
  $("#settled").innerHTML = d.settled.length ? d.settled.map(s=>settledCard(s,now)).join("")
    : '<div class="empty">No settled bets yet.</div>';

  prevSettled = d.settled.length;
  $("#clock").textContent = "updated "+new Date(now).toLocaleTimeString();
}

function activeCard(b,now){
  const pending = b.status==="pending";
  const danger = b.status==="open" && b.goalAfterEntry;
  const cls = pending?"pending":("open"+(danger?" danger":""));
  const badge = pending?'<span class="badge b-pending">Pending entry</span>':'<span class="badge b-open">Open</span>';
  let delayBar = "";
  if(pending){
    const total=b.delayRemainingMs+ (now-b.signalAt);
    const pct = Math.max(0,Math.min(100, (1-(b.delayRemainingMs/Math.max(1,total)))*100));
    delayBar = '<div class="bar"><i style="width:'+pct+'%"></i></div>'+
      '<div class="odmove">locking in '+(Math.ceil(b.delayRemainingMs/100)/10).toFixed(1)+'s…</div>';
  }
  const moved = b.oddChangedDuringDelay ? '<div class="odmove">odd moved '+odd(b.noGoalOddAtSignal)+' → '+odd(b.lockedOdd)+' during delay</div>' : "";
  return '<div class="card betcard '+cls+'">'+
    '<div class="statusrow">'+badge+(danger?'<span class="badge b-lost">goal '+esc(b.goalMinute||"")+'</span>':"")+'</div>'+
    '<div class="teams">'+esc(b.home)+' <span class="neu">v</span> '+esc(b.away)+'</div>'+
    '<div class="lg">'+esc(b.league||"")+'</div>'+
    '<div class="grid2">'+
      kv("Entry", b.entryScore+" @"+ (b.entryMinute||"?")+"'")+
      kv("Now", (b.lastScore||b.entryScore)+" @"+(b.lastMinute||"?")+"'")+
      kv("Board", b.board?("+"+b.board):"—")+
      kv("No-Goal", pending?("~"+odd(b.noGoalOddAtSignal)):odd(b.lockedOdd))+
      kv("Stake", pending?"(all-in)":money(b.stake))+
      (pending?"":kv("If wins", money(b.potentialPayout)))+
    '</div>'+moved+delayBar+'</div>';
}

function watchCard(w,now){
  const g=w.gates;
  let verdict, cls="";
  if(w.bet){ verdict='<span class="verdict v-bet">● bet '+w.bet.status+'</span>'; cls="holding"; }
  else if(w.enterSignal){ verdict='<span class="verdict v-enter">▲ enter</span>'; cls="enter"; }
  else { verdict='<span class="verdict v-skip">skip</span>'; }
  // Informative "only 2 markets" detail: say WHAT is wrong (no FTR / no Next / N extra), not a bare
  // "0 extra open" that wrongly implies the gate should pass.
  let twoDet;
  if(w.eventSuspended) twoDet="suspended";
  else if(g.twoMarkets) twoDet="FTR + Next";
  else { const p=[]; if(!w.ftrActive)p.push("no FTR"); if(!w.ngActive)p.push("no Next"); if(w.otherMarketsRemaining>0)p.push(w.otherMarketsRemaining+" extra"); twoDet=p.join(", ")||"—"; }
  const teamDet = (w.teamOdds&&w.teamOdds.length)? w.teamOdds.map(t=>odd(t.odds)).join(" / ") : "none";
  // Full Time Result tracker (1 / X / 2) shown below the gates.
  const ftr=w.fullTimeOdds||[]; const fm={}; ftr.forEach(o=>fm[o.outcome]=o.odds);
  const ftrLine = ftr.length ? ('1&nbsp;'+odd(fm.home)+'&nbsp;&nbsp; X&nbsp;'+odd(fm.Draw)+'&nbsp;&nbsp; 2&nbsp;'+odd(fm.away)) : 'n/a';
  const ngLine = (w.noGoalOdd!=null) ? ('No&nbsp;Goal '+odd(w.noGoalOdd)+(w.teamOdds.length?'&nbsp;&nbsp; teams '+w.teamOdds.map(t=>odd(t.odds)).join('/'):'')) : 'n/a';
  const susp = w.eventSuspended? '<div class="susp">⚠ event suspended (bets not accepted)</div>':"";
  const mkts = (!g.twoMarkets && w.otherMarketsRemaining>0 && w.otherMarketsList.length)?
    '<div class="mkts">extra open: '+w.otherMarketsList.map(m=>'<span>'+esc(m)+'</span>').join("")+'</div>':"";
  return '<div class="card wcard '+cls+'">'+
    '<div class="whead"><div><div class="teams">'+esc(w.home)+' <span class="neu">v</span> '+esc(w.away)+'</div>'+
      '<div class="lg">'+esc(w.league||"")+'</div></div>'+
      '<div class="wmin">'+w.minuteDisplay+(w.board?'<small>+'+w.board+" board</small>":"<small>&nbsp;</small>")+'</div></div>'+
    '<div class="wscore">score <b>'+esc(w.score)+'</b></div>'+
    verdict+
    '<div class="gates">'+
      gateRow(g.board, "board announced", w.board?("+"+w.board):"none")+
      gateRow(g.twoMarkets, "only 2 markets", twoDet)+
      gateRow(g.noGoal, "No-Goal ≥ "+cfg.noGoalMin.toFixed(2), w.noGoalOdd!=null?odd(w.noGoalOdd):"n/a")+
      gateRow(g.teams, "both teams ≥ "+cfg.teamMin, teamDet)+
      gateRow(g.teamBalance, "unequal teams at " + cfg.noGoalMin.toFixed(2) + " floor", g.teamBalance?"ok":"equal — blocked")+
      gateRow(g.timing, "late entry +"+(w.minAddedForEntry!=null?w.minAddedForEntry:"?"), w.board?("+"+(w.addedNow||0)+" now"):"no board")+
    '</div>'+
    '<div class="track"><span class="tlbl">Next Goal</span><span class="tval'+(w.noGoalOdd!=null?'':' off')+'">'+ngLine+'</span></div>'+
    '<div class="track"><span class="tlbl">Full Time</span><span class="tval'+(ftr.length?'':' off')+'">'+ftrLine+'</span></div>'+
    susp+mkts+'</div>';
}

// Settled-card odds helpers — compact FTR / NG line from saved arrays.
function ftrStr(fto){
  if(!fto||!fto.length) return '<span class="sod-na">n/a</span>';
  const m={}; fto.forEach(o=>m[o.outcome]=o.odds);
  return '<span class="sod">1&nbsp;'+odd(m.home)+'&nbsp; X&nbsp;'+odd(m.Draw)+'&nbsp; 2&nbsp;'+odd(m.away)+'</span>';
}
function ngStr(noGoal,teams){
  if(noGoal==null&&(!teams||!teams.length)) return '<span class="sod-na">n/a</span>';
  const parts=[];
  if(noGoal!=null) parts.push('No&nbsp;Goal&nbsp;<b>'+odd(noGoal)+'</b>');
  if(teams&&teams.length) parts.push('teams&nbsp;'+teams.map(t=>odd(t.odds)).join('/'));
  return '<span class="sod">'+parts.join('&nbsp;&nbsp;')+'</span>';
}

// Settled history is rendered as one card per result (no wide table → no horizontal scrollbar). Each
// card is stamped with the local day + hour it settled, plus a relative "ago".
function goalTxt(s){ return s.goalMinute ? esc(s.goalMinute) : (s.status==="lost"?"?":"—"); }
function kvs(k,v){ return '<div class="kv"><div class="k">'+k+'</div><div class="vv">'+v+'</div></div>'; }
function settledCard(s,now){
  const st = s.status;
  const badge = st==="won"?'<span class="badge b-won">Won</span>'
    : st==="lost"?'<span class="badge b-lost">Lost</span>'
    : st==="void"?'<span class="badge b-void">Void</span>'
    : '<span class="badge b-skip">Skip</span>';
  const when = '<div class="swhen"><span class="cal">🕑</span>'+stamp(s.settledAt)+
    (s.settledAt?' · '+ago(s.settledAt,now):'')+'</div>';
  let grid;
  if(st==="skipped"){
    grid = '<div class="sgrid sgrid4">'+
      kvs("Reached", (s.lastMinute||"?")+"'")+
      kvs("Final", esc(s.finalScore||"?"))+
      kvs("Board", s.board?("+"+s.board):"—")+
      kvs("Goal min", goalTxt(s))+
    '</div>'+
    '<div class="sodds">'+
      '<span class="sodlbl">FTR</span>'+ftrStr(s.fullTimeOdds)+
      '<span class="sodlbl">Next Goal</span>'+ngStr(s.noGoalOdd,s.teamOdds)+
    '</div>';
  } else {
    grid = '<div class="sgrid">'+
      kvs("Entry", esc(s.entryScore)+" @"+(s.entryMinute||"?")+"'")+
      kvs("Final", esc(s.finalScore||"?"))+
      kvs("Odd", odd(s.lockedOdd))+
      kvs("Stake", money(s.stake))+
      kvs("Payout", money(s.payout))+
      kvs("Bankroll", s.bankrollAfter!=null?money(s.bankrollAfter):"—")+
      kvs("Board", s.board?("+"+s.board):"—")+
      kvs("Goal min", goalTxt(s))+
    '</div>'+
    '<div class="sodds">'+
      '<span class="sodlbl">No Goal</span>'+(s.noGoalOddAtSignal!=null?'<span class="sod"><b>'+odd(s.noGoalOddAtSignal)+'</b></span>':'<span class="sod-na">n/a</span>')+
      '<span class="sodlbl">Teams</span>'+(s.teamOddsAtSignal&&s.teamOddsAtSignal.length?'<span class="sod">'+s.teamOddsAtSignal.map(t=>odd(t.odds)).join(' / ')+'</span>':'<span class="sod-na">—</span>')+
    '</div>';
  }
  const why = s.reason? '<div class="swhy">'+esc(s.reason)+'</div>':"";
  return '<div class="card scard '+st+'">'+
    '<div class="shead"><div><div class="teams">'+esc(s.home)+' <span class="neu">v</span> '+esc(s.away)+'</div>'+when+'</div>'+badge+'</div>'+
    grid+why+'</div>';
}

function kv(k,v){ return '<div class="kv"><div class="k">'+k+'</div><div class="vv">'+esc(String(v))+'</div></div>'; }
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

async function tick(){
  try{
    const r = await fetch("/api/backtest",{cache:"no-store"});
    if(r.ok) render(await r.json());
  }catch(e){}
}
$("#reset").addEventListener("click", async ()=>{
  if(!confirm("Reset the run? Clears all bets and returns the bankroll to start.")) return;
  await fetch("/api/backtest/reset",{method:"POST"});
  prevBankroll=null; prevSettled=0; tick();
});
tick();
setInterval(tick, 1500);
</script>
</body></html>`;
// ─────────────────────────────────────  END TEMPORARY /backtest  ──────────────────────────

const httpServer = app.listen(PORT, "0.0.0.0", async () => {
  console.log(`Automated Monitor Active at http://localhost:${PORT}`);
  logPersistenceStatus();
  loadBlacklist();
  systemLog = loadSystemLog();
  console.log(`[SYSTEM LOG] Loaded ${systemLog.length} persisted exclusion(s) from ${SYSTEM_LOG_PATH}`);
  loadTestMonitor();
  initWebPush();
  await startOneWinMonitorLoop();
});

// ── Instant dashboard push over WebSocket ──────────────────────────────────────────────────────
// The browser cannot connect to 1win's socket directly (needs server-side origin/partner headers +
// subscription management, and CORS would block it), so the server stays the single 1win consumer
// and relays each change to browsers over this socket. WebSocket upgrades aren't buffered by the HF
// proxy the way SSE is, so pushes land in ~100ms. Shares buildDashboardPayload with the SSE/poll
// paths; the client falls back to 1.5s polling if the socket can't connect.
const dashboardWss = new WebSocketServer({ server: httpServer, path: "/ws/dashboard" });
dashboardWss.on("connection", (ws) => {
  dashboardWsClients.add(ws);
  ws.isAlive = true;
  ws.on("pong", () => { ws.isAlive = true; });
  ws.on("close", () => dashboardWsClients.delete(ws));
  ws.on("error", () => dashboardWsClients.delete(ws));
  try { ws.send(JSON.stringify(buildDashboardPayload())); } catch { dashboardWsClients.delete(ws); }
});
// Keepalive: ping every 30s and drop sockets that didn't pong, so dead clients don't leak and idle
// proxies don't silently close the connection.
setInterval(() => {
  for (const ws of dashboardWsClients) {
    if (ws.isAlive === false) { try { ws.terminate(); } catch {} dashboardWsClients.delete(ws); continue; }
    ws.isAlive = false;
    try { ws.ping(); } catch { dashboardWsClients.delete(ws); }
  }
}, 30000);
