/* codle.js — Codle AI Platform client-side engine
   Handles: particles, toast, command palette, flow visualizer,
            complexity chart, keyboard shortcuts, export utilities */
"use strict";

// ── Namespace ────────────────────────────────────────────────────────────────
window.Codle = window.Codle || {};

// ── Particle background ──────────────────────────────────────────────────────
Codle.Particles = (function () {
  let canvas, ctx, particles = [], raf;
  const CFG = { count: 55, speed: 0.28, size: [1, 2.2], color: "99,102,241", connDist: 130, opacity: 0.55 };

  function init() {
    canvas = document.getElementById("codle-particles");
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    resize();
    spawn();
    loop();
    window.addEventListener("resize", resize);
  }

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  function spawn() {
    particles = [];
    for (let i = 0; i < CFG.count; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * CFG.speed,
        vy: (Math.random() - 0.5) * CFG.speed,
        r: CFG.size[0] + Math.random() * (CFG.size[1] - CFG.size[0]),
        o: 0.2 + Math.random() * CFG.opacity,
      });
    }
  }

  function loop() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > canvas.width)  p.vx *= -1;
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${CFG.color},${p.o})`;
      ctx.fill();
    });
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const d  = Math.sqrt(dx * dx + dy * dy);
        if (d < CFG.connDist) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(${CFG.color},${0.12 * (1 - d / CFG.connDist)})`;
          ctx.lineWidth   = 0.6;
          ctx.stroke();
        }
      }
    }
    raf = requestAnimationFrame(loop);
  }

  return { init };
})();

