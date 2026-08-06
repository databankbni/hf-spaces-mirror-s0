const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const processBtn = document.getElementById("process-btn");

const stageUpload = document.getElementById("stage-upload");
const stageProcessing = document.getElementById("stage-processing");
const stageDone = document.getElementById("stage-done");
const stageError = document.getElementById("stage-error");

const statusText = document.getElementById("status-text");
const statusProgress = document.getElementById("status-progress");
const meterFill = document.getElementById("meter-fill");
const queueBanner = document.getElementById("queue-banner");
const processingCloseBtn = document.getElementById("processing-close-btn");

const uploadingBanner = document.getElementById("uploading-banner");
const uploadingText = document.getElementById("uploading-text");
const uploadingPct = document.getElementById("uploading-pct");
const uploadingCancelBtn = document.getElementById("uploading-cancel-btn");
const cancelBtn = document.getElementById("cancel-btn");

const jobListEl = document.getElementById("job-list");

const MY_JOB_KEY = "silenceCutterMyJob";
const UPLOADING_KEY = "silenceCutterUploading";

let selectedFile = null;
let currentJobId = null;
let currentFilename = null;
let watchingProcessing = true; // whether poll updates should force the processing stage into view
let uploadXhr = null; // the in-flight upload request, so it can be aborted (cancel)

// Build the little animated bars once
const tapeBars = document.getElementById("tape-bars");
for (let i = 0; i < 28; i++) {
  const bar = document.createElement("span");
  const h = 20 + Math.random() * 80;
  bar.style.height = h + "%";
  bar.style.animationDelay = (Math.random() * 1).toFixed(2) + "s";
  tapeBars.appendChild(bar);
}

function showStage(stage) {
  [stageUpload, stageProcessing, stageDone, stageError].forEach(s => s.classList.add("stage--hidden"));
  stage.classList.remove("stage--hidden");
  processingCloseBtn.classList.toggle("stage--hidden", stage !== stageProcessing);
}

function fmtTime(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : str;
  return div.innerHTML;
}

// --- Storage wrapper: falls back to an in-memory store when localStorage is
// blocked (e.g. this page loaded inside a third-party iframe). ---
const memoryStore = {};
function storageGet(key) {
  try {
    return localStorage.getItem(key);
  } catch (err) {
    return Object.prototype.hasOwnProperty.call(memoryStore, key) ? memoryStore[key] : null;
  }
}
function storageSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (err) {
    memoryStore[key] = value;
  }
}
function storageRemove(key) {
  try {
    localStorage.removeItem(key);
  } catch (err) {
    delete memoryStore[key];
  }
}

