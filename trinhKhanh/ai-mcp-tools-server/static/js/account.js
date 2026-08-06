/* Thanh tài khoản trên tabbar + khối "Thiết bị của tôi" trong tab mua nội dung.
   Nguồn: GET /api/auth/me, GET /api/devices/mine, POST /api/devices/claim,
   POST /api/auth/logout. Session ở cookie httpOnly nên JS không giữ token. */

let currentAccount = null;

async function loadAccount() {
  const box = document.getElementById('acctBox');
  try {
    const data = await fetch('/api/auth/me').then(r => r.json());
    currentAccount = data.authenticated ? data.account : null;
  } catch {
    currentAccount = null;
  }

  if (!currentAccount) {
    box.innerHTML = '<a class="acct-link" href="/login">Đăng nhập</a>';
    document.getElementById('myDevBox').style.display = 'none';
    return;
  }

  box.innerHTML = `
    <span class="acct-email" title="${escapeHtml(currentAccount.email)}">
      ${escapeHtml(currentAccount.full_name || currentAccount.email)}
    </span>
    ${currentAccount.role === 'admin'
      ? '<a class="acct-link" href="/adminctrl">Admin</a>' : ''}
    <button class="acct-link btn" onclick="logoutAccount()">Đăng xuất</button>`;

  document.getElementById('myDevBox').style.display = '';
  loadMyDevices();
}

async function logoutAccount() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch { /* vẫn reload để về trạng thái chưa đăng nhập */ }
  window.location.reload();
}

async function loadMyDevices() {
  const list = document.getElementById('myDevList');
  try {
    const res = await fetch('/api/devices/mine');
    if (!res.ok) {
      list.innerHTML = '<div class="store-empty">Cần đăng nhập lại.</div>';
      return;
    }
    const { devices } = await res.json();
    if (!devices.length) {
      list.innerHTML = `<div class="store-empty">
        Chưa có robot nào gắn với tài khoản này. Dán Websocket URL bên dưới để nhận thiết bị
        bạn đã đăng ký trước đó.
      </div>`;
      return;
    }

    list.innerHTML = devices.map(d => {
      const chips = (d.products || []).map(p => {
        const cls = p.unlocked ? 'ok' : 'off';
        const icon = p.unlocked ? '🔓' : '🔒';
        const note = p.is_free ? ' (miễn phí)'
                   : p.source === 'account' ? ' (tài khoản)'
                   : p.source === 'device' ? ' (thiết bị)' : '';
        return `<span class="chip ${cls}">${icon} ${escapeHtml(p.title)}${note}</span>`;
      }).join('');

      const dot = d.status === 'connected' ? 'online'
                : (d.status === 'connecting' || d.status === 'reconnecting') ? 'checking' : '';

      return `<div class="mydev-item">
        <div class="mydev-head">
          <span class="device-dot ${dot}"></span>
          <span class="mydev-name">${escapeHtml(d.device_name)}</span>
          <span class="mydev-key">${escapeHtml(d.endpoint_key)}</span>
        </div>
        <div class="mydev-chips">${chips || '<span class="chip">Chưa khai báo nội dung bán</span>'}</div>
      </div>`;
    }).join('');
  } catch {
    list.innerHTML = '<div class="store-empty error">Không tải được thiết bị của bạn</div>';
  }
}

async function claimDevice() {
  const input = document.getElementById('claimUrl');
  const msg = document.getElementById('claimMsg');
  const url = input.value.trim();
  msg.className = 'mydev-msg';
  if (!url) {
    msg.className = 'mydev-msg error';
    msg.textContent = 'Hãy dán Websocket URL của robot.';
    return;
  }
  try {
    const res = await fetch('/api/devices/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ websocket_url: url }),
    });
    const data = await res.json();
    if (res.status === 401) {
      msg.className = 'mydev-msg error';
      msg.textContent = 'Phiên đăng nhập đã hết. Hãy đăng nhập lại.';
      return;
    }
    if (!data.success) {
      msg.className = 'mydev-msg error';
      msg.textContent = data.error || data.detail || 'Không nhận được thiết bị.';
      return;
    }
    msg.className = 'mydev-msg ok';
    msg.textContent = data.already_mine
      ? `"${data.device_name}" đã thuộc tài khoản này rồi.`
      : `Đã nhận "${data.device_name}" về tài khoản của bạn.`;
    input.value = '';
    loadMyDevices();
  } catch {
    msg.className = 'mydev-msg error';
    msg.textContent = 'Không gọi được server.';
  }
}

loadAccount();
