import json
import time
import asyncio
from . import db
from . import state

logger = state.logger

# Tham số định danh thiết bị được TIÊM vào arguments phía server, không phải do
# LLM cung cấp. combined_server.py là subprocess dùng chung mọi thiết bị nên tool
# không tự biết ai gọi; chỉ worker outbound biết `url` của chính nó.
# Tool nào cần định danh thì khai báo param `endpoint_key` trong signature —
# build_tools_payload() sẽ ẩn nó khỏi tools/list để LLM không thấy/bịa giá trị.
INJECTED_ARG = "endpoint_key"


def _strip_injected(schema: dict) -> dict:
    """Bỏ INJECTED_ARG khỏi inputSchema (copy, không sửa registry)."""
    props = (schema or {}).get("properties") or {}
    if INJECTED_ARG not in props:
        return schema
    clean = dict(schema)
    clean["properties"] = {k: v for k, v in props.items() if k != INJECTED_ARG}
    if isinstance(clean.get("required"), list):
        clean["required"] = [r for r in clean["required"] if r != INJECTED_ARG]
    return clean


def _tool_wants_injection(tool_name: str) -> bool:
    for item in state.mcp_tools_registry:
        t = item["tool"]
        if t.name == tool_name:
            return INJECTED_ARG in ((t.inputSchema or {}).get("properties") or {})
    return False


def build_tools_payload() -> list:
    result = []
    for item in state.mcp_tools_registry:
        t = item["tool"]
        schema = t.inputSchema if t.inputSchema else {"type": "object", "properties": {}}
        result.append({
            "name": t.name,
            "description": t.description or "",
            "inputSchema": _strip_injected(schema),
        })
    return result


async def call_tool_by_name(tool_name: str, arguments: dict) -> str:
    server_name = next(
        (item["server"] for item in state.mcp_tools_registry if item["tool"].name == tool_name), None
    )
    if not server_name or server_name not in state.mcp_sessions:
        return f"Tool '{tool_name}' not found"
    try:
        result = await state.mcp_sessions[server_name].call_tool(tool_name, arguments=arguments)
        texts = [c.text for c in result.content if hasattr(c, "text")]
        return "\n".join(texts) if texts else "OK"
    except Exception as e:
        logger.exception(f"❌ [OUTBOUND] Lỗi tool '{tool_name}':")
        return f"Error: {e}"


async def _dispatch_tool_call(ws, msg_id, tool_name: str, tool_args: dict, url: str = ""):
    """Thực thi tool trong background — không block vòng recv chính.

    Tiêm `endpoint_key` (định danh thiết bị, suy từ JWT trong `url`) cho những
    tool có khai báo param đó — dùng để kiểm tra quyền nội dung đã mua.
    """
    try:
        if url and _tool_wants_injection(tool_name):
            endpoint_key = db.endpoint_key_for(url)
            tool_args = {**tool_args, INJECTED_ARG: endpoint_key}
            logger.info(f"🔑 [OUTBOUND] Tiêm endpoint_key='{endpoint_key}' cho '{tool_name}'")
        result_text = await call_tool_by_name(tool_name, tool_args)
        logger.info(f"✅ [OUTBOUND] Tool '{tool_name}' xong: {str(result_text)[:80]}")
        try:
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": result_text}]}
            }))
        except Exception as send_err:
            logger.info(f"🔄 [OUTBOUND] Session đóng trước khi gửi kết quả '{tool_name}' (broker reconnect)")
    except Exception as e:
        logger.warning(f"⚠️ [OUTBOUND] Lỗi thực thi tool '{tool_name}': {e}")
        try:
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32603, "message": str(e)}
            }))
        except Exception:
            pass


async def mcp_outbound_worker(url: str, device_name: str):
    import websockets as _ws
    headers = {
        "Origin": "https://xiaozhi.ai",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    while True:
        info = state.outbound_connections.get(url)
        if not info:
            break
        info["status"] = "connecting"
        info["error"] = None
        try:
            logger.info(f"🔌 [OUTBOUND] Kết nối broker: {url[:70]}...")
            async with _ws.connect(
                url, open_timeout=20, additional_headers=headers,
                ping_interval=None
            ) as ws:
                info["status"] = "connected"
                logger.info("✅ [OUTBOUND] Kết nối broker thành công")

                raw = await asyncio.wait_for(ws.recv(), timeout=15)
                server_msg = json.loads(raw)
                logger.info(f"   [OUTBOUND] Broker initialize: {str(server_msg)[:150]}")

                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": server_msg.get("id", 0),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": device_name or "ai-robot-server", "version": "1.0"}
                    }
                }))
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))

                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=20)
                    except asyncio.TimeoutError:
                        try:
                            await ws.send(json.dumps({
                                "jsonrpc": "2.0",
                                "id": int(time.time() * 1000) % 0x7FFFFFFF,
                                "method": "ping"
                            }))
                        except Exception:
                            break
                        continue

                    msg = json.loads(raw)
                    method = msg.get("method")
                    msg_id = msg.get("id")

                    if method == "ping":
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0", "id": msg_id,
                            "result": {}
                        }))

                    elif method == "tools/list":
                        tools = build_tools_payload()
                        info["tools_count"] = len(tools)
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0", "id": msg_id,
                            "result": {"tools": tools}
                        }))
                        logger.info(f"📋 [OUTBOUND] Đăng ký {len(tools)} tools với broker")

                    elif method == "tools/call":
                        params = msg.get("params", {})
                        tool_name = params.get("name", "")
                        tool_args = params.get("arguments", {})
                        logger.info(f"⚙️ [OUTBOUND] Broker gọi tool: {tool_name}, args: {json.dumps(tool_args, ensure_ascii=False)}")
                        asyncio.create_task(_dispatch_tool_call(ws, msg_id, tool_name, tool_args, url))

                    elif method and method.startswith("notifications/"):
                        pass

                    elif msg_id is not None and method:
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0", "id": msg_id,
                            "error": {"code": -32601, "message": f"Method not found: {method}"}
                        }))

        except asyncio.CancelledError:
            logger.info(f"🛑 [OUTBOUND] Worker dừng: {url[:60]}")
            break
        except Exception as e:
            info = state.outbound_connections.get(url)
            if not info:
                break
            info["status"] = "reconnecting"
            info["error"] = str(e)
            logger.info(f"🔄 [OUTBOUND] Session kết thúc ({type(e).__name__}). Kết nối lại sau 1s...")
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break

    if url in state.outbound_connections:
        state.outbound_connections[url]["status"] = "disconnected"