// --- "Which job did *this browser* personally start" — purely so a reload
// can snap back into *your* full-screen view. It no longer gates what the
// shared job list below shows; that's entirely server-driven so anyone
// visiting sees every job, from any uploader. ---
function getMyJob() {
  try {
    const raw = storageGet(MY_JOB_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return null;
  }
}
function setMyJob(jobId, filename) {
  storageSet(MY_JOB_KEY, JSON.stringify({ jobId, filename }));
}
function clearMyJob() {
  storageRemove(MY_JOB_KEY);
}

// --- Uploading-phase tracking: the file is still being transferred, so
// there's no job_id yet — this is genuinely local-only knowledge. ---
function getUploading() {
  try {
    const raw = storageGet(UPLOADING_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return null;
  }
}
function setUploading(filename, pct) {
  storageSet(UPLOADING_KEY, JSON.stringify({ filename, pct }));
}
function setUploadingPct(pct) {
  const cur = getUploading();
  if (cur) setUploading(cur.filename, pct);
}
function clearUploading() {
  storageRemove(UPLOADING_KEY);
}

function renderUploadingBanner() {
  const uploading = getUploading();
  if (uploading) {
    uploadingBanner.classList.remove("stage--hidden");
    uploadingText.textContent = `Mengunggah "${uploading.filename}"…`;
    uploadingPct.textContent = `${uploading.pct || 0}%`;
  } else {
    uploadingBanner.classList.add("stage--hidden");
  }
}

function updateUploadLock() {
  // Uploads to this tool always succeed and queue — the only thing that
  // actually blocks the form is *this browser* still transferring bytes.
  const locked = !!getUploading();
  fileInput.disabled = locked;
  dropZone.classList.toggle("slot--disabled", locked);
  processBtn.disabled = locked ? true : !selectedFile;
}

function showUploadPhaseUI(pct) {
  statusText.textContent = "Mengunggah video…";
  statusProgress.textContent = `${pct}%`;
  meterFill.style.width = `${pct}%`;
}

function goHome() {
  showStage(stageUpload);
  renderUploadingBanner();
  updateUploadLock();
  renderJobList();
  refreshQueueBanner();
}

function resetDropZoneVisual() {
  selectedFile = null;
  fileInput.value = "";
  dropZone.querySelector(".slot__text strong").textContent = "Taruh video di sini";
  dropZone.querySelector(".slot__text span").textContent = DEFAULT_SLOT_HINT;
}

// --- Mode switch: Normal vs Advanced settings are mutually exclusive — only
// one panel's values are ever actually submitted (see processBtn handler).
// Choice persists across visits like the other tool preferences here. ---
const SETTINGS_MODE_KEY = "silenceCutterSettingsMode";
const modeSwitch = document.getElementById("mode-switch");
const normalPanel = document.getElementById("normal-panel");
const advancedPanel = document.getElementById("advanced-panel");

function setSettingsMode(mode) {
  normalPanel.classList.toggle("stage--hidden", mode !== "normal");
  advancedPanel.classList.toggle("stage--hidden", mode !== "advanced");
  modeSwitch.querySelectorAll(".mode-switch__btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  storageSet(SETTINGS_MODE_KEY, mode);
}

modeSwitch.addEventListener("click", (e) => {
  const btn = e.target.closest(".mode-switch__btn");
  if (btn) setSettingsMode(btn.dataset.mode);
});

setSettingsMode(storageGet(SETTINGS_MODE_KEY) === "advanced" ? "advanced" : "normal");

// --- Normal setting: the original simple 3-slider setup ---
const silenceDb = document.getElementById("silence_db");
const minSilence = document.getElementById("min_silence");
const padding = document.getElementById("padding");

silenceDb.addEventListener("input", () => {
  document.getElementById("silence_db_val").textContent = `${silenceDb.value} dB`;
});
minSilence.addEventListener("input", () => {
  document.getElementById("min_silence_val").textContent = `${minSilence.value}s`;
});
padding.addEventListener("input", () => {
  document.getElementById("padding_val").textContent = `${padding.value}s`;
});

// --- Advanced setting: AutoCut-style granular controls ---
const advSilenceDb = document.getElementById("adv_silence_db");
const advRemoveSilenceMs = document.getElementById("adv_remove_silence_ms");
const advKeepTalkMs = document.getElementById("adv_keep_talk_ms");
const advMarginBeforeMs = document.getElementById("adv_margin_before_ms");
const advMarginAfterMs = document.getElementById("adv_margin_after_ms");
const advMergeGapToggle = document.getElementById("adv_merge_gap_toggle");
const MERGE_GAP_MS_ON = 120; // fixed magnitude applied whenever the toggle is on

advSilenceDb.addEventListener("input", () => {
  document.getElementById("adv_silence_db_val").textContent = `${advSilenceDb.value}dB`;
  clearActivePreset();
});
[advRemoveSilenceMs, advKeepTalkMs, advMarginBeforeMs, advMarginAfterMs].forEach(el => {
  el.addEventListener("input", clearActivePreset);
});
advMergeGapToggle.addEventListener("change", clearActivePreset);

// --- Presets: built-in "feel" combos (AutoCut-style) + user-saved custom ones
// — these only ever touch the Advanced panel's own fields. ---
const BUILTIN_PRESETS = [
  { id: "calm", label: "Calm", silenceDb: -35, removeMs: 500, keepMs: 300, beforeMs: 300, afterMs: 150, mergeOn: false },
  { id: "measured", label: "Measured", silenceDb: -30, removeMs: 350, keepMs: 250, beforeMs: 220, afterMs: 100, mergeOn: false },
  { id: "paced", label: "Paced", silenceDb: -28, removeMs: 220, keepMs: 180, beforeMs: 180, afterMs: 60, mergeOn: true },
  { id: "energetic", label: "Energetic", silenceDb: -26, removeMs: 140, keepMs: 120, beforeMs: 120, afterMs: 30, mergeOn: true },
  { id: "jumpy", label: "Jumpy", silenceDb: -24, removeMs: 80, keepMs: 80, beforeMs: 60, afterMs: 10, mergeOn: true },
];
const CUSTOM_PRESETS_KEY = "silenceCutterCustomPresets";

function getCustomPresets() {
  try {
    const raw = storageGet(CUSTOM_PRESETS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (err) {
    return [];
  }
}
function setCustomPresets(list) {
  storageSet(CUSTOM_PRESETS_KEY, JSON.stringify(list));
}

let activePresetId = "measured";

function applyPreset(preset) {
  advSilenceDb.value = preset.silenceDb;
  document.getElementById("adv_silence_db_val").textContent = `${preset.silenceDb}dB`;
  advRemoveSilenceMs.value = preset.removeMs;
  advKeepTalkMs.value = preset.keepMs;
  advMarginBeforeMs.value = preset.beforeMs;
  advMarginAfterMs.value = preset.afterMs;
  advMergeGapToggle.checked = !!preset.mergeOn;
  activePresetId = preset.id;
  renderPresetRow();
}

function clearActivePreset() {
  if (activePresetId !== null) {
    activePresetId = null;
    renderPresetRow();
  }
}

function renderPresetRow() {
  const presetRow = document.getElementById("preset-row");
  presetRow.innerHTML = "";

  [...BUILTIN_PRESETS, ...getCustomPresets()].forEach(preset => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `preset-chip${preset.custom ? " preset-chip--custom" : ""}${preset.id === activePresetId ? " active" : ""}`;
    chip.textContent = preset.label;
    chip.addEventListener("click", () => applyPreset(preset));

    if (preset.custom) {
      const removeBtn = document.createElement("span");
      removeBtn.className = "preset-chip__remove";
      removeBtn.textContent = "×";
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const remaining = getCustomPresets().filter(p => p.id !== preset.id);
        setCustomPresets(remaining);
        if (activePresetId === preset.id) activePresetId = null;
        renderPresetRow();
      });
      chip.appendChild(removeBtn);
    }
    presetRow.appendChild(chip);
  });

  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "preset-chip preset-chip--add";
  addBtn.textContent = "+";
  addBtn.title = "Simpan setting saat ini sebagai preset baru";
  addBtn.addEventListener("click", async () => {
    const name = await showPrompt("Nama preset baru:", "");
    if (!name) return;
    const custom = getCustomPresets();
    const preset = {
      id: `custom-${Date.now()}`,
      label: name.slice(0, 20),
      custom: true,
      silenceDb: Number(advSilenceDb.value),
      removeMs: Number(advRemoveSilenceMs.value),
      keepMs: Number(advKeepTalkMs.value),
      beforeMs: Number(advMarginBeforeMs.value),
      afterMs: Number(advMarginAfterMs.value),
      mergeOn: advMergeGapToggle.checked,
    };
    custom.push(preset);
    setCustomPresets(custom);
    activePresetId = preset.id;
    renderPresetRow();
  });
  presetRow.appendChild(addBtn);
}

applyPreset(BUILTIN_PRESETS[1]); // "Measured" as the default starting point

// --- "Calculate by AI": estimate a sensible noise-floor threshold straight
// from the selected file's audio track (client-side, no upload needed yet).
// Skipped for very large files — decoding the whole track in-browser isn't
// worth the memory/time cost past a few hundred MB. ---
const AI_CALC_MAX_BYTES = 300 * 1024 * 1024;

async function estimateNoiseFloorDb(file) {
  const arrayBuffer = await file.arrayBuffer();
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  let audioBuffer;
  try {
    audioBuffer = await ctx.decodeAudioData(arrayBuffer);
  } finally {
    ctx.close();
  }

  const channel = audioBuffer.getChannelData(0);
  const windowSize = Math.max(1, Math.floor(audioBuffer.sampleRate * 0.1)); // ~100ms windows
  const rmsValues = [];
  for (let i = 0; i + windowSize <= channel.length; i += windowSize) {
    let sumSquares = 0;
    for (let j = i; j < i + windowSize; j++) sumSquares += channel[j] * channel[j];
    const rms = Math.sqrt(sumSquares / windowSize);
    if (rms > 0) rmsValues.push(rms);
  }
  if (rmsValues.length === 0) throw new Error("no decodable audio samples");

  rmsValues.sort((a, b) => a - b);
  // 20th percentile ~= the ambient noise floor without being fooled by
  // completely dead-silent stretches that would drag the estimate too low.
  const floorRms = rmsValues[Math.floor(rmsValues.length * 0.2)];
  const floorDb = 20 * Math.log10(floorRms);
  return floorDb + 6; // small margin above the floor so true silence still triggers cuts
}

const aiCalcBtn = document.getElementById("ai-calc-btn");
aiCalcBtn.addEventListener("click", async () => {
  if (!selectedFile) {
    showAlert("Pilih video dulu sebelum menghitung threshold otomatis.");
    return;
  }
  if (selectedFile.size > AI_CALC_MAX_BYTES) {
    showAlert("Video terlalu besar untuk dianalisis otomatis di browser (maks 300 MB). Atur manual atau pilih salah satu preset.");
    return;
  }

  const originalText = aiCalcBtn.textContent;
  aiCalcBtn.disabled = true;
  aiCalcBtn.textContent = "Menganalisis audio…";
  try {
    const db = Math.round(Math.min(-10, Math.max(-50, await estimateNoiseFloorDb(selectedFile))));
    advSilenceDb.value = db;
    advSilenceDb.dispatchEvent(new Event("input"));
  } catch (err) {
    showAlert("Gagal menganalisis audio, coba atur threshold manual.");
  } finally {
    aiCalcBtn.disabled = false;
    aiCalcBtn.textContent = originalText;
  }
});

// --- Upload / drag & drop ---
const DEFAULT_SLOT_HINT = dropZone.querySelector(".slot__text span").textContent;

function handleFile(file) {
  if (!file || getUploading()) return;
  selectedFile = file;
  processBtn.disabled = false;
  dropZone.querySelector(".slot__text strong").textContent = file.name;
  dropZone.querySelector(".slot__text span").textContent =
    `${(file.size / (1024 * 1024)).toFixed(1)} MB — klik "Proses Video" untuk lanjut`;
}

fileInput.addEventListener("change", (e) => handleFile(e.target.files[0]));

["dragover", "dragenter"].forEach(evt => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    if (getUploading()) return;
    dropZone.classList.add("slot--drag");
  });
});
["dragleave", "drop"].forEach(evt => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove("slot--drag");
  });
});
dropZone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

