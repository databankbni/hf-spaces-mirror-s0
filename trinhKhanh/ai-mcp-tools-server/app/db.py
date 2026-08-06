import asyncio
import base64
import json
import os
import uuid
from urllib.parse import urlparse, parse_qs

import asyncpg

from . import state

logger = state.logger

# ── Neon (schema tools) — dùng cho user_subscriptions ───────────────────────
# Cùng cấu hình WHY_DB_* với servers/combined_server.py, nhưng pool riêng
# vì đây là process chính (combined_server chạy ở subprocess stdio).
# KHÔNG hardcode — lấy từ .env (đã load ở app/state.py, import trước file này)
# hoặc HF Secrets. Port 5432 là default chuẩn của Postgres, không phải bí mật.
_WHY_DB_HOST = os.getenv("WHY_DB_HOST")
_WHY_DB_PORT = int(os.getenv("WHY_DB_PORT", "5432"))
_WHY_DB_NAME = os.getenv("WHY_DB_NAME")
_WHY_DB_USER = os.getenv("WHY_DB_USER")
_WHY_DB_PASSWORD = os.getenv("WHY_DB_PASSWORD")

_subs_pool: asyncpg.Pool | None = None
_subs_pool_lock = asyncio.Lock()


async def _get_subs_pool() -> asyncpg.Pool:
    global _subs_pool
    if _subs_pool is None:
        async with _subs_pool_lock:
            if _subs_pool is None:
                _subs_pool = await asyncpg.create_pool(
                    host=_WHY_DB_HOST, port=_WHY_DB_PORT, database=_WHY_DB_NAME,
                    user=_WHY_DB_USER, password=_WHY_DB_PASSWORD,
                    ssl="require", min_size=0, max_size=2, timeout=15,
                )
    return _subs_pool


async def list_subscriptions(account_id=None) -> list[dict]:
    """Khách đã đăng ký. Không truyền account_id → tất cả (dùng khi restore lúc startup);
    truyền vào → chỉ thiết bị của tài khoản đó."""
    try:
        pool = await _get_subs_pool()
        async with pool.acquire() as conn:
            if account_id is None:
                rows = await conn.fetch(
                    "SELECT device_name, wss_url, endpoint_key, account_id, created_at "
                    "FROM tools.user_subscriptions ORDER BY created_at")
            else:
                rows = await conn.fetch(
                    "SELECT device_name, wss_url, endpoint_key, account_id, created_at "
                    "FROM tools.user_subscriptions WHERE account_id = $1 ORDER BY created_at",
                    account_id)
        return [dict(r) for r in rows]
    except asyncpg.UndefinedColumnError:
        logger.warning("⚠️ [SUBS] Thiếu cột account_id — chạy migration 008")
        return []
    except Exception:
        logger.exception("❌ [SUBS] Lỗi đọc danh sách subscription:")
        return []


async def claim_subscription(wss_url: str, account_id) -> dict:
    """Gắn thiết bị (theo endpoint_key của wss) vào một tài khoản.

    Trả `{"success": bool, "error"|"device_name", "already_mine": bool}`.
    Thiết bị đã thuộc người khác → từ chối, không cướp quyền.
    """
    key = endpoint_key_for(wss_url)
    try:
        pool = await _get_subs_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT device_name, account_id FROM tools.user_subscriptions "
                "WHERE endpoint_key = $1", key)
            if row is None:
                return {"success": False,
                        "error": "Chưa có thiết bị nào đăng ký với Websocket URL này. "
                                 "Hãy kết nối MCP trước rồi mới nhận thiết bị."}
            if row["account_id"] is not None:
                if str(row["account_id"]) == str(account_id):
                    return {"success": True, "device_name": row["device_name"],
                            "already_mine": True}
                return {"success": False,
                        "error": "Thiết bị này đã thuộc một tài khoản khác."}
            await conn.execute(
                "UPDATE tools.user_subscriptions SET account_id = $1 WHERE endpoint_key = $2",
                account_id, key)
        logger.info(f"🔗 [SUBS] Thiết bị {key} đã gắn vào account {account_id}")
        return {"success": True, "device_name": row["device_name"], "already_mine": False}
    except Exception as exc:
        logger.exception("❌ [SUBS] Lỗi nhận thiết bị:")
        return {"success": False, "error": str(exc)}


async def delete_subscription(wss_url: str):
    """Xóa subscription khi khách chủ động disconnect — để server restart không tự kết nối lại.

    Xóa theo endpoint_key để vẫn trúng dòng cũ kể cả khi wss trong DB
    là token phiên bản khác của cùng thiết bị.
    """
    try:
        pool = await _get_subs_pool()
        async with pool.acquire() as conn:
            status = await conn.execute(
                "DELETE FROM tools.user_subscriptions WHERE endpoint_key = $1",
                endpoint_key_for(wss_url))
        logger.info(f"💾 [SUBS] Đã xóa subscription ({status}): {wss_url[:60]}")
    except Exception:
        logger.exception("❌ [SUBS] Lỗi xóa subscription:")


