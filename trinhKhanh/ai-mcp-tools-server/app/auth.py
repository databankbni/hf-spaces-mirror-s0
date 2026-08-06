"""Đăng ký / đăng nhập bằng tài khoản riêng của server (schema `tools`).

Thiết kế:
- Tài khoản trong `tools.accounts`, mật khẩu bcrypt. Email là danh tính đăng nhập
  (so sánh không phân biệt hoa thường).
- Session KHÔNG dùng JWT: cookie `session` giữ token random 32 byte, DB chỉ lưu
  sha256(token) trong `tools.sessions` — cùng cách làm với ack_token ở app/media.py.
  Không cần thêm secret ký; đổi/khoá session = xoá dòng trong DB.
- Chống dò mật khẩu: đếm số lần sai theo (email, IP) trong RAM. App chạy 1 process
  trên HF nên đủ; không dùng được nếu sau này scale nhiều worker.

Schema `public` là của sản phẩm khác — tuyệt đối không dùng ở đây.
"""
import asyncio
import hashlib
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import state

logger = state.logger
router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "session"
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

# Số lần đăng nhập sai tối đa trước khi khoá tạm, và thời gian khoá (giây).
MAX_FAILED = int(os.getenv("LOGIN_MAX_FAILED", "8"))
LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# (email, ip) → [số lần sai, thời điểm sai gần nhất]
_failed: dict[tuple[str, str], list] = {}
_failed_lock = asyncio.Lock()


def _cookie_secure() -> bool:
    """Cookie chỉ gửi qua HTTPS khi deploy; local http phải tắt nếu không cookie bị bỏ.

    Mặc định suy từ môi trường (HF Spaces / PUBLIC_URL https), override bằng
    SESSION_COOKIE_SECURE=1|0.
    """
    override = os.getenv("SESSION_COOKIE_SECURE")
    if override is not None:
        return override.strip() not in ("0", "false", "False", "")
    if os.getenv("SPACE_ID"):
        return True
    return os.getenv("PUBLIC_URL", "").startswith("https://")


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("ascii"))
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _require_pool() -> asyncpg.Pool:
    if state.db_pool is None:
        raise HTTPException(status_code=503, detail="Chưa kết nối database")
    return state.db_pool


# ── Rate limit ───────────────────────────────────────────────────────────────
async def _check_lockout(email: str, ip: str) -> None:
    key = (email.lower(), ip)
    async with _failed_lock:
        entry = _failed.get(key)
        if not entry:
            return
        count, last = entry
        if time.time() - last > LOCKOUT_SECONDS:
            _failed.pop(key, None)
            return
        if count >= MAX_FAILED:
            wait = int(LOCKOUT_SECONDS - (time.time() - last))
            raise HTTPException(
                status_code=429,
                detail=f"Sai mật khẩu quá nhiều lần. Thử lại sau {max(1, wait // 60)} phút.",
            )


async def _note_failure(email: str, ip: str) -> None:
    key = (email.lower(), ip)
    async with _failed_lock:
        count = _failed.get(key, [0, 0])[0]
        _failed[key] = [count + 1, time.time()]


async def _clear_failures(email: str, ip: str) -> None:
    async with _failed_lock:
        _failed.pop((email.lower(), ip), None)


