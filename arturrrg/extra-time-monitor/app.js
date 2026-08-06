const $ = id => document.getElementById(id);
const activeMatches = new Set();
const displayedToastIds = new Set(); // Tracks displayed toasts to prevent duplicates
const chimedNextGoal = new Set(); // Matches that already played the stoppage-time next-goal chime
const seenBeforeBoard = new Set(); // Matches witnessed live before the 2nd-half added-time board went up
const MAX_ALERT_ADDED_MINUTES = 5; // Boards over +5' are atypically long finishes (server retires the card) — no alert
const liveCardMidsSeen = new Set(); // Mids ever shown as a live card this session — drives removal toasts even after the card is pruned
const animatedLogIds = new Set(); // Exclusion-log ids that already played their entrance animation
let isFirstDashboardRender = true;
// Default OFF on first launch (mirrors the old "muted").
let nextGoalAlertsOn = loadAlertPref("nextGoalAlertsOn");
let dashboardStream = null;
let dashboardStreamConnected = false;
let dashboardWs = null;
let dashboardWsConnected = false;
let dashboardWsReconnectTimer = null;
const dashboardCardOrder = new Map();
let nextDashboardCardOrder = 0;
let lastDashboardPayload = null;
const favoriteCards = new Set(loadFavoriteCards());
const seenRemovalIds = new Set(loadInitialSeenRemovalIds());

function loadInitialSeenRemovalIds() {
  try {
    const logs = JSON.parse(localStorage.getItem("removed_matches_log") || "[]");
    return logs.map(log => log.id);
  } catch {
    return [];
  }
}

function loadFavoriteCards() {
  try {
    return JSON.parse(localStorage.getItem("favoriteMatchCards") || "[]");
  } catch {
    return [];
  }
}

function saveFavoriteCards() {
  try {
    localStorage.setItem("favoriteMatchCards", JSON.stringify([...favoriteCards]));
  } catch {
    // Ignore storage failures in private or restricted browser sessions.
  }
}

// Alert prefs default OFF. We also honour the legacy "alertsMuted" key so a user who
// had the old single toggle UNMUTED keeps both alerts on after upgrade.
function loadAlertPref(key) {
  try {
    const stored = localStorage.getItem(key);
    if (stored !== null) return stored === "true";
    const legacy = localStorage.getItem("alertsMuted");
    if (legacy !== null) return legacy === "false"; // unmuted → alerts on
    return false; // default off on first launch
  } catch {
    return false;
  }
}

function saveAlertPrefs() {
  try {
    localStorage.setItem("nextGoalAlertsOn", nextGoalAlertsOn ? "true" : "false");
  } catch {
    // Ignore storage failures in private or restricted browser sessions.
  }
}

// The alert being on means the device should hold a push subscription.
function anyAlertOn() {
  return nextGoalAlertsOn;
}

// ── Web Audio chime ──────────────────────────────────────────────
// Browsers block audio until a user gesture, so the context is created
// lazily and resumed on the first interaction (see setupMuteToggle).
let audioCtx = null;

function ensureAudioContext() {
  const Ctor = window.AudioContext || window.webkitAudioContext;
  if (!Ctor) return null;
  if (!audioCtx) {
    try {
      audioCtx = new Ctor();
    } catch {
      return null;
    }
  }
  if (audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

function playChimeTone(ctx, freq, startOffset, duration, peak) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const t0 = ctx.currentTime + startOffset;

  osc.type = "triangle";
  osc.frequency.setValueAtTime(freq, t0);

  gain.gain.setValueAtTime(0.0001, t0);
  gain.gain.exponentialRampToValueAtTime(peak, t0 + 0.04);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);

  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(t0);
  osc.stop(t0 + duration + 0.05);
}

function playAlertChime() {
  // Animate the bell first so it reacts even when audio is blocked/suspended.
  pulseBell();
  const ctx = ensureAudioContext();
  if (!ctx) return;
  // Warm rising two-note ding (A5 -> E6), soft exponential decay.
  playChimeTone(ctx, 880, 0, 0.45, 0.22);
  playChimeTone(ctx, 1318.5, 0.16, 0.5, 0.2);
}

// Swing + glow the bell button on any alert (next-goal @90' or an incoming push
// relayed to the open tab). Re-trigger-safe via reflow.
function pulseBell() {
  const btn = $("alert-mute-btn");
  if (!btn) return;
  btn.classList.remove("bell-alerting");
  void btn.offsetWidth;
  btn.classList.add("bell-alerting");
  setTimeout(() => btn.classList.remove("bell-alerting"), 1100);
}

// Basic desktop notification (Notifications API), fired from the open page.
// Only when the tab is VISIBLE — a hidden/closed tab is covered by the service
// worker push instead, so the two paths never double up.
function showDesktopNotification(title, body) {
  try {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    if (document.visibilityState !== "visible") return;
    new Notification(title, {
      body,
      icon: "/favicon.svg",
      badge: "/favicon.svg",
      tag: "nextgoal-alert",
      renotify: true
    });
  } catch {
    // Some mobile browsers forbid the Notification constructor — push covers those.
  }
}

function updateFavoriteButton(mid) {
  const btn = $(`favoriteBtn-${mid}`);
  if (!btn) return;

  const isFavorite = favoriteCards.has(mid);
  btn.classList.toggle("is-active", isFavorite);
  btn.setAttribute("aria-pressed", isFavorite ? "true" : "false");
  btn.setAttribute("data-tooltip", isFavorite ? "Unpin favorite" : "Pin favorite");
}

function toggleFavoriteCard(mid, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget) event.currentTarget.blur();
  }

  if (favoriteCards.has(mid)) favoriteCards.delete(mid);
  else favoriteCards.add(mid);

  saveFavoriteCards();
  updateFavoriteButton(mid);
  if (lastDashboardPayload) renderDashboardPayload(lastDashboardPayload);
}

function getCurrentMinute(timeStr) {
  if (!timeStr) return null;
  const cleanTime = String(timeStr).trim().toUpperCase();
  if (cleanTime === "HT") return 45;
  if (cleanTime === "FT") return 90;
  
  const match = cleanTime.match(/^(\d+)/);
  if (match) {
    return parseInt(match[1], 10);
  }
  return null;
}

function getPositiveInt(value) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function getSecondHalfStoppageClock(info = {}) {
  const explicit = getPositiveInt(info.secondHalfElapsedAddedTime);
  if (explicit > 0 && explicit <= 30) return explicit;

  // Only DERIVE a stoppage clock from the running minute when it is a plausible second-half
  // stoppage (<= +15). A larger gap means the match is in extra time — the server drops ET
  // matches, but this guards against ever rendering a bogus "+29"-style clock mid-drop.
  const currentMin = getPositiveInt(info.currentMin);
  if (currentMin > 90 && currentMin - 90 <= 15) return currentMin - 90;

  const timeMin = getCurrentMinute(info.time);
  if (timeMin > 90 && timeMin - 90 <= 15) return timeMin - 90;

  return 0;
}

function formatMatchClock(info = {}, isFinished = false) {
  const announcedAddedTime = getPositiveInt(info.secondHalfInjuryTime);
  const stoppageClock = getSecondHalfStoppageClock(info);
  const hasAnnouncedAddedTime = announcedAddedTime > 0;

  if (stoppageClock > 0) {
    const liveClock = `${90 + stoppageClock}'`;
    return hasAnnouncedAddedTime ? `${liveClock} +${announcedAddedTime}` : liveClock;
  }

  if (isFinished) {
    return hasAnnouncedAddedTime ? `90' +${announcedAddedTime}` : "90'";
  }

  const timeText = info.time || "00:00";
  return hasAnnouncedAddedTime ? `${timeText} +${announcedAddedTime}` : timeText;
}

// Compact leg label for the "other markets" chips: abbreviate Over/Under/Yes/No, append the line
// value when present (e.g. "Over 2.5" → "O 2.5", a handicap leg → "Home -1"). Anything else (team
// names, "Yes"/"No") shows as-is. Keeps a Total/Handicap board readable as a row of small chips.
function formatOtherLegLabel(leg = {}) {
  const outcomeRaw = String(leg.outcome || "").trim();
  const line = String(leg.line == null ? "" : leg.line).trim();
  const lc = outcomeRaw.toLowerCase();
  let label = outcomeRaw;
  if (lc === "over" || lc === "o") label = "O";
  else if (lc === "under" || lc === "u") label = "U";
  else if (lc === "yes") label = "Yes";
  else if (lc === "no") label = "No";
  // Avoid doubling the line if the outcome string already carries it (e.g. "Over 2.5").
  const lineShown = line && !outcomeRaw.includes(line) ? ` ${line}` : "";
  return `${label}${lineShown}` || "—";
}

// One leg as a compact label+odds chip (e.g. "O 2.5  1.85"), reused by the detail strip.
function buildOtherLegChip(leg = {}) {
  const oddsNum = parseFloat(leg.odds);
  const val = Number.isFinite(oddsNum) ? oddsNum.toFixed(2) : String(leg.odds ?? "");
  return `<span class="odds-chip-mkt"><span class="chip-leg">${escapeHtml(formatOtherLegLabel(leg))}</span><span class="chip-odd">${escapeHtml(val)}</span></span>`;
}

// One accordion ROW for a market: a full-width name header + an (initially empty) inline detail
// area that the odds get rendered into when the row is open. Odds are revealed on demand — hover on
// desktop, tap on mobile — so the default view is just a clean list of market names. Suspended
// markets render muted with a "SUSP" tag instead of being dropped.
function buildOtherMarketRow(market = {}, mid, idx) {
  const suspTag = market.suspended ? `<span class="odds-other-susp">SUSP</span>` : "";
  return `<div class="odds-mkt-row${market.suspended ? " is-suspended" : ""}">` +
    `<button type="button" class="odds-mkt-head" data-mid="${mid}" data-idx="${idx}" aria-expanded="false">` +
      `<span class="odds-mkt-name">${escapeHtml(market.name || "Market")}${suspTag}</span>` +
      `<span class="odds-mkt-chev" aria-hidden="true"></span>` +
    `</button>` +
    `<div class="odds-mkt-detail"></div>` +
  `</div>`;
}

