const POLL_INTERVAL = 3000;
const QUEUE_REFRESH_INTERVAL = 5000;
const ACTIVE_STATUSES = ["queued", "downloading"];

const listEl = document.getElementById("job-list");
const banner = document.getElementById("queue-banner");
const bannerText = document.getElementById("queue-banner-text");

const checkForm = document.getElementById("check-form");
const urlInput = document.getElementById("video-url");
const checkError = document.getElementById("check-error");
const checkBtn = document.getElementById("check-btn");

const previewCard = document.getElementById("preview-card");
const previewThumb = document.getElementById("preview-thumb");
const previewTitle = document.getElementById("preview-title");
const previewPlatform = document.getElementById("preview-platform");
const previewDuration = document.getElementById("preview-duration");
const watermarkNote = document.getElementById("watermark-note");
const formatButtons = document.querySelectorAll(".format-btn");
const resolutionSection = document.getElementById("resolution-section");
const resolutionList = document.getElementById("resolution-list");
const downloadBtn = document.getElementById("download-btn");

// job_id -> last-rendered <div class="job-card">, reused across poll ticks
// for jobs whose status hasn't changed since, so in-card UI state survives.
const cardElements = new Map();

let currentMeta = null; // {url, title, thumbnail, duration, platform, resolutions}
let selectedMode = "video";
let selectedHeight = null;
let selectedLabel = null;

const STATUS_META = {
  queued: { dot: "dot-yellow", label: "ANTRIAN", cls: "status-queued" },
  downloading: { dot: "dot-amber", label: "MENGUNDUH", cls: "status-active", progressLabel: "unduh" },
  done: { dot: "dot-teal", label: "SELESAI", cls: "status-done" },
  error: { dot: "dot-red", label: "GAGAL", cls: "status-error" },
  cancelled: { dot: "dot-muted", label: "DIBATALKAN", cls: "status-cancelled" },
};

function statusMeta(status) {
  return STATUS_META[status] || { dot: "dot-muted", label: (status || "").toUpperCase(), cls: "" };
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : str;
  return div.innerHTML;
}

function formatTime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function modeLabel(job) {
  if (job.mode === "audio") return "Audio (MP3)";
  return job.resolution_label ? `Video ${job.resolution_label}` : "Video (kualitas terbaik)";
}

// -------------------------------------------------------------------------
// Check video (metadata fetch, no download) — purely local/ephemeral state
// until the moment a download actually starts.
// -------------------------------------------------------------------------
checkForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  checkError.textContent = "";
  const url = urlInput.value.trim();
  if (!url) return;

  checkBtn.disabled = true;
  checkBtn.textContent = "Mengecek...";
  previewCard.classList.add("hidden");
  try {
    const res = await fetch("/video-downloader/api/metadata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      currentMeta = { ...data, url };
      renderPreview();
    } else {
      checkError.textContent = data.error || "Gagal mengambil info video.";
    }
  } catch (err) {
    checkError.textContent = "Gagal menghubungi server.";
  } finally {
    checkBtn.disabled = false;
    checkBtn.textContent = "Cek Video";
  }
});

function renderPreview() {
  if (!currentMeta) return;

  if (currentMeta.thumbnail) {
    previewThumb.src = currentMeta.thumbnail;
    previewThumb.classList.remove("hidden");
  } else {
    previewThumb.classList.add("hidden");
    previewThumb.removeAttribute("src");
  }

  previewTitle.textContent = currentMeta.title;
  previewPlatform.textContent = currentMeta.platform;
  previewDuration.textContent = currentMeta.duration ? formatTime(currentMeta.duration) : "-";
  watermarkNote.classList.toggle("hidden", currentMeta.platform !== "TikTok");

  selectedMode = "video";
  formatButtons.forEach((b) => b.classList.toggle("active", b.dataset.mode === "video"));

  const resolutions = currentMeta.resolutions || [];
  selectedHeight = resolutions.length ? resolutions[0].height : null;
  selectedLabel = resolutions.length ? resolutions[0].label : null;
  renderResolutionList(resolutions);
  resolutionSection.classList.toggle("hidden", resolutions.length === 0);

  previewCard.classList.remove("hidden");
}

