import os
import json
import io
import asyncio
import requests
import queue
import threading
from typing import Dict, Any, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

from core.agent import (
    init_agent,
    RollingMemory,
    queue_debug_event,
    queue_maybe_notify_arun,
    run_pre_escalation,
    queue_chat_history_to_telegram,
    queue_automated_chat_alert,
    generate_admin_token,
    verify_admin_token,
)

HUMAN_MESSAGES_STORE: Dict[str, List[Dict[str, Any]]] = {}
SESSION_CHAT_STORE: Dict[str, List[Dict[str, Any]]] = {}
HUMAN_CONTROL_SESSIONS: Dict[str, bool] = {}

def record_session_message(session_id: str, sender: str, text: str, name: str = "", thoughts: Optional[List[str]] = None) -> Dict[str, Any]:
    import time, datetime
    now_str = datetime.datetime.now().strftime("%I:%M %p")
    entry = {
        "id": f"msg_{sender}_{int(time.time() * 1000)}_{len(SESSION_CHAT_STORE.get(session_id, []))}",
        "sender": sender,
        "name": name or ("Arun Yadav" if sender == "human_arun" else "Arun's AI Assistant" if sender == "twin" else "You"),
        "text": text,
        "timestamp": now_str,
    }
    if thoughts:
        entry["thoughts"] = thoughts

    if session_id not in SESSION_CHAT_STORE:
        SESSION_CHAT_STORE[session_id] = []
    SESSION_CHAT_STORE[session_id].append(entry)
    return entry

_GLOBAL_VECTORSTORE = None
_GLOBAL_BM25 = None
_GLOBAL_COMPRESSOR = None

_task_queue = queue.Queue()


def _background_worker():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    while True:
        try:
            task = _task_queue.get()
            if task is None:
                break
            func, args, kwargs = task
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(f"[BACKGROUND WORKER ERROR] Failed in {func.__name__}: {e}")
            finally:
                _task_queue.task_done()
        except Exception as outer_e:
            print(f"[BACKGROUND WORKER FATAL] Queue fetch failed: {outer_e}")


worker_thread = threading.Thread(target=_background_worker, daemon=True)
worker_thread.start()


def _submit_background_task(name: str, func, *args, **kwargs) -> bool:
    try:
        _task_queue.put((func, args, kwargs))
        print(f"[BACKGROUND] {name}: Task queued.")
        return True
    except Exception as e:
        print(f"[BACKGROUND ERROR] Failed to queue {name}: {e}")
        return False


def load_static_context() -> Tuple[str, str]:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    profile_path = os.path.join(base_dir, "data", "static", "public_profile.md")
    rules_path = os.path.join(base_dir, "data", "static", "rules_of_engagement.md")

    profile_content = ""
    rules_content = ""

    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_content = f.read()

    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_content = f.read()

    return profile_content, rules_content


def _safe_truncate(text: str, limit: int = 1500) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."


def _is_truthy_env(val: Optional[str], default: bool = True) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _is_telegram_debug_enabled() -> bool:
    return _is_truthy_env(os.getenv("TELEGRAM_DEBUG_ENABLED"), default=True)