// Per-card store of the latest other-markets array + the selected (clicked) row, so the open row
// survives the ~1s re-renders and document-level delegation can look up legs. Selection is by click
// on any device (no hover) — one row open at a time; click it again to collapse.
const otherMarketsByMid = new Map();   // mid -> markets array
const otherMarketSelByMid = new Map(); // mid -> selected market index (set by click)

// Open the selected market's row and fill its inline detail with leg chips; collapse all others.
// Re-rendered every tick so the open row's odds stay live, but the detail innerHTML only rewrites
// when the legs actually change (a stable sig) — so an open row doesn't reflow on an unrelated tick.
function renderOtherMarketDetail(mid) {
  const listEl = $(`odds-other-list-${mid}`);
  if (!listEl) return;
  const markets = otherMarketsByMid.get(mid) || [];
  const idx = otherMarketSelByMid.get(mid);
  const valid = idx != null && idx >= 0 && idx < markets.length;

  listEl.querySelectorAll(".odds-mkt-row").forEach((row, i) => {
    const on = valid && i === idx;
    row.classList.toggle("is-open", on);
    const head = row.querySelector(".odds-mkt-head");
    if (head) head.setAttribute("aria-expanded", on ? "true" : "false");
    const detail = row.querySelector(".odds-mkt-detail");
    if (!detail) return;
    if (on) {
      const legs = markets[idx].legs || [];
      const sig = "d:" + legs.map(l => `${l.outcome}@${l.line}=${l.odds}`).join(",");
      if (detail.dataset.sig !== sig) {
        detail.dataset.sig = sig;
        detail.innerHTML = legs.map(buildOtherLegChip).join("") || `<span class="odds-mkt-empty">no odds</span>`;
      }
    } else if (detail.dataset.sig) {
      detail.dataset.sig = "";
      detail.innerHTML = "";
    }
  });
}

// Timeline event icons — circular dark badges with one accent colour per event type:
// goals/corners sit inside a ringed disc, cards are rounded slips, substitution is a
// looped green-in / red-out arrow pair.
function getEventIcon(type, side) {
  switch (type) {
    case "goal":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#111827" stroke="#ef4444" stroke-width="1.5" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" stroke="#ef4444" stroke-width="1" /><polygon points="12,8 15,10 14,14 10,14 9,10" fill="#ef4444" fill-opacity="0.2" stroke="#ef4444" stroke-width="1" /></svg>`;
    case "disallowed_goal":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5"><circle cx="12" cy="12" r="10" fill="#111827" /><polygon points="12,8 15,10 14,14 10,14 9,10" fill="#1f2937" stroke="#ef4444" stroke-width="1" fill-opacity="0.1" /><line x1="4" y1="4" x2="20" y2="20" stroke="#ef4444" stroke-width="1.5" /></svg>`;
    case "penalty":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="1.5"><circle cx="12" cy="12" r="10" fill="#111827" /><polygon points="12,8 15,10 14,14 10,14 9,10" fill="#1f2937" stroke="#22c55e" stroke-width="1" /><rect x="11" y="11" width="8" height="8" rx="1.5" fill="#111827" stroke="#22c55e" stroke-width="1" /><text x="13.5" y="17.5" font-family="monospace" font-size="7" fill="#ffffff" font-weight="bold">P</text></svg>`;
    case "penalty_missed":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5"><circle cx="12" cy="12" r="10" fill="#111827" /><polygon points="12,8 15,10 14,14 10,14 9,10" fill="#1f2937" stroke="#9ca3af" stroke-width="1" /><line x1="5" y1="5" x2="19" y2="19" stroke="#ef4444" stroke-width="2" /></svg>`;
    case "yellow":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="7" y="4" width="10" height="16" rx="2" fill="#ffcc00" stroke="#ffb300" stroke-width="1" /></svg>`;
    case "red":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="7" y="4" width="10" height="16" rx="2" fill="#ff3b30" stroke="#d6251b" stroke-width="1" /></svg>`;
    case "substitution":
      return `<svg class="icon-sub" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M17 2l4 4-4 4" stroke="#22c55e" /><path d="M21 6H9a4 4 0 0 0-4 4v2" stroke="#22c55e" /><path d="M7 22l-4-4 4-4" stroke="#ef4444" /><path d="M3 18h12a4 4 0 0 0 4-4v-2" stroke="#ef4444" /></svg>`;
    case "var":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="1.5"><rect x="3" y="4" width="18" height="12" rx="1.5" fill="#111111" stroke="#eab308" /><line x1="8" y1="20" x2="16" y2="20" stroke="#eab308" /><line x1="12" y1="16" x2="12" y2="20" stroke="#eab308" /><text x="5.5" y="11.5" font-family="sans-serif" font-size="4.5" fill="#eab308" font-weight="bold">VAR</text></svg>`;
    case "corner":
      const flagColor = (side === "home") ? "#ef4444" : "#3b82f6";
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${flagColor}" stroke-width="1.5"><circle cx="12" cy="12" r="10" fill="#111827" /><path d="M9 17h6M11 17V5h1M11 5l7 3.5-7 3.5" stroke="${flagColor}" stroke-linejoin="round" stroke-linecap="round" fill="${flagColor}" fill-opacity="0.3" /></svg>`;
    case "race":
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="1.5"><circle cx="12" cy="12" r="10" fill="#111827" /><line x1="8" y1="8" x2="16" y2="8" stroke="#22c55e" stroke-width="2" /><line x1="8" y1="12" x2="16" y2="12" stroke="#22c55e" stroke-width="2" /><line x1="8" y1="16" x2="13" y2="16" stroke="#22c55e" stroke-width="2" /></svg>`;
    default:
      return `<span class="icon-sport icon-other">⬡</span>`;
  }
}

function renderSingleEvent(e) {
  const iconHtml = getEventIcon(e.type, e.side);
  const minToShow = e.minuteDisplay || `${e.minute}'`;

  return `
    <div class="timeline-row-compact">
      <div class="tl-time">${minToShow}</div>
      <div class="tl-icon">${iconHtml}</div>
      <div class="tl-event">${e.display}</div>
    </div>
  `;
}

function renderEvents(mid, events, info, timelinePending = false) {
  const log = $(`events-${mid}`);
  if (!log) return;

  if (timelinePending && events.length === 0) {
    if (log.dataset.sig === "pending") return;
    log.dataset.sig = "pending";
    log.innerHTML = `<div class="timeline-empty-period">Scanning 1win tracker timeline...</div>`;
    return;
  }

  // Skip the (expensive) timeline rebuild when nothing relevant changed.
  const sig = `${info.firstHalfScore || "0-0"}|${info.secondHalfScore || "0-0"}|` +
    events.map(e => `${e.minute}:${e.type}:${e.minuteDisplay || ""}:${e.display || ""}`).join(";");
  if (log.dataset.sig === sig) return;
  log.dataset.sig = sig;

  const firstHalf = events.filter(e => e.minute <= 45);
  const secondHalf = events.filter(e => e.minute > 45);

  let html = `<div class="timeline-period-header"><span>1ST HALF</span><span class="period-score">${info.firstHalfScore || "0-0"}</span></div>`;
  if (firstHalf.length === 0) html += `<div class="timeline-empty-period">No events</div>`;
  else html += firstHalf.map(e => renderSingleEvent(e)).join("");

  html += `<div class="timeline-period-header"><span>2ND HALF</span><span class="period-score">${info.secondHalfScore || "0-0"}</span></div>`;
  if (secondHalf.length === 0) html += `<div class="timeline-empty-period">No events</div>`;
  else html += secondHalf.map(e => renderSingleEvent(e)).join("");

  log.innerHTML = html;
}

function prepareViewportDOM() {
  const appContainer = document.querySelector(".app-container");
  if (!appContainer || $("view-viewport")) return;

  const viewport = document.createElement("div");
  viewport.className = "view-viewport";
  viewport.id = "view-viewport";

  // Single live pane now; System Logs is a modal popup (see prepareLoggerDOM).
  viewport.innerHTML = `
    <div class="view-pane pane-live" id="pane-live"></div>
  `;
  appContainer.appendChild(viewport);
}

function prepareDashboardDOM() {
  prepareViewportDOM();
  const paneLive = $("pane-live");
  if (!paneLive || $("dashboard-grid")) return;

  const legacyWorkspace = document.querySelector(".workspace-rows");
  if (legacyWorkspace) legacyWorkspace.remove();

  // The Next-goal No-Goal market renders inside each card, so the old top-level
  // market tab switcher is gone.
  const legacySwitcher = $("market-switcher");
  if (legacySwitcher) legacySwitcher.remove();

  const grid = document.createElement("div");
  grid.className = "dashboard-grid";
  grid.id = "dashboard-grid";
  paneLive.appendChild(grid);
}

function prepareAwaitingModalDOM() {
  if ($("awaiting-modal")) return;

  const overlay = document.createElement("div");
  overlay.className = "awaiting-modal-overlay";
  overlay.id = "awaiting-modal";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Awaiting matches queue");
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="awaiting-modal-panel" id="awaiting-modal-panel">
      <div class="awaiting-header">
        <span class="awaiting-status-dot" id="awaiting-dot"></span>
        <h2>AWAITING MATCHES</h2>
        <span class="awaiting-count" id="awaiting-count">0 IN QUEUE</span>
        <button class="awaiting-close-btn" id="awaiting-close-btn" type="button" aria-label="Close awaiting matches">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
      </div>
      <div class="awaiting-list" id="awaiting-list">
        <div class="awaiting-empty-state">NO MATCHES IN QUEUE...</div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.addEventListener("click", event => {
    if (event.target === overlay) closeAwaitingModal();
  });
  const closeBtn = $("awaiting-close-btn");
  if (closeBtn) closeBtn.addEventListener("click", closeAwaitingModal);
}

function openAwaitingModal() {
  const overlay = $("awaiting-modal");
  const toggle = $("awaiting-toggle-btn");
  if (!overlay) return;
  overlay.hidden = false;

  // Force reflow so the open transition runs from the hidden state.
  void overlay.offsetWidth;
  overlay.classList.add("is-open");
  lockScroll();
  if (toggle) toggle.setAttribute("aria-expanded", "true");
}

// True while either popup overlay is open — used to keep the body scroll-lock on
// until the last one closes.
function isAnyModalOpen() {
  return [".logs-modal-overlay", "#awaiting-modal"].some(sel => {
    const el = document.querySelector(sel);
    return el && el.classList.contains("is-open");
  });
}

// Set by setupHeaderScroll — lets modal open/close force the navbar to redraw so
// it shows its default (un-scrolled) look while a modal is up.
let navMorphApply = null;

function lockScroll() {
  // If a scrollbar is occupying width, replace it with padding so centred content
  // (the navbar) doesn't jump sideways when overflow:hidden removes the scrollbar.
  const sbw = window.innerWidth - document.documentElement.clientWidth;
  if (sbw > 0) document.body.style.paddingRight = `${sbw}px`;
  document.body.classList.add("modal-open");
  document.documentElement.classList.add("modal-open");
  if (navMorphApply) navMorphApply(); // navbar → default state behind the modal
}

function unlockScroll() {
  if (isAnyModalOpen()) return; // another modal still open — stay locked
  document.body.classList.remove("modal-open");
  document.documentElement.classList.remove("modal-open");
  document.body.style.paddingRight = "";
  if (navMorphApply) navMorphApply(); // restore navbar to match the scroll position
}

function closeAwaitingModal() {
  const overlay = $("awaiting-modal");
  const toggle = $("awaiting-toggle-btn");
  if (!overlay) return;
  overlay.classList.remove("is-open");
  unlockScroll();
  if (toggle) toggle.setAttribute("aria-expanded", "false");
  setTimeout(() => { overlay.hidden = true; }, 220);
}

function toggleAwaitingModal() {
  const overlay = $("awaiting-modal");
  if (!overlay) return;
  if (overlay.classList.contains("is-open")) closeAwaitingModal();
  else openAwaitingModal();
}

function setupAwaitingToggle() {
  const btn = $("awaiting-toggle-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    toggleAwaitingModal();
    btn.blur();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeAwaitingModal();
  });
}