# ── Session ──────────────────────────────────────────────────────────────────
async def create_session(account_id, request: Request) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tools.sessions
                (token_hash, account_id, expires_at, last_seen_at, user_agent, ip)
            VALUES ($1, $2, $3, NOW(), $4, $5)
            """,
            _token_hash(token), account_id, expires,
            request.headers.get("user-agent", "")[:300], _client_ip(request),
        )
    return token, expires


async def current_account(request: Request) -> dict | None:
    """Tài khoản của session trong cookie, hoặc None nếu chưa đăng nhập/hết hạn."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or state.db_pool is None:
        return None
    try:
        async with state.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT a.account_id, a.email, a.full_name, a.phone, a.role, a.is_active,
                       s.expires_at
                FROM tools.sessions s
                JOIN tools.accounts a USING (account_id)
                WHERE s.token_hash = $1 AND s.expires_at > NOW()
                """,
                _token_hash(token),
            )
            if row is None or not row["is_active"]:
                return None
            await conn.execute(
                "UPDATE tools.sessions SET last_seen_at = NOW() WHERE token_hash = $1",
                _token_hash(token))
        return dict(row)
    except asyncpg.UndefinedTableError:
        logger.warning("⚠️ [AUTH] Chưa có tools.accounts/sessions — chạy migration 007")
        return None
    except Exception:
        logger.exception("❌ [AUTH] Lỗi đọc session:")
        return None


async def require_account(request: Request) -> dict:
    acc = await current_account(request)
    if acc is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập")
    return acc


async def require_admin(request: Request) -> dict:
    acc = await require_account(request)
    if acc["role"] != "admin":
        raise HTTPException(status_code=403, detail="Cần quyền admin")
    return acc


def _set_cookie(response: Response, token: str, expires: datetime) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
    )


def _public(acc: dict) -> dict:
    return {
        "account_id": str(acc["account_id"]),
        "email": acc["email"],
        "full_name": acc.get("full_name"),
        "phone": acc.get("phone"),
        "role": acc["role"],
    }


# ── API ──────────────────────────────────────────────────────────────────────
class RegisterPayload(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30)


class LoginPayload(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=128)


@router.post("/register")
async def register(payload: RegisterPayload, request: Request, response: Response):
    email = payload.email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Email không hợp lệ")

    pool = _require_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tools.accounts (email, password_hash, full_name, phone)
                VALUES ($1, $2, $3, $4)
                RETURNING account_id, email, full_name, phone, role
                """,
                email, hash_password(payload.password),
                (payload.full_name or "").strip() or None,
                (payload.phone or "").strip() or None,
            )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email này đã được đăng ký")
    except asyncpg.UndefinedTableError:
        raise HTTPException(status_code=503, detail="Chưa chạy migration 007 (tools.accounts)")

    token, expires = await create_session(row["account_id"], request)
    _set_cookie(response, token, expires)
    logger.info("👤 [AUTH] Đăng ký mới: %s", email)
    return {"success": True, "account": _public(dict(row))}


@router.post("/login")
async def login(payload: LoginPayload, request: Request, response: Response):
    email = payload.email.strip()
    ip = _client_ip(request)
    await _check_lockout(email, ip)

    pool = _require_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT account_id, email, password_hash, full_name, phone, role, is_active
                FROM tools.accounts
                WHERE LOWER(email) = LOWER($1)
                """,
                email,
            )
    except asyncpg.UndefinedTableError:
        raise HTTPException(status_code=503, detail="Chưa chạy migration 007 (tools.accounts)")

    # Cùng một thông báo cho email sai và mật khẩu sai — không tiết lộ email nào tồn tại.
    if row is None or not verify_password(payload.password, row["password_hash"]):
        await _note_failure(email, ip)
        logger.info("🔒 [AUTH] Đăng nhập sai: %s từ %s", email, ip)
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khoá")

    await _clear_failures(email, ip)
    token, expires = await create_session(row["account_id"], request)
    _set_cookie(response, token, expires)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tools.accounts SET last_login_at = NOW() WHERE account_id = $1",
            row["account_id"])
    logger.info("👤 [AUTH] Đăng nhập: %s (role=%s)", row["email"], row["role"])
    return {"success": True, "account": _public(dict(row))}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token and state.db_pool is not None:
        try:
            async with state.db_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM tools.sessions WHERE token_hash = $1", _token_hash(token))
        except Exception:
            logger.exception("❌ [AUTH] Lỗi xoá session:")
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"success": True}


@router.get("/me")
async def me(request: Request):
    acc = await current_account(request)
    if acc is None:
        return {"authenticated": False}
    return {"authenticated": True, "account": _public(acc)}


async def cleanup_expired_sessions() -> int:
    """Xoá session hết hạn. Gọi lúc startup; rẻ nên không cần task định kỳ riêng."""
    if state.db_pool is None:
        return 0
    try:
        async with state.db_pool.acquire() as conn:
            status = await conn.execute("DELETE FROM tools.sessions WHERE expires_at < NOW()")
        return int(status.split()[-1]) if status.startswith("DELETE") else 0
    except asyncpg.UndefinedTableError:
        return 0
    except Exception:
        logger.exception("❌ [AUTH] Lỗi dọn session hết hạn:")
        return 0