async def close_subs_pool():
    global _subs_pool
    if _subs_pool is not None:
        await _subs_pool.close()
        _subs_pool = None


def endpoint_key_for(wss_url: str) -> str:
    """Danh tính thật của thiết bị đằng sau một wss URL.

    Broker kiểu xiaozhi nhúng JWT vào query param `token`; token có thể được
    cấp lại (iat/exp đổi) làm cả chuỗi wss thay đổi dù vẫn là cùng thiết bị.
    Decode payload JWT (không cần verify chữ ký) lấy endpointId để so trùng.
    Nếu không phải dạng JWT thì fallback dùng cả chuỗi wss.
    """
    try:
        parsed = urlparse(wss_url)
        token = parse_qs(parsed.query).get("token", [""])[0]
        parts = token.split(".")
        if len(parts) == 3:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            endpoint_id = payload.get("endpointId") or payload.get("agentId") or payload.get("userId")
            if endpoint_id:
                return f"{parsed.hostname}/{endpoint_id}"
    except Exception:
        pass
    return wss_url


async def save_subscription(device_name: str, wss_url: str, account_id=None):
    """Lưu khách đăng ký MCP tools vào tools.user_subscriptions (Neon).

    Chống trùng theo endpoint_key: cùng một thiết bị đăng ký lại với token
    mới (wss khác) sẽ thay thế dòng cũ thay vì tạo bản ghi mới.

    `account_id` (khi khách đang đăng nhập lúc đăng ký) → thiết bị có chủ ngay,
    khỏi phải "nhận thiết bị" sau. COALESCE để lần đăng ký lại **không** xoá chủ
    cũ nếu lần này gọi mà không có session.
    """
    try:
        pool = await _get_subs_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tools.user_subscriptions
                    (device_name, wss_url, endpoint_key, account_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (endpoint_key) DO UPDATE
                    SET device_name = EXCLUDED.device_name,
                        wss_url = EXCLUDED.wss_url,
                        account_id = COALESCE(EXCLUDED.account_id,
                                              tools.user_subscriptions.account_id)
                RETURNING (xmax = 0) AS inserted
                """,
                device_name, wss_url, endpoint_key_for(wss_url), account_id)
        if row["inserted"]:
            logger.info(f"💾 [SUBS] Đăng ký mới: {device_name} — {wss_url[:60]}")
        else:
            logger.info(f"💾 [SUBS] Thiết bị đã có, cập nhật wss/tên: {device_name} — {wss_url[:60]}")
    except Exception:
        logger.exception("❌ [SUBS] Lỗi lưu subscription (không ảnh hưởng kết nối):")


async def get_user_profile(user_id: str) -> dict:
    if not state.db_pool:
        return None
    async with state.db_pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT full_name, age, preferences, weak_points FROM users WHERE user_id = $1::uuid",
                user_id)
            return dict(row) if row else None
        except Exception as e:
            logger.warning(f"⚠️ [DB] Không tải được profile bé: {e}")
            return None


async def update_user_preferences(user_id: str, category: str, value: str) -> str:
    if not state.db_pool:
        return "Lỗi khi ghi nhớ"
    async with state.db_pool.acquire() as conn:
        try:
            raw = await conn.fetchval(
                "SELECT preferences::text FROM users WHERE user_id = $1::uuid", user_id)
            prefs = json.loads(raw) if raw else {}
            if category in prefs:
                if isinstance(prefs[category], list):
                    if value.lower() not in [v.lower() for v in prefs[category]]:
                        prefs[category].append(value)
                else:
                    prefs[category] = [prefs[category], value]
            else:
                prefs[category] = [value]
            await conn.execute(
                "UPDATE users SET preferences = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(prefs, ensure_ascii=False), user_id)
            logger.info(f"💾 [DB] Cập nhật sở thích: [{category}] = {value}")
            return "Đã ghi nhớ thành công"
        except Exception:
            logger.exception("❌ [DB] Lỗi khi ghi nhớ sở thích:")
            return "Lỗi khi ghi nhớ"


async def create_chat_session(user_id: str) -> str:
    if not state.db_pool:
        return uuid.uuid4().hex
    async with state.db_pool.acquire() as conn:
        return str(await conn.fetchval(
            "INSERT INTO chat_sessions (user_id) VALUES ($1::uuid) RETURNING session_id",
            user_id))


async def save_chat_history(session_id: str, sender: str, content: str):
    if not state.db_pool:
        return
    async with state.db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_history (session_id, sender, content) VALUES ($1, $2, $3)",
            session_id, sender, content)