const POLL_INTERVAL = 3000;
const QUEUE_REFRESH_INTERVAL = 5000;
const ALLOWED_EXT = ["mp4", "mov", "mkv"];
const ACTIVE_STATUSES = ["queued", "extracting_audio", "downloading_audio", "transcribing"];

const listEl = document.getElementById("job-list");
const form = document.getElementById("upload-form");
const fileInput = document.getElementById("video-input");
const uploadError = document.getElementById("upload-error");
const banner = document.getElementById("queue-banner");
const bannerText = document.getElementById("queue-banner-text");
const dropzone = document.getElementById("dropzone");
const dropzoneTitle = document.getElementById("dropzone-title");
const dropzoneSub = document.getElementById("dropzone-sub");
const DROPZONE_DEFAULT_TITLE = dropzoneTitle.textContent;
const DROPZONE_DEFAULT_SUB = dropzoneSub.textContent;

// --- Upload-file vs. link-video source toggle ---
const sourceButtons = document.querySelectorAll(".format-btn[data-source]");
const urlForm = document.getElementById("url-form");
const urlInput = document.getElementById("video-url");
const urlError = document.getElementById("url-error");
const urlCheckBtn = document.getElementById("url-check-btn");
const urlPreviewCard = document.getElementById("url-preview-card");
const urlPreviewThumb = document.getElementById("url-preview-thumb");
const urlPreviewTitle = document.getElementById("url-preview-title");
const urlPreviewPlatform = document.getElementById("url-preview-platform");
const urlPreviewDuration = document.getElementById("url-preview-duration");
const urlTranscribeBtn = document.getElementById("url-transcribe-btn");

let currentUrlMeta = null; // {url, title, thumbnail, duration, platform}

sourceButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    sourceButtons.forEach((b) => b.classList.toggle("active", b === btn));
    const isUrlMode = btn.dataset.source === "url";
    form.classList.toggle("hidden", isUrlMode);
    urlForm.classList.toggle("hidden", !isUrlMode);
    if (!isUrlMode) urlPreviewCard.classList.add("hidden");
  });
});

// Uploads still transferring bytes have no job_id yet, so they can't come
// from the server — tracked purely client-side until the response arrives.
// localId -> { filename, progress, xhr }
const uploadPlaceholders = new Map();

// job_id -> the last-rendered <div class="job-card">. Reused across poll
// ticks for jobs whose status hasn't changed since, so an expanded
// transcript view (or any other in-card UI state) survives the next poll
// instead of getting wiped by a fresh re-render every few seconds.
const cardElements = new Map();

const STATUS_META = {
  queued: { dot: "dot-yellow", label: "ANTRIAN", cls: "status-queued" },
  extracting_audio: { dot: "dot-amber", label: "EKSTRAK AUDIO", cls: "status-active", progressLabel: "progress" },
  downloading_audio: { dot: "dot-amber", label: "UNDUH AUDIO", cls: "status-active", progressLabel: "unduh" },
  transcribing: { dot: "dot-amber", label: "TRANSKRIPSI", cls: "status-active", progressLabel: "progress" },
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
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function isAllowedFile(filename) {
  const ext = filename.split(".").pop().toLowerCase();
  return ALLOWED_EXT.includes(ext);
}

function renderPlaceholderCard(localId, p) {
  const card = document.createElement("div");
  card.className = "job-card status-active";
  card.innerHTML = `
    <div class="job-header">
      <span class="status-dot dot-amber"></span>
      <span class="job-filename">${escapeHtml(p.filename)}</span>
      <span class="job-status-text">UPLOADING</span>
    </div>
    <div class="progress-row">
      <span class="progress-label">upload</span>
      <span class="progress-value">${p.progress}%</span>
    </div>
    <div class="slider-track">
      <div class="slider-fill" style="width:${p.progress}%"><span class="slider-thumb"></span></div>
    </div>
    <div class="job-actions">
      <button class="btn-warn" data-action="cancel-upload">Batalkan</button>
    </div>
  `;
  card.querySelector('[data-action="cancel-upload"]').addEventListener("click", () => {
    const entry = uploadPlaceholders.get(localId);
    if (entry && entry.xhr) entry.xhr.abort();
  });
  return card;
}

function renderJobCard(job) {
  const meta = statusMeta(job.status);
  const isActive = ACTIVE_STATUSES.includes(job.status);
  const isDone = job.status === "done";
  const isError = job.status === "error";
  const isCancelled = job.status === "cancelled";
  const canRetry = isError || isCancelled;
  const progress = job.progress || 0;

  const card = document.createElement("div");
  card.className = `job-card ${meta.cls}`;
  card.id = `job-${job.job_id}`;

  card.innerHTML = `
    <div class="job-header">
      <span class="status-dot ${meta.dot}"></span>
      <span class="job-filename">${escapeHtml(job.filename)}</span>
      <span class="job-status-text">${meta.label}</span>
    </div>
    ${isActive ? `
      <div class="progress-row">
        <span class="progress-label">${meta.progressLabel || "progress"}</span>
        <span class="progress-value">${progress}%</span>
      </div>
      <div class="slider-track">
        <div class="slider-fill" style="width:${progress}%"><span class="slider-thumb"></span></div>
      </div>
      <div class="job-sub" id="sub-${job.job_id}"></div>
    ` : ""}
    ${isError ? `<div class="job-error">${escapeHtml(job.error || "Terjadi kesalahan.")}</div>` : ""}
    ${isCancelled ? `<div class="job-note">Dibatalkan.</div>` : ""}
    <div class="job-actions">
      ${isDone ? `
        <button class="btn-secondary" data-action="view">Lihat Transkrip</button>
        <a class="btn-secondary" href="/transcript/api/download/${job.job_id}/srt">Download .srt</a>
        <a class="btn-secondary" href="/transcript/api/download/${job.job_id}/txt">Download .txt</a>
      ` : ""}
      ${canRetry ? `<button class="btn-secondary" data-action="retry">Coba Lagi</button>` : ""}
      ${isActive ? `<button class="btn-warn" data-action="cancel">Batalkan</button>` : ""}
      <button class="btn-danger" data-action="delete" ${isActive ? "disabled" : ""}>Hapus</button>
    </div>
    <div class="transcript-view" id="transcript-${job.job_id}"></div>
  `;

  card.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => handleJobAction(btn.dataset.action, job));
  });

  return card;
}

