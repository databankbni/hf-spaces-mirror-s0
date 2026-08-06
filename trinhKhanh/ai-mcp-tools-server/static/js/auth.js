/* Trang /login: đăng nhập + đăng ký.
   Session nằm trong cookie httpOnly → JS KHÔNG giữ token, trạng thái đăng nhập
   luôn hỏi lại GET /api/auth/me. Script classic, hàm ở global scope. */

let authMode = 'login';

/* /login?next=/adminctrl → sau khi vào thì về đúng trang đó. Chỉ nhận đường dẫn
   nội bộ bắt đầu bằng '/' (và không phải '//host') để tránh open redirect. */
function nextUrl() {
  const raw = new URLSearchParams(window.location.search).get('next') || '/';
  return /^\/(?!\/)/.test(raw) ? raw : '/';
}

function setAuthMode(mode) {
  authMode = mode;
  const isReg = mode === 'register';

  document.getElementById('tabLogin').classList.toggle('active', !isReg);
  document.getElementById('tabRegister').classList.toggle('active', isReg);
  document.getElementById('authTitle').textContent = isReg ? 'Đăng ký' : 'Đăng nhập';
  document.getElementById('authSub').textContent = isReg
    ? 'Tạo tài khoản để gắn robot và nội dung đã mua vào tên bạn.'
    : 'Quản lý robot và nội dung đã mua của bạn.';
  document.getElementById('fieldName').style.display = isReg ? '' : 'none';
  document.getElementById('fieldPhone').style.display = isReg ? '' : 'none';
  document.getElementById('pwHint').style.display = isReg ? '' : 'none';
  document.getElementById('btnSubmit').textContent = isReg ? 'TẠO TÀI KHOẢN' : 'ĐĂNG NHẬP';
  document.getElementById('inPassword').autocomplete = isReg ? 'new-password' : 'current-password';
  showAuthMsg('');
}

function showAuthMsg(text, kind) {
  const box = document.getElementById('authMsg');
  box.className = 'auth-msg' + (text ? ` ${kind || 'error'}` : '');
  box.textContent = text;
}

async function submitAuth(event) {
  event.preventDefault();
  const btn = document.getElementById('btnSubmit');
  const email = document.getElementById('inEmail').value.trim();
  const password = document.getElementById('inPassword').value;

  if (authMode === 'register' && password.length < 8) {
    showAuthMsg('Mật khẩu phải có tối thiểu 8 ký tự.');
    return;
  }

  const body = { email, password };
  if (authMode === 'register') {
    body.full_name = document.getElementById('inName').value.trim() || null;
    body.phone = document.getElementById('inPhone').value.trim() || null;
  }

  btn.disabled = true;
  showAuthMsg('');
  try {
    const res = await fetch(`/api/auth/${authMode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!res.ok) {
      // FastAPI trả lỗi ở `detail`; validation lỗi thì detail là mảng.
      const detail = Array.isArray(data.detail)
        ? (data.detail[0]?.msg || 'Dữ liệu không hợp lệ')
        : (data.detail || 'Có lỗi xảy ra');
      showAuthMsg(detail);
      return;
    }

    showAuthMsg('Thành công, đang chuyển trang...', 'ok');
    window.location.href = nextUrl();
  } catch {
    showAuthMsg('Không gọi được server. Kiểm tra kết nối.');
  } finally {
    btn.disabled = false;
  }
}

/* Đã đăng nhập rồi thì không cần ở lại trang này. */
(async function redirectIfLoggedIn() {
  try {
    const { authenticated, account } = await fetch('/api/auth/me').then(r => r.json());
    if (authenticated) {
      showAuthMsg(`Đang đăng nhập bằng ${account.email}. Chuyển về trang chủ...`, 'ok');
      setTimeout(() => { window.location.href = nextUrl(); }, 1200);
    }
  } catch { /* chưa có DB / server lỗi → cứ để form hiện bình thường */ }
})();