function prepareLoggerDOM() {
  if ($("logs-modal")) return;

  const overlay = document.createElement("div");
  overlay.className = "awaiting-modal-overlay logs-modal-overlay";
  overlay.id = "logs-modal";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "System logs");
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="awaiting-modal-panel logs-modal-panel" id="removal-logger-section">
      <div class="logger-header">
        <span class="logger-status-dot" id="logger-dot"></span>
        <h2>SYSTEM LOGS</h2>
        <span class="logger-count" id="logger-count">0 SYSTEM LOGS</span>
        <a class="logs-export-btn" id="logs-export-btn" href="/api/system-log.json" target="_blank" rel="noopener" role="button" aria-label="Open full system log (JSON)" data-tooltip="System logs">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 3h5a1 1 0 0 1 1 1v5M20 4l-8 8M11 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </a>
        <button class="awaiting-close-btn" id="logs-close-btn" type="button" aria-label="Close system logs">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
      </div>
      <div class="logger-terminal" id="logger-terminal">
        <div class="logger-empty-state">AWAITING SYSTEM LOGS...</div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.addEventListener("click", event => {
    if (event.target === overlay) closeLogsModal();
  });
  const closeBtn = $("logs-close-btn");
  if (closeBtn) closeBtn.addEventListener("click", closeLogsModal);
}

function openLogsModal() {
  const overlay = $("logs-modal");
  const toggle = $("nav-logs");
  if (!overlay) return;
  overlay.hidden = false;

  void overlay.offsetWidth;
  overlay.classList.add("is-open");
  lockScroll();
  if (toggle) {
    toggle.setAttribute("aria-expanded", "true");
    toggle.classList.add("is-active");
  }
}

function closeLogsModal() {
  const overlay = $("logs-modal");
  const toggle = $("nav-logs");
  if (!overlay) return;
  overlay.classList.remove("is-open");
  unlockScroll();
  if (toggle) {
    toggle.setAttribute("aria-expanded", "false");
    toggle.classList.remove("is-active");
  }
  setTimeout(() => { overlay.hidden = true; }, 220);
}

function toggleLogsModal() {
  const overlay = $("logs-modal");
  if (!overlay) return;
  if (overlay.classList.contains("is-open")) closeLogsModal();
  else openLogsModal();
}

function prepareToastDOM() {
  if ($("toast-container")) return;
  const container = document.createElement("div");
  container.id = "toast-container";
  container.className = "toast-container";
  document.body.appendChild(container);
}

function createMatchCard(mid, targetGridId) {
  const targetGrid = $(targetGridId);
  if (!targetGrid) return;

  const card = document.createElement("div");
  card.className = "match-card";
  card.id = `card-${mid}`;

  card.innerHTML = `
    <header class="card-header">
      <div class="header-left">
        <span class="pulse-dot active"></span>
        <span id="leagueName-${mid}" class="card-logo-text">1WIN // MONITORING</span>
      </div>
      <div class="header-right">
        <button id="favoriteBtn-${mid}" class="favorite-card-btn" type="button" onclick="toggleFavoriteCard('${mid}', event)" aria-label="Pin favorite" aria-pressed="false" data-tooltip="Pin favorite">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.4l2.55 5.17 5.7.83-4.12 4.02.97 5.68L12 16.42 6.9 19.1l.97-5.68L3.75 9.4l5.7-.83L12 3.4z"/></svg>
        </button>
        <a id="brandLink-${mid}" role="button" class="brand-link-1w" data-tooltip="Match Link" onmousedown="oneWinLinkMouseDown(event)" onclick="copyHomeTeamName('${mid}', event)" onauxclick="copyHomeTeamName('${mid}', event)" style="display: none;"><img class="brand-1w-logo" src="/onewin-logo.png" alt="1win" /></a>
      </div>
    </header>
    <div class="card-body is-loading" id="body-${mid}">
      <div class="skeleton-container">
        <div class="skeleton-scoreboard">
          <div class="skeleton-element skeleton-text" style="width: 120px; height: 16px;"></div>
          <div class="skeleton-element skeleton-box" style="width: 60px; height: 32px;"></div>
          <div class="skeleton-element skeleton-text" style="width: 120px; height: 16px;"></div>
        </div>
        <div class="skeleton-center" style="display: flex; justify-content: center; margin-top: 10px;">
          <div class="skeleton-element skeleton-text" style="width: 50px; height: 14px;"></div>
        </div>
        <div class="skeleton-pred">
          <div class="skeleton-element skeleton-box" style="width: 100%; height: 22px; border-radius: 4px; margin: 20px 0 8px;"></div>
          <div class="skeleton-element skeleton-box" style="width: 100%; height: 22px; border-radius: 4px; margin: 0 0 8px;"></div>
          <div class="skeleton-element skeleton-box" style="width: 100%; height: 22px; border-radius: 4px; margin: 0;"></div>
        </div>
        <div class="skeleton-timeline" style="margin-top: 24px; border-top: 1px solid var(--border); padding-top: 20px;">
          <div class="skeleton-element skeleton-text" style="width: 110px; height: 10px; margin-bottom: 16px; display: block;"></div>
          <div class="skeleton-element skeleton-box" style="width: 100%; height: 36px; border-radius: 4px; margin-bottom: 10px; display: block;"></div>
          <div class="skeleton-element skeleton-box" style="width: 100%; height: 36px; border-radius: 4px; display: block;"></div>
        </div>
      </div>

      <div class="score-row-wrapper">
        <div class="teams-score-header">
          <span id="homeName-${mid}" class="team-name-lbl home-team-lbl">HOME</span>
          <span id="score-${mid}" class="match-score">0-0</span>
          <span id="awayName-${mid}" class="team-name-lbl away-team-lbl">AWAY</span>
        </div>
        <div id="phase-${mid}" class="match-live-phase">1ST HALF</div>
        <div id="time-${mid}" class="match-live-time">00:00</div>
      </div>
      <div class="odds-wrapper" id="odds-container-${mid}">
        <div class="odds-combined">
          <div class="odds-suspend" id="odds-suspend-${mid}" hidden>Suspended · bets not accepted</div>
          <div class="odds-section odds-section--fulltime" id="odds-section-fulltime-${mid}">
            <div class="odds-list odds-list--fulltime" id="odds-fulltime-${mid}"></div>
          </div>
          <div class="odds-section odds-section--nextgoal" id="odds-section-nextgoal-${mid}">
            <div class="odds-list odds-list--nextgoal" id="odds-nextgoal-${mid}"></div>
          </div>
          <div class="odds-other" id="odds-other-${mid}" hidden>
            <div class="odds-other-head">
              <span class="odds-other-title">Other markets</span>
              <span class="odds-other-count" id="odds-other-count-${mid}">0</span>
            </div>
            <div class="odds-other-list" id="odds-other-list-${mid}"></div>
          </div>
        </div>
      </div>

      <div class="timeline-container" id="timeline-container-${mid}">
        <div class="timeline-header">
          <span class="timeline-header-title">KEY MATCH TIMELINE</span>
        </div>
        <div class="event-log" id="events-${mid}"></div>
      </div>
    </div>
  `;
  targetGrid.appendChild(card);
}

// The single reusable widget window. Every 1win click reuses this ONE floating
// window (a fixed window name) — it navigates to the clicked match and comes to
// front, so there's never a second window to lose track of behind the dashboard.
const ONE_WIN_WIDGET_NAME = "onewin_widget";
let oneWinWidget = null; // WindowProxy of the reusable widget, if open