function renderResolutionList(resolutions) {
  resolutionList.innerHTML = "";
  resolutions.forEach((r, i) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "res-chip" + (r.height === selectedHeight ? " active" : "");
    chip.innerHTML = `
      <span class="res-chip-label">${escapeHtml(r.label)}</span>
      ${r.filesize_mb ? `<span class="res-chip-size">~${r.filesize_mb} MB</span>` : ""}
      ${i === 0 ? `<span class="res-chip-badge">Rekomendasi</span>` : ""}
    `;
    chip.addEventListener("click", () => {
      selectedHeight = r.height;
      selectedLabel = r.label;
      resolutionList.querySelectorAll(".res-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
    });
    resolutionList.appendChild(chip);
  });
}

formatButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    selectedMode = btn.dataset.mode;
    formatButtons.forEach((b) => b.classList.toggle("active", b === btn));
    const hasResolutions = !!(currentMeta && currentMeta.resolutions && currentMeta.resolutions.length);
    resolutionSection.classList.toggle("hidden", selectedMode !== "video" || !hasResolutions);
  });
});

// -------------------------------------------------------------------------
// Start a download job — the server owns it entirely from here (yt-dlp runs
// in the background worker, decoupled from this request), so there's no
// "uploading bytes" phase to lose by navigating away, unlike the other tools.
// -------------------------------------------------------------------------
downloadBtn.addEventListener("click", async () => {
  if (!currentMeta) return;
  downloadBtn.disabled = true;
  downloadBtn.textContent = "Memulai...";
  checkError.textContent = "";
  try {
    const res = await fetch("/video-downloader/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: currentMeta.url,
        mode: selectedMode,
        height: selectedMode === "video" ? selectedHeight : null,
        resolution_label: selectedMode === "video" ? selectedLabel : null,
        title: currentMeta.title,
        thumbnail: currentMeta.thumbnail,
        duration: currentMeta.duration,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.job_id) {
      renderJobList();
    } else {
      checkError.textContent = data.error || "Gagal memulai download.";
    }
  } catch (err) {
    checkError.textContent = "Gagal menghubungi server.";
  } finally {
    downloadBtn.disabled = false;
    downloadBtn.textContent = "Download";
  }
});

// -------------------------------------------------------------------------
// Shared job list: server-driven, visible to every visitor regardless of
// who started what.
// -------------------------------------------------------------------------
function renderJobCard(job) {
  const meta = statusMeta(job.status);
  const isActive = ACTIVE_STATUSES.includes(job.status);
  const isDownloading = job.status === "downloading";
  const isError = job.status === "error";
  const isCancelled = job.status === "cancelled";
  const isDone = job.status === "done";
  const canRetry = isError || isCancelled;
  const progress = job.progress || 0;

  const card = document.createElement("div");
  card.className = `job-card ${meta.cls}`;
  card.id = `job-${job.job_id}`;

  card.innerHTML = `
    <div class="job-header">
      <span class="status-dot ${meta.dot}"></span>
      <span class="job-filename">${escapeHtml(job.title)}</span>
      <span class="job-status-text">${meta.label}</span>
    </div>
    <div class="job-sub">${escapeHtml(modeLabel(job))}</div>
    ${isDownloading ? `
      <div class="progress-row">
        <span class="progress-label">${job.phase === "processing" ? "memproses" : "unduh"}</span>
        <span class="progress-value">${progress}%</span>
      </div>
      <div class="slider-track">
        <div class="slider-fill" style="width:${progress}%"><span class="slider-thumb"></span></div>
      </div>
    ` : ""}
    ${isActive ? `<div class="job-sub" id="sub-${job.job_id}"></div>` : ""}
    ${isError ? `<div class="job-error">${escapeHtml(job.error || "Terjadi kesalahan.")}</div>` : ""}
    ${isCancelled ? `<div class="job-note">Dibatalkan.</div>` : ""}
    ${isDone && job.output_filename ? `<div class="job-note">${escapeHtml(job.output_filename)}</div>` : ""}
    <div class="job-actions">
      ${isDone ? `<a class="btn-secondary" href="/video-downloader/api/download-file/${job.job_id}">Simpan File</a>` : ""}
      ${canRetry ? `<button class="btn-secondary" data-action="retry">Coba Lagi</button>` : ""}
      ${isActive ? `<button class="btn-warn" data-action="cancel">Batalkan</button>` : ""}
      <button class="btn-danger" data-action="delete" ${isActive ? "disabled" : ""}>Hapus</button>
    </div>
  `;

  card.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => handleJobAction(btn.dataset.action, job));
  });

  return card;
}