async function handleJobAction(action, job) {
  if (action === "delete") {
    if (!(await showConfirm("Hapus video dan hasil transkrip ini?"))) return;
    const res = await fetch(`/transcript/api/job/${job.job_id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal menghapus.");
      return;
    }
    cardElements.delete(job.job_id);
    renderJobList();
  } else if (action === "view") {
    await showTranscript(job.job_id);
  } else if (action === "cancel") {
    const res = await fetch(`/transcript/api/job/${job.job_id}/cancel`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal membatalkan.");
    }
    renderJobList();
  } else if (action === "retry") {
    const res = await fetch(`/transcript/api/job/${job.job_id}/retry`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal mencoba lagi.");
    }
    renderJobList();
  }
}

async function showTranscript(jobId) {
  const container = document.getElementById(`transcript-${jobId}`);
  if (!container) return;
  if (container.dataset.loaded === "1") {
    container.classList.toggle("open");
    return;
  }
  const res = await fetch(`/transcript/api/result/${jobId}`);
  if (!res.ok) return;
  const data = await res.json();
  container.innerHTML = data.segments
    .map(
      (seg) => `
    <div class="segment">
      <span class="segment-time">${formatTime(seg.start)} - ${formatTime(seg.end)}</span>
      <span class="segment-text">${escapeHtml(seg.text)}</span>
    </div>`
    )
    .join("");
  container.dataset.loaded = "1";
  container.classList.add("open");
}

function queueMessage(data) {
  if (data.status === "queued") {
    if (data.error) return data.error; // auto-retry note from the server
    const prefix = data.queue_position > 0 ? `Posisi antrian: ${data.queue_position}` : "Menunggu giliran...";
    return data.currently_processing ? `${prefix} — sedang memproses "${data.currently_processing}"` : prefix;
  }
  if (data.status === "downloading_audio") {
    return "Sedang mengunduh audio dari link...";
  }
  if (data.status === "extracting_audio" || data.status === "transcribing") {
    return "Sedang memproses video ini...";
  }
  return "";
}

async function refreshSubText(jobId) {
  try {
    const res = await fetch(`/transcript/api/status/${jobId}`);
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
    // Terminal and unchanged since last render — reuse untouched so any
    // expanded transcript view (or other in-card state) survives.
    return existing;
  }
  const card = renderJobCard(job);
  card.dataset.lastStatus = job.status;
  cardElements.set(job.job_id, card);
  return card;
}

async function renderJobList() {
  try {
    const res = await fetch("/transcript/api/jobs");
    if (!res.ok) return;
    const jobs = await res.json();

    listEl.innerHTML = "";
    uploadPlaceholders.forEach((p, localId) => listEl.appendChild(renderPlaceholderCard(localId, p)));

    if (jobs.length === 0 && uploadPlaceholders.size === 0) {
      listEl.innerHTML = '<p class="empty">Belum ada video yang diupload.</p>';
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

function updateDropzoneSelection() {
  const file = fileInput.files[0];
  if (!file) {
    dropzoneTitle.textContent = DROPZONE_DEFAULT_TITLE;
    dropzoneSub.textContent = DROPZONE_DEFAULT_SUB;
    return;
  }
  dropzoneTitle.textContent = file.name;
  dropzoneSub.textContent = isAllowedFile(file.name)
    ? "klik Upload & Transkrip untuk mulai"
    : "format tidak didukung — gunakan MP4, MOV, atau MKV";
}

fileInput.addEventListener("change", updateDropzoneSelection);

["dragover", "dragenter"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("slot--drag");
  })
);

["dragleave", "dragend"].forEach((evt) =>
  dropzone.addEventListener(evt, () => dropzone.classList.remove("slot--drag"))
);

dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("slot--drag");
  const files = e.dataTransfer.files;
  if (files && files.length) {
    fileInput.files = files;
    updateDropzoneSelection();
  }
});

function uploadFile(localId, file) {
  const xhr = new XMLHttpRequest();
  const entry = uploadPlaceholders.get(localId);
  entry.xhr = xhr;

  xhr.upload.addEventListener("progress", (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    const cur = uploadPlaceholders.get(localId);
    if (cur) {
      cur.progress = pct;
      renderJobList();
    }
  });

  xhr.onload = () => {
    uploadPlaceholders.delete(localId);
    let data = {};
    try {
      data = JSON.parse(xhr.responseText);
    } catch (e) {
      // ignore malformed response body
    }
    if (!(xhr.status >= 200 && xhr.status < 300 && data.job_id)) {
      uploadError.textContent = data.error || "Upload gagal.";
    }
    renderJobList();
  };

  xhr.onerror = () => {
    uploadPlaceholders.delete(localId);
    uploadError.textContent = "Upload gagal (koneksi terputus).";
    renderJobList();
  };

  xhr.onabort = () => {
    uploadPlaceholders.delete(localId);
    renderJobList();
  };

  xhr.open("POST", "/transcript/api/upload");
  const formData = new FormData();
  formData.append("video", file);
  xhr.send(formData);
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  uploadError.textContent = "";
  const file = fileInput.files[0];
  if (!file) return;
  if (!isAllowedFile(file.name)) {
    uploadError.textContent = "Format tidak didukung. Gunakan MP4, MOV, atau MKV.";
    return;
  }
  const localId = `u${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  uploadPlaceholders.set(localId, { filename: file.name, progress: 0, xhr: null });
  renderJobList();
  uploadFile(localId, file);
  form.reset();
  updateDropzoneSelection();
});

// --- Link-video source: check via the Video Downloader's metadata
// endpoint (same yt-dlp lookup, no need to duplicate it here), then start
// a transcript job from the confirmed URL. ---
urlForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  urlError.textContent = "";
  const url = urlInput.value.trim();
  if (!url) return;

  urlCheckBtn.disabled = true;
  urlCheckBtn.textContent = "Mengecek...";
  urlPreviewCard.classList.add("hidden");
  try {
    const res = await fetch("/video-downloader/api/metadata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      currentUrlMeta = { ...data, url };
      renderUrlPreview();
    } else {
      urlError.textContent = data.error || "Gagal mengambil info video.";
    }
  } catch (err) {
    urlError.textContent = "Gagal menghubungi server.";
  } finally {
    urlCheckBtn.disabled = false;
    urlCheckBtn.textContent = "Cek Video";
  }
});

