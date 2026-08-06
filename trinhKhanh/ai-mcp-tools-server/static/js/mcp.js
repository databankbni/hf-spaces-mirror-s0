/* Kết nối MCP outbound: connect / disconnect / refresh / devices */

let lastUrl = '';

/* ---- Connect (persistent outbound) ---- */
async function connectMCP() {
  const url = document.getElementById('wsUrl').value.trim();
  if (!url) { alert('Vui lòng nhập Websocket URL'); return; }
  lastUrl = url;

  const btn = document.getElementById('btnConnect');
  btn.disabled = true;
  btn.textContent = 'Đang kết nối...';

  document.getElementById('overlay').classList.add('show');
  setStatus('checking', 'Đang kết nối...');
  document.getElementById('tagsWrap').innerHTML =
    '<div class="modal-loading"><div class="spinner" style="display:block;margin:0 auto 8px"></div>Đang thiết lập kết nối...</div>';

  try {
    const res = await fetch('/api/mcp/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_name: document.getElementById('deviceName').value.trim() || 'ai-robot-server',
        websocket_url: url
      })
    });
    const data = await res.json();
    applyStatus(data);
    loadDevices();
  } catch (e) {
    setStatus('offline', 'Lỗi kết nối');
    document.getElementById('tagsWrap').innerHTML =
      '<div style="color:#ff6666;font-size:13px">Không thể gọi server</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = 'KẾT NỐI MCP NGAY';
  }
}

function applyStatus(data) {
  const s = data.status;
  if (s === 'connected') {
    setStatus('online', 'Đã kết nối ✓');
  } else if (s === 'reconnecting') {
    setStatus('checking', 'Đang kết nối lại...');
  } else if (s === 'connecting') {
    setStatus('checking', 'Đang kết nối...');
  } else {
    setStatus('offline', data.error ? `Lỗi: ${data.error}` : 'Offline');
  }
  renderTags(data.registered_tools || []);
}

function renderTags(tools) {
  const wrap = document.getElementById('tagsWrap');
  if (!tools?.length) {
    wrap.innerHTML = '<div style="color:#777;font-size:13px">Chưa có tools nào được đăng ký</div>';
    return;
  }
  wrap.innerHTML = tools.map(name =>
    `<div class="tag">${TOOL_ICONS[name] || '🔧'} ${TOOL_LABELS[name] || name}</div>`
  ).join('');
}

/* ---- Disconnect ---- */
async function disconnectMCP() {
  if (!lastUrl) return;
  try {
    await fetch('/api/mcp/disconnect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ websocket_url: lastUrl })
    });
  } catch {}
  setStatus('offline', 'Đã ngắt kết nối');
  document.getElementById('tagsWrap').innerHTML =
    '<div style="color:#777;font-size:13px">Đã ngắt kết nối</div>';
  lastUrl = '';
  loadDevices();
}

/* ---- Refresh ---- */
async function refresh() {
  if (!lastUrl) return;
  try {
    const { connections, registered_tools } = await fetch('/api/mcp/status').then(r => r.json());
    const conn = connections.find(c => c.url === lastUrl);
    if (conn) {
      applyStatus({ ...conn, registered_tools });
    } else {
      setStatus('offline', 'Không tìm thấy kết nối');
    }
  } catch {}
}

function setStatus(state, text) {
  const dot = document.getElementById('statusDot');
  dot.className = 'dot' + (state === 'online' ? '' : state === 'offline' ? ' offline' : ' checking');
  document.getElementById('statusText').textContent = text;
}

async function deleteDevice() {
  const url = document.getElementById('deleteUrl').value.trim();
  if (!url) { alert('Vui lòng nhập Websocket URL cần xoá'); return; }
  try {
    const res = await fetch('/api/mcp/disconnect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ websocket_url: url })
    });
    const data = await res.json();
    alert(data.success ? '✅ Đã ngắt kết nối thành công' : `❌ ${data.error}`);
    loadDevices();
  } catch { alert('❌ Không thể gọi server'); }
}

/* ---- Danh sách thiết bị đã kết nối ---- */
async function loadDevices() {
  const list = document.getElementById('devicesList');
  try {
    const { devices } = await fetch('/api/mcp/subscriptions').then(r => r.json());
    if (!devices?.length) {
      list.innerHTML = '<div class="devices-empty">Chưa có thiết bị nào đăng ký</div>';
      return;
    }
    list.innerHTML = devices.map(d => {
      const dot = d.status === 'connected' ? 'online'
                : (d.status === 'connecting' || d.status === 'reconnecting') ? 'checking' : '';
      const date = d.created_at
        ? new Date(d.created_at).toLocaleString('vi-VN', {
            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
        : '';
      return `<div class="device-item" title="${d.wss_masked}">
        <div class="device-dot ${dot}"></div>
        <div class="device-info">
          <div class="device-name">${escapeHtml(d.device_name)}</div>
          <div class="device-date">Kết nối: ${date}</div>
        </div>
      </div>`;
    }).join('');
  } catch {
    list.innerHTML = '<div class="devices-empty">Không tải được danh sách</div>';
  }
}

function closeModal() { document.getElementById('overlay').classList.remove('show'); }
function overlayClick(e) { if (e.target === document.getElementById('overlay')) closeModal(); }
