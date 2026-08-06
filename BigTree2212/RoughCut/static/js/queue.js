const currentEl = document.getElementById("queue-current");
const pendingEl = document.getElementById("queue-pending");

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : str;
  return div.innerHTML;
}

const TOOL_BADGE_CLASS = {
  "silence-cutter": "tool-badge tool-badge--amber",
  "transcript": "tool-badge tool-badge--teal",
  "video-downloader": "tool-badge tool-badge--yellow",
};
function toolBadgeClass(tool) {
  return TOOL_BADGE_CLASS[tool] || "tool-badge tool-badge--teal";
}

const TOOL_HREF = {
  "silence-cutter": "/silence-cutter/",
  "transcript": "/transcript/",
  "video-downloader": "/video-downloader/",
};
function toolHref(tool) {
  return TOOL_HREF[tool] || "/queue";
}

function render(data) {
  if (data.current) {
    const c = data.current;
    const progress = c.progress || 0;
    currentEl.innerHTML = `
      <div class="job-card">
        <div class="job-header">
          <span class="status-dot dot-amber"></span>
          <span class="job-filename">${escapeHtml(c.filename)}</span>
          <span class="${toolBadgeClass(c.tool)}">${escapeHtml(c.tool_label)}</span>
        </div>
        <div class="progress-row">
          <span class="progress-label">progress</span>
          <span class="progress-value">${progress}%</span>
        </div>
        <div class="slider-track">
          <div class="slider-fill" style="width:${progress}%"><span class="slider-thumb"></span></div>
        </div>
        <div class="job-actions">
          <a class="btn-secondary" href="${toolHref(c.tool)}">Buka ${escapeHtml(c.tool_label)}</a>
        </div>
      </div>`;
  } else {
    currentEl.innerHTML = '<p class="queue-empty">Tidak ada yang sedang diproses saat ini.</p>';
  }

  if (data.pending && data.pending.length) {
    pendingEl.innerHTML = data.pending
      .map(
        (e) => `
      <div class="queue-row">
        <span class="queue-row__position">#${e.position}</span>
        <span class="${toolBadgeClass(e.tool)}">${escapeHtml(e.tool_label)}</span>
        <span class="queue-row__filename">${escapeHtml(e.filename)}</span>
      </div>`
      )
      .join("");
  } else {
    pendingEl.innerHTML = '<p class="queue-empty">Antrian kosong.</p>';
  }
}

async function poll() {
  try {
    const res = await fetch("/api/queue-overview");
    const data = await res.json();
    render(data);
  } catch (err) {
    // silent — keep last known state, try again next tick
  }
  setTimeout(poll, 2000);
}

poll();