function renderUrlPreview() {
  if (!currentUrlMeta) return;
  if (currentUrlMeta.thumbnail) {
    urlPreviewThumb.src = currentUrlMeta.thumbnail;
    urlPreviewThumb.classList.remove("hidden");
  } else {
    urlPreviewThumb.classList.add("hidden");
    urlPreviewThumb.removeAttribute("src");
  }
  urlPreviewTitle.textContent = currentUrlMeta.title;
  urlPreviewPlatform.textContent = currentUrlMeta.platform;
  urlPreviewDuration.textContent = currentUrlMeta.duration ? formatTime(currentUrlMeta.duration) : "-";
  urlPreviewCard.classList.remove("hidden");
}

urlTranscribeBtn.addEventListener("click", async () => {
  if (!currentUrlMeta) return;
  urlTranscribeBtn.disabled = true;
  urlTranscribeBtn.textContent = "Memulai...";
  urlError.textContent = "";
  try {
    const res = await fetch("/transcript/api/from-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrlMeta.url, title: currentUrlMeta.title }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.job_id) {
      urlPreviewCard.classList.add("hidden");
      urlForm.reset();
      currentUrlMeta = null;
      renderJobList();
    } else {
      urlError.textContent = data.error || "Gagal memulai transkripsi.";
    }
  } catch (err) {
    urlError.textContent = "Gagal menghubungi server.";
  } finally {
    urlTranscribeBtn.disabled = false;
    urlTranscribeBtn.textContent = "Transkrip Video Ini";
  }
});

// --- Cross-tool queue banner ---
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

// --- Warn before leaving mid-upload: navigating away (closing the tab,
// clicking a nav link, reloading) aborts any in-flight upload outright —
// the bytes already sent are discarded and no job ever gets created. ---
window.addEventListener("beforeunload", (e) => {
  if (uploadPlaceholders.size > 0) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// init
renderJobList();
setInterval(renderJobList, POLL_INTERVAL);
refreshGlobalQueue();
setInterval(refreshGlobalQueue, QUEUE_REFRESH_INTERVAL);
