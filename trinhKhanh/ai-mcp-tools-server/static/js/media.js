/* Media Sync SD Card: upload / list / delete */

let mediaItems = [];

function setMediaStatus(text, isError = false) {
  const el = document.getElementById('mediaStatus');
  el.textContent = text || '';
  el.classList.toggle('error', Boolean(isError));
}

async function uploadMedia() {
  const fileEl = document.getElementById('mediaFile');
  const file = fileEl.files?.[0];
  if (!file) { alert('Choose a media file first'); return; }

  const btn = document.getElementById('btnUploadMedia');
  btn.disabled = true;
  btn.textContent = 'Uploading...';
  setMediaStatus('Uploading media to S3/R2...');

  const form = new FormData();
  form.append('file', file);
  const title = document.getElementById('mediaTitle').value.trim();
  if (title) form.append('title', title);

  try {
    const res = await fetch('/api/admin/media/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || data.success === false) throw new Error(data.detail || data.error || 'Upload failed');
    setMediaStatus(`Uploaded: ${data.media.stored_key}\nsha256: ${data.media.sha256}`);
    fileEl.value = '';
    await loadMedia();
  } catch (e) {
    setMediaStatus(`Upload failed: ${e.message}`, true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Upload to S3/R2';
  }
}

async function loadMedia() {
  const list = document.getElementById('mediaList');
  list.innerHTML = '<div class="loading-tools">Loading media...</div>';
  try {
    const { media } = await fetch('/api/admin/media').then(r => r.json());
    mediaItems = media || [];
    if (!mediaItems.length) {
      list.innerHTML = '<div class="loading-tools">No media uploaded yet</div>';
      return;
    }
    list.innerHTML = mediaItems.map(item => `
      <div class="media-row">
        <div>
          <div class="media-name">${escapeHtml(item.title || item.original_name)}</div>
          <div class="media-meta">${escapeHtml(item.type)} | ${escapeHtml(item.status)} | ${formatBytes(item.size)}</div>
          <div class="media-meta">${escapeHtml(item.dest_filename || '')}</div>
          <div class="media-meta">sha256: ${escapeHtml(item.sha256)}</div>
        </div>
        <button class="btn-media secondary" onclick="deleteMedia('${item.media_id}')">Delete</button>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = '<div class="loading-tools" style="color:#ff8888">Cannot load media</div>';
  }
}

async function deleteMedia(mediaId) {
  if (!confirm('Delete this media from R2?')) return;
  setMediaStatus('Deleting media...');
  try {
    const res = await fetch(`/api/admin/media/${mediaId}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok || data.success === false) throw new Error(data.detail || data.error || 'Delete failed');
    setMediaStatus('Media deleted');
    await loadMedia();
  } catch (e) {
    setMediaStatus(`Delete failed: ${e.message}`, true);
  }
}
