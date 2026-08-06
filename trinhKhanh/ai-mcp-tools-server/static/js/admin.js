/* Trang /adminctrl: danh sách thiết bị → bấm vào xem tools + quyền nội dung.
   Nguồn: GET /api/admin/devices, GET /api/admin/device?endpoint_key=...
   Script classic (không module) như phần còn lại của frontend — hàm ở global scope. */

let adminSelected = null;

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

function fmtVnd(n) {
  return Number(n || 0).toLocaleString('vi-VN') + 'đ';
}

function statusDot(status) {
  if (status === 'connected') return 'online';
  if (status === 'connecting' || status === 'reconnecting') return 'checking';
  return '';
}

function statusBadge(status) {
  if (status === 'connected') return '<span class="badge ok">● đang kết nối</span>';
  if (status === 'connecting' || status === 'reconnecting')
    return `<span class="badge warn">● ${escapeHtml(status)}</span>`;
  return '<span class="badge off">● mất kết nối</span>';
}

/* ── Danh sách thiết bị ─────────────────────────────────────── */
async function loadAdminDevices() {
  const box = document.getElementById('adminDevices');
  const meta = document.getElementById('adminMeta');
  box.innerHTML = '<div class="admin-empty">Đang tải danh sách...</div>';
  try {
    const res = await fetch('/api/admin/devices');
    if (res.status === 401 || res.status === 403) {
      box.innerHTML = '<div class="admin-empty error">Cần đăng nhập bằng tài khoản admin.</div>';
      meta.textContent = 'Chưa có quyền admin';
      setTimeout(() => { window.location.href = '/login?next=/adminctrl'; }, 1200);
      return;
    }
    const data = await res.json();
    const devices = data.devices || [];
    const online = devices.filter(d => d.status === 'connected').length;
    meta.textContent =
      `${devices.length} thiết bị đã đăng ký • ${online} đang kết nối • ${data.registered_tools} tools trên server`;

    if (!devices.length) {
      box.innerHTML = '<div class="admin-empty">Chưa có thiết bị nào đăng ký</div>';
      return;
    }

    box.innerHTML = devices.map(d => `
      <div class="dev-card" data-key="${escapeHtml(d.endpoint_key)}"
           onclick="selectDevice(this.dataset.key)">
        <div class="dev-dot ${statusDot(d.status)}"></div>
        <div class="dev-main">
          <div class="dev-name">${escapeHtml(d.device_name)}</div>
          <div class="dev-key">${escapeHtml(d.endpoint_key)}</div>
          <div class="dev-badges">
            ${statusBadge(d.status)}
            ${d.owner_email
              ? `<span class="badge ok">👤 ${escapeHtml(d.owner_email)}</span>`
              : '<span class="badge warn">chưa có chủ</span>'}
            ${d.store_ready
              ? `<span class="badge ${d.purchased_count ? 'ok' : ''}">🔓 ${d.unlocked_count}/${d.product_count} chủ đề</span>`
              : '<span class="badge warn">chưa có bảng store</span>'}
            ${d.purchased_count ? `<span class="badge ok">đã mua ${d.purchased_count}</span>` : ''}
          </div>
        </div>
      </div>`).join('');

    if (adminSelected && devices.some(d => d.endpoint_key === adminSelected)) {
      selectDevice(adminSelected);
    }
  } catch {
    box.innerHTML = '<div class="admin-empty error">Không tải được danh sách thiết bị</div>';
  }
}

/* ── Chi tiết 1 thiết bị ────────────────────────────────────── */
async function selectDevice(endpointKey) {
  adminSelected = endpointKey;
  document.querySelectorAll('.dev-card').forEach(c =>
    c.classList.toggle('active', c.dataset.key === endpointKey)
  );

  const pane = document.getElementById('adminDetail');
  pane.innerHTML = '<div class="admin-empty">Đang tải chi tiết...</div>';
  try {
    const data = await fetch('/api/admin/device?endpoint_key=' + encodeURIComponent(endpointKey))
      .then(r => r.json());
    if (!data.success) {
      pane.innerHTML = `<div class="admin-empty error">${escapeHtml(data.error || 'Lỗi không rõ')}</div>`;
      return;
    }
    pane.innerHTML = renderDetail(data);
  } catch {
    pane.innerHTML = '<div class="admin-empty error">Không tải được chi tiết thiết bị</div>';
  }
}

