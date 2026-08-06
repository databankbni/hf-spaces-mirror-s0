CSS = """
@import url('https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600&family=Geist:wght@400;500;600;700;800&display=swap');

:root {
  --paper: #f4faff;
  --paper-light: #ffffff;
  --ink: #071f35;
  --ink-soft: #1f364d;
  --line: #84b9df;
  --line-soft: #c6e0f2;
  --blue: #2489c9;
  --blue-dark: #12689d;
  --blue-soft: #e6f4fe;
  --blue-strong: #d2ecfc;
  --red: #c15b62;
  --red-dark: #9c4a52;
  --red-soft: #fbeeee;
  --amber: #c47a18;
  --slate: #4c6176;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xs: 6px;
  --radius-control: 8px;
  --radius-card: 12px;
  --radius-pill: 10px;
}

* {
  box-sizing: border-box;
  font-family: 'Geist', Arial, sans-serif !important;
}

html,
body {
  background: var(--paper) !important;
  color: var(--ink) !important;
}

body,
.gradio-container {
  color-scheme: light !important;
}

.gradio-container {
  min-height: 100vh;
  color: var(--ink);
  background: var(--paper);
}

.gradio-container,
.gradio-container .main,
.gradio-container .app,
.gradio-container .container,
.gradio-container .wrap {
  background-color: transparent !important;
}

footer {
  display: none !important;
}

.main-wrap,
.gradio-container > .main {
  max-width: 1280px !important;
  margin: 0 auto !important;
}

.gradio-container .block,
.gradio-container .form,
.gradio-container .panel {
  color: var(--ink);
}

/* Brand bar: compact site identity above the hero, every tab */
.brand-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 14px;
  padding: 0 2px;
}

.brand-mark {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-ball {
  flex-shrink: 0;
  color: var(--red-dark);
}

.brand-word {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.brand-title {
  color: var(--ink);
  font-size: 15px;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.brand-sub {
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.brand-tag {
  flex-shrink: 0;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--red);
  color: #fff;
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
  font-weight: 800;
}

/* Hero */
.hero {
  position: relative;
  overflow: hidden;
  margin: 0 0 22px;
  padding: 38px clamp(22px, 4vw, 52px);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
  box-shadow: none;
}

.hero::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, var(--blue), var(--red), var(--blue-dark));
}

.hero::after {
  content: "2026";
  position: absolute;
  right: clamp(18px, 4vw, 56px);
  bottom: 18px;
  color: rgba(18, 104, 157, 0.05);
  font: 800 clamp(56px, 8vw, 112px)/1 var(--font-display, 'Geist');
  letter-spacing: -0.08em;
  pointer-events: none;
}

.eyebrow,
.match-meta,
.pick-label,
.section-index,
.field-label {
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.10em;
  text-transform: uppercase;
}

.hero .eyebrow {
  color: var(--red-dark);
}

.hero h1 {
  position: relative;
  z-index: 1;
  max-width: 800px;
  margin: 10px 0 14px;
  color: var(--ink);
  font-size: clamp(42px, 6vw, 76px);
  font-weight: 750;
  line-height: 0.98;
  letter-spacing: -0.055em;
}

.hero p {
  position: relative;
  z-index: 1;
  max-width: 760px;
  margin: 0 0 10px;
  color: var(--ink-soft);
  font-size: 17px;
  line-height: 1.6;
}

.metric-strip {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

.metric-pill,
.cutoff-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  background: rgba(255,255,255,0.78);
  color: var(--ink-soft);
  font-size: 13px;
  font-weight: 600;
}

.metric-pill strong {
  color: var(--ink);
  font-weight: 750;
}

.cutoff-badge {
  margin: 4px 0 14px;
  border-color: rgba(214, 63, 77, 0.28);
  background: var(--red-soft);
}

.cutoff-badge::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--red);
}

/* Card system */
.match-card,
.forecast-card,
.factor-card,
.reveal-card,
.lab-card {
  margin-bottom: 16px;
  padding: 20px 22px;
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: rgba(255,255,255,0.90);
  box-shadow: 0 10px 26px rgba(18, 104, 157, 0.08);
}

.match-card:last-child,
.forecast-card:last-child,
.factor-card:last-child,
.reveal-card:last-child,
.lab-card:last-child {
  margin-bottom: 0;
}

/* Player Awards uses a flatter editorial surface; the stat panels already
   provide the visual hierarchy inside each card. */
.player-awards-section {
  box-shadow: none !important;
}

.match-card:hover,
.forecast-card:hover,
.lab-card:hover {
  border-color: var(--blue);
}

.journey-intro {
  margin: 0 0 16px;
  padding: 20px 22px;
  border: 1px solid var(--line);
  border-left: 4px solid var(--red);
  border-radius: var(--radius-card);
  background: rgba(255,255,255,0.94);
}

.journey-intro h2 {
  margin-bottom: 8px;
}

.journey-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}

.journey-steps li {
  padding: 12px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-control);
  background: var(--blue-soft);
}

.journey-steps span {
  display: block;
  margin-top: 4px;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.45;
}

.challenge-panel {
  padding: 14px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-card);
  background: rgba(255,255,255,0.55);
}

.evidence-coverage {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-control);
  background: var(--blue-soft);
}

.evidence-coverage strong {
  color: var(--red-dark);
  font-size: 24px;
}

.evidence-coverage span {
  color: var(--ink-soft);
  font-size: 13px;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  padding: 5px 9px;
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  background: var(--blue-soft);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 700;
}

.stat-legend {
  margin-top: 14px;
  padding: 11px 13px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  background: rgba(255, 250, 247, 0.72);
}

.stat-legend-title {
  color: var(--ink);
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.stat-legend-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 8px;
}

.stat-legend-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 8px;
}

.stat-legend-group-title {
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.stat-legend-item {
  color: var(--ink-soft);
  font-size: 12px;
}

.stat-legend-item strong {
  margin-right: 4px;
  color: var(--red-dark);
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
}

.match-meta {
  font-size: 12px;
}

.teams {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 14px 0;
}

.team {
  min-width: 0;
  color: var(--ink);
  font-size: clamp(24px, 4vw, 40px);
  font-weight: 760;
  line-height: 1.05;
  letter-spacing: -0.035em;
}

.versus {
  flex: 0 0 auto;
  padding: 5px 13px;
  border: 1px solid rgba(214,63,77,0.28);
  border-radius: var(--radius-pill);
  background: var(--red-soft);
  color: var(--red-dark);
  font-family: 'Geist Mono', monospace !important;
  font-size: 12px;
  font-weight: 800;
}

.context,
.forecast-note,
.factor-detail,
.warning,
.small,
.signal-detail,
.pick-confidence {
  color: var(--ink-soft);
  font-size: 14px;
  line-height: 1.58;
}

.small {
  font-size: 13px;
}

code {
  padding: 2px 5px;
  border: 1px solid var(--line-soft);
  border-radius: 6px;
  background: var(--blue-soft);
  color: var(--ink);
  font-family: 'Geist Mono', monospace !important;
}

/* Forecast bars */
.prob-row {
  display: grid;
  grid-template-columns: minmax(96px, 0.8fr) minmax(80px, 1fr) 72px;
  gap: 12px;
  align-items: center;
  margin: 11px 0;
}

.prob-label {
  min-width: 0;
  overflow: hidden;
  color: var(--ink);
  font-size: 15px;
  font-weight: 750;
  text-overflow: ellipsis;
}

.prob-track {
  height: 13px;
  overflow: hidden;
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  background: #eef7fd;
}

.prob-fill {
  height: 100%;
  border-radius: inherit;
  transition: width 420ms ease;
}

.home-fill { background: linear-gradient(90deg, var(--red-dark), var(--red)); }
.draw-fill { background: linear-gradient(90deg, #7c8795, #9aa8b7); }
.away-fill { background: linear-gradient(90deg, var(--blue-dark), var(--blue)); }

.prob-value {
  color: var(--ink);
  text-align: right;
  font-family: 'Geist Mono', monospace !important;
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.forecast-note {
  margin-top: 14px;
}

/* Pick cards */
.pick-card {
  border-color: rgba(214,63,77,0.35) !important;
  background:
    linear-gradient(135deg, rgba(255,255,255,0.96), rgba(255,246,247,0.90));
}

.pick-summary,
.pick-pill {
  min-width: 160px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
  text-align: right;
}

.pick-pill.home { border-color: rgba(214,63,77,0.32); background: var(--red-soft); }
.pick-pill.draw { border-color: var(--line-soft); background: #f7fbff; }
.pick-pill.away { border-color: rgba(36,137,201,0.34); background: var(--blue-soft); }

.pick-result {
  margin-top: 4px;
  color: var(--ink);
  font-size: 22px;
  font-weight: 780;
  letter-spacing: -0.03em;
}

/* Factors and scores */
.factor-grid {
  display: grid;
  gap: 10px;
}

.factor-chip {
  padding: 12px 14px;
  border: 1px solid rgba(36,137,201,0.28);
  border-left: 4px solid var(--blue);
  border-radius: var(--radius-control);
  background: var(--blue-soft);
}

.factor-chip.dropped {
  border-color: rgba(124,135,149,0.28);
  border-left-color: #7c8795;
  background: #f7fbff;
}

.factor-title {
  color: var(--ink);
  font-weight: 760;
}

.warning {
  color: var(--red-dark);
}

.score-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.score-box {
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
}

.score-box span {
  display: block;
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.score-box strong {
  display: block;
  margin-top: 4px;
  color: var(--red-dark);
  font-size: 28px;
  font-weight: 780;
  letter-spacing: -0.04em;
}

.score-box.warn strong {
  color: var(--amber);
}

.result {
  margin: 10px 0;
  color: var(--ink);
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -0.04em;
}

/* Tables */
.table-scroll {
  margin-top: 16px;
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
}

table {
  width: 100%;
  border-collapse: collapse;
  color: var(--ink);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

th,
td {
  padding: 11px 14px;
  border-bottom: 1px solid var(--line-soft);
  text-align: left;
  white-space: nowrap;
}

th {
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

td {
  color: var(--ink);
}

tbody tr:hover {
  background: var(--blue-soft);
}

.probability-table {
  max-height: 560px;
  overflow-y: auto;
}

/* Player cards */
.player-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.player-card {
  display: flex;
  flex-direction: column;
  padding: 15px;
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: #fff;
  box-shadow: none;
}

.player-card-head {
  display: flex;
  align-items: center;
  min-height: 128px;
  gap: 12px;
  margin-bottom: 12px;
}

.player-card .attribute-panel {
  margin-top: auto;
}

.player-photo,
.player-photo-fallback {
  box-sizing: border-box !important;
  width: 66px !important;
  height: 84px !important;
  flex-shrink: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--blue-soft);
}

.player-photo {
  object-fit: cover;
  object-position: 50% 12%;
}

.player-photo-fallback,
.ovr-badge {
  display: flex;
  align-items: center;
  justify-content: center;
}

.ovr-badge {
  box-sizing: border-box !important;
  width: 52px !important;
  height: 52px !important;
  flex-shrink: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
}

.estimated-attributes {
  position: relative;
}

.ovr-value {
  color: var(--red-dark);
  font-size: 21px;
  font-weight: 800;
  line-height: 1;
}

.player-rank {
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.model-form {
  color: var(--blue-dark, #24547a);
}

.model-signal {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: baseline;
  gap: 8px;
  margin: 2px 0 10px;
  padding: 8px 10px;
  border: 1px solid rgba(36, 137, 201, 0.22);
  border-radius: var(--radius-sm);
  background: var(--blue-soft);
}

.model-signal-kicker {
  color: var(--blue-dark);
  font-family: 'Geist Mono', monospace !important;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.model-signal strong {
  color: var(--blue-dark);
  font-size: 17px;
  line-height: 1;
}

.model-signal-note {
  justify-self: end;
  color: var(--blue-dark);
  font-size: 10px;
  font-weight: 600;
  text-align: right;
}

.model-form-label {
  display: inline-block;
  margin-right: 4px;
  color: var(--blue-dark, #24547a);
  font-size: 9px;
  letter-spacing: 0.07em;
}

.rating-layer-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 2px 0 8px;
  padding-top: 9px;
  border-top: 1px solid var(--line-soft);
  color: var(--red-dark);
  font-family: 'Geist Mono', monospace !important;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.rating-layer-label small {
  color: var(--ink-muted);
  font-family: 'Geist', sans-serif !important;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.attribute-panel {
  padding: 8px 10px 10px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  background: rgba(247, 249, 252, 0.7);
  box-shadow: none;
}

.attribute-panel .rating-layer-label {
  margin: 0 0 8px;
  padding-top: 0;
  border-top: 0;
}

.player-name {
  margin-top: 2px;
  color: var(--ink);
  font-size: 16px;
  font-weight: 780;
}

.player-team {
  color: var(--ink-soft);
  font-size: 13px;
  font-weight: 600;
}

.campaign-chip {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 7px;
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  vertical-align: 1px;
}

.campaign-chip.alive {
  border-color: rgba(36, 137, 201, 0.4);
  color: var(--blue-dark, #24547a);
  background: var(--blue-soft);
}

.player-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 12px;
}

.stat-methodology {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  background: rgba(255, 250, 247, 0.8);
}

.stat-methodology-title {
  color: var(--ink);
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.stat-methodology-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 8px;
}

.stat-methodology-item {
  display: grid;
  gap: 3px;
  padding-left: 9px;
  border-left: 2px solid var(--line);
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.45;
}

.stat-methodology-item strong {
  color: var(--red-dark);
  font-size: 12px;
}

.stat-methodology-item.model-form {
  border-left-color: var(--line);
}

.stat-methodology-item.model-form strong {
  color: var(--blue-dark, #24547a);
}

@media (max-width: 640px) {
  .model-signal {
    grid-template-columns: auto auto;
  }

  .model-signal-note {
    grid-column: 1 / -1;
    justify-self: start;
    text-align: left;
  }

  .stat-methodology-grid {
    grid-template-columns: 1fr;
  }

  .stat-legend-groups {
    grid-template-columns: 1fr;
  }
}

.stat-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 700;
}

.stat-track {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8edf4;
  box-shadow: none;
}

.stat-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--blue);
  box-shadow: none;
}

.stat-fill.tier-elite {
  background: var(--blue-dark, #24547a);
}

.stat-fill.tier-weak {
  background: #a9b6c6;
}

.stat-value.tier-elite {
  color: var(--blue-dark, #24547a);
  font-weight: 800;
}

.stat-value.tier-weak {
  color: var(--ink-soft);
}

/* Gradio chrome */
.tabs {
  border-bottom: none !important;
}

/* Real structural classes for this Gradio build: .tabs > .tab-wrapper (the
   nav row) is a sibling of .tabitem (each tab's content), and every nav
   button lives inside .tab-wrapper -- so this can never leak into a tab's
   own content buttons. A restrained underline, not a pill, per the
   editorial direction. */
.tab-wrapper {
  gap: 28px !important;
  border-bottom: 1px solid var(--line-soft) !important;
  background: transparent !important;
}

/* Beat the Model and Methodology are real Tabs (5th and 6th) so their
   content gets full-page layout, but they're reached only through the
   "How this works" launch buttons or the in-page cross-links -- never
   through the visible nav row. */
.tab-wrapper .tab-container > button:nth-child(5),
.tab-wrapper .tab-container > button:nth-child(6) {
  display: none !important;
}

/* "How this works" launch buttons */
.how-it-works-launch-row {
  gap: 12px !important;
  margin-top: 8px !important;
}

button.how-it-works-launch-btn {
  border: 1px solid var(--blue) !important;
  background: #fff !important;
  color: var(--blue-dark) !important;
  font-weight: 700 !important;
  font-size: 13.5px !important;
  padding: 10px 16px !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  width: auto !important;
}

button.how-it-works-launch-btn:hover {
  background: var(--blue-soft) !important;
  border-color: var(--blue-dark) !important;
}

/* "How this works" accordion header: styled as an inviting entry point to
   the Beat the Model challenge and the methodology write-up nested inside
   it, not a plain disclosure strip. */
.gr-accordion > .label-wrap {
  padding: 14px 18px !important;
  border-radius: var(--radius-sm) !important;
  border: 1px solid rgba(36, 137, 201, 0.28) !important;
  background: var(--blue-soft) !important;
  transition: background 150ms ease, border-color 150ms ease;
}

.gr-accordion > .label-wrap:hover {
  background: var(--blue-strong) !important;
  border-color: var(--blue) !important;
}

.gr-accordion > .label-wrap span {
  color: var(--blue-dark) !important;
  font-size: 16px !important;
  font-weight: 800 !important;
  letter-spacing: -0.005em;
}

.tab-wrapper button,
.tab-wrapper span {
  padding: 12px 18px !important;
  border: 0 !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  background: transparent !important;
  color: var(--ink-soft) !important;
  font-size: 14.5px !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em !important;
  transition: color 150ms ease, border-color 150ms ease;
}

.tab-wrapper button:hover,
.tab-wrapper span:hover {
  color: var(--ink) !important;
}

.tab-wrapper button.selected,
.tab-wrapper span.selected {
  color: var(--ink) !important;
  font-weight: 700 !important;
  background: transparent !important;
  border-bottom-color: var(--red-dark) !important;
}

button,
.primary-button {
  border-radius: var(--radius-control) !important;
  font-weight: 750 !important;
}

.primary-button {
  border: 2px solid var(--red-dark) !important;
  background: var(--red) !important;
  color: #fff !important;
  box-shadow: 0 4px 0 var(--red-dark) !important;
}

.primary-button:hover {
  transform: translateY(1px);
  box-shadow: 0 3px 0 var(--red-dark) !important;
}

.secondary-button {
  border: 1px solid var(--line) !important;
  background: #fff !important;
  color: var(--ink) !important;
}

input,
textarea,
select {
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-control) !important;
  background: #fff !important;
  color: var(--ink) !important;
  font-size: 15px !important;
}

input::placeholder,
textarea::placeholder {
  color: #7890a5 !important;
}

label,
.wrap label {
  color: var(--ink) !important;
  font-weight: 650 !important;
}

/* Gradio's Soft theme renders every field label as a filled pill (light
   blue chip). Flatten it site-wide to a plain caption above the control. */
.gradio-container {
  --block-label-background-fill: transparent !important;
  --block-label-border-color: transparent !important;
  --block-label-border-width: 0px !important;
  --block-label-text-color: var(--ink-soft) !important;
  --block-label-shadow: none !important;
  --block-label-radius: 0 !important;
  --block-label-text-size: 13px !important;
  --block-label-margin: 0 !important;
  --block-label-padding: 0 !important;
  --checkbox-label-background-fill-selected: var(--blue-soft) !important;
  --checkbox-label-border-color-selected: var(--blue) !important;
  --checkbox-label-text-color-selected: var(--blue-dark) !important;
}

/* Only the block's own caption span, never a per-choice radio/checkbox
   option label (those live inside a nested .wrap > label > span and must
   keep their normal case and weight). Radio/Checkbox captions are a direct
   span child of the fieldset; Dropdown/Textbox/Slider captions sit inside
   an extra wrapper div (class "container") one level down. */
.gradio-container .block > span,
.gradio-container .block > .container > span,
.gradio-container .block .svelte-jdcl7l {
  padding: 0 !important;
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 12px !important;
  font-weight: 700 !important;
  color: var(--ink-soft) !important;
}

.prose,
.markdown,
.md {
  color: var(--ink-soft);
  line-height: 1.65;
}

.prose h2,
.prose h3,
.markdown h2,
.markdown h3,
.lab-card h2,
.world-cup-summary h2 {
  color: var(--ink);
  font-weight: 780;
  letter-spacing: -0.035em;
}

/* Upcoming compact rows */
.fixture-row {
  display: grid;
  grid-template-columns: 90px 1fr 80px 1fr 64px;
  gap: 16px;
  align-items: center;
  margin-bottom: 8px;
  padding: 14px 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
}

.fixture-row:hover {
  background: var(--blue-soft);
}

.fixture-date,
.fixture-probs {
  color: var(--ink-soft);
  font-family: 'Geist Mono', monospace !important;
  font-size: 13px;
  font-weight: 650;
}

.fixture-team {
  color: var(--ink);
  font-size: 15px;
  font-weight: 750;
}

.fixture-team.away {
  text-align: right;
}

.fixture-probs {
  display: flex;
  gap: 6px;
}

.fixture-probs .p-home { color: var(--red-dark); }
.fixture-probs .p-draw { color: var(--slate); }
.fixture-probs .p-away { color: var(--blue-dark); }

.flag {
  display: inline-block;
  margin-right: 0.4em;
  font-size: 0.95em;
  filter: drop-shadow(0 1px 1px rgba(7,31,53,0.12));
}

@media (max-width: 760px) {
  .journey-steps {
    grid-template-columns: 1fr 1fr;
  }

  .hero {
    padding: 30px 20px;
  }

  .hero h1 {
    font-size: clamp(36px, 13vw, 54px);
  }

  .hero p {
    font-size: 16px;
  }

  .match-card,
  .forecast-card,
  .factor-card,
  .reveal-card,
  .lab-card {
    padding: 16px;
  }

  .teams {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    gap: 8px;
    width: 100%;
  }

  .team {
    font-size: 18px;
    line-height: 1.14;
  }

  .team:last-child {
    text-align: right;
  }

  .versus {
    padding: 4px 9px;
  }

  .prob-row {
    grid-template-columns: minmax(70px, 0.8fr) minmax(40px, 1fr) 48px;
    gap: 8px;
  }

  .prob-label,
  .prob-value {
    font-size: 12px;
  }

  .fixture-row {
    grid-template-columns: 1fr;
  }

  .fixture-team.away {
    text-align: left;
  }
}

/* ==========================================================================
   Research shell — editorial redesign for Evidence, Beat the Model, Compare.
   Scoped entirely under .research-shell so the rest of the app (World Cup,
   Awards, Methodology) keeps its existing punchier visual language.
   ========================================================================== */

.research-shell {
  --r-bg: #faf8f3;
  --r-panel: #fffdf9;
  --r-ink: #16222f;
  --r-slate: #5d6a7a;
  --r-line: #e4e0d5;
  --r-line-soft: #eeebe1;
  --r-blue: var(--blue-dark);
  --r-red: var(--red-dark);
  --r-green: #2e7d54;
  --r-green-soft: #eef7f1;
  --r-serif: Georgia, 'Times New Roman', serif;
  color: var(--r-ink);
  font-family: 'Geist', Arial, sans-serif;
}

/* Soften the shared card system when it appears inside a research page
   (e.g. the Beat the Model challenge panel), without touching how those
   same classes look elsewhere (World Cup tab, Player Awards). */
.research-shell .match-card,
.research-shell .forecast-card,
.research-shell .factor-card,
.research-shell .reveal-card,
.research-shell .lab-card,
.research-shell .journey-intro {
  border-radius: var(--radius-sm);
  border-color: var(--r-line);
  background: var(--r-panel);
  box-shadow: none;
}

.research-shell .journey-intro {
  border-left-width: 3px;
  border-left-color: var(--r-red);
}

.research-shell .score-box {
  border-color: var(--r-line);
  background: var(--r-panel);
}

/* Flatten the app's skeuomorphic 3D button (bold color + drop-shadow lip)
   to a plain solid/outline pair when it appears on a research page. */
.research-shell .primary-button {
  border: 1px solid var(--r-red) !important;
  background: var(--r-red) !important;
  box-shadow: none !important;
  border-radius: 6px !important;
}

.research-shell .primary-button:hover {
  transform: none;
  background: #a92f3c !important;
  box-shadow: none !important;
}

.research-shell .secondary-button {
  border: 1px solid var(--r-line) !important;
  background: #fff !important;
  border-radius: 6px !important;
}

.research-shell button:not(.primary-button):not(.secondary-button) {
  border-radius: 6px !important;
}

.research-shell input,
.research-shell textarea,
.research-shell select {
  border-color: var(--r-line) !important;
  border-radius: 6px !important;
}

.research-shell .score-box strong {
  color: var(--r-ink);
}

.research-shell section.r-block {
  max-width: 1140px;
  margin: 0 auto 56px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.research-shell section.r-block:first-child {
  margin-bottom: 36px;
}

.research-shell section.r-block + section.r-block {
  padding-top: 40px;
  border-top: 1px solid var(--r-line);
}

.r-hero {
  display: flex;
  flex-wrap: wrap;
  gap: 32px;
  align-items: flex-start;
}

.r-hero-main {
  flex: 1 1 420px;
  min-width: 0;
  background: var(--r-panel);
  border: 1px solid var(--r-line);
  border-radius: var(--radius-sm);
  padding: 22px 26px;
}

.r-hero h1 {
  font-family: var(--r-serif);
  font-size: clamp(32px, 4.4vw, 44px);
  line-height: 1.08;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--r-ink);
  margin: 0 0 12px;
}

.r-hero .r-dek {
  color: var(--r-slate);
  font-size: 16.5px;
  line-height: 1.6;
  max-width: 58ch;
  margin: 0 0 12px;
}

.r-hero .r-meta {
  font-size: 12.5px;
  color: var(--r-slate);
}

/* Deliberately the one dark-toned surface on the page: a KPI card that
   reads as a headline stat, not a form field. Every color inside is
   picked for contrast against the dark fill -- never the default ink
   text, which would be nearly invisible here. */
.r-headstat {
  flex: 0 0 240px;
  border: 1px solid var(--r-ink);
  border-radius: var(--radius-sm);
  background: var(--r-ink);
  padding: 16px 20px;
}

.r-headstat .r-k {
  font-family: 'Geist Mono', monospace !important;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.62);
}

.r-headstat .r-v {
  font-family: var(--r-serif);
  font-size: 34px;
  line-height: 1.1;
  margin: 4px 0 3px;
  color: #fff;
}

.r-headstat .r-v.good { color: #7bd9a5; }
.r-headstat .r-v.bad { color: #e3949a; }

.r-headstat .r-s {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.5;
}

.r-secno {
  display: inline-block;
  font-family: 'Geist Mono', monospace !important;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--r-red);
  margin-bottom: 4px;
}

.research-shell h2 {
  font-family: var(--r-serif);
  font-size: 23px;
  font-weight: 700;
  color: var(--r-ink);
  margin: 0 0 4px;
}

.research-shell .r-sub {
  color: var(--r-slate);
  font-size: 14px;
  line-height: 1.55;
  margin: 0 0 18px;
  max-width: 72ch;
}

.r-statrow {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  border: 1px solid var(--r-line);
  background: var(--r-panel);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.r-statrow > div {
  padding: 16px 20px;
  border-right: 1px solid var(--r-line-soft);
}

.r-statrow > div:last-child {
  border-right: 0;
}

.r-statrow .r-k {
  font-size: 10.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--r-slate);
  font-weight: 700;
  font-family: 'Geist Mono', monospace !important;
}

.r-statrow .r-v {
  font-family: var(--r-serif);
  font-size: 24px;
  margin: 3px 0 2px;
  color: var(--r-ink);
}

.r-statrow .r-s {
  font-size: 11.5px;
  color: var(--r-slate);
  line-height: 1.4;
}

.research-shell table.r-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--r-panel);
  border: 1px solid var(--r-line);
  border-radius: var(--radius-sm);
  font-size: 13.5px;
  overflow: hidden;
}

.research-shell table.r-table th {
  font-family: 'Geist Mono', monospace !important;
  font-size: 10.5px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--r-slate);
  text-align: left;
  padding: 11px 16px;
  border-bottom: 1px solid var(--r-line);
  font-weight: 700;
  background: var(--r-bg);
}

.research-shell table.r-table td {
  padding: 11px 16px;
  border-bottom: 1px solid var(--r-line-soft);
  color: var(--r-ink);
}

.research-shell table.r-table tr:last-child td {
  border-bottom: 0;
}

.research-shell table.r-table td.r-num,
.research-shell table.r-table th.r-num {
  text-align: right;
  font-family: 'Geist Mono', monospace !important;
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
}

.research-shell .r-bar {
  height: 7px;
  min-width: 90px;
  background: var(--r-line-soft);
  border-radius: 999px;
  overflow: hidden;
}

.research-shell .r-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--r-blue);
}

.research-shell .r-bar.r-gray i { background: #9aa5b1; }
.research-shell .r-bar.r-red i { background: var(--r-red); }

.r-note {
  font-size: 12px;
  color: var(--r-slate);
  margin-top: 10px;
  line-height: 1.5;
}

.r-callout {
  border: 1px solid var(--r-line);
  border-left: 3px solid var(--r-blue);
  background: var(--blue-soft);
  padding: 13px 17px;
  font-size: 13.5px;
  color: var(--r-ink);
  margin-top: 18px;
  line-height: 1.55;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.r-warn {
  border: 1px solid #e8d9b8;
  border-left: 3px solid #c9992e;
  background: #fdf8ec;
  padding: 12px 16px;
  font-size: 13px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--r-ink);
  line-height: 1.5;
}

.r-src {
  font-size: 11.5px;
  color: var(--r-slate);
  border-top: 1px solid var(--r-line-soft);
  margin-top: 12px;
  padding-top: 8px;
  line-height: 1.5;
}

.r-src a { color: var(--r-blue); }

.r-grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 36px;
}

.research-shell details.r-details {
  border: 1px solid var(--r-line);
  border-radius: var(--radius-sm);
  background: var(--r-panel);
  padding: 14px 18px;
}

.research-shell details.r-details summary {
  cursor: pointer;
  font-size: 14px;
  color: var(--r-ink);
  list-style: none;
}

.research-shell details.r-details summary::-webkit-details-marker {
  display: none;
}

.research-shell details.r-details summary::before {
  content: "▸";
  display: inline-block;
  margin-right: 8px;
  color: var(--r-red);
  transition: transform 150ms ease;
}

.research-shell details.r-details[open] summary::before {
  transform: rotate(90deg);
}

.r-chip {
  display: inline-block;
  border: 1px solid var(--r-line);
  border-radius: var(--radius-pill);
  padding: 1px 9px;
  font-size: 10px;
  font-family: 'Geist Mono', monospace !important;
  color: var(--r-slate);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  vertical-align: 1px;
}

.r-cta {
  max-width: 1140px !important;
  margin: 8px auto 0 !important;
  border: 1px solid var(--r-line) !important;
  background: var(--red-soft) !important;
  border-radius: var(--radius-sm) !important;
  padding: 18px 22px !important;
  display: flex !important;
  align-items: center !important;
  gap: 16px !important;
  flex-wrap: wrap !important;
}

.r-cta .r-cta-title {
  font-weight: 700;
  color: var(--r-ink);
  font-size: 15px;
}

.r-cta .r-cta-sub {
  font-size: 13px;
  color: var(--r-slate);
}

/* The CTA action is a real gr.Button(elem_classes="r-cta-btn") so it can
   switch tabs; style it to read as the same rounded action pill regardless
   of Gradio's own button chrome. */
button.r-cta-btn {
  flex-shrink: 0;
  margin-left: auto !important;
  background: var(--r-red) !important;
  border: 1px solid var(--r-red) !important;
  color: #fff !important;
  font-weight: 700 !important;
  font-size: 13.5px !important;
  padding: 10px 18px !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  white-space: nowrap;
  width: auto !important;
}

button.r-cta-btn:hover {
  background: var(--r-ink) !important;
  border-color: var(--r-ink) !important;
}

/* Beat the Model — progress stepper */
.r-stepper {
  display: flex;
  flex-wrap: wrap;
  border: 1px solid var(--r-line);
  background: var(--r-panel);
  border-radius: var(--radius-sm);
  overflow: hidden;
  max-width: 1140px;
  margin: 0 auto 30px;
}

.r-step {
  flex: 1 1 200px;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px 16px;
  border-right: 1px solid var(--r-line-soft);
}

.r-step:last-child {
  border-right: 0;
}

.r-step .r-dot {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid var(--r-line);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11.5px;
  font-weight: 800;
  color: var(--r-slate);
}

.r-step.on .r-dot {
  background: var(--r-red);
  border-color: var(--r-red);
  color: #fff;
}

.r-step.done .r-dot {
  background: var(--r-green);
  border-color: var(--r-green);
  color: #fff;
}

.r-step .r-t {
  font-size: 13px;
  color: var(--r-slate);
}

.r-step.on .r-t {
  color: var(--r-ink);
  font-weight: 700;
}

.r-step .r-d {
  font-size: 10.5px;
  color: var(--r-slate);
}

@media (max-width: 760px) {
  .research-shell .r-hero {
    flex-direction: column;
  }

  .research-shell .r-headstat {
    flex-basis: auto;
    width: 100%;
  }

  .research-shell .r-grid2 {
    grid-template-columns: 1fr;
  }

  .research-shell .r-statrow {
    grid-template-columns: repeat(2, 1fr);
  }

  .research-shell table.r-table {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
  }

  .research-shell .r-stepper {
    flex-direction: column;
  }

  .research-shell .r-step {
    border-right: 0;
    border-bottom: 1px solid var(--r-line-soft);
  }

  .research-shell .r-step:last-child {
    border-bottom: 0;
  }

  .research-shell .r-cta {
    flex-direction: column;
    align-items: flex-start;
  }

  .research-shell .r-cta .r-cta-btn {
    margin-left: 0;
  }
}
"""