// --- Process ---
processBtn.addEventListener("click", () => {
  if (!selectedFile || getUploading()) return;

  const filename = selectedFile.name;
  const form = new FormData();
  form.append("video", selectedFile);

  const usingAdvanced = !advancedPanel.classList.contains("stage--hidden");
  if (usingAdvanced) {
    form.append("silence_db", advSilenceDb.value);
    form.append("remove_silence_ms", advRemoveSilenceMs.value);
    form.append("keep_talk_ms", advKeepTalkMs.value);
    form.append("margin_before_ms", advMarginBeforeMs.value);
    form.append("margin_after_ms", advMarginAfterMs.value);
    form.append("merge_gap_enabled", advMergeGapToggle.checked ? "1" : "0");
    form.append("merge_gap_ms", MERGE_GAP_MS_ON);
  } else {
    // Normal setting: the original simple behavior — a single symmetric
    // margin, a fixed keep-talk floor, and no forced cut merging (the
    // backend's own 50ms floor still guards against zero-length gaps).
    const marginMs = Math.round(padding.value * 1000);
    form.append("silence_db", silenceDb.value);
    form.append("remove_silence_ms", Math.round(minSilence.value * 1000));
    form.append("keep_talk_ms", "300");
    form.append("margin_before_ms", marginMs);
    form.append("margin_after_ms", marginMs);
    form.append("merge_gap_enabled", "0");
  }

  watchingProcessing = true;
  currentFilename = filename;
  setUploading(filename, 0);
  renderUploadingBanner();
  updateUploadLock();
  showStage(stageProcessing);
  showUploadPhaseUI(0);

  const xhr = new XMLHttpRequest();
  uploadXhr = xhr;
  xhr.open("POST", "/silence-cutter/api/upload");

  xhr.upload.addEventListener("progress", (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    setUploadingPct(pct);
    if (watchingProcessing) showUploadPhaseUI(pct);
    renderUploadingBanner();
  });

  xhr.addEventListener("load", () => {
    uploadXhr = null;
    if (xhr.status < 200 || xhr.status >= 300) {
      clearUploading();
      let message = "Upload gagal";
      try {
        message = JSON.parse(xhr.responseText).error || message;
      } catch (err) { /* keep default message */ }
      if (watchingProcessing) {
        showError(message);
      } else {
        renderUploadingBanner();
        updateUploadLock();
      }
      return;
    }

    const data = JSON.parse(xhr.responseText);
    clearUploading();
    currentJobId = data.job_id;
    setMyJob(currentJobId, currentFilename);
    renderUploadingBanner();
    updateUploadLock();
    renderJobList();
    pollStatus();
  });

  xhr.addEventListener("error", () => {
    uploadXhr = null;
    clearUploading();
    if (watchingProcessing) {
      showError("Koneksi ke server terputus saat mengunggah.");
    } else {
      renderUploadingBanner();
      updateUploadLock();
    }
  });

  xhr.addEventListener("abort", () => {
    uploadXhr = null;
    clearUploading();
    watchingProcessing = false;
    resetDropZoneVisual();
    goHome();
  });

  xhr.send(form);
});