// Opens a 1win link in the single reusable floating "widget" window (a sized
// popup) instead of a full browser tab. A user-gesture window.open with
// width/height drops the tab strip + bookmarks bar, so it behaves like a
// detached widget. Clicking a different match loads it into the SAME window and
// brings it forward — one window, always in the same spot. We can't iframe the
// page directly: 1win sends X-Frame-Options: SAMEORIGIN which blocks it.
function openOneWinWidget(url, event) {
  if (event) {
    // auxclick fires for any non-primary button. The RIGHT button (2) must be
    // ignored so the native context menu shows and nothing launches; only the
    // MIDDLE button (1) opens the widget. Left-clicks come through "click"
    // (button 0) and are always handled.
    if (event.type === "auxclick" && event.button !== 1) return;
    event.preventDefault();
    event.stopPropagation();
  }
  if (!url || url === "#" || url === "not_found") return;

  const width = 440;
  const height = 780;

  // Position only takes effect when the widget is first created; once it exists
  // the browser keeps it where the user left it and just navigates it. Centre it
  // on the current screen.
  const screenLeft = window.screenLeft ?? window.screenX ?? 0;
  const screenTop = window.screenTop ?? window.screenY ?? 0;
  const availW = window.screen?.availWidth || window.innerWidth || width;
  const availH = window.screen?.availHeight || window.innerHeight || height;
  const left = Math.round(screenLeft + Math.max(0, (availW - width) / 2));
  const top = Math.round(screenTop + Math.max(0, (availH - height) / 2));

  const features = `popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`;

  // Reuse the fixed-name window: if it already exists the browser navigates that
  // same window to the new URL; otherwise it creates it.
  const w = window.open(url, ONE_WIN_WIDGET_NAME, features);
  if (w) {
    oneWinWidget = w;
    try { w.opener = null; } catch (_) {}
    try { w.focus(); } catch (_) {} // bring the widget forward over the dashboard
  } else {
    // Popup blocked → fall back to a normal new tab so the link still works.
    window.open(url, "_blank", "noopener");
  }
}

// Cancel the browser's native middle-click "open in new tab" before it starts.
// Chromium queues that navigation at mousedown (button 1), so cancelling it here
// — earlier than auxclick — is what actually stops the stray tab. preventDefault
// also suppresses middle-click autoscroll. The widget itself is still opened from
// the auxclick/click handler. Left (0) and right (2) buttons are left untouched.
function oneWinLinkMouseDown(event) {
  if (event && event.button === 1) event.preventDefault();
}

function copyHomeTeamName(mid, event) {
  const brandLink = $(`brandLink-${mid}`);
  if (!brandLink) return;

  if (event && event.currentTarget) {
    event.currentTarget.blur();
  }

  const existingUrl = brandLink.getAttribute("data-url");
  if (existingUrl) {
    // URL resolved → open the 1win tracker as a floating widget window.
    openOneWinWidget(existingUrl, event);
    return;
  }

  event.preventDefault();
  const homeName = brandLink.getAttribute("data-home");
  if (homeName) {
    navigator.clipboard.writeText(homeName).then(() => {
      const originalText = brandLink.textContent;
      brandLink.textContent = "COPIED!";
      brandLink.style.borderColor = "#ffffff";
      brandLink.style.color = "#ffffff";
      
      setTimeout(() => {
        brandLink.textContent = originalText;
        brandLink.style.borderColor = "";
        brandLink.style.color = "";
      }, 1000);
    }).catch(err => console.error("[CLIPBOARD ERROR]", err));
  }
}

function applyTeamNameSizing(el, name) {  if (!el) return;
  const cleanName = (name || "").trim().toUpperCase();
  el.textContent = cleanName;
  
  el.classList.remove("name-size-md", "name-size-sm", "name-size-xs");
  
  const len = cleanName.length;
  if (len > 18) {
    el.classList.add("name-size-xs");
  } else if (len > 13) {
    el.classList.add("name-size-sm");
  } else if (len > 9) {
    el.classList.add("name-size-md");
  }
}

// Tab-open chime + desktop notification for the next-goal alert. It fires the moment
// sportcast announces the 2nd-half added-time board (info.secondHalfInjuryTime), not at a
// fixed 90' — mirrors the server push.
function maybeChimeForMatch(mid, currentMin, isLive, info, match) {
  if (!isLive || currentMin === null) return;

  const home = (info.home || "Home").toUpperCase();
  const away = (info.away || "Away").toUpperCase();
  const score = info.score ? ` · ${info.score}` : "";

  // ── Next-goal stoppage-time alert ── gated on in-window eligibility, not the section's
  // market-present display state, so a match whose market is temporarily hidden still chimes
  // (matches push). Only fires once the announced board appears, and only for matches seen live
  // before it went up (so a match picked up already in stoppage time doesn't chime late).
  const bothMarketsActive = match && match.fullTimeState === "active" && match.nextGoalState === "active";
  const board = getPositiveInt(info.secondHalfInjuryTime);
  if (!board) {
    seenBeforeBoard.add(mid);
  } else if (board <= MAX_ALERT_ADDED_MINUTES && bothMarketsActive && !chimedNextGoal.has(mid) && seenBeforeBoard.has(mid)) {
    if (nextGoalAlertsOn) {
      chimedNextGoal.add(mid);
      playAlertChime();
      showDesktopNotification(`+${board}' Stoppage Time — ${home} vs ${away}`, `Next-goal "No Goal" window${score}.`);
    }
  }
}

// "active" → normal; "off" → section hidden (out of its 62'+ time window).
function applyOddsSectionState(sectionEl, state) {
  sectionEl.classList.toggle("is-off", state === "off");
}

function updateCardContent(mid, match) {
  const info = match.matchInfo || {};
  const events = match.events || [];
  const nextGoalOdds = match.nextGoalOdds || [];
  const fullTimeOdds = match.fullTimeOdds || [];

  const cardEl = $(`card-${mid}`);
  const bodyEl = $(`body-${mid}`);

  if (bodyEl && cardEl) {
    if (match.hasDetailedEvents || match.timelinePending || match.trackerTimelineReady) {
      bodyEl.classList.remove("is-loading");
    } else {
      bodyEl.classList.add("is-loading");
    }
  }

  const isLoading = bodyEl ? bodyEl.classList.contains("is-loading") : false;

  const homeNameEl = $(`homeName-${mid}`);
  const scoreEl = $(`score-${mid}`);
  const awayNameEl = $(`awayName-${mid}`);
  const phaseEl = $(`phase-${mid}`);
  const timeEl = $(`time-${mid}`);
  const brandLink = $(`brandLink-${mid}`);
  const leagueNameEl = $(`leagueName-${mid}`);

  if (homeNameEl) applyTeamNameSizing(homeNameEl, info.home);
  if (awayNameEl) applyTeamNameSizing(awayNameEl, info.away);
  if (scoreEl) scoreEl.textContent = info.score || "0-0";
  
  if (leagueNameEl) {
    leagueNameEl.textContent = match.league || "1WIN // MONITORING";
  }
  
  if (brandLink && info.home) {
    brandLink.setAttribute("data-home", info.home);
    if (match.oneWinUrl) {
      brandLink.setAttribute("data-url", match.oneWinUrl);
      brandLink.style.display = "inline-flex";
    } else {
      brandLink.removeAttribute("data-url");
      brandLink.style.display = "none";
    }
  }
  
  const phaseUpper = (info.phase || "").toUpperCase();
  const isFinished = phaseUpper.includes("FINISHED") || phaseUpper.includes("FT") || phaseUpper.includes("FRO") || phaseUpper.includes("FINISHED / PEN.");
  const isScheduled = phaseUpper.includes("SCHEDULED") || phaseUpper.includes("WAITING") || phaseUpper.includes("AM") || phaseUpper.includes("PM");
  const isLive = !isFinished && !isScheduled;

  if (phaseEl) {
    if (isFinished) { phaseEl.textContent = "FT"; phaseEl.classList.remove("live-active"); } 
    else { phaseEl.textContent = info.phase || "1ST HALF"; if (isLive) phaseEl.classList.add("live-active"); else phaseEl.classList.remove("live-active"); }
  }

  if (timeEl) {
    timeEl.textContent = formatMatchClock(info, isFinished);
    if (isFinished) { 
      timeEl.classList.remove("live-active"); 
    } else {
      if (isLive) timeEl.classList.add("live-active"); 
      else timeEl.classList.remove("live-active"); 
    }
  }

  const currentMin = getCurrentMinute(info.time);

  if (cardEl) {
    if (currentMin !== null && currentMin >= 62 && !isLoading) {
      cardEl.classList.add("eye-monitor-active");
    } else {
      cardEl.classList.remove("eye-monitor-active");
    }
    cardEl.classList.toggle("no-goal-entry-active", match.noGoalEntrySignal === true);
  }

  const alertMin = Number.isFinite(info.currentMin) ? info.currentMin : currentMin;
  maybeChimeForMatch(mid, alertMin, isLive, info, match);

  // The Full Time Result (1/X/2) section sits directly above No-Goal. Both visible at once is
  // the place-bet signal; visibility is driven by the server state ("active"|"off").
  const fullTimeSectionEl = $(`odds-section-fulltime-${mid}`);
  const fullTimeListEl = $(`odds-fulltime-${mid}`);

  if (fullTimeSectionEl && fullTimeListEl) {
    const state = match.fullTimeState || (fullTimeOdds.length > 0 ? "active" : "off");
    applyOddsSectionState(fullTimeSectionEl, state);
    const oddsSig = "ftr:" + state + ":" + ((fullTimeOdds && fullTimeOdds.length > 0)
      ? fullTimeOdds.map(item => `${item.outcome}=${item.odds}`).join(",")
      : "empty");
    if (fullTimeListEl.dataset.sig !== oddsSig) {
      fullTimeListEl.dataset.sig = oddsSig;
      if (fullTimeOdds && fullTimeOdds.length > 0) {
        // One row: "Full time result" label + the three 1/X/2 prices inline (ordered home/draw/away).
        const vals = fullTimeOdds.map(item => {
          const oddsNum = parseFloat(item.odds);
          const valStr = Number.isFinite(oddsNum) ? oddsNum.toFixed(2) : item.odds;
          return `<span class="odds-val">${valStr}</span>`;
        }).join("");
        fullTimeListEl.innerHTML =
          `<div class="odds-row odds-row--ftr"><span class="odds-line">Full time result</span><span class="ftr-vals">${vals}</span></div>`;
      } else {
        // No market priced → render nothing. The section is empty (no placeholder) until the
        // market actually appears; its visibility is driven by the server state.
        fullTimeListEl.innerHTML = "";
      }
    }
  }

  // The Next-goal market: one row, "Next goal" label + three inline badges (home scores next /
  // No Goal / away scores next), styled exactly like the Full time result row above.
  const nextGoalSectionEl = $(`odds-section-nextgoal-${mid}`);
  const nextGoalListEl = $(`odds-nextgoal-${mid}`);

  if (nextGoalSectionEl && nextGoalListEl) {
    const state = match.nextGoalState || (nextGoalOdds.length > 0 ? "active" : "off");
    applyOddsSectionState(nextGoalSectionEl, state);
    const oddsSig = "ng:" + state + ":" + ((nextGoalOdds && nextGoalOdds.length > 0)
      ? nextGoalOdds.map(item => `${item.outcome}=${item.odds}`).join(",")
      : "empty");
    if (nextGoalListEl.dataset.sig !== oddsSig) {
      nextGoalListEl.dataset.sig = oddsSig;
      if (nextGoalOdds && nextGoalOdds.length > 0) {
        const vals = nextGoalOdds.map(item => {
          const oddsNum = parseFloat(item.odds);
          const valStr = Number.isFinite(oddsNum) ? oddsNum.toFixed(2) : item.odds;
          return `<span class="odds-val">${valStr}</span>`;
        }).join("");
        nextGoalListEl.innerHTML =
          `<div class="odds-row odds-row--ftr"><span class="odds-line">Next goal</span><span class="ftr-vals">${vals}</span></div>`;
      } else {
        // No market priced → render nothing (empty section, no placeholder) until odds appear.
        nextGoalListEl.innerHTML = "";
      }
    }
  }

  // Full-event suspend banner: when 1win shows "bets not accepted", both market sections are
  // already forced to "off" (hidden) by the server, so the card surfaces only this banner.
  const suspendEl = $(`odds-suspend-${mid}`);
  if (suspendEl) suspendEl.hidden = !match.eventSuspended;

  // Compact "all other markets" list, shown directly below the No-Goal block: every market still
  // open on this fixture besides Full Time Result + No-Goal, each with its live legs/odds. Reaches
  // an empty list (count 0) when only FTR + No-Goal remain — the bet signal. Visible only while
  // No-Goal is in-window. A market that 1win suspends shows muted; one that's removed disappears
  // instantly (driven straight off the odds payload).
  const otherWrapEl = $(`odds-other-${mid}`);
  const otherCountEl = $(`odds-other-count-${mid}`);
  const otherListEl = $(`odds-other-list-${mid}`);
  if (otherWrapEl && otherCountEl && otherListEl) {
    const ngInWindow = match.nextGoalEligible !== false;
    const markets = Array.isArray(match.otherMarkets) ? match.otherMarkets : [];
    if (ngInWindow && !match.eventSuspended) {
      otherWrapEl.hidden = false;
      otherCountEl.textContent = String(markets.length);
      // Zero-state signal: glow on the count when only FTR + No-Goal are left.
      otherCountEl.classList.toggle("is-zero", markets.length === 0);
      otherMarketsByMid.set(mid, markets);

      // Render one accordion row per market (name only); odds appear in a row's inline detail on
      // hover/tap. Only rebuild the rows when the SET of markets changes, so an open row under the
      // cursor isn't torn down on an odds-only tick.
      const sig = "om:" + markets.map(mk => `${mk.id}:${mk.suspended ? "s" : "o"}`).join("|");
      if (otherListEl.dataset.sig !== sig) {
        otherListEl.dataset.sig = sig;
        otherListEl.innerHTML = markets.map((mk, i) => buildOtherMarketRow(mk, mid, i)).join("");
        // A selection that no longer maps to a market (removed/reshuffled) is cleared.
        const sel = otherMarketSelByMid.get(mid);
        if (sel != null && sel >= markets.length) otherMarketSelByMid.delete(mid);
      }
      // Re-fill the open row every tick so its odds stay live (no-op when legs are unchanged).
      renderOtherMarketDetail(mid);
    } else {
      otherWrapEl.hidden = true;
      otherListEl.dataset.sig = "";
      otherListEl.innerHTML = "";
      otherCountEl.classList.remove("is-zero");
      otherMarketsByMid.delete(mid);
      otherMarketSelByMid.delete(mid);
    }
  }

  renderEvents(mid, events, info, match.timelinePending === true);
}