def _get_telegram_target(debug: bool = False, alert: bool = False) -> Tuple[Optional[str], Optional[str]]:
    if alert:
        token = os.getenv("TELEGRAM_ALERT_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_ALERT_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        return token, chat_id
    if debug:
        token = os.getenv("TELEGRAM_DEBUG_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_DEBUG_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        return token, chat_id

    return os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")


def _chunk_text(text: str, limit: int = 2200) -> List[str]:
    cleaned = (text or "").strip() or "(empty)"
    parts: List[str] = []
    remaining = cleaned

    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < int(limit * 0.5):
            split_at = remaining.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit

        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        parts.append(remaining)

    return parts or ["(empty)"]


def _send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    max_attempts: int = 3,
    delivery_label: str = "default",
    retry_sleep_seconds: float = 1.0,
) -> str:
    import urllib.request
    import urllib.parse
    import ssl

    token = (token or "").strip()
    if token.lower().startswith("bot"):
        token = token[3:].strip()

    chat_id = (chat_id or "").strip()

    if not token or not chat_id:
        msg = f"FAILED: Token or Chat ID empty (token_len={len(token)}, chat_id_len={len(chat_id)})"
        print(f"[TELEGRAM:{delivery_label}] {msg}")
        return msg

    chunks = _chunk_text(text)
    total_chunks = len(chunks)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    for idx, chunk in enumerate(chunks, 1):
        payload: Dict[str, Any] = {
            "token": token,
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        sent_chunk = False
        last_error = ""

        # Attempt 1: Try Vercel Serverless Relay (bypasses HF Space Telegram firewall block)
        relay_url = "https://aruncore.vercel.app/api/telegram"
        try:
            relay_data = json.dumps(payload).encode("utf-8")
            relay_req = urllib.request.Request(
                relay_url,
                data=relay_data,
                headers={"Content-Type": "application/json", "User-Agent": "ArunCore/1.0", "Connection": "close"},
            )
            with urllib.request.urlopen(relay_req, timeout=8, context=ssl_ctx) as resp:
                resp_bytes = resp.read()
                resp_data = json.loads(resp_bytes.decode("utf-8"))
                if resp.status == 200 and resp_data.get("ok"):
                    sent_chunk = True
        except Exception as e:
            last_error = f"Vercel Relay error: {e}"

        if not sent_chunk:
            # Direct Telegram API Fallback
            for attempt in range(1, max_attempts + 1):
                try:
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    direct_payload = {
                        "chat_id": chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                    }
                    if parse_mode:
                        direct_payload["parse_mode"] = parse_mode

                    data = json.dumps(direct_payload).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=data,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "ArunCore/1.0",
                            "Connection": "close",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
                        resp_bytes = resp.read()
                        resp_data = json.loads(resp_bytes.decode("utf-8"))
                        if resp.status == 200 and resp_data.get("ok"):
                            sent_chunk = True
                            break
                        else:
                            last_error = f"HTTP {resp.status}: {resp_bytes.decode('utf-8')[:200]}"
                except Exception as e:
                    last_error = str(e)

                if attempt < max_attempts:
                    import time
                    time.sleep(retry_sleep_seconds)

        if not sent_chunk and parse_mode == "HTML":
            fallback_payload = {
                "chat_id": chat_id,
                "text": f"[{delivery_label}] (Plain Text Fallback {idx}/{total_chunks})\n{chunk}",
                "disable_web_page_preview": True,
            }
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = json.dumps(fallback_payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "ArunCore/1.0",
                        "Connection": "close",
                    },
                )
                with urllib.request.urlopen(req, timeout=12, context=ssl_ctx) as resp:
                    resp_bytes = resp.read()
                    resp_data = json.loads(resp_bytes.decode("utf-8"))
                    if resp.status == 200 and resp_data.get("ok"):
                        sent_chunk = True
            except Exception as e:
                last_error = f"Fallback error: {e}"

        if not sent_chunk:
            err_msg = f"FAILED chunk {idx}/{total_chunks}: {last_error}"
            print(f"[TELEGRAM:{delivery_label}] {err_msg}")
            return err_msg

    print(f"[TELEGRAM:{delivery_label}] SUCCESS")
    return "SUCCESS: message delivered."


# Initialize the ArunCore Engine
try:
    print("Initializing ArunCore API Backend...")
    main_llm, prompt, default_memory, tools = init_agent()

    global_tool_map = {t.name: t for t in tools}

    print("API Backend Initialized Successfully.")
except Exception as e:
    print(f"Failed to initialize backend: {e}")
    raise e

app = FastAPI(title="ArunCore API", description="Stateful Agentic Backend for Arun Yadav's Digital Twin.")

# Enable CORS for external frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === SESSION MANAGEMENT ===
active_sessions: Dict[str, RollingMemory] = {}


class ChatRequest(BaseModel):
    session_id: str
    message: str
    tutor_id: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "alloy"


@app.get("/api/config")
@app.get("/config")
async def get_tutor_config_endpoint(tutor: Optional[str] = None):
    from core.agent import load_tutor_config
    cfg = load_tutor_config(tutor)
    if not cfg:
        return {"tutor_id": tutor or "arun", "config": None}
    return cfg


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    if req.session_id not in active_sessions:
        summary_llm = ChatOpenAI(temperature=0.0, model="gpt-4.1-nano", api_key=os.getenv("OPENAI_API_KEY"))
        active_sessions[req.session_id] = RollingMemory(summary_llm=summary_llm)

    memory = active_sessions[req.session_id]
    record_session_message(req.session_id, "user", req.message)

    if HUMAN_CONTROL_SESSIONS.get(req.session_id, False):
        queue_automated_chat_alert(
            session_id=req.session_id,
            user_input=req.message,
            assistant_response="[Real Arun is currently in live control of this chat session. AI Twin paused.]",
        )

        async def generate_human_controlled_pause():
            yield json.dumps({"type": "status", "content": "🟢 Real Arun is in control of this session. AI Twin paused. Waiting for Real Arun or /answer command..."}) + "\n"
            yield json.dumps({
                "type": "final",
                "reply": "",
                "thoughts": ["Real Arun in live control. AI Twin paused."],
                "session_id": req.session_id,
            }) + "\n"

        return StreamingResponse(generate_human_controlled_pause(), media_type="application/x-ndjson")

    async def generate_response():
        thoughts = []
        try:
            queue_debug_event(
                "user_message",
                req.message,
                {"channel": "api", "session_id": req.session_id, "tutor_id": req.tutor_id},
            )

            session_llm, session_prompt, _, _ = init_agent(tutor_id=req.tutor_id)

            yield json.dumps({"type": "status", "content": "Analyzing request & retrieving context..."}) + "\n"
            thoughts.append("Analyzing request & retrieving context...")

            pre_escalation = run_pre_escalation(req.message, global_tool_map)
            if pre_escalation and pre_escalation.get("escalate"):
                yield json.dumps({"type": "status", "content": "Triggering instant Telegram alert..."}) + "\n"
                thoughts.append("Triggering instant Telegram alert...")
                queue_maybe_notify_arun(
                    user_input=req.message,
                    reason=pre_escalation.get("reason"),
                    channel="api",
                    session_id=req.session_id,
                )

            scratchpad = []
            max_iterations = 5
            iterations = 0
            max_search_limit = 3
            search_count = 0
            final_response = ""
            executed_tools = []
            retrieved_chunks = []
            github_data = []

            while iterations < max_iterations:
                messages = session_prompt.format_messages(
                    running_summary=memory.running_summary,
                    chat_history=memory.get_messages(),
                    input=req.message,
                    agent_scratchpad=scratchpad,
                )

                # Inject dynamic Real Human Presence notice if Real Human is active in this session
                arun_human_msgs = [m for m in SESSION_CHAT_STORE.get(req.session_id, []) if m.get("sender") == "human_arun"]
                if arun_human_msgs:
                    formatted_arun_msgs = "\n".join([f"• Real Human Instructor (👨‍💻): \"{m.get('text')}\"" for m in arun_human_msgs])
                    live_notice = SystemMessage(content=(
                        f"🟢 CRITICAL LIVE 3-WAY CHAT NOTICE (REAL HUMAN INSTRUCTOR IS PRESENT):\n"
                        f"The REAL HUMAN INSTRUCTOR (👨‍💻) HAS JOINED THIS CHAT ROOM LIVE AND IS CURRENTLY CHATTING!\n\n"
                        f"REAL INSTRUCTOR'S MESSAGES IN THIS SESSION:\n{formatted_arun_msgs}\n\n"
                        f"MANDATORY INSTRUCTIONS FOR AI ASSISTANT IN THIS 3-WAY CHAT:\n"
                        f"1. Acknowledge that the REAL human instructor is present right next to you in this chat session!\n"
                        f"2. If the user asks how the instructor came here or questions about their arrival, explain enthusiastically: \"The real instructor tapped their 1-Click Telegram link and joined our chat live from their phone! So both of us (Real Instructor + AI Assistant) are here together with you!\"\n"
                        f"3. Never confuse yourself as the human — you are the AI Assistant co-piloting alongside the Real Instructor!"
                    ))
                    if len(messages) > 1:
                        messages.insert(1, live_notice)
                    else:
                        messages.append(live_notice)

                ai_msg = await asyncio.to_thread(session_llm.invoke, messages)

                if ai_msg.tool_calls:
                    scratchpad.append(ai_msg)
                    for tc in ai_msg.tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc.get("args", {})

                        status_msg = "Searching Arun's knowledge base..." if tool_name == "search_arun_knowledge" else \
                                     "Sending notification to Arun..." if tool_name == "notify_arun" else \
                                     f"Executing {tool_name}..."

                        yield json.dumps({"type": "status", "content": status_msg}) + "\n"
                        thoughts.append(status_msg)
                        executed_tools.append(f"{tool_name}({tool_args})")

                        if tool_name == "search_arun_knowledge":
                            search_count += 1

                        if search_count > max_search_limit:
                            tool_result = f"Search limit reached ({max_search_limit}). Finalizing based on existing context."
                        else:
                            tool_func = global_tool_map.get(tool_name)
                            tool_result = await asyncio.to_thread(tool_func.invoke, tool_args)

                        if tool_name == "search_arun_knowledge" and tool_result:
                            retrieved_chunks.append(str(tool_result)[:1000])
                        elif tool_name == "get_github_live_data" and tool_result:
                            github_data.append(str(tool_result)[:1000])

                        scratchpad.append({
                            "role": "tool",
                            "name": tool_name,
                            "tool_call_id": tc["id"],
                            "content": str(tool_result)[:2000],
                        })
                    iterations += 1
                else:
                    yield json.dumps({"type": "status", "content": "Synthesizing final response..."}) + "\n"
                    thoughts.append("Synthesizing final response...")

                    full_reply = ""
                    for chunk in session_llm.stream(messages):
                        if chunk.content:
                            full_reply += chunk.content
                            yield json.dumps({"type": "token", "content": chunk.content}) + "\n"
                            await asyncio.sleep(0.005)

                    final_response = full_reply
                    break

            if not final_response:
                final_response = "I encountered a processing limit. How else can I help?"

            memory.add_interaction(req.message, final_response)
            record_session_message(req.session_id, "twin", final_response, thoughts=thoughts)

            queue_chat_history_to_telegram(
                session_id=req.session_id,
                user_input=req.message,
                assistant_response=final_response,
                thoughts=thoughts,
                tool_calls=executed_tools,
                retrieved_chunks=retrieved_chunks,
                github_data=github_data,
            )

            # Unconditionally queue 100% automated chat alert for EVERY message with 1-Click Join Link
            queue_automated_chat_alert(
                session_id=req.session_id,
                user_input=req.message,
                assistant_response=final_response,
            )

            yield json.dumps({
                "type": "final",
                "reply": final_response,
                "thoughts": thoughts,
                "session_id": req.session_id,
            }) + "\n"

        except Exception as err:
            err_msg = f"API Error: {str(err)}"
            yield json.dumps({"type": "error", "content": err_msg}) + "\n"

    return StreamingResponse(generate_response(), media_type="application/x-ndjson")


@app.post("/tts")
async def tts_endpoint(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing.")

        clean_snippet = (
            req.text
            .replace("*", "")
            .replace("#", "")
            .replace("`", "")
            .replace("\n", " ")
            [:1000]
        )

        res = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": clean_snippet,
                "voice": req.voice or "alloy",
            },
            timeout=10,
        )

        if res.status_code == 200:
            return StreamingResponse(io.BytesIO(res.content), media_type="audio/mpeg")
        else:
            raise HTTPException(status_code=res.status_code, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health_check():
    from core.agent import TELEGRAM_DELIVERY_LOGS
    alert_tok = os.getenv("TELEGRAM_ALERT_BOT_TOKEN", "")
    bot_tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    alert_cid = os.getenv("TELEGRAM_ALERT_CHAT_ID", "")
    bot_cid = os.getenv("TELEGRAM_CHAT_ID", "")

    return {
        "status": "online",
        "active_sessions": len(active_sessions),
        "telegram_alert_bot_preview": f"{alert_tok[:6]}...{alert_tok[-4:]}" if alert_tok else "MISSING",
        "telegram_alert_chat_id": alert_cid or "MISSING",
        "telegram_bot_preview": f"{bot_tok[:6]}...{bot_tok[-4:]}" if bot_tok else "MISSING",
        "telegram_chat_id": bot_cid or "MISSING",
        "telegram_logs": TELEGRAM_DELIVERY_LOGS[-10:],
    }


class HumanMessageRequest(BaseModel):
    session_id: str
    admin_token: str
    message: str

async def trigger_ai_answer(session_id: str, extra_prompt: str = "") -> str:
    if session_id not in active_sessions:
        summary_llm = ChatOpenAI(temperature=0.0, model="gpt-4.1-nano", api_key=os.getenv("OPENAI_API_KEY"))
        active_sessions[session_id] = RollingMemory(summary_llm=summary_llm)

    memory = active_sessions[session_id]
    main_llm, prompt, _, _ = init_agent()

    session_msgs = SESSION_CHAT_STORE.get(session_id, [])
    transcript_lines = []
    last_user_input = ""
    for m in session_msgs:
        sender_label = "Visitor" if m.get("sender") == "user" else "Real Arun Yadav (👨‍💻)" if m.get("sender") == "human_arun" else "Arun's AI Assistant"
        transcript_lines.append(f"{sender_label}: {m.get('text')}")
        if m.get("sender") == "user":
            last_user_input = m.get("text")

    full_transcript = "\n".join(transcript_lines)

    system_notice = SystemMessage(content=(
        f"🟢 3-WAY CHAT INSTRUCTION FOR AI TWIN:\n"
        f"Real Arun Yadav issued the /answer command for you to respond to the visitor's question.\n"
        f"Read the full 3-party conversation transcript below (Visitor, Real Arun Yadav, and AI Twin):\n\n"
        f"--- FULL 3-WAY CHAT TRANSCRIPT ---\n{full_transcript}\n\n"
        f"MANDATORY INSTRUCTIONS FOR AI TWIN:\n"
        f"1. Synthesize all context from the visitor's question and Real Arun Yadav's live comments.\n"
        f"2. Generate an accurate, helpful, and natural response for the visitor.\n"
        f"3. Acknowledge Real Arun Yadav's live presence if relevant."
    ))

    messages = prompt.format_messages(
        running_summary=memory.running_summary,
        chat_history=memory.get_messages(),
        input=extra_prompt or last_user_input or "Please answer the visitor's question based on our 3-way conversation.",
        agent_scratchpad=[],
    )
    messages.insert(1, system_notice)

    ai_msg = await asyncio.to_thread(main_llm.invoke, messages)
    final_reply = ai_msg.content.strip()

    if final_reply:
        record_session_message(session_id, "twin", final_reply, thoughts=["AI Twin triggered via /answer command."])
        memory.add_interaction(last_user_input or "Visitor Query", final_reply)

    return final_reply


@app.post("/chat/human-message")
async def post_human_message(req: HumanMessageRequest):
    if not verify_admin_token(req.session_id, req.admin_token):
        raise HTTPException(status_code=403, detail="Invalid admin token.")
    
    clean_text = (req.message or "").strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    lowered = clean_text.lower().strip()

    # Command: /release or /resume -> Hand control back to AI Twin
    if lowered in ("/release", "/resume"):
        HUMAN_CONTROL_SESSIONS[req.session_id] = False
        rel_entry = record_session_message(req.session_id, "human_arun", "[Handed back auto-response control to AI Twin]", name="Arun Yadav")
        return {"status": "success", "entry": rel_entry, "human_control": False}

    # Command: /answer -> Trigger AI Twin to answer reading all 3 participants' chat history
    if lowered.startswith("/answer"):
        HUMAN_CONTROL_SESSIONS[req.session_id] = True
        extra_prompt = clean_text[7:].strip()
        cmd_entry = record_session_message(req.session_id, "human_arun", f"/answer {extra_prompt}".strip(), name="Arun Yadav")
        ai_reply = await trigger_ai_answer(req.session_id, extra_prompt)
        return {"status": "success", "entry": cmd_entry, "ai_reply": ai_reply, "human_control": True}

    # Real Arun's first human message activates Human Control Mode!
    HUMAN_CONTROL_SESSIONS[req.session_id] = True
    entry = record_session_message(req.session_id, "human_arun", clean_text, name="Arun Yadav")
    if req.session_id not in HUMAN_MESSAGES_STORE:
        HUMAN_MESSAGES_STORE[req.session_id] = []
    HUMAN_MESSAGES_STORE[req.session_id].append(entry)

    # Extract last user message to pair with Real Arun's answer for RAG vector DB ingestion
    last_user_msg = ""
    session_history = SESSION_CHAT_STORE.get(req.session_id, [])
    for m in reversed(session_history):
        if m.get("sender") == "user":
            last_user_msg = m.get("text", "")
            break

    if last_user_msg:
        try:
            from core.agent import save_unknown_question_answer
            save_unknown_question_answer(last_user_msg, clean_text)
            print(f"[RAG AUTO-UPDATE] Saved Q&A pair to unknown_questions.json & triggered ChromaDB re-ingestion.")
        except Exception as e:
            print(f"[RAG AUTO-UPDATE ERROR] Failed to auto-ingest admin answer: {e}")

    memory = get_or_create_memory(req.session_id)
    memory.add_interaction(f"[REAL ARUN JOINED LIVE]: {clean_text}", "Acknowledged real Arun input.")

    return {"status": "success", "entry": entry, "human_control": True}


@app.get("/chat/history")
async def get_chat_history(session_id: str):
    msgs = SESSION_CHAT_STORE.get(session_id, [])
    return {"session_id": session_id, "messages": msgs}


@app.get("/chat/human-messages")
async def get_human_messages(session_id: str):
    msgs = HUMAN_MESSAGES_STORE.get(session_id, [])
    return {"session_id": session_id, "messages": msgs}


@app.get("/chat/verify-admin-token")
async def verify_admin(session_id: str, admin_token: str):
    valid = verify_admin_token(session_id, admin_token)
    return {"valid": valid, "session_id": session_id}


# Mount static frontend export if built (for Hugging Face Spaces production deployment)
frontend_out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "out")
if os.path.exists(frontend_out):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_out, html=True), name="static_frontend")
