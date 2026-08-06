import json
import re
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types

from . import state
from . import db
from . import audio

logger = state.logger


async def _safe_send_message(chat, payload, websocket: WebSocket, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return await chat.send_message(payload)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 15.0
                m = re.search(r'retry in ([\d\.]+)s', err)
                if m:
                    wait = float(m.group(1)) + 2.0
                logger.warning(f"⏳ [LLM] Rate Limit. Ngủ {wait:.1f}s (lần {attempt + 1}/{max_retries})...")
                if attempt == 0:
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "text_response",
                            "message": "Câu hỏi này khó quá, chú Robot đang suy nghĩ, con đợi chú một tẹo nhé!"
                        }, ensure_ascii=False))
                    except Exception:
                        pass
                await asyncio.sleep(wait)
                if attempt == max_retries - 1:
                    raise Exception("Hệ thống AI đang quá tải, không thể thử lại.")
            else:
                logger.exception("❌ [LLM] Lỗi Gemini API:")
                raise e


async def robot_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    logger.info(f"🔌 [WS] Robot (User ID: {user_id}) đã kết nối.")
    session_id = None

    try:
        session_id = await db.create_chat_session(user_id)
        user_profile = await db.get_user_profile(user_id)

        # Xây dựng danh sách tools cho Gemini
        all_gemini_tools = [state.preference_tool]
        dynamic_funcs = [
            types.FunctionDeclaration(
                name=item["tool"].name,
                description=item["tool"].description,
                parameters=state.json_schema_to_gemini(item["tool"].inputSchema)
            )
            for item in state.mcp_tools_registry
        ]
        if dynamic_funcs:
            all_gemini_tools.append(types.Tool(function_declarations=dynamic_funcs))

        base_prompt = (
            "Bạn là chú Robot thông minh, vui vẻ và thân thiện đang nói chuyện với trẻ em. "
            "Hãy trả lời ngắn gọn, xưng là 'Chú Robot'. "
            "Nếu trẻ hỏi thông tin mà bạn không biết hoặc công cụ không tìm ra, tuyệt đối không nói dối. "
            "Hãy xin lỗi khéo léo, thừa nhận chưa biết và lái bé sang chủ đề khác vui hơn. "
            "QUAN TRỌNG: Với bất kỳ câu hỏi nào về sự kiện thực tế, tin tức, kết quả, điểm số thể thao, "
            "giải đấu, tỷ số, bảng xếp hạng, hay thông tin có thể thay đổi theo thời gian → "
            "LUÔN gọi google_search trước khi trả lời, NGAY CẢ KHI bạn nghĩ mình đã biết câu trả lời. "
            "Tuyệt đối không tự suy đoán hay trả lời từ kiến thức huấn luyện cho các câu hỏi thực tế."
        )
        if user_profile:
            name = user_profile.get("full_name", "bé")
            age = user_profile.get("age", "không rõ")
            prefs = user_profile.get("preferences", "{}")
            logger.info(f"👤 [USER] Profile: {name} ({age} tuổi)")
            system_instruction = (base_prompt +
                f" Bạn đang nói chuyện với bé tên {name}, {age} tuổi. Sở thích: {prefs}. Gọi bé là '{name}' hoặc 'con'.")
        else:
            logger.info("👤 [USER] Khách ẩn danh kết nối.")
            system_instruction = base_prompt + " Bé mới kết nối, hãy hỏi thăm để làm quen!"

        chat = state.gemini_client.aio.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                temperature=0.7,
                system_instruction=system_instruction,
                tools=all_gemini_tools
            )
        )

        while True:
            message = await websocket.receive()
            payload = ""

            if "text" in message:
                payload = message["text"]
                logger.info(f"⌨️ [WS] Text: {payload}")
            elif "bytes" in message:
                payload = await audio.audio_to_text(message["bytes"])
                logger.info(f"📝 [STT] Kết quả: {payload}")

            if not payload or payload == "Chú Robot không nghe rõ con nói gì.":
                await websocket.send_text(
                    json.dumps({"type": "text_response", "message": "Con nói to lên một chút nhé!"}))
                continue

            await db.save_chat_history(session_id, "user", payload)

            try:
                response = await _safe_send_message(chat, payload, websocket)
            except Exception:
                await websocket.send_text(json.dumps({
                    "type": "text_response",
                    "message": "Hệ thống AI đang quá tải, con hỏi lại sau nhé!"
                }, ensure_ascii=False))
                continue

            ai_text = response.text
            search_handled = False

            if response.function_calls:
                for tool_call in response.function_calls:
                    logger.info(f"⚙️ [LLM] Gọi tool: {tool_call.name}")
                    args = dict(tool_call.args) if tool_call.args else {}

                    if tool_call.name == "update_preferences":
                        status = await db.update_user_preferences(
                            user_id, args.get("category"), args.get("value"))
                        part = types.Part.from_function_response(
                            name="update_preferences", response={"status": status})
                        ai_text = (await _safe_send_message(chat, part, websocket)).text
                        continue

                    server_name = next(
                        (item["server"] for item in state.mcp_tools_registry
                         if item["tool"].name == tool_call.name), None)

                    if server_name and server_name in state.mcp_sessions:
                        try:
                            logger.info(f"🚀 [MCP] Chuyển tiếp tới {server_name}...")
                            mcp_result = await state.mcp_sessions[server_name].call_tool(
                                tool_call.name, arguments=args)
                            texts = [c.text for c in mcp_result.content if c.type == "text"]
                            calc_result = "\n".join(texts) if len(texts) > 1 else texts[0]
                            try:
                                calc_result = json.loads(calc_result)
                            except Exception:
                                pass
                            logger.info(f"✅ [MCP] Kết quả từ {server_name}: {str(calc_result)[:100]}")
                        except Exception as e:
                            logger.exception(f"❌ [MCP] Lỗi tool '{tool_call.name}':")
                            calc_result = f"Lỗi: {e}"

                        if tool_call.name == "google_search":
                            await websocket.send_text(
                                json.dumps({"success": True, "result": calc_result}, ensure_ascii=False))
                            search_handled = True
                            continue

                        part = types.Part.from_function_response(
                            name=tool_call.name, response={"result": calc_result})
                        ai_text = (await _safe_send_message(chat, part, websocket)).text
                    else:
                        logger.warning(f"⚠️ [MCP] Tool chưa đăng ký: {tool_call.name}")

            if search_handled:
                continue

            ai_text = str(ai_text or "").strip()
            if not ai_text:
                ai_text = "Xin lỗi con, chú Robot chưa biết trả lời câu này. Con hỏi chú chuyện khác vui hơn nhé!"

            logger.info(f"🤖 [LLM] Trả lời: {ai_text}")
            await db.save_chat_history(session_id, "robot", ai_text)
            await websocket.send_text(
                json.dumps({"type": "text_response", "message": ai_text}, ensure_ascii=False))

            audio_bytes = await audio.text_to_audio_bytes(ai_text)
            if audio_bytes:
                await websocket.send_bytes(audio_bytes)
                logger.debug("🔊 [WS] Đã gửi Audio xuống Robot.")

    except WebSocketDisconnect:
        logger.info(f"🔌 [WS] User {user_id} đã ngắt kết nối.")
        if session_id and state.db_pool:
            async with state.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE chat_sessions SET is_active = FALSE WHERE session_id = $1", session_id)
    except Exception:
        logger.exception("❌ [WS] Crash luồng WebSocket:")