const STAGE_LABEL = {
  queued: "Menunggu di antrian…",
  detecting: "Mendeteksi bagian sunyi…",
  cutting: "Memotong & merender video…",
  done: "Selesai!",
};

async function pollStatus() {
  try {
    const res = await fetch(`/silence-cutter/api/status/${currentJobId}`);

    if (res.status === 404) {
      // Job no longer exists server-side (expired / server restarted) — don't get stuck.
      clearMyJobIfMatches();
      if (watchingProcessing) {
        resetToUpload();
      } else {
        updateUploadLock();
      }
      return;
    }

    const data = await res.json();

    if (data.status === "error") {
      clearMyJobIfMatches();
      if (watchingProcessing) {
        showError(data.error || "Terjadi kesalahan saat memproses video.");
      } else {
        updateUploadLock();
      }
      return;
    }

    if (data.status === "cancelled") {
      clearMyJobIfMatches();
      if (watchingProcessing) {
        resetToUpload();
      } else {
        updateUploadLock();
      }
      return;
    }

    let label = STAGE_LABEL[data.status] || "Memproses…";
    if (data.status === "queued" && data.queue_position) {
      label = `Menunggu di antrian… (posisi #${data.queue_position})`;
    }
    statusText.textContent = label;
    statusProgress.textContent = `${data.progress || 0}%`;
    meterFill.style.width = `${data.progress || 0}%`;

    if (watchingProcessing) showStage(stageProcessing);

    if (data.status === "done") {
      clearMyJobIfMatches();
      renderJobList();

      if (watchingProcessing) {
        showDone(data.stats);
      } else {
        updateUploadLock();
      }
      return;
    }

    setTimeout(pollStatus, 1200);
  } catch (err) {
    if (watchingProcessing) {
      showError("Koneksi ke server terputus.");
    } else {
      setTimeout(pollStatus, 1200);
    }
  }
}

function clearMyJobIfMatches() {
  const mine = getMyJob();
  if (mine && mine.jobId === currentJobId) clearMyJob();
}

function showDone(stats) {
  document.getElementById("stat-original").textContent = fmtTime(stats.original_duration);
  document.getElementById("stat-new").textContent = fmtTime(stats.new_duration);
  document.getElementById("stat-removed").textContent = fmtTime(stats.removed_duration);
  const pct = stats.original_duration > 0
    ? Math.round((stats.removed_duration / stats.original_duration) * 100)
    : 0;
  document.getElementById("stat-percent").textContent = `${pct}%`;
  showStage(stageDone);
}

function showError(message) {
  clearMyJobIfMatches();
  document.getElementById("error-message").textContent = message;
  showStage(stageError);
}

document.getElementById("download-btn").addEventListener("click", () => {
  window.location.href = `/silence-cutter/api/download/${currentJobId}`;
});

function resetToUpload() {
  currentJobId = null;
  currentFilename = null;
  watchingProcessing = false;
  resetDropZoneVisual();
  goHome();
}

document.getElementById("reset-btn").addEventListener("click", resetToUpload);
document.getElementById("error-reset-btn").addEventListener("click", resetToUpload);

// --- Close (x): step away from the processing view without stopping the job ---
processingCloseBtn.addEventListener("click", () => {
  watchingProcessing = false;
  resetDropZoneVisual();
  goHome();
});

// --- Open the full-screen tape view for any job (mine or someone else's) ---
function watchJob(jobId, filename) {
  currentJobId = jobId;
  currentFilename = filename;
  watchingProcessing = true;
  showStage(stageProcessing);
  pollStatus();
}

// --- Uploading banner: click reopens the upload-progress view; its own
// cancel button aborts the in-flight XHR. ---
uploadingBanner.addEventListener("click", (e) => {
  if (e.target === uploadingCancelBtn) return;
  const uploading = getUploading();
  if (!uploading) return;
  watchingProcessing = true;
  showStage(stageProcessing);
  showUploadPhaseUI(uploading.pct || 0);
});
uploadingCancelBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  if (uploadXhr) uploadXhr.abort();
});

// --- Cancel button inside the full-screen view: cancels whichever job_id
// is currently being watched, regardless of who started it. ---
cancelBtn.addEventListener("click", async () => {
  if (!currentJobId) return;
  if (!(await showConfirm(`Batalkan proses "${currentFilename}"? File yang sedang diproses akan dihapus.`))) {
    return;
  }
  try {
    const res = await fetch(`/silence-cutter/api/cancel/${currentJobId}`, { method: "POST" });
    if (!res.ok && res.status !== 409) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal membatalkan proses.");
    }
  } catch (err) {
    // best-effort — the poll loop reflects the real server state regardless
  }
});

// --- Cancel a specific job directly from a job-list row ---
async function cancelJobFromList(jobId, filename) {
  if (!(await showConfirm(`Batalkan proses "${filename}"? File yang sedang diproses akan dihapus.`))) return;
  try {
    const res = await fetch(`/silence-cutter/api/cancel/${jobId}`, { method: "POST" });
    if (!res.ok && res.status !== 409) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal membatalkan proses.");
    }
  } catch (err) {
    showAlert("Koneksi ke server terputus, coba lagi.");
  }
  renderJobList();
}