function showRemovalToast(matchName, reason) {
  const container = $("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = "custom-toast";
  
  toast.innerHTML = `
    <div class="toast-header">
      <svg class="toast-warn-icon" width="16" height="14" viewBox="0 0 115 100" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M57.5 0L115 100H0L57.5 0Z" fill="#F5A623"/>
        <rect x="52" y="32" width="11" height="35" rx="5.5" fill="black"/>
        <circle cx="57.5" cy="80.5" r="7.5" fill="black"/>
      </svg>
      <span class="toast-title">MATCH FILTERED / REMOVED</span>
    </div>
    <div class="toast-body">
      <div class="toast-match-name">${matchName.toUpperCase()}</div>
      <div class="toast-reason">REASON: ${reason.toUpperCase()}</div>
    </div>
    <div class="toast-progress-bar"></div>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-fade-out");
    setTimeout(() => toast.remove(), 400);
  }, 4500);
}

function getSystemCodeByReason(reason) {
  const r = String(reason).toUpperCase();
  if (r.includes("1WIN LINK")) return "FILT-URL";
  if (r.includes("COMPLETED")) return "SYS-FT";
  if (r.includes("TIME FELL")) return "SYS-TIME";
  if (r.includes("RED CARD")) return "ALERT-RED";
  if (r.includes("GOAL SCORED")) return "ALERT-GOAL";
  if (r.includes("COOLDOWN") || r.includes("ADVANTAGE")) return "FILT-ODDS";
  return "SYS-FILT";
}

function isCompletedLogReason(reason) {
  const r = String(reason || "").toUpperCase();
  return r.includes("COMPLETED") || r.includes("NO LONGER IN CACHE") || r.includes("FINISHED") || r.includes("FULL TIME");
}

function formatLogTime(time, reason, actualAddedMinutes) {
  if (!isCompletedLogReason(reason)) return time || "60'+";
  const cleanTime = String(time || "").trim();
  // If we have actual added time, show it clearly
  if (Number.isFinite(actualAddedMinutes) && actualAddedMinutes >= 0) {
    return `FT +${actualAddedMinutes}`;
  }
  if (cleanTime === "FT") return "FT";
  if (cleanTime.startsWith("FT ") || cleanTime.startsWith("FT(")) return cleanTime;
  const displayTime = cleanTime.endsWith("'") ? cleanTime : `${cleanTime}'`;
  return `FT (${displayTime})`;
}

function normalizeLogTelemetry(reason, telemetry) {
  const nextTelemetry = telemetry || { score: "0-0", time: "60'+", oddsCount: 0, odds: [], actualAddedMinutes: null };
  if (!isCompletedLogReason(reason)) return nextTelemetry;

  return {
    ...nextTelemetry,
    oddsCount: 0,
    odds: []
  };
}

function getCardLatestData(mid) {
  const cardEl = $(`card-${mid}`);
  let telemetry = {
    score: "0-0",
    time: "60'+",
    oddsCount: 0,
    odds: [],
    oneWinUrl: null
  };

  if (cardEl) {
    telemetry.score = cardEl.querySelector(".match-score")?.textContent || "0-0";
    telemetry.time = cardEl.querySelector(".match-live-time")?.textContent || "00:00";
    const brandHref = cardEl.querySelector(".brand-link-1w")?.getAttribute("data-url");
    telemetry.oneWinUrl = brandHref || null;
    // The Under market was removed, so removal telemetry no longer captures betting
    // lines from the card — odds stay empty.
  }
  return telemetry;
}

function handleRecentRemovals(removals, serverTime) {
  if (!removals || removals.length === 0) return;
  
  const now = Date.now();
  const refTime = serverTime ? Number(serverTime) : now;
  let storedLogs = [];
  try {
    storedLogs = JSON.parse(localStorage.getItem("removed_matches_log") || "[]");
  } catch (e) {
    storedLogs = [];
  }

  let activeLogs = storedLogs.filter(log => now - log.removedAt < 20 * 60 * 1000);
  let logsChanged = false;
  
  removals.forEach(rem => {
    if (!seenRemovalIds.has(rem.id)) {
      seenRemovalIds.add(rem.id);

      const age = Math.max(0, refTime - (rem.timestamp || refTime));

      const alreadyInLogs = activeLogs.some(log => log.id === rem.id);
      if (!alreadyInLogs) {
        const mid = rem.key.replace(/[^a-z0-9]/g, "_");
        const telemetry = normalizeLogTelemetry(rem.reason, rem.telemetry || getCardLatestData(mid));

        const clientRemovedAt = now - age;

        activeLogs.push({
          id: rem.id,
          name: rem.name,
          reason: rem.reason,
          mid: mid,
          matchId: rem.matchId || null,
          removedAt: clientRemovedAt,
          telemetry: telemetry
        });
        logsChanged = true;
      }

      // Toast fires whenever the tab is visible and the removal is new (not previously seen).
      // seenRemovalIds (persisted to localStorage) is the sole anti-respam gate — once an ID
      // is in there (set unconditionally above) it will never re-enter this block, even after
      // a page reload or reconnect. No isFirstDashboardRender suppressor: if the user was
      // offline when removals happened, they should still see the toast when they return.
      //
      // However, we only show toast notifications for "fresh" system logs where remaining TTL
      // is 15 minutes or more (i.e. aged less than 5 minutes). If 14:59 hit, we suppress the toast
      // but still append it to the logger modal.
      const remainingMs = (20 * 60 * 1000) - age;
      const isFresh = remainingMs >= 15 * 60 * 1000;

      if (document.visibilityState === "visible" && isFresh) {
        if (!displayedToastIds.has(rem.id)) {
          displayedToastIds.add(rem.id);
          showRemovalToast(rem.name, rem.reason);
        }
      } else {
        displayedToastIds.add(rem.id);
      }
    }
  });

  if (logsChanged || activeLogs.length !== storedLogs.length) {
    activeLogs.sort((a, b) => b.removedAt - a.removedAt);
    localStorage.setItem("removed_matches_log", JSON.stringify(activeLogs));
    updateExclusionLogger();
  }
}

// A match that was excluded (e.g. "No FTR / Next-goal market") and then came back alive
// once its markets reappeared must not keep showing in the exclusion log. The log is
// persisted in localStorage additively, so the server dropping it from recentRemovals is
// not enough on its own — we also evict any stored entry whose fixture is a live card now,
// matched by mid or by stable matchId (covers a 1win team-name reformat while it was gone).
function evictRelistedExclusions(matches) {
  if (!Array.isArray(matches) || matches.length === 0) return;

  const liveMids = new Set();
  const liveMatchIds = new Set();
  for (const match of matches) {
    if (match.mid) liveMids.add(match.mid);
    const id = String(match.matchInfo?.matchId || "").trim();
    if (/^\d+$/.test(id)) liveMatchIds.add(id);
  }
  if (liveMids.size === 0 && liveMatchIds.size === 0) return;

  let storedLogs = [];
  try {
    storedLogs = JSON.parse(localStorage.getItem("removed_matches_log") || "[]");
  } catch (e) {
    storedLogs = [];
  }
  if (storedLogs.length === 0) return;

  const kept = storedLogs.filter(
    log => !(liveMids.has(log.mid) || (log.matchId && liveMatchIds.has(log.matchId)))
  );
  if (kept.length !== storedLogs.length) {
    localStorage.setItem("removed_matches_log", JSON.stringify(kept));
    updateExclusionLogger();
  }
}

function updateExclusionLogger() {
  const terminal = $("logger-terminal");
  if (!terminal) return;

  const logsOverlay = $("logs-modal");
  const isLogsModalOpen = !!(logsOverlay && logsOverlay.classList.contains("is-open"));

  const now = Date.now();
  let storedLogs = [];
  try {
    storedLogs = JSON.parse(localStorage.getItem("removed_matches_log") || "[]");
  } catch (e) {
    storedLogs = [];
  }
  
  const activeLogs = storedLogs.filter(log => now - log.removedAt < 20 * 60 * 1000);
  
  if (activeLogs.length !== storedLogs.length) {
    localStorage.setItem("removed_matches_log", JSON.stringify(activeLogs));
  }

  const countLbl = $("logger-count");
  if (countLbl) {
    countLbl.textContent = `${activeLogs.length} SYSTEM LOG${activeLogs.length === 1 ? "" : "S"}`;
  }

  const dot = $("logger-dot");
  if (dot) {
    dot.classList.toggle("is-active", activeLogs.length > 0);
  }

  // Nav button badge — mirrors the awaiting-queue badge, but only shows when there
  // is at least one active exclusion (system-log red, not amber).
  const navBadge = $("logs-badge");
  const navBtn = $("nav-logs");
  if (navBadge) {
    navBadge.textContent = activeLogs.length > 99 ? "99+" : String(activeLogs.length);
    navBadge.hidden = activeLogs.length === 0;
  }
  if (navBtn) navBtn.classList.toggle("has-logs", activeLogs.length > 0);

  if (activeLogs.length === 0) {
    terminal.innerHTML = `<div class="logger-empty-state">AWAITING SYSTEM LOGS...</div>`;
    return;
  }

  const renderedRows = Array.from(terminal.querySelectorAll(".logger-row"));
  const renderedIds = renderedRows.map(row => row.dataset.id);
  const activeIds = activeLogs.map(log => log.id);

  // Drop expired ids so a future re-occurrence animates in again; keeps the set bounded.
  for (const id of [...animatedLogIds]) {
    if (!activeIds.includes(id)) animatedLogIds.delete(id);
  }

  const isStructureIdentical = 
    renderedIds.length === activeIds.length && 
    renderedIds.every((id, idx) => id === activeIds[idx]);

  if (!isStructureIdentical) {
    terminal.innerHTML = activeLogs.map(log => {
      const elapsed = now - log.removedAt;
      const remainingMs = Math.max(0, (20 * 60 * 1000) - elapsed);
      const remainingMin = Math.floor(remainingMs / 60000);
      const remainingSec = Math.floor((remainingMs % 60000) / 1000);

      const remDate = new Date(log.removedAt);
      const pad = n => String(n).padStart(2, "0");
      const timeStr = `${pad(remDate.getHours())}:${pad(remDate.getMinutes())}:${pad(remDate.getSeconds())}`;

      const systemCode = getSystemCodeByReason(log.reason);
      const tel = normalizeLogTelemetry(log.reason, log.telemetry);

      const oneWinUrl = tel.oneWinUrl && tel.oneWinUrl !== "not_found" ? tel.oneWinUrl : "";
      const oneWinLinkHtml = oneWinUrl
        ? `<a class="brand-link-1w log-1w-link" role="button" data-tooltip="Match Link" onmousedown="oneWinLinkMouseDown(event)" onclick="openOneWinWidget('${oneWinUrl}', event)" onauxclick="openOneWinWidget('${oneWinUrl}', event)"><img class="brand-1w-logo" src="/onewin-logo.png" alt="1win" /></a>`
        : "";

      const buildOddsChip = (item) => {
        // Newer logs store { line, odds }; older ones stored a bare odds string.
        const rawOdds = (item && typeof item === "object") ? item.odds : item;
        const val = parseFloat(rawOdds);
        const valStr = Number.isFinite(val) ? val.toFixed(2) : String(rawOdds ?? "");
        const lineNum = (item && typeof item === "object") ? parseFloat(item.line) : NaN;
        if (Number.isFinite(lineNum)) {
          return `<span class="odds-chip"><span class="odds-chip-line">U${lineNum}</span><span class="odds-chip-sep">/</span><span class="odds-chip-val">${valStr}</span></span>`;
        }
        return `<span class="odds-chip"><span class="odds-chip-val">${valStr}</span></span>`;
      };

      const hasActualOdds = tel.odds && tel.odds.length > 0;
      const oddsChips = hasActualOdds
        ? tel.odds.map(buildOddsChip).join("")
        : (tel.oddsCount > 0 ? `<span class="odds-chip odds-chip-empty">${tel.oddsCount} LINE${tel.oddsCount === 1 ? "" : "S"}</span>` : "");
      // Odds live INSIDE the SCORE/MIN/EST telemetry row as their own box (not a strip below).
      const oddsBoxHtml = oddsChips
        ? `<div class="tel-box tel-box-odds"><span class="tel-lbl">ODDS</span><span class="tel-val">${oddsChips}</span></div>`
        : "";

      // First render of a given id → entrance animation; existing rows stay put on rebuild.
      // Only animate while the modal is actually open — otherwise the class gets baked
      // into hidden rows and the red border flash replays when the modal is next shown.
      const isNewLog = !animatedLogIds.has(log.id);
      animatedLogIds.add(log.id);
      const enterClass = (isNewLog && isLogsModalOpen) ? " logger-row--enter" : "";

      return `
        <div class="logger-row${enterClass}" data-id="${log.id}">
          <div class="log-header-line">
            <span class="log-tag tag-${systemCode.toLowerCase()}">${systemCode}</span>
            <span class="log-time">[${timeStr}]</span>
            ${oneWinLinkHtml}
            <div class="log-expiry">
              <span class="expiry-label">TTL:</span>
              <span class="expiry-value">${pad(remainingMin)}M ${pad(remainingSec)}S</span>
            </div>
          </div>

          <div class="log-match-name">${log.name.toUpperCase()}</div>

          <div class="log-telemetry">
            <div class="tel-box">
              <span class="tel-lbl">SCORE</span>
              <span class="tel-val tel-score">${tel.score}</span>
            </div>
            <div class="tel-box">
              <span class="tel-lbl">MIN</span>
              <span class="tel-val tel-time">${formatLogTime(tel.time, log.reason, tel.actualAddedMinutes)}</span>
            </div>
            ${oddsBoxHtml}
          </div>

          <div class="log-reason-pane">
            <span class="reason-title">DIAGNOSTIC CRITERIA //</span>
            <div class="log-reason">${log.reason.toUpperCase()}</div>
          </div>
        </div>
      `;
    }).join("");
    // Strip the one-shot entrance class once it has played so re-opening the modal
    // (display:none → visible restarts CSS animations) can't replay the red border
    // flash on rows that were already on screen.
    terminal.querySelectorAll(".logger-row--enter").forEach(rowEl => {
      rowEl.addEventListener("animationend", () => {
        rowEl.classList.remove("logger-row--enter");
      }, { once: true });
    });
  } else {
    activeLogs.forEach(log => {
      const rowEl = terminal.querySelector(`.logger-row[data-id="${log.id}"]`);
      if (rowEl) {
        const elapsed = now - log.removedAt;
        const remainingMs = Math.max(0, (20 * 60 * 1000) - elapsed);
        const remainingMin = Math.floor(remainingMs / 60000);
        const remainingSec = Math.floor((remainingMs % 60000) / 1000);

        const pad = n => String(n).padStart(2, "0");
        const timerStr = `${pad(remainingMin)}M ${pad(remainingSec)}S`;

        const expiryValEl = rowEl.querySelector(".expiry-value");
        if (expiryValEl && expiryValEl.textContent !== timerStr) {
          expiryValEl.textContent = timerStr;
        }
      }
    });
  }
}

const BELL_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>`;
const BELL_OFF_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 18.69L7.84 6.14 5.27 3.49 4 4.76l2.8 2.8v.01c-.52.99-.8 2.16-.8 3.42v5l-2 2v1h13.73l2 2L21 21.72l-1-1.03zM12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-7.32V11c0-3.08-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68c-.15.03-.29.08-.42.12-.1.03-.2.07-.3.11h-.01c-.01 0-.01 0-.02.01-.23.09-.46.2-.68.31 0 0-.01 0-.01.01L18 14.68z"/></svg>`;

// ── Background push (OS notifications when the tab is closed/hidden) ──────
// Best-effort: degrades silently to the tab-open chime where unsupported
// (e.g. iOS Safari not installed as a PWA, or permission denied).
let swRegistration = null;
let pushSubscribed = false;

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

async function registerServiceWorker() {
  if (!pushSupported() || swRegistration) return swRegistration;
  try {
    swRegistration = await navigator.serviceWorker.register("/sw.js");
    return swRegistration;
  } catch (err) {
    console.warn("[PUSH] Service worker registration failed:", err.message);
    return null;
  }
}

// Subscribe this device to push and register it with the server. Must run from a
// user gesture (the mute button click) so the permission prompt is allowed.
async function enablePushNotifications() {
  if (!pushSupported()) return false;

  const reg = await registerServiceWorker();
  if (!reg) return false;

  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return false;

    const keyRes = await fetch("/api/push/public-key");
    if (!keyRes.ok) return false;
    const { publicKey } = await keyRes.json();
    if (!publicKey) return false;

    let subscription = await reg.pushManager.getSubscription();
    if (!subscription) {
      subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey)
      });
    }

    await fetch("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subscription, mutedNextGoal: !nextGoalAlertsOn })
    });

    pushSubscribed = true;
    return true;
  } catch (err) {
    console.warn("[PUSH] Enable failed:", err.message);
    return false;
  }
}