async function handleJobAction(action, job) {
  if (action === "delete") {
    if (!(await showConfirm("Hapus riwayat download ini?"))) return;
    const res = await fetch(`/video-downloader/api/job/${job.job_id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal menghapus.");
      return;
    }
    cardElements.delete(job.job_id);
    renderJobList();
  } else if (action === "cancel") {
    const res = await fetch(`/video-downloader/api/job/${job.job_id}/cancel`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal membatalkan.");
    }
    renderJobList();
  } else if (action === "retry") {
    const res = await fetch(`/video-downloader/api/job/${job.job_id}/retry`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal mencoba lagi.");
    }
    renderJobList();
  }
}

function queueMessage(data) {
  if (data.status === "queued") {
    if (data.error) return data.error; // auto-retry note from the server
    const prefix = data.queue_position > 0 ? `Posisi antrian: ${data.queue_position}` : "Menunggu giliran...";
    return data.currently_processing ? `${prefix} — sedang memproses "${data.currently_processing}"` : prefix;
  }
  if (data.status === "downloading") {
    return data.phase === "processing" ? "Memproses (merge/convert ke MP3)..." : "Sedang mengunduh dari server...";
  }
  return "";
}

async function refreshSubText(jobId) {
  try {
    const res = await fetch(`/video-downloader/api/status/${jobId}`);
    if (!res.ok) return;
    const data = await res.json();
    const sub = document.getElementById(`sub-${jobId}`);
    if (sub) sub.textContent = queueMessage(data);
  } catch (err) {
    // ignore — best effort, next tick retries
  }
}

function buildOrUpdateCard(job) {
  const existing = cardElements.get(job.job_id);
  const isActive = ACTIVE_STATUSES.includes(job.status);
  if (existing && !isActive && existing.dataset.lastStatus === job.status) {
    // Terminal and unchanged since last render — reuse untouched.
    return existing;
  }
  const card = renderJobCard(job);
  card.dataset.lastStatus = job.status;
  cardElements.set(job.job_id, card);
  return card;
}

async function renderJobList() {
  try {
    const res = await fetch("/video-downloader/api/jobs");
    if (!res.ok) return;
    const jobs = await res.json();

    listEl.innerHTML = "";
    if (jobs.length === 0) {
      listEl.innerHTML = '<p class="empty">Belum ada video yang diunduh.</p>';
      return;
    }

    const seen = new Set();
    for (const job of jobs) {
      seen.add(job.job_id);
      const card = buildOrUpdateCard(job);
      listEl.appendChild(card);
      if (ACTIVE_STATUSES.includes(job.status)) {
        refreshSubText(job.job_id);
      }
    }

    for (const jobId of Array.from(cardElements.keys())) {
      if (!seen.has(jobId)) cardElements.delete(jobId); // deleted server-side
    }
  } catch (err) {
    // silent — best effort, next tick retries
  }
}

async function jobListLoop() {
  await renderJobList();
  setTimeout(jobListLoop, POLL_INTERVAL);
}

// --- "Someone else is currently processing" banner — cross-tool aware ---
async function refreshGlobalQueue() {
  try {
    const res = await fetch("/api/queue-overview");
    const data = await res.json();
    if (data.current) {
      const extra = data.pending && data.pending.length > 0
        ? ` (${data.pending.length} video lain menunggu antrian)`
        : "";
      bannerText.textContent = `sedang diproses: "${data.current.filename}" (${data.current.tool_label})${extra}`;
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  } catch (e) {
    // ignore transient network errors
  }
}
async function queueLoop() {
  await refreshGlobalQueue();
  setTimeout(queueLoop, QUEUE_REFRESH_INTERVAL);
}

// init
jobListLoop();
queueLoop();
