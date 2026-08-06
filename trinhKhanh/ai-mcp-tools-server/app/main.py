import json
import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from . import auth
from . import db
from . import media
from . import state
from . import mcp_outbound
from . import ws_handler

ROOT = Path(__file__).parent.parent

_restore_task: asyncio.Task | None = None


async def _restore_subscriptions():
    """Tự động kết nối lại các broker đã đăng ký trong tools.user_subscriptions.

    Chạy sau khi server khởi động (build lại / update server) để khách
    không phải vào đăng ký lại."""
    subs = await db.list_subscriptions()
    restored = 0
    for sub in subs:
        url = sub["wss_url"]
        device_name = sub["device_name"]
        if url in state.outbound_connections:
            continue
        state.outbound_connections[url] = {
            "url": url, "device_name": device_name,
            "status": "connecting", "tools_count": 0, "error": None, "task": None
        }
        task = asyncio.create_task(mcp_outbound.mcp_outbound_worker(url, device_name))
        state.outbound_connections[url]["task"] = task
        restored += 1
        state.logger.info(f"🔁 [SUBS] Tự động kết nối lại: {device_name} — {url[:60]}")
    if restored:
        state.logger.info(f"🔁 [SUBS] Đã khôi phục {restored} kết nối broker từ database.")
    else:
        state.logger.info("🔁 [SUBS] Không có subscription nào cần khôi phục.")