// Mirror the local mute flag to the server so background push respects it too.
// Sends the FULL subscription (not just the endpoint) so the server can upsert a
// fresh record if this device's endpoint rotated out from under it (MIUI/FCM) —
// otherwise an unmute would silently no-op against an endpoint the server no
// longer has, and the device would never re-arm.
async function syncMuteToServer() {
  if (!swRegistration) return;
  try {
    const subscription = await swRegistration.pushManager.getSubscription();
    if (!subscription) return;
    await fetch("/api/push/mute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subscription, mutedNextGoal: !nextGoalAlertsOn })
    });
  } catch (err) {
    console.warn("[PUSH] Mute sync failed:", err.message);
  }
}

// If the user revoked notifications in browser settings, tear down any lingering
// push subscription so the server stops sending to this device.
async function reconcileRevokedPush() {
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    if (!reg) return;
    const subscription = await reg.pushManager.getSubscription();
    if (!subscription) return;
    await fetch("/api/push/unsubscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint: subscription.endpoint })
    });
    await subscription.unsubscribe();
    pushSubscribed = false;
  } catch (err) {
    console.warn("[PUSH] Revoke reconcile failed:", err.message);
  }
}

function updateMuteButton() {
  const btn = $("alert-mute-btn");
  if (!btn) return;
  const on = anyAlertOn();
  // "is-muted" (red bell-off) when the 90' alert is off.
  btn.classList.toggle("is-muted", !on);
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  btn.innerHTML = on ? BELL_ICON : BELL_OFF_ICON;
  btn.setAttribute("data-tooltip", on ? "Alert on · 90'" : "Alert off");
}