function renderDetail(data) {
  const d = data.device;
  const unlocked = data.products.filter(p => p.unlocked);

  return `
    <div class="detail-head">
      <div class="detail-name">${escapeHtml(d.device_name)}</div>
      <div class="detail-rows">
        <div class="detail-label">Chủ thiết bị</div>
        <div class="detail-value">${d.owner_email
          ? escapeHtml(d.owner_email)
          : '<span class="badge warn">chưa gắn tài khoản nào</span>'}</div>
        <div class="detail-label">Endpoint key</div>
        <div class="detail-value">${escapeHtml(d.endpoint_key)}</div>
        <div class="detail-label">Websocket</div>
        <div class="detail-value">${escapeHtml(d.wss_masked)}</div>
        <div class="detail-label">Đăng ký lúc</div>
        <div class="detail-value">${fmtDate(d.created_at)}</div>
        <div class="detail-label">Trạng thái</div>
        <div class="detail-value">${statusBadge(d.status)}${
          d.tools_count ? ` <span class="badge">broker đã lấy ${d.tools_count} tools</span>` : ''
        }${d.error ? ` <span class="badge off">${escapeHtml(d.error)}</span>` : ''}</div>
      </div>
    </div>

    ${data.store_ready ? '' : `<div class="admin-note">
      Chưa có bảng <code>tools.products</code> / <code>tools.entitlements</code> —
      chạy <code>python scripts/run_migration.py scripts/migrate_006_create_store.sql</code>.
      Khi thiếu bảng, tool KHÔNG khoá nội dung nào.
    </div>`}

    <div class="detail-block">
      <div class="detail-block-title">
        🔓 CHỨC NĂNG ĐÃ MỞ KHOÁ
        <span class="count">${unlocked.length}/${data.products.length}</span>
      </div>
      ${data.products.length ? `<div class="perm-grid">${
        data.products.map(renderPerm).join('')
      }</div>` : '<div class="admin-empty">Chưa khai báo sản phẩm nào trong tools.products</div>'}
    </div>

    <div class="detail-block">
      <div class="detail-block-title">
        🔧 TOOLS THIẾT BỊ ĐANG ĐƯỢC CẤP
        <span class="count">${data.tools.length}</span>
      </div>
      <div class="tool-list">${data.tools.map(renderTool).join('')}</div>
    </div>

    <div class="detail-block">
      <div class="detail-block-title">
        💳 LỊCH SỬ THANH TOÁN
        <span class="count">${data.orders.length}</span>
      </div>
      ${data.orders.length ? `<table class="order-table">
        <thead><tr>
          <th>Mã đơn</th><th>Sản phẩm</th><th>Số tiền</th>
          <th>Trạng thái</th><th>MoMo trans</th><th>Tạo lúc</th><th>Thanh toán</th>
        </tr></thead>
        <tbody>${data.orders.map(o => `<tr>
          <td>${escapeHtml(o.order_id)}</td>
          <td>${escapeHtml(o.product_code)}</td>
          <td>${fmtVnd(o.amount)}</td>
          <td>${escapeHtml(o.status)}</td>
          <td>${escapeHtml(o.momo_trans_id || '—')}</td>
          <td>${fmtDate(o.created_at)}</td>
          <td>${fmtDate(o.paid_at)}</td>
        </tr>`).join('')}</tbody>
      </table>` : `<div class="admin-empty">
        Chưa có đơn nào. Cổng thanh toán MoMo chưa đấu nối — quyền hiện chỉ cấp bằng
        <code>INSERT tools.entitlements</code>.
      </div>`}
    </div>
  `;
}

function renderPerm(p) {
  const state = p.is_free ? 'free' : (p.purchased ? 'unlocked' : 'locked');
  const label = p.is_free ? 'MIỄN PHÍ' : (p.purchased ? 'ĐÃ MỞ' : 'CHƯA MUA');
  const scope = p.source === 'account' ? 'theo tài khoản' : 'theo thiết bị';
  const foot = p.purchased
    ? `${scope} • cấp lúc ${fmtDate(p.granted_at)}${p.expires_at ? ` • hết hạn ${fmtDate(p.expires_at)}` : ' • vĩnh viễn'}${
        p.order_id ? ` • đơn ${escapeHtml(p.order_id)}` : ' • cấp tay'}`
    : (p.is_free ? 'Bản dùng thử, không cần mua' : `<span class="perm-price">${fmtVnd(p.price_vnd)}</span> — chưa thanh toán`);

  return `
    <div class="perm-card ${p.unlocked ? 'unlocked' : 'locked'}">
      <div class="perm-top">
        <div class="perm-title">${escapeHtml(p.title)}</div>
        <div class="perm-state ${state}">${label}</div>
      </div>
      <div class="perm-desc">${escapeHtml(p.description || '')}</div>
      <div class="perm-foot">${escapeHtml(p.product_code)} → ${escapeHtml(p.tool)}<br>${foot}</div>
    </div>`;
}

function renderTool(t) {
  const refs = [
    ...t.unlocked_refs.map(r => `<span class="badge ok">🔓 ${escapeHtml(r)}</span>`),
    ...t.locked_refs.map(r => `<span class="badge off">🔒 ${escapeHtml(r)}</span>`),
  ].join('');

  return `
    <div class="tool-row ${t.gated ? 'gated' : ''}">
      <div class="tool-row-head">
        <div class="tool-row-name">${escapeHtml(t.name)}</div>
        ${t.gated ? '<span class="badge warn">có nội dung mua thêm</span>' : ''}
      </div>
      <div class="tool-row-desc">${escapeHtml(t.description)}</div>
      ${refs ? `<div class="tool-row-refs">${refs}</div>` : ''}
    </div>`;
}

loadAdminDevices();