# ==========================================
# LIFESPAN – KHỞI ĐỘNG / TẮT HỆ THỐNG
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    state.logger.info("🚀 [SYSTEM] Đang khởi động hệ thống AI Backend...")

    # 1. Database
    try:
        ssl_mode = None if state.DB_SSL in ("", "disable", "false") else state.DB_SSL
        state.db_pool = await asyncpg.create_pool(
            state.DSN, ssl=ssl_mode, min_size=1, max_size=5
        )
        state.logger.info("✅ [DB] Kết nối Database PostgreSQL thành công.")
    except Exception:
        state.logger.exception("❌ [DB] Lỗi kết nối Database:")
        state.db_pool = None

    await media.init_store()
    await media.start_cleanup()

    removed = await auth.cleanup_expired_sessions()
    if removed:
        state.logger.info(f"🧹 [AUTH] Đã xoá {removed} session hết hạn.")

    # 2. MCP stdio servers
    # MCP stdio servers
    try:
        with open(ROOT / "mcp_config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        for name, srv in config.get("mcpServers", {}).items():
            if srv.get("type") != "stdio":
                continue
            state.logger.info(f"⏳ [MCP] Đang nạp server: {name}...")
            params = StdioServerParameters(
                command=srv["command"],
                args=srv.get("args", []),
                env=os.environ.copy()
            )
            transport = await state.exit_stack.enter_async_context(stdio_client(params))
            session = await state.exit_stack.enter_async_context(ClientSession(*transport))
            await session.initialize()
            state.mcp_sessions[name] = session
            state.logger.info(f"✅ [MCP] Đã kết nối server: {name}")
            for t in (await session.list_tools()).tools:
                state.mcp_tools_registry.append({"server": name, "tool": t})
                state.logger.info(f"   🔧 Nạp công cụ: {t.name}")
    except Exception:
        state.logger.exception("❌ [MCP] Lỗi khởi tạo MCP Client:")

    # 3. Tự động kết nối lại các broker đã đăng ký (background — không block startup)
    global _restore_task
    _restore_task = asyncio.create_task(_restore_subscriptions())

    yield

    state.logger.info("🛑 [SYSTEM] Đang tắt hệ thống...")
    await media.stop_cleanup()
    await db.close_subs_pool()
    await state.exit_stack.aclose()


# ==========================================
# APP
# ==========================================
app = FastAPI(title="AI Backend – Robot Orchestrator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
app.include_router(media.router)
app.include_router(auth.router)


# ==========================================
# HTTP ROUTES
# ==========================================
@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """Lightweight health check cho UptimeRobot và Render – không phụ thuộc DB hay MCP."""
    return {
        "status": "ok",
        "mcp_tools": len(state.mcp_tools_registry),
        "db_connected": state.db_pool is not None,
    }


@app.head("/")
async def serve_index_head():
    return Response()


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open(ROOT / "static" / "index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    with open(ROOT / "static" / "login.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/tools")
async def get_tools():
    # Dùng chung payload với tools/list gửi broker → cùng ẩn param được tiêm
    # phía server (endpoint_key), tránh lệch giữa UI và những gì LLM thấy.
    return {"tools": mcp_outbound.build_tools_payload()}


@app.get("/api/why/categories")
async def get_why_categories():
    """Danh sách chủ đề của kho '1 vạn câu hỏi vì sao' (tab Mua thêm nội dung).

    Đọc thẳng tools.why_questions trên Neon — db_pool mặc định đã trỏ cùng Neon
    (xem "Chỉ 1 DB" trong CLAUDE.md), nên không cần pool riêng.
    """
    if state.db_pool is None:
        return {"success": False, "error": "Chưa kết nối database", "categories": []}
    try:
        async with state.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT category,
                       COUNT(*)                                              AS total,
                       COUNT(*) FILTER (WHERE image_urls <> '[]'::jsonb)     AS with_image
                FROM tools.why_questions
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY total DESC
            """)
        categories = [
            {"category": r["category"], "total": r["total"], "with_image": r["with_image"]}
            for r in rows
        ]
        return {
            "success": True,
            "categories": categories,
            "total_questions": sum(c["total"] for c in categories),
        }
    except Exception as exc:
        state.logger.exception("❌ /api/why/categories:")
        return {"success": False, "error": str(exc), "categories": []}


@app.post("/api/tools/run")
async def run_tool(request: Request):
    data = await request.json()
    tool_name = data.get("tool_name", "").strip()
    arguments = data.get("arguments", {})
    if not tool_name:
        return {"success": False, "error": "Thiếu tool_name"}
    raw = await mcp_outbound.call_tool_by_name(tool_name, arguments)
    try:
        return {"success": True, "result": json.loads(raw)}
    except Exception:
        return {"success": True, "result": raw}


async def _call_device_tool_via_broker(tool_name: str, arguments: dict) -> dict:
    """Connect to broker as MCP client and call a device tool directly."""
    import websockets as _ws

    broker_url = None
    for url, info in state.outbound_connections.items():
        if info.get("status") == "connected":
            broker_url = url
            break

    if not broker_url:
        return {"success": False, "error": "No active broker connection"}

    headers = {
        "Origin": "https://xiaozhi.ai",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        async with _ws.connect(broker_url, open_timeout=10, additional_headers=headers) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            server_msg = json.loads(raw)
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": server_msg.get("id", 0),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "img-push-client", "version": "1.0"}
                }
            }))
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))

            call_id = int(time.time() * 1000) % 0x7FFFFFFF

            # Drain initial messages; respond to tools/list so broker completes handshake
            for _ in range(8):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3)
                    msg = json.loads(raw)
                    if msg.get("method") == "tools/list":
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0", "id": msg["id"],
                            "result": {"tools": []}
                        }))
                        break
                    elif msg.get("method") == "ping":
                        await ws.send(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {}}))
                except asyncio.TimeoutError:
                    break

            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": call_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments}
            }))

            for _ in range(15):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)
                    if msg.get("id") == call_id:
                        if "error" in msg:
                            return {"success": False, "error": str(msg["error"])}
                        return {"success": True}
                    if msg.get("method") == "tools/list":
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0", "id": msg["id"],
                            "result": {"tools": []}
                        }))
                    elif msg.get("method") == "ping":
                        await ws.send(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {}}))
                except asyncio.TimeoutError:
                    break

            return {"success": False, "error": "Timeout waiting for device tool result"}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


@app.post("/api/internal/push_image")
async def push_image_to_device(request: Request):
    """Internal endpoint: push image display command to device via broker."""
    data = await request.json()
    url = data.get("url", "")
    state.logger.info("🖼️ [PUSH] push_image via broker: %s", url[:70])
    result = await _call_device_tool_via_broker("self.screen.preview_image", {"url": url})
    state.logger.info("🖼️ [PUSH] broker call result: %s", result)
    return result


# ── Why-image queue ─────────────────────────────────────────────────────────
# show_why_image (cloud mode) stores an image URL here; the device polls
# GET /api/image_queue immediately after detecting `% show_why_image`.
#
# Thay vì đưa URL wsrv.nl cho thiết bị (hay bị Wikimedia rate-limit 429 rồi
# wsrv cache lại thành 404), server tự tải ảnh gốc + convert baseline JPEG 320px
# bằng Pillow, rồi phục vụ từ chính domain của mình. Thiết bị chỉ tải từ server,
# không còn phụ thuộc wsrv.nl. Nếu bước tải/convert lỗi → fallback URL wsrv.nl.

_pending_image_url: str = ""
_pending_image_lock = asyncio.Lock()

_why_image_store: dict[str, bytes] = {}
_why_image_order: list[str] = []
_why_image_lock = asyncio.Lock()
_WHY_IMAGE_MAX = 20


def _derive_public_url() -> str:
    """Public base URL mà thiết bị dùng để tải ảnh (khớp logic của combined_server)."""
    if os.getenv("PUBLIC_URL"):
        return os.getenv("PUBLIC_URL").rstrip("/")
    space_id = os.getenv("SPACE_ID", "")          # HuggingFace tự set: "user/space"
    if space_id:
        return "https://" + space_id.replace("/", "-").lower() + ".hf.space"
    return os.getenv("MEDIA_API_BASE_URL", "http://127.0.0.1:7860").rstrip("/")


_PUBLIC_URL = _derive_public_url()


def _source_from_any(url: str) -> str:
    """Trả URL ảnh gốc để tải trực tiếp: bóc ?url= nếu là link wsrv.nl cũ,
    unquote, và bỏ tiền tố ngôn ngữ của thumbnail SVG Wikipedia (langvi-330px-)."""
    import urllib.parse
    import re
    if "wsrv.nl" in url:
        try:
            q = urllib.parse.urlparse(url).query
            inner = urllib.parse.parse_qs(q).get("url", [""])[0]
            if inner:
                url = inner
        except Exception:
            pass
    clean = urllib.parse.unquote(url)
    clean = re.sub(r'/lang\w+-(\d+px-)', r'/\1', clean)
    return clean


def _to_wsrv(url: str) -> str:
    """Fallback: dựng URL wsrv.nl (hành vi cũ) khi tự xử lý ảnh thất bại."""
    import urllib.parse
    import re
    if "wsrv.nl" in url:
        return url
    clean = urllib.parse.unquote(url)
    clean = re.sub(r'/lang\w+-(\d+px-)', r'/\1', clean)
    encoded = urllib.parse.quote(clean, safe="")
    return f"https://wsrv.nl/?url={encoded}&output=jpg&q=75&w=320"


# User-Agent theo chính sách Wikimedia (mô tả rõ + có liên hệ) để giảm 429.
_WIKI_UA = ("XiaozhiVN-WhyImageBot/1.0 "
            "(+https://github.com/78/xiaozhi-esp32; educational AI robot)")


def _fetch_and_process_image(src_url: str) -> bytes | None:
    """Tải ảnh gốc trực tiếp + convert sang baseline JPEG rộng 320px cho ESP32.
    Xử lý cả PNG/GIF (flatten RGB) và progressive JPEG → baseline. None nếu lỗi.
    Retry 429/5xx (Wikimedia rate-limit ngẫu nhiên). Import nội bộ để thiếu
    Pillow chỉ vô hiệu tối ưu này, không sập app."""
    try:
        import io
        import time
        import requests
        from PIL import Image
    except Exception as exc:
        state.logger.warning("⚠️ [WHY-IMG] Pillow/requests không khả dụng: %s", exc)
        return None

    raw = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(src_url, headers={"User-Agent": _WIKI_UA}, timeout=12)
            if resp.status_code == 429 or resp.status_code >= 500:
                state.logger.warning("⚠️ [WHY-IMG] HTTP %d (lần %d/3): %.60s",
                                     resp.status_code, attempt, src_url)
                if attempt < 3:
                    time.sleep(0.6 * attempt)
                    continue
                return None
            resp.raise_for_status()
            raw = resp.content
            break
        except Exception as exc:
            state.logger.warning("⚠️ [WHY-IMG] tải lỗi (lần %d/3): %s", attempt, exc)
            if attempt < 3:
                time.sleep(0.6 * attempt)
                continue
            return None

    if not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = im.size
        if w > 320:
            im = im.resize((320, max(1, round(h * 320 / w))), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=75, progressive=False, optimize=True)
        return out.getvalue()
    except Exception as exc:
        state.logger.warning("⚠️ [WHY-IMG] convert lỗi (%.60s): %s", src_url, exc)
        return None


@app.post("/api/internal/set_image")
async def set_pending_image(request: Request):
    """Called by show_why_image (cloud mode) to queue an image for the device."""
    global _pending_image_url
    data = await request.json()
    url = data.get("url", "")
    if not url:
        return {"success": False, "error": "missing url"}

    src = _source_from_any(url)
    img_bytes = await asyncio.to_thread(_fetch_and_process_image, src)

    served_url = None
    if img_bytes:
        image_id = uuid.uuid4().hex[:12]
        async with _why_image_lock:
            _why_image_store[image_id] = img_bytes
            _why_image_order.append(image_id)
            while len(_why_image_order) > _WHY_IMAGE_MAX:
                _why_image_store.pop(_why_image_order.pop(0), None)
        served_url = f"{_PUBLIC_URL}/api/why_image/{image_id}.jpg"

    final_url = served_url or _to_wsrv(url)  # fallback về wsrv.nl nếu xử lý lỗi
    async with _pending_image_lock:
        _pending_image_url = final_url
    state.logger.info(
        "🖼️ [QUEUE] set_pending_image: %.70s (%s, %s)",
        final_url,
        "served" if served_url else "wsrv-fallback",
        f"{len(img_bytes)}B" if img_bytes else "no-bytes",
    )
    return {"success": True, "served": bool(served_url)}


@app.get("/api/why_image/{image_id}")
async def serve_why_image(image_id: str):
    """Serve baseline JPEG đã xử lý cho thiết bị (thay cho wsrv.nl)."""
    if image_id.endswith(".jpg"):
        image_id = image_id[:-4]
    async with _why_image_lock:
        data = _why_image_store.get(image_id)
    if not data:
        return Response(status_code=404)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/image_queue")
async def get_image_queue():
    """Long-poll endpoint: device calls this when it detects % show_why_image.
    Waits up to 3 s for show_why_image to post the URL, then returns it once."""
    global _pending_image_url
    for _ in range(30):  # 30 × 0.1 s = 3 s max wait
        async with _pending_image_lock:
            if _pending_image_url:
                url = _pending_image_url
                _pending_image_url = ""
                state.logger.info("🖼️ [QUEUE] Delivering image to device: %.70s", url)
                return {"url": url}
        await asyncio.sleep(0.1)
    return {"url": ""}


@app.post("/api/mcp/probe")
async def probe_mcp(request: Request):
    import websockets as _ws
    data = await request.json()
    ws_url = data.get("websocket_url", "").strip()
    if not ws_url:
        return {"status": "offline", "error": "Thiếu websocket_url", "tools": []}
    headers = {
        "Origin": "https://xiaozhi.ai",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        async with _ws.connect(ws_url, open_timeout=20, additional_headers=headers) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            server_msg = json.loads(raw)
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": server_msg.get("id", 0),
                "result": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "serverInfo": {"name": "probe-device", "version": "1.0"}}
            }))
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            asked = False
            for _ in range(15):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                if msg.get("method") == "tools/list" and not asked:
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": []}}))
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}))
                    asked = True
                elif str(msg.get("id")) == "99":
                    tools = (msg.get("result") or {}).get("tools", [])
                    return {"status": "online", "tools": tools}
            return {"status": "online", "tools": []}
    except Exception as e:
        return {"status": "offline", "error": f"{type(e).__name__}: {e}", "tools": []}


@app.post("/api/mcp/connect")
async def connect_mcp_broker(request: Request):
    data = await request.json()
    url = data.get("websocket_url", "").strip()
    device_name = data.get("device_name", "ai-robot-server").strip()
    if not url:
        return {"success": False, "error": "Thiếu websocket_url"}
    if url in state.outbound_connections:
        old = state.outbound_connections[url]
        if old.get("task") and not old["task"].done():
            old["task"].cancel()
    # Cùng thiết bị nhưng token mới (wss khác) → hủy worker cũ để không
    # có 2 kết nối tranh nhau cùng một endpoint trên broker.
    new_key = db.endpoint_key_for(url)
    for old_url in list(state.outbound_connections.keys()):
        if old_url != url and db.endpoint_key_for(old_url) == new_key:
            old = state.outbound_connections[old_url]
            if old.get("task") and not old["task"].done():
                old["task"].cancel()
            del state.outbound_connections[old_url]
            state.logger.info(f"🔄 [OUTBOUND] Thay kết nối cũ cùng thiết bị: {old_url[:60]}")
    state.outbound_connections[url] = {
        "url": url, "device_name": device_name,
        "status": "connecting", "tools_count": 0, "error": None, "task": None
    }
    task = asyncio.create_task(mcp_outbound.mcp_outbound_worker(url, device_name))
    state.outbound_connections[url]["task"] = task
    await asyncio.sleep(3)
    info = state.outbound_connections.get(url, {})
    if info.get("status") == "connected":
        # Đăng nhập sẵn thì thiết bị có chủ ngay; chưa đăng nhập vẫn cho kết nối
        # (giữ luồng cũ), khách nhận thiết bị sau qua POST /api/devices/claim.
        acc = await auth.current_account(request)
        asyncio.create_task(db.save_subscription(
            device_name, url, acc["account_id"] if acc else None))
    return {
        "success": True,
        "status": info.get("status", "connecting"),
        "tools_count": info.get("tools_count", 0),
        "error": info.get("error"),
        "registered_tools": [item["tool"].name for item in state.mcp_tools_registry]
    }


@app.post("/api/mcp/disconnect")
async def disconnect_mcp_broker(request: Request):
    data = await request.json()
    url = data.get("websocket_url", "").strip()
    if not url:
        return {"success": False, "error": "Thiếu websocket_url"}
    # Token trong wss có thể đã xoay vòng (JWT iat/exp đổi) nên chuỗi url gửi lên
    # không khớp chính xác với chuỗi lúc connect. So khớp theo endpoint_key để
    # vẫn trúng đúng worker của cùng thiết bị (đối xứng với /api/mcp/connect).
    target_key = db.endpoint_key_for(url)
    removed = 0
    for conn_url in list(state.outbound_connections.keys()):
        if db.endpoint_key_for(conn_url) == target_key:
            info = state.outbound_connections[conn_url]
            if info.get("task") and not info["task"].done():
                info["task"].cancel()
            del state.outbound_connections[conn_url]
            removed += 1
    # Xóa subscription trong DB (delete_subscription tự so theo endpoint_key) —
    # await để chắc chắn xóa xong trước khi trả về, tránh restart tự kết nối lại.
    await db.delete_subscription(url)
    state.logger.info(f"🛑 [OUTBOUND] Đã ngắt kết nối ({removed} worker): {url[:60]}")
    return {"success": True, "removed": removed}


def _mask_wss(url: str) -> str:
    """Che bớt token trong wss trước khi trả về trang public."""
    if "token=" in url:
        base, token = url.split("token=", 1)
        if len(token) > 20:
            token = f"{token[:10]}...{token[-6:]}"
        return f"{base}token={token}"
    if len(url) > 60:
        return url[:50] + "..."
    return url


@app.get("/api/mcp/subscriptions")
async def get_subscriptions():
    """Danh sách thiết bị đã đăng ký (từ DB) kèm trạng thái kết nối hiện tại."""
    runtime_status = {
        db.endpoint_key_for(url): info.get("status", "unknown")
        for url, info in state.outbound_connections.items()
    }
    subs = await db.list_subscriptions()
    return {"devices": [
        {
            "device_name": s["device_name"],
            "wss_masked": _mask_wss(s["wss_url"]),
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
            "status": runtime_status.get(
                s.get("endpoint_key") or db.endpoint_key_for(s["wss_url"]), "disconnected"),
        }
        for s in subs
    ]}


# ==========================================
# THIẾT BỊ CỦA TÔI (cần đăng nhập)
# ==========================================
async def _products_for_endpoint(endpoint_key: str) -> tuple[list, bool]:
    """Products kèm trạng thái mở khoá của một thiết bị.

    Tính cả 2 loại chủ quyền (migration 008): quyền của account sở hữu thiết bị,
    và quyền cấp trực tiếp cho endpoint_key. Phải KHỚP LOGIC với
    `_locked_products()` trong servers/combined_server.py — nếu sửa một bên,
    sửa cả bên kia, không thì UI hiện khác với cái tool thực sự trả về.
    """
    if state.db_pool is None:
        return [], False
    try:
        async with state.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT p.product_code, p.tool, p.kind, p.ref, p.title, p.description,
                       p.price_vnd, p.is_free,
                       e.granted_at, e.expires_at, e.order_id,
                       (e.product_code IS NOT NULL) AS purchased,
                       (e.account_id IS NOT NULL)   AS via_account
                FROM tools.products p
                LEFT JOIN tools.entitlements e
                       ON e.product_code = p.product_code
                      AND (e.expires_at IS NULL OR e.expires_at > NOW())
                      AND (
                            e.endpoint_key = $1
                         OR (e.account_id IS NOT NULL AND e.account_id = (
                                 SELECT s.account_id
                                 FROM tools.user_subscriptions s
                                 WHERE s.endpoint_key = $1
                                   AND s.account_id IS NOT NULL
                                 LIMIT 1))
                      )
                WHERE p.is_active
                ORDER BY p.sort_order
                """,
                endpoint_key,
            )
        return [dict(r) for r in rows], True
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return [], False
    except Exception:
        state.logger.exception("❌ [STORE] Lỗi đọc products/entitlements:")
        return [], False


def _product_public(p: dict) -> dict:
    return {
        "product_code": p["product_code"],
        "tool": p["tool"],
        "title": p["title"],
        "description": p["description"],
        "ref": p["ref"],
        "price_vnd": p["price_vnd"],
        "is_free": p["is_free"],
        "purchased": bool(p["purchased"]),
        "unlocked": bool(p["is_free"] or p["purchased"]),
        "source": ("free" if p["is_free"]
                   else "account" if p["purchased"] and p["via_account"]
                   else "device" if p["purchased"] else None),
        "granted_at": p["granted_at"].isoformat() if p["granted_at"] else None,
        "expires_at": p["expires_at"].isoformat() if p["expires_at"] else None,
        "order_id": p["order_id"],
    }


@app.get("/api/devices/mine")
async def my_devices(request: Request):
    """Thiết bị của tài khoản đang đăng nhập + chủ đề đã/chưa mở của từng máy."""
    acc = await auth.require_account(request)
    runtime = _runtime_by_endpoint()
    subs = await db.list_subscriptions(account_id=acc["account_id"])
    devices = []
    for s in subs:
        key = s.get("endpoint_key") or db.endpoint_key_for(s["wss_url"])
        products, store_ready = await _products_for_endpoint(key)
        info = runtime.get(key, {})
        devices.append({
            "device_name": s["device_name"],
            "endpoint_key": key,
            "wss_masked": _mask_wss(s["wss_url"]),
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
            "status": info.get("status", "disconnected"),
            "store_ready": store_ready,
            "products": [_product_public(p) for p in products],
        })
    return {"success": True, "account": {"email": acc["email"]}, "devices": devices}


@app.post("/api/devices/claim")
async def claim_device(request: Request):
    """Nhận một thiết bị đã đăng ký về tài khoản đang đăng nhập (dán lại wss URL).

    Dùng cho thiết bị đã kết nối MCP từ trước khi có hệ tài khoản. Sở hữu wss =
    bằng chứng sở hữu robot; thiết bị đã có chủ khác thì từ chối.
    """
    acc = await auth.require_account(request)
    data = await request.json()
    url = (data.get("websocket_url") or "").strip()
    if not url:
        return {"success": False, "error": "Thiếu websocket_url"}
    result = await db.claim_subscription(url, acc["account_id"])
    return result


# ==========================================
# ADMIN (/adminctrl) — chỉ ĐỌC: thiết bị, tools, quyền nội dung
# ==========================================
# Cần đăng nhập bằng tài khoản role='admin' (tạo bằng scripts/make_admin.py).
# Không trả wss đầy đủ (token là credential) — luôn mask qua _mask_wss.


@app.get("/adminctrl", response_class=HTMLResponse)
async def serve_admin(request: Request):
    # Trang tự nạp dữ liệu qua /api/admin/* (đã chặn theo role). Chưa đăng nhập
    # admin thì chuyển sang /login thay vì trả 403 trơ trọi.
    acc = await auth.current_account(request)
    if acc is None or acc["role"] != "admin":
        return RedirectResponse(url="/login?next=/adminctrl", status_code=302)
    with open(ROOT / "static" / "admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.head("/adminctrl")
async def serve_admin_head():
    return Response()


def _runtime_by_endpoint() -> dict:
    """endpoint_key → info kết nối in-memory (outbound_connections keyed theo url)."""
    out = {}
    for url, info in state.outbound_connections.items():
        out[db.endpoint_key_for(url)] = info
    return out


async def _owner_emails(account_ids: list) -> dict:
    """account_id → email, để trang admin hiện thiết bị thuộc về ai."""
    ids = [a for a in {str(x) for x in account_ids if x}]
    if not ids or state.db_pool is None:
        return {}
    try:
        async with state.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT account_id, email FROM tools.accounts WHERE account_id = ANY($1::uuid[])",
                ids)
        return {str(r["account_id"]): r["email"] for r in rows}
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return {}
    except Exception:
        state.logger.exception("❌ [ADMIN] Lỗi đọc email chủ thiết bị:")
        return {}


@app.get("/api/admin/devices")
async def admin_list_devices(request: Request):
    """Danh sách thiết bị đã đăng ký + trạng thái kết nối + số quyền đã mở."""
    await auth.require_admin(request)
    runtime = _runtime_by_endpoint()
    subs = await db.list_subscriptions()
    emails = await _owner_emails([s.get("account_id") for s in subs])
    devices = []
    for s in subs:
        key = s.get("endpoint_key") or db.endpoint_key_for(s["wss_url"])
        info = runtime.get(key, {})
        products, store_ready = await _products_for_endpoint(key)
        devices.append({
            "device_name": s["device_name"],
            "endpoint_key": key,
            "wss_masked": _mask_wss(s["wss_url"]),
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
            "status": info.get("status", "disconnected"),
            "tools_count": info.get("tools_count", 0),
            "error": info.get("error"),
            "owner_email": emails.get(str(s.get("account_id"))) if s.get("account_id") else None,
            "store_ready": store_ready,
            "unlocked_count": sum(1 for p in products if p["is_free"] or p["purchased"]),
            "purchased_count": sum(1 for p in products if p["purchased"]),
            "product_count": len(products),
        })
    return {"devices": devices, "registered_tools": len(state.mcp_tools_registry)}


@app.get("/api/admin/device")
async def admin_device_detail(request: Request, endpoint_key: str):
    """Chi tiết 1 thiết bị: tools đang được cấp + chức năng đã/chưa mở khoá.

    `endpoint_key` chứa dấu `/` nên nhận qua query param, không phải path param.
    """
    await auth.require_admin(request)
    subs = await db.list_subscriptions()
    sub = next(
        (s for s in subs
         if (s.get("endpoint_key") or db.endpoint_key_for(s["wss_url"])) == endpoint_key),
        None,
    )
    if sub is None:
        return {"success": False, "error": f"Không tìm thấy thiết bị '{endpoint_key}'"}

    info = _runtime_by_endpoint().get(endpoint_key, {})
    products, store_ready = await _products_for_endpoint(endpoint_key)
    emails = await _owner_emails([sub.get("account_id")])

    # Nội dung mua thêm gắn theo từng tool (products.tool) → hiện ngay trên thẻ tool.
    by_tool: dict[str, list] = {}
    for p in products:
        by_tool.setdefault(p["tool"], []).append(p)

    tools = []
    for t in mcp_outbound.build_tools_payload():
        gated = by_tool.get(t["name"], [])
        tools.append({
            "name": t["name"],
            "description": t["description"],
            "params": list((t["inputSchema"] or {}).get("properties", {})),
            "gated": bool(gated),
            "unlocked_refs": [p["ref"] for p in gated if p["is_free"] or p["purchased"]],
            "locked_refs": [p["ref"] for p in gated if not (p["is_free"] or p["purchased"])],
        })

    orders = []
    if state.db_pool is not None and store_ready:
        try:
            async with state.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT order_id, product_code, amount, status, momo_trans_id,
                           created_at, paid_at
                    FROM tools.orders
                    WHERE endpoint_key = $1
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    endpoint_key,
                )
            orders = [dict(r) for r in rows]
        except Exception:
            state.logger.exception("❌ [ADMIN] Lỗi đọc orders:")

    return {
        "success": True,
        "device": {
            "device_name": sub["device_name"],
            "endpoint_key": endpoint_key,
            "wss_masked": _mask_wss(sub["wss_url"]),
            "created_at": sub["created_at"].isoformat() if sub.get("created_at") else None,
            "status": info.get("status", "disconnected"),
            "tools_count": info.get("tools_count", 0),
            "error": info.get("error"),
            "owner_email": emails.get(str(sub.get("account_id"))) if sub.get("account_id") else None,
        },
        "store_ready": store_ready,
        "tools": tools,
        "products": [_product_public(p) for p in products],
        "orders": [
            {
                "order_id": o["order_id"],
                "product_code": o["product_code"],
                "amount": o["amount"],
                "status": o["status"],
                "momo_trans_id": o["momo_trans_id"],
                "created_at": o["created_at"].isoformat() if o["created_at"] else None,
                "paid_at": o["paid_at"].isoformat() if o["paid_at"] else None,
            }
            for o in orders
        ],
    }


@app.get("/api/mcp/status")
async def get_mcp_status():
    connections = [
        {"url": url, "device_name": info.get("device_name", ""),
         "status": info.get("status", "unknown"), "tools_count": info.get("tools_count", 0),
         "error": info.get("error")}
        for url, info in state.outbound_connections.items()
    ]
    return {
        "connections": connections,
        "registered_tools": [item["tool"].name for item in state.mcp_tools_registry]
    }


# ==========================================
# WEBSOCKET
# ==========================================
@app.websocket("/ws/robot/{user_id}")
async def robot_ws(websocket: WebSocket, user_id: str):
    await ws_handler.robot_endpoint(websocket, user_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "7860")),
        log_level="warning",
    )