// ── Toast notifications ──────────────────────────────────────────────────────
Codle.Toast = (function () {
  function show(msg, type = "info", duration = 3200) {
    let container = document.getElementById("codle-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "codle-toast-container";
      document.body.appendChild(container);
    }
    const icons = { success: "✓", error: "✕", info: "ℹ" };
    const el = document.createElement("div");
    el.className = `codle-toast toast-${type}`;
    el.innerHTML = `<span>${icons[type] || "ℹ"}</span><span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => {
      el.style.animation = "toast-out 0.3s ease forwards";
      setTimeout(() => el.remove(), 310);
    }, duration);
  }
  return { show, success: m => show(m, "success"), error: m => show(m, "error"), info: m => show(m, "info") };
})();

// ── Command palette ──────────────────────────────────────────────────────────
Codle.CommandPalette = (function () {
  const CMDS = [
    { icon: "🚀", label: "Analyze Code",           shortcut: "Ctrl+Enter", action: () => document.querySelector(".btn-primary")?.click() },
    { icon: "🗑",  label: "Clear Editor",           shortcut: "Ctrl+K",     action: () => document.querySelector(".btn-clear")?.click() },
    { icon: "📋", label: "Copy Report",             shortcut: "Ctrl+Shift+C", action: () => Codle.Export.copyReport() },
    { icon: "📥", label: "Download Markdown",       shortcut: "Ctrl+S",     action: () => document.querySelector(".btn-download-md")?.click() },
    { icon: "📊", label: "Download JSON",           shortcut: "",           action: () => document.querySelector(".btn-download-json")?.click() },
    { icon: "🔄", label: "Go to Translator tab",   shortcut: "",           action: () => Codle.UI.switchTab(1) },
    { icon: "📈", label: "Go to Complexity tab",   shortcut: "",           action: () => Codle.UI.switchTab(2) },
    { icon: "🌊", label: "Go to Flow tab",         shortcut: "",           action: () => Codle.UI.switchTab(3) },
  ];

  let overlay, input, listEl, filtered = [...CMDS], selected = 0;

  function build() {
    if (document.getElementById("codle-cmd-overlay")) return;
    overlay = document.createElement("div");
    overlay.id = "codle-cmd-overlay";
    overlay.innerHTML = `
      <div id="codle-cmd-box">
        <input id="codle-cmd-input" placeholder="Type a command…" autocomplete="off" spellcheck="false"/>
        <div id="codle-cmd-list"></div>
      </div>`;
    document.body.appendChild(overlay);
    input  = overlay.querySelector("#codle-cmd-input");
    listEl = overlay.querySelector("#codle-cmd-list");
    overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
    input.addEventListener("input", () => filter(input.value));
    input.addEventListener("keydown", onKey);
    render();
  }

  function filter(q) {
    filtered = q ? CMDS.filter(c => c.label.toLowerCase().includes(q.toLowerCase())) : [...CMDS];
    selected = 0;
    render();
  }

  function render() {
    listEl.innerHTML = filtered.map((c, i) => `
      <div class="cmd-item${i === selected ? " selected" : ""}" data-idx="${i}">
        <span class="cmd-icon">${c.icon}</span>
        <span class="cmd-label">${c.label}</span>
        ${c.shortcut ? `<span class="cmd-shortcut">${c.shortcut}</span>` : ""}
      </div>`).join("");
    listEl.querySelectorAll(".cmd-item").forEach(el => {
      el.addEventListener("click", () => { exec(+el.dataset.idx); });
    });
  }

  function onKey(e) {
    if (e.key === "ArrowDown") { selected = Math.min(selected + 1, filtered.length - 1); render(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { selected = Math.max(selected - 1, 0); render(); e.preventDefault(); }
    else if (e.key === "Enter")  { exec(selected); }
    else if (e.key === "Escape") { close(); }
  }

  function exec(idx) {
    if (filtered[idx]) { close(); filtered[idx].action(); }
  }

  function open()  { build(); overlay.classList.add("open"); input.value = ""; filter(""); setTimeout(() => input.focus(), 50); }
  function close() { overlay && overlay.classList.remove("open"); }
  function toggle() { overlay && overlay.classList.contains("open") ? close() : open(); }

  return { open, close, toggle };
})();

// ── Complexity Chart (Canvas 2D) ─────────────────────────────────────────────
Codle.ComplexityChart = (function () {
  const CURVES = {
    "O(1)":        { fn: n => 1,                     color: "#34d399", label: "O(1)" },
    "O(log n)":    { fn: n => Math.log2(n + 1),      color: "#22d3ee", label: "O(log n)" },
    "O(n)":        { fn: n => n,                     color: "#818cf8", label: "O(n)" },
    "O(n log n)":  { fn: n => n * Math.log2(n + 1),  color: "#a78bfa", label: "O(n log n)" },
    "O(n²)":       { fn: n => n * n,                 color: "#fbbf24", label: "O(n²)" },
    "O(2^n)":      { fn: n => Math.pow(2, n),        color: "#f87171", label: "O(2^n)" },
  };

  function draw(canvasEl, highlight) {
    const W = canvasEl.width  = canvasEl.offsetWidth  || 600;
    const H = canvasEl.height = canvasEl.offsetHeight || 220;
    const ctx = canvasEl.getContext("2d");
    const pad = { t: 20, r: 20, b: 40, l: 52 };
    const cw = W - pad.l - pad.r;
    const ch = H - pad.t - pad.b;
    const N  = 40;

    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = "rgba(6,8,16,0.9)";
    ctx.fillRect(0, 0, W, H);

    // Axis grid
    ctx.strokeStyle = "rgba(30,41,59,0.8)";
    ctx.lineWidth   = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (ch * i) / 4;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + cw, y); ctx.stroke();
    }
    for (let i = 0; i <= 5; i++) {
      const x = pad.l + (cw * i) / 5;
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t + ch); ctx.stroke();
    }

    // Axis labels
    ctx.fillStyle = "rgba(148,163,184,0.7)";
    ctx.font      = "11px Inter, sans-serif";
    ctx.fillText("n →", pad.l + cw - 8, pad.t + ch + 32);
    ctx.save(); ctx.translate(14, pad.t + ch / 2);
    ctx.rotate(-Math.PI / 2); ctx.fillText("ops", -12, 0); ctx.restore();

    // Compute max visible value (exclude O(2^n) for scaling)
    const maxVal = Object.values(CURVES)
      .filter(c => c.label !== "O(2^n)")
      .reduce((m, c) => Math.max(m, c.fn(N)), 0) * 1.1;

    const toX = n => pad.l + (n / N) * cw;
    const toY = v => pad.t + ch - Math.min((v / maxVal) * ch, ch);

    Object.entries(CURVES).forEach(([key, c]) => {
      const isHighlighted = highlight && key === highlight;
      ctx.beginPath();
      ctx.strokeStyle = isHighlighted ? c.color : c.color + "66";
      ctx.lineWidth   = isHighlighted ? 2.5 : 1.2;
      ctx.shadowColor = isHighlighted ? c.color : "transparent";
      ctx.shadowBlur  = isHighlighted ? 10 : 0;
      for (let n = 0; n <= N; n++) {
        const x = toX(n);
        const y = toY(c.fn(n));
        n === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Label at end of curve
      const endY = toY(c.fn(N));
      if (endY > pad.t && endY < pad.t + ch) {
        ctx.fillStyle = isHighlighted ? c.color : c.color + "99";
        ctx.font      = isHighlighted ? "bold 11px Fira Code, monospace" : "10px Fira Code, monospace";
        ctx.fillText(c.label, pad.l + cw + 4, Math.max(pad.t + 10, Math.min(endY + 4, pad.t + ch)));
      }
    });
  }

  function animateDraw(canvasEl, highlight) {
    let frame = 0, total = 40;
    const loop = () => {
      frame++;
      if (frame <= total) {
        drawPartial(canvasEl, highlight, frame / total);
        requestAnimationFrame(loop);
      } else {
        draw(canvasEl, highlight);
      }
    };
    loop();
  }

  function drawPartial(canvasEl, highlight, progress) {
    const W = canvasEl.width  = canvasEl.offsetWidth  || 600;
    const H = canvasEl.height = canvasEl.offsetHeight || 220;
    const ctx = canvasEl.getContext("2d");
    const pad = { t: 20, r: 20, b: 40, l: 52 };
    const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b, N = 40;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "rgba(6,8,16,0.9)"; ctx.fillRect(0, 0, W, H);

    const maxVal = Object.values(CURVES).filter(c => c.label !== "O(2^n)").reduce((m, c) => Math.max(m, c.fn(N)), 0) * 1.1;
    const toX = n => pad.l + (n / N) * cw;
    const toY = v => pad.t + ch - Math.min((v / maxVal) * ch, ch);
    const drawN = Math.floor(N * progress);

    Object.entries(CURVES).forEach(([key, c]) => {
      ctx.beginPath();
      ctx.strokeStyle = key === highlight ? c.color : c.color + "55";
      ctx.lineWidth   = key === highlight ? 2.5 : 1.2;
      for (let n = 0; n <= drawN; n++) {
        const x = toX(n), y = toY(c.fn(n));
        n === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
    });
  }

  return { draw, animateDraw };
})();

// ── Execution Flow Visualizer (Canvas 2D) ────────────────────────────────────
Codle.FlowViz = (function () {
  const NODE_COLORS = {
    start:      { bg: "rgba(52,211,153,0.18)",  border: "#34d399", text: "#6ee7b7" },
    "return":   { bg: "rgba(248,113,113,0.18)", border: "#f87171", text: "#fca5a5" },
    condition:  { bg: "rgba(251,191,36,0.18)",  border: "#fbbf24", text: "#fde68a" },
    loop:       { bg: "rgba(167,139,250,0.18)", border: "#a78bfa", text: "#c4b5fd" },
    function:   { bg: "rgba(99,102,241,0.18)",  border: "#6366f1", text: "#a5b4fc" },
    call:       { bg: "rgba(34,211,238,0.18)",  border: "#22d3ee", text: "#67e8f9" },
    assignment: { bg: "rgba(30,41,59,0.6)",     border: "#475569", text: "#94a3b8" },
    default:    { bg: "rgba(30,41,59,0.6)",     border: "#334155", text: "#94a3b8" },
  };

  let state = { data: null, canvas: null, ctx: null, playing: false, step: 0, speed: 800, raf: null, view: "flow" };

  function loadData(data, canvasEl) {
    state.data = data;
    state.canvas = canvasEl;
    state.ctx = canvasEl.getContext("2d");
    state.step = 0;
    state.playing = false;
    render();
  }

  function layout(nodes) {
    const cols = Math.ceil(Math.sqrt(nodes.length));
    const padX = 160, padY = 110, startX = 120, startY = 80;
    return nodes.map((n, i) => ({
      ...n,
      x: startX + (i % cols) * padX,
      y: startY + Math.floor(i / cols) * padY,
      w: 130, h: 54,
    }));
  }

  function render() {
    if (!state.canvas || !state.data) return;
    const W = state.canvas.width  = state.canvas.offsetWidth  || 700;
    const H = state.canvas.height = state.canvas.offsetHeight || 420;
    const ctx = state.ctx;

    ctx.clearRect(0, 0, W, H);

    // Dark bg with subtle grid
    ctx.fillStyle = "rgba(6,8,16,0.97)";
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(30,41,59,0.4)";
    ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
    for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

    if (!state.data.nodes || !state.data.nodes.length) {
      ctx.fillStyle = "rgba(148,163,184,0.5)";
      ctx.font = "14px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("No flow data. Run analysis first.", W/2, H/2);
      return;
    }

    const laid = layout(state.data.nodes);

    // Draw edges
    (state.data.edges || []).forEach(edge => {
      const from = laid.find(n => n.id === edge.from);
      const to   = laid.find(n => n.id === edge.to);
      if (!from || !to) return;
      const sx = from.x + from.w/2, sy = from.y + from.h;
      const ex = to.x + to.w/2,    ey = to.y;
      const isActive = state.step > 0 && (from.id <= state.step && to.id <= state.step + 1);

      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.bezierCurveTo(sx, sy + 30, ex, ey - 30, ex, ey);
      ctx.strokeStyle = isActive ? "rgba(99,102,241,0.85)" : "rgba(51,65,85,0.6)";
      ctx.lineWidth   = isActive ? 2 : 1.2;
      ctx.shadowColor = isActive ? "#6366f1" : "transparent";
      ctx.shadowBlur  = isActive ? 8 : 0;
      ctx.stroke();
      ctx.shadowBlur  = 0;

      // Arrowhead
      const angle = Math.atan2(ey - (sy+30), ex - (sx+30));
      ctx.beginPath();
      ctx.moveTo(ex, ey);
      ctx.lineTo(ex - 9*Math.cos(angle-0.4), ey - 9*Math.sin(angle-0.4));
      ctx.lineTo(ex - 9*Math.cos(angle+0.4), ey - 9*Math.sin(angle+0.4));
      ctx.closePath();
      ctx.fillStyle = isActive ? "rgba(99,102,241,0.85)" : "rgba(51,65,85,0.6)";
      ctx.fill();

      // Edge label
      if (edge.label) {
        ctx.fillStyle = "rgba(148,163,184,0.7)";
        ctx.font = "10px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(edge.label, (sx+ex)/2, (sy+ey)/2);
      }
    });

    // Draw nodes
    laid.forEach(n => {
      const col     = NODE_COLORS[n.type] || NODE_COLORS.default;
      const active  = state.step > 0 && n.id === state.step;
      const visited = state.step > 0 && n.id < state.step;

      // Shadow glow on active
      if (active) {
        ctx.shadowColor = col.border;
        ctx.shadowBlur  = 18;
      }

      // Card bg
      ctx.fillStyle = active ? col.bg.replace("0.18","0.38") : col.bg;
      roundRect(ctx, n.x, n.y, n.w, n.h, 10);
      ctx.fill();

      // Card border
      ctx.strokeStyle = active ? col.border : (visited ? col.border + "77" : "rgba(30,41,59,0.8)");
      ctx.lineWidth   = active ? 2 : 1;
      roundRect(ctx, n.x, n.y, n.w, n.h, 10);
      ctx.stroke();
      ctx.shadowBlur  = 0;

      // Label
      ctx.fillStyle   = active ? col.text : (visited ? col.text + "cc" : "rgba(148,163,184,0.7)");
      ctx.font        = active ? "bold 12px Inter, sans-serif" : "12px Inter, sans-serif";
      ctx.textAlign   = "center";
      ctx.fillText(truncate(n.label, 18), n.x + n.w/2, n.y + n.h/2 - 6);

      // Detail
      ctx.fillStyle   = "rgba(148,163,184,0.55)";
      ctx.font        = "10px Inter, sans-serif";
      ctx.fillText(truncate(n.detail, 22), n.x + n.w/2, n.y + n.h/2 + 9);

      // Line number badge
      ctx.fillStyle   = "rgba(99,102,241,0.5)";
      ctx.font        = "9px Fira Code, monospace";
      ctx.fillText("L" + n.line, n.x + n.w - 18, n.y + 12);
    });

    // Title
    if (state.data.title) {
      ctx.fillStyle = "rgba(165,180,252,0.7)";
      ctx.font      = "12px Inter, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText("⟶ " + state.data.title, 14, 20);
    }
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function truncate(s, len) { return s && s.length > len ? s.slice(0, len) + "…" : (s || ""); }

  function play() {
    if (!state.data) return;
    state.playing = true;
    const total = state.data.nodes.length;
    function tick() {
      if (!state.playing) return;
      state.step = (state.step % (total + 1)) + 1;
      render();
      if (state.step <= total) state.raf = setTimeout(tick, state.speed);
      else { state.playing = false; state.step = 0; render(); }
    }
    tick();
  }

  function pause()  { state.playing = false; clearTimeout(state.raf); }
  function replay() { pause(); state.step = 0; render(); setTimeout(play, 200); }
  function setSpeed(v) { state.speed = Math.max(200, 1600 - v * 14); }
  function stepFwd()  { if (!state.data) return; state.step = Math.min(state.step + 1, state.data.nodes.length); render(); }
  function stepBack() { if (!state.data) return; state.step = Math.max(state.step - 1, 0); render(); }

  return { loadData, render, play, pause, replay, setSpeed, stepFwd, stepBack };
})();

// ── Export utilities ─────────────────────────────────────────────────────────
Codle.Export = (function () {
  function getOutputText() {
    const el = document.querySelector(".output-panel, .prose");
    return el ? el.innerText : "";
  }

  function copyReport() {
    const text = getOutputText();
    if (!text || text.includes("Results will appear here")) {
      Codle.Toast.info("No report to copy yet.");
      return;
    }
    navigator.clipboard.writeText(text)
      .then(() => Codle.Toast.success("Report copied to clipboard!"))
      .catch(() => Codle.Toast.error("Clipboard access denied."));
  }

  function downloadMarkdown(text, filename) {
    if (!text || text.includes("Results will appear here")) {
      Codle.Toast.info("No report to export yet.");
      return;
    }
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    triggerDownload(blob, filename || "codle_report.md");
    Codle.Toast.success("Markdown report downloaded!");
  }

  function downloadJSON(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    triggerDownload(blob, filename || "codle_report.json");
    Codle.Toast.success("JSON report downloaded!");
  }

  function screenshotReport() {
    Codle.Toast.info("Use browser Print (Ctrl+P) → Save as PDF for a full-page screenshot.");
  }

  function triggerDownload(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return { copyReport, downloadMarkdown, downloadJSON, screenshotReport, getOutputText };
})();

// ── UI helpers ───────────────────────────────────────────────────────────────
Codle.UI = (function () {
  function switchTab(idx) {
    const tabs = document.querySelectorAll(".tab-nav button");
    if (tabs[idx]) tabs[idx].click();
  }

  function showSkeleton(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = `
      <div class="skeleton-block" style="height:18px;width:65%;margin-bottom:12px;"></div>
      <div class="skeleton-block" style="height:14px;width:90%;margin-bottom:8px;"></div>
      <div class="skeleton-block" style="height:14px;width:80%;margin-bottom:8px;"></div>
      <div class="skeleton-block" style="height:14px;width:75%;margin-bottom:24px;"></div>
      <div class="skeleton-block" style="height:18px;width:50%;margin-bottom:12px;"></div>
      <div class="skeleton-block" style="height:14px;width:88%;margin-bottom:8px;"></div>
      <div class="skeleton-block" style="height:14px;width:70%;"></div>`;
  }

  function hideSkeleton(containerId) {
    const el = document.getElementById(containerId);
    if (el) el.innerHTML = "";
  }

  return { switchTab, showSkeleton, hideSkeleton };
})();

// ── Keyboard shortcuts ───────────────────────────────────────────────────────
Codle.Shortcuts = (function () {
  function init() {
    document.addEventListener("keydown", e => {
      const ctrl = e.ctrlKey || e.metaKey;

      // Ctrl+Enter → Analyze
      if (ctrl && e.key === "Enter") {
        e.preventDefault();
        document.querySelector(".btn-primary")?.click();
        Codle.Toast.info("Analyzing…");
      }
      // Ctrl+K → Clear
      if (ctrl && e.key === "k") {
        e.preventDefault();
        document.querySelector(".btn-clear")?.click();
      }
      // Ctrl+Shift+P or Ctrl+/ → Command palette
      if ((ctrl && e.shiftKey && e.key === "P") || (ctrl && e.key === "/")) {
        e.preventDefault();
        Codle.CommandPalette.toggle();
      }
      // Ctrl+S → download markdown
      if (ctrl && e.key === "s") {
        e.preventDefault();
        document.querySelector(".btn-download-md")?.click();
      }
      // Ctrl+Shift+C → copy report
      if (ctrl && e.shiftKey && e.key === "C") {
        e.preventDefault();
        Codle.Export.copyReport();
      }
      // Escape → close command palette
      if (e.key === "Escape") {
        Codle.CommandPalette.close();
      }
    });
  }
  return { init };
})();

// ── Boot ─────────────────────────────────────────────────────────────────────
Codle.boot = function () {
  Codle.Particles.init();
  Codle.Shortcuts.init();
  // Removed startup toast — cleaner UX
};

// Boot when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", Codle.boot);
} else {
  setTimeout(Codle.boot, 100);
}