// We only have a single notification (the 90' next-goal alert), so the bell
// button toggles it directly — no popover. Turning it on (re-)subscribes to
// push; turning it off tears the subscription down. enablePushNotifications()
// is idempotent so re-running it never double-prompts; it also re-arms a device
// whose endpoint rotated while silenced.
async function toggleAlert() {
  ensureAudioContext();
  const turningOn = !nextGoalAlertsOn;
  nextGoalAlertsOn = !nextGoalAlertsOn;
  saveAlertPrefs();
  updateMuteButton();

  if (turningOn && pushSupported()) {
    await enablePushNotifications();
  }
  if (anyAlertOn()) {
    syncMuteToServer();
  } else {
    // Off — stop background pushes to this device entirely.
    reconcileRevokedPush();
  }
}

function setupMuteToggle() {
  const btn = $("alert-mute-btn");
  if (!btn) return;

  updateMuteButton();

  // If this device already granted notifications in a previous visit, re-register
  // the (possibly refreshed) subscription silently — no prompt, no gesture needed.
  // If permission is missing/revoked, drop any stale server subscription so the
  // backend stops pushing to a device the user has silenced in browser settings.
  if (pushSupported()) {
    if (Notification.permission === "granted" && anyAlertOn()) {
      enablePushNotifications().then(() => syncMuteToServer());
    } else {
      reconcileRevokedPush();
    }
  }

  btn.addEventListener("click", () => {
    toggleAlert();
    btn.blur();
  });
}

function startLoggerTick() {
  updateExclusionLogger();
  setInterval(updateExclusionLogger, 1000);
}

function setupNavigation() {
  const btnLogs = $("nav-logs");
  if (!btnLogs) return;

  btnLogs.addEventListener("click", () => {
    toggleLogsModal();
    btnLogs.blur();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeLogsModal();
  });
}

// Scroll-linked pill draw-in. The pill outline is a FIXED-size stroke around
// the buttons. At rest NOTHING is drawn (the header is transparent, buttons
// float). As the page scrolls, the stroke grows symmetrically from the bottom
// centre: the bottom line draws out, the two ends climb the sides rounding the
// corners, with no top edge yet — until they reach the top and meet, closing
// the pill. In step, the pill's translucent backdrop + blur fade in. Done with
// a single centred dash (stroke-dasharray/offset). See .nav-morph in style.css.
const NAV_MORPH_RANGE = 70; // px of scroll over which the pill fully draws in

// Stadium (pill) outline, FIXED geometry, traced CLOCKWISE starting at the top
// centre. Because the shape is left-right symmetric, the bottom centre lands at
// exactly half the total path length — which lets a single dash centred there
// grow evenly up both sides and close at the top.
function navPillPath(left, top, right, bottom) {
  const r = (bottom - top) / 2;
  const cx = (left + right) / 2;
  return `M${cx},${top}`
    + `L${right - r},${top}`
    + `A${r},${r} 0 0 1 ${right - r},${bottom}`
    + `L${left + r},${bottom}`
    + `A${r},${r} 0 0 1 ${left + r},${top}`
    + `L${cx},${top}Z`;
}

function setupHeaderScroll() {
  const header = document.querySelector(".app-header");
  const pill = header && header.querySelector(".nav-pill");
  if (!header || !pill) return;

  // Inject the morph SVG once, behind the buttons.
  let svg = pill.querySelector(".nav-morph");
  let path;
  if (!svg) {
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "nav-morph");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("preserveAspectRatio", "none");
    path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    svg.appendChild(path);
    pill.insertBefore(svg, pill.firstChild);
  } else {
    path = svg.querySelector("path");
  }

  // Geometry (px), recomputed only when the pill actually changes size. Dims are
  // pixel-snapped (and width forced even) so the centred SVG never lands on a
  // half-pixel — a source of shimmer while the layer recomposites on scroll.
  let total = 0;
  let prevW = -1, prevH = -1;
  let lastT = -1; // last drawn progress; reset on geometry change to force a redraw
  const measure = () => {
    const rect = pill.getBoundingClientRect();
    let W = Math.round(rect.width);
    const H = Math.round(rect.height);
    if (W % 2) W += 1; // even width → translateX(-50%) stays on the pixel grid
    if (W === prevW && H === prevH) return; // ignore no-op mobile URL-bar resizes
    prevW = W; prevH = H;
    const left = 0.75, right = W - 0.75, top = 0.75, bottom = H - 0.75;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.width = `${W}px`;
    svg.style.height = `${H}px`;
    path.setAttribute("d", navPillPath(left, top, right, bottom));
    total = path.getTotalLength();
    lastT = -1; // geometry changed → next draw must run
  };

  // Skip redundant per-frame DOM writes — only repaint when the progress moves
  // meaningfully (or hits an endpoint). Cuts paint churn during fast scrolling.
  const draw = () => {
    if (!total) return;
    // While a modal is open, hold the navbar in its default (un-scrolled) look so
    // it matches its resting position rather than the scrolled pill behind the modal.
    const locked = document.body.classList.contains("modal-open");
    const raw = locked ? 0 : Math.min(1, Math.max(0, window.scrollY / NAV_MORPH_RANGE));
    const t = raw * raw * (3 - 2 * raw); // smoothstep
    if (Math.abs(t - lastT) < 0.003 && t > 0 && t < 1) return;
    lastT = t;
    // Drawn length grows from 0 (nothing) to the whole perimeter, kept centred
    // on the bottom centre (path length total/2) so it draws out from the bottom.
    const vis = total * t;
    if (vis >= total - 0.5) {
      path.style.strokeDasharray = "none"; // fully closed — clean continuous outline
      path.style.strokeDashoffset = "0";
      path.style.opacity = "1";
    } else if (vis < 1) {
      path.style.opacity = "0"; // nothing yet — avoid a stray round-cap dot
    } else {
      path.style.strokeDasharray = `${vis} ${total}`;
      path.style.strokeDashoffset = `${(vis - total) / 2}`;
      path.style.opacity = "1";
    }
    // Pill backdrop + blur fade in together with the draw.
    pill.style.backgroundColor = `rgba(12, 12, 12, ${(0.55 * t).toFixed(3)})`;
    pill.style.setProperty("--nav-blur", `${(14 * t).toFixed(2)}px`);
    pill.style.boxShadow = t > 0.01 ? `0 6px 20px rgba(0, 0, 0, ${(0.5 * t).toFixed(3)})` : "none";
    header.classList.toggle("is-scrolled", raw > 0.02);
  };

  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { draw(); ticking = false; });
  };

  navMorphApply = draw; // let modal open/close force a navbar redraw
  measure();
  draw();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", () => { measure(); draw(); }, { passive: true });
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}