async function deleteJobFromList(jobId, filename) {
  const label = filename || "video ini";
  if (!(await showConfirm(`Hapus "${label}" secara permanen dari server? Tindakan ini tidak bisa dibatalkan.`))) {
    return;
  }
  try {
    const res = await fetch(`/silence-cutter/api/jobs/${jobId}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.error || "Gagal menghapus file di server.");
      return;
    }
  } catch (err) {
    showAlert("Koneksi ke server terputus, coba lagi.");
    return;
  }
  renderJobList();
}

// --- Shared job list: server-driven, visible to every visitor regardless
// of who uploaded what. Polled independently of the full-screen stage. ---
const ACTIVE_STATUSES = new Set(["queued", "detecting", "cutting"]);
const STATUS_LABELS = {
  queued: "ANTRIAN",
  detecting: "MENDETEKSI",
  cutting: "MEMOTONG",
  done: "SELESAI",
  error: "GAGAL",
  cancelled: "DIBATALKAN",
};
const STATUS_DOT = {
  queued: "dot-yellow",
  detecting: "dot-amber",
  cutting: "dot-amber",
  done: "dot-teal",
  error: "dot-red",
  cancelled: "dot-muted",
};
const STATUS_CLASS = {
  queued: "status-queued",
  detecting: "status-active",
  cutting: "status-active",
  done: "status-done",
  error: "status-error",
  cancelled: "status-cancelled",
};

function renderJobCard(job) {
  const status = job.status;
  const isActive = ACTIVE_STATUSES.has(status);
  const isDone = status === "done";
  const isError = status === "error";
  const isCancelled = status === "cancelled";
  const progress = job.progress || 0;
  const filename = job.original_filename || "video.mp4";

  const card = document.createElement("div");
  card.className = `job-card ${STATUS_CLASS[status] || ""}`;

  let statsLine = "";
  if (isDone && job.stats) {
    const pct = job.stats.original_duration > 0
      ? Math.round((job.stats.removed_duration / job.stats.original_duration) * 100)
      : 0;
    statsLine = `<div class="job-sub">${fmtTime(job.stats.new_duration)} • -${pct}%</div>`;
  }

  card.innerHTML = `
    <div class="job-header">
      <span class="status-dot ${STATUS_DOT[status] || "dot-muted"}"></span>
      <span class="job-filename">${escapeHtml(filename)}</span>
      <span class="job-status-text">${STATUS_LABELS[status] || status.toUpperCase()}</span>
    </div>
    ${isActive ? `
      <div class="progress-row">
        <span class="progress-label">progress</span>
        <span class="progress-value">${progress}%</span>
      </div>
      <div class="slider-track">
        <div class="slider-fill" style="width:${progress}%"><span class="slider-thumb"></span></div>
      </div>
    ` : ""}
    ${statsLine}
    <div class="job-actions">
      ${isActive ? `<button class="btn-secondary" data-action="watch">Lihat Progress</button>` : ""}
      ${isActive ? `<button class="btn-warn" data-action="cancel">Batal</button>` : ""}
      ${isDone ? `<button class="btn-secondary" data-action="download">Download</button>` : ""}
      ${(isDone || isError || isCancelled) ? `<button class="btn-danger" data-action="delete">Hapus</button>` : ""}
    </div>
  `;

  card.querySelector('[data-action="watch"]')?.addEventListener("click", () => watchJob(job.job_id, filename));
  card.querySelector('[data-action="cancel"]')?.addEventListener("click", () => cancelJobFromList(job.job_id, filename));
  card.querySelector('[data-action="download"]')?.addEventListener("click", () => {
    window.location.href = `/silence-cutter/api/download/${job.job_id}`;
  });
  card.querySelector('[data-action="delete"]')?.addEventListener("click", () => deleteJobFromList(job.job_id, filename));

  return card;
}

async function renderJobList() {
  try {
    const res = await fetch("/silence-cutter/api/jobs");
    if (!res.ok) return;
    const data = await res.json();
    const jobs = (data.jobs || []).slice().sort((a, b) => {
      // Active jobs first, then everything else in whatever order the server gave us.
      const aActive = ACTIVE_STATUSES.has(a.status) ? 0 : 1;
      const bActive = ACTIVE_STATUSES.has(b.status) ? 0 : 1;
      return aActive - bActive;
    });

    jobListEl.innerHTML = "";
    if (jobs.length === 0) {
      jobListEl.innerHTML = '<p class="empty">Belum ada video yang diproses.</p>';
      return;
    }
    jobs.forEach(job => jobListEl.appendChild(renderJobCard(job)));
  } catch (err) {
    // silent — best-effort, next tick will retry
  }
}

async function jobListLoop() {
  await renderJobList();
  setTimeout(jobListLoop, 3000);
}

// --- "Someone else is currently processing" banner — cross-tool aware ---
async function refreshQueueBanner() {
  try {
    const res = await fetch("/api/queue-overview");
    const data = await res.json();
    const onUploadScreen = !stageUpload.classList.contains("stage--hidden");
    const totalWaiting = (data.pending || []).length;
    if (data.current && onUploadScreen) {
      const extra = totalWaiting > 0 ? ` — ${totalWaiting} video lagi menunggu` : "";
      queueBanner.classList.remove("stage--hidden");
      queueBanner.innerHTML = `⚠ "${escapeHtml(data.current.filename)}" (${escapeHtml(data.current.tool_label)}) sedang diproses${extra}. <a href="/queue" style="color:inherit;text-decoration:underline;">Lihat Antrian</a>`;
    } else {
      queueBanner.classList.add("stage--hidden");
    }
  } catch (err) {
    // silent — queue banner is a nice-to-have, not critical
  }
}
async function queueLoop() {
  await refreshQueueBanner();
  setTimeout(queueLoop, 5000);
}

// --- Warn before leaving mid-upload: navigating away (closing the tab,
// clicking a nav link, reloading) aborts the in-flight upload outright —
// the bytes already sent are discarded and no job ever gets created. ---
window.addEventListener("beforeunload", (e) => {
  if (uploadXhr) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// --- Init: resume watching a job *this browser* started (if any), restore
// upload-in-progress banner, start the shared job list + queue polling ---
(function init() {
  // Any "uploading" marker left over from a previous page load is necessarily
  // stale — the real XHR object died with that page, so there's nothing left
  // to resume watching. Clear it rather than leaving a banner stuck forever.
  if (getUploading()) clearUploading();

  updateUploadLock();
  renderUploadingBanner();
  jobListLoop();
  queueLoop();

  const mine = getMyJob();
  if (mine) {
    currentJobId = mine.jobId;
    currentFilename = mine.filename;
    watchingProcessing = true;
    pollStatus();
  }
})();