function renderAwaitingQueue(awaiting) {
  const list = $("awaiting-list");
  if (!list) return;

  const countLbl = $("awaiting-count");
  if (countLbl) {
    countLbl.textContent = `${awaiting.length} IN QUEUE`;
  }

  const dot = $("awaiting-dot");
  if (dot) dot.classList.toggle("is-active", awaiting.length > 0);

  const badge = $("awaiting-badge");
  const toggle = $("awaiting-toggle-btn");
  if (badge) {
    badge.textContent = awaiting.length > 99 ? "99+" : String(awaiting.length);
    // Hidden entirely when the queue is empty; amber count when queued.
    badge.hidden = awaiting.length === 0;
  }
  if (toggle) toggle.classList.toggle("has-queue", awaiting.length > 0);

  if (awaiting.length === 0) {
    if (list.dataset.sig !== "empty") {
      list.dataset.sig = "empty";
      list.innerHTML = `<div class="awaiting-empty-state">NO MATCHES IN QUEUE...</div>`;
    }
    return;
  }

  const sig = awaiting.map(m => `${m.mid}:${m.time}:${m.score}:${m.minutesUntilAnalysis}`).join("|");
  if (list.dataset.sig === sig) return;
  list.dataset.sig = sig;

  list.innerHTML = awaiting.map(m => {
    const home = escapeHtml((m.home || "Home").toUpperCase());
    const away = escapeHtml((m.away || "Away").toUpperCase());
    const league = escapeHtml((m.league || "1WIN LIVE SOCCER").toUpperCase());
    const score = escapeHtml(m.score || "0-0");
    const minLabel = escapeHtml((m.time || `${m.currentMin}'`).trim());
    const eta = m.minutesUntilAnalysis > 0 ? `${m.minutesUntilAnalysis} MIN` : "ANY MOMENT";
    const oneWinUrl = m.oneWinUrl && m.oneWinUrl !== "not_found" ? m.oneWinUrl : "";
    const linkHtml = oneWinUrl
      ? `<a class="brand-link-1w awaiting-1w-link" role="button" data-tooltip="Match Link" onmousedown="oneWinLinkMouseDown(event)" onclick="openOneWinWidget('${escapeHtml(oneWinUrl)}', event)" onauxclick="openOneWinWidget('${escapeHtml(oneWinUrl)}', event)"><img class="brand-1w-logo" src="/onewin-logo.png" alt="1win" /></a>`
      : "";

    return `
      <div class="awaiting-row" data-id="${escapeHtml(m.mid)}">
        <div class="awaiting-row-top">
          <span class="awaiting-min">${minLabel}</span>
          <span class="awaiting-league">${league}</span>
          ${linkHtml}
        </div>
        <div class="awaiting-row-main">
          <span class="awaiting-team awaiting-team-home">${home}</span>
          <span class="awaiting-score">${score}</span>
          <span class="awaiting-team awaiting-team-away">${away}</span>
        </div>
        <div class="awaiting-row-eta">
          <span class="awaiting-eta-label">ANALYSIS IN</span>
          <span class="awaiting-eta-value">${eta}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderDashboardPayload(data) {
  lastDashboardPayload = data;
  prepareDashboardDOM();
  prepareLoggerDOM();
  prepareToastDOM();
  prepareAwaitingModalDOM();

  handleRecentRemovals(data.recentRemovals || [], data.serverTime);
  evictRelistedExclusions(data.matches || []);
  renderAwaitingQueue(data.awaiting || []);

  const activeMids = new Set();
  const grid = $("dashboard-grid");

  if (!grid) return;

  const allMatches = (data.matches || []).filter(match => {
    const events = Array.isArray(match.events) ? match.events : [];
    const timelineOk = match.timelinePending !== true || match.hasDetailedEvents === true || match.trackerTimelineReady === true || events.length > 0;
    if (!timelineOk) return false;
    // One card per match. Keep the card for the whole time the match is live and in the 62'+
    // window — tracked by nextGoalEligible (in-window), NOT nextGoalState (which is the Next-goal
    // section's market-present display state and goes "off" when that one market is merely absent;
    // gating the card on it would make in-window matches vanish). The server already removes the
    // match from the payload entirely on FT / extra-time / penalties / both-markets lapse, so a
    // still-present, in-window match is genuinely live.
    return match.nextGoalEligible !== false;
  });

  // ── Live monitor status: nothing to update in the navbar (indicator removed) ──

  if (allMatches.length === 0) {
    dashboardCardOrder.clear();
    nextDashboardCardOrder = 0;
    grid.innerHTML = `<div class="no-matches-placeholder">Awaiting matches...</div>`;
    return;
  }

  const placeholder = grid.querySelector(".no-matches-placeholder");
  if (placeholder) grid.innerHTML = "";

  for (const match of allMatches) {
    if (!dashboardCardOrder.has(match.mid)) {
      dashboardCardOrder.set(match.mid, nextDashboardCardOrder++);
    }
  }

  const favoriteRank = new Map([...favoriteCards].map((mid, index) => [mid, index]));
  const sortedMatches = allMatches.sort((a, b) => {
    const favA = favoriteCards.has(a.mid) ? 1 : 0;
    const favB = favoriteCards.has(b.mid) ? 1 : 0;
    if (favA !== favB) return favB - favA;
    if (favA && favB) return (favoriteRank.get(b.mid) || 0) - (favoriteRank.get(a.mid) || 0);

    const minA = getCurrentMinute(a.matchInfo?.time) || 0;
    const minB = getCurrentMinute(b.matchInfo?.time) || 0;
    if (minA !== minB) return minB - minA;
    return (dashboardCardOrder.get(a.mid) ?? 0) - (dashboardCardOrder.get(b.mid) ?? 0);
  });

  sortedMatches.forEach((match, index) => {
    const mid = match.mid;
    activeMids.add(mid);
    liveCardMidsSeen.add(mid); // remember it was on the board, so its later removal can toast even after the card is pruned

    let card = $(`card-${mid}`);
    if (!card) {
      createMatchCard(mid, "dashboard-grid");
      card = $(`card-${mid}`);
      if (card) card.dataset.created = Date.now();
    }

    if (card) {
      card.style.order = index;
      dashboardCardOrder.set(mid, index);
    }
    updateCardContent(mid, match);
    updateFavoriteButton(mid);
  });

  const currentCards = document.querySelectorAll(".match-card");
  currentCards.forEach(card => {
    const mid = card.id.replace("card-", "");
    if (!activeMids.has(mid)) {
      dashboardCardOrder.delete(mid);
      chimedNextGoal.delete(mid);
      seenBeforeBoard.delete(mid);
      removeMatchCard(mid);
    }
  });

  nextDashboardCardOrder = dashboardCardOrder.size;
  isFirstDashboardRender = false;
}

async function syncAutoDashboard() {
  try {
    const res = await fetch("/api/auto-matches");

    if (res.status === 404) {
      console.warn(
        `[DASHBOARD ALERT] Fetch call failed with a 404 status. Static file hosts (like GitHub Pages) do not execute backend Node environments. Please ensure your backend is active.`
      );
      throw new Error(`API returned 404 status.`);
    }

    if (!res.ok) throw new Error(`API error, status: ${res.status}`);
    renderDashboardPayload(await res.json());
  } catch (err) {
    if (err instanceof TypeError && err.message.includes("fetch")) {
      console.warn("[DASHBOARD] Sync connection failed: Relative API endpoint is unreachable.");
    } else {
      console.error("[DASHBOARD CRITICAL ERROR] syncAutoDashboard failed:", err.message);
    }
  }
}

// Primary realtime channel: a WebSocket to our server, which already holds the 1win odds socket and
// relays each change instantly (~100ms). Unlike SSE, WS upgrades aren't buffered by the HF proxy, so
// this is the path that actually feels live. Auto-reconnects; if it can't connect, the 1.5s poll in
// DOMContentLoaded keeps the board fresh.
function connectDashboardWebSocket() {
  if (!window.WebSocket || dashboardWs) return;
  try {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    dashboardWs = new WebSocket(`${proto}//${location.host}/ws/dashboard`);
  } catch (err) {
    dashboardWs = null;
    return;
  }
  dashboardWs.addEventListener("open", () => {
    dashboardWsConnected = true;
  });
  dashboardWs.addEventListener("message", event => {
    dashboardWsConnected = true;
    try {
      renderDashboardPayload(JSON.parse(event.data));
    } catch (err) {
      console.warn("[DASHBOARD] WS payload failed:", err.message);
    }
  });
  const drop = () => {
    dashboardWsConnected = false;
    if (dashboardWs) { try { dashboardWs.close(); } catch {} dashboardWs = null; }
    if (!dashboardWsReconnectTimer) {
      dashboardWsReconnectTimer = setTimeout(() => { dashboardWsReconnectTimer = null; connectDashboardWebSocket(); }, 2000);
    }
  };
  dashboardWs.addEventListener("close", drop);
  dashboardWs.addEventListener("error", drop);
}

function connectDashboardStream() {
  if (!window.EventSource || dashboardStream) return;

  dashboardStream = new EventSource("/api/dashboard-stream");
  dashboardStream.addEventListener("dashboard", event => {
    dashboardStreamConnected = true;
    try {
      renderDashboardPayload(JSON.parse(event.data));
    } catch (err) {
      console.warn("[DASHBOARD] Stream payload failed:", err.message);
    }
  });

  dashboardStream.onerror = () => {
    dashboardStreamConnected = false;
  };
}

function removeMatchCard(mid) {
  const card = $(`card-${mid}`);
  if (card && !card.classList.contains("removing")) {
    card.classList.add("removing");
    setTimeout(() => card.remove(), 350);
  }
}

// Reveal a market's odds inline in its accordion row. Click (or tap) a row to open it; click the
// same row again — OR anywhere outside the odds box — to collapse. Same behaviour on desktop and
// mobile (no hover), one row open at a time. Document-level delegation covers rows re-rendered on
// each ~1s refresh without re-binding.
function collapseAllOtherMarkets() {
  for (const mid of [...otherMarketSelByMid.keys()]) {
    otherMarketSelByMid.delete(mid);
    renderOtherMarketDetail(mid);
  }
}
function setupOtherMarketsReveal() {
  const idOf = row => {
    const head = row.querySelector(".odds-mkt-head");
    return head ? { mid: head.dataset.mid, idx: Number(head.dataset.idx) } : null;
  };

  document.addEventListener("click", (e) => {
    const row = e.target.closest?.(".odds-mkt-row");
    if (row) {
      const id = idOf(row);
      if (!id) return;
      const wasOpen = otherMarketSelByMid.get(id.mid) === id.idx;
      // Open this market on its card; close any other card's open row (one open at a time).
      collapseAllOtherMarkets();
      if (!wasOpen) {
        otherMarketSelByMid.set(id.mid, id.idx);
        renderOtherMarketDetail(id.mid);
      }
      return;
    }
    // Click outside any market row (incl. outside the odds box entirely) → collapse everything.
    collapseAllOtherMarkets();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  prepareDashboardDOM();
  prepareLoggerDOM();
  prepareToastDOM();
  prepareAwaitingModalDOM();
  setupNavigation();
  setupHeaderScroll();
  setupMuteToggle();
  setupAwaitingToggle();
  setupOtherMarketsReveal();
  connectDashboardWebSocket();
  syncAutoDashboard();
  startLoggerTick();
  document.addEventListener("visibilitychange", () => {
    // skipRemovalsOnNextPayload removed
  });
  // Fallback only: poll every 1.5s WHEN the WebSocket isn't delivering (failed to connect / dropped).
  // While the WS is up the server pushes every change instantly (~100ms) and we skip polling entirely.
  setInterval(() => { if (!dashboardWsConnected) syncAutoDashboard(); }, 1500);
});
