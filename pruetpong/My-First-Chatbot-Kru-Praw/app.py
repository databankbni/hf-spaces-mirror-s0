# app.py — คุยกับพี่ในอนาคต (Talk with Your Future Self) (FastAPI v2.2)
# โรงเรียนสาธิต มหาวิทยาลัยศิลปากร (มัธยมศึกษา)
# แนวคิดได้แรงบันดาลใจหลักจากงานวิจัย "Future You" (Pataranutaporn et al., MIT Media Lab × KBTG, 2024)

# =========================================================
# SECTION 1: IMPORTS & LOGGING [DO NOT EDIT]
# =========================================================
import logging
import os
import re
import uuid
import json
from datetime import datetime
from typing import List, Optional

# from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
# load_dotenv()


# =========================================================
# SECTION 2: APP CONFIG [TEACHER-EDITABLE]
# แก้ไขได้: ตั้งค่าหลักของแอปพลิเคชัน
# =========================================================
APP_CONFIG = {
    "app_name": "คุยกับพี่ในอนาคต (Talk with Your Future Self)",
    "school_name": "โรงเรียนสาธิต มหาวิทยาลัยศิลปากร (มัธยมศึกษา)",
    # LLM Provider — รองรับ 2 รูปแบบ (ดู references/llm-integration.md, openai-native-api.md):
    #   openai_native     = เรียก api.openai.com โดยตรง ตรวจ tier จากชื่อโมเดลอัตโนมัติ
    #                        (legacy: gpt-4o/gpt-4o-mini/gpt-4.1 ใช้ temperature/max_tokens ปกติ
    #                         reasoning: gpt-5*/o-series ใช้ reasoning_effort/verbosity/
    #                         max_completion_tokens แทน — ส่ง temperature/max_tokens ไปจะ 400 error)
    #   openai_compatible = proxy อื่น ๆ (Typhoon/OpenRouter/DeepSeek/Together/Ollama ฯลฯ)
    #                        ใช้ temperature/max_tokens แบบเดิมเสมอ
    "llm_provider": os.getenv("LLM_PROVIDER", "openai_native"),
    # ตัวแปรใหม่ LLM_* เป็นหลัก — fallback ไปตัวแปรเดิม (API_MODEL/API_KEY/API_BASE_URL) ให้อัตโนมัติ
    # เพื่อไม่ให้ deployment เดิมบน HF Spaces พังตอน redeploy โค้ดใหม่นี้
    "model": os.getenv("LLM_MODEL", os.getenv("API_MODEL", "gpt-4o-mini")),
    "api_key": os.getenv("LLM_API_KEY", os.getenv("API_KEY", "")),
    "api_base_url": os.getenv("LLM_BASE_URL", os.getenv("API_BASE_URL", "https://api.openai.com/v1")),
    # มีผลเฉพาะเมื่อโมเดลเป็น reasoning tier (gpt-5*/o-series) บน openai_native เท่านั้น
    "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "low"),
    "verbosity": os.getenv("LLM_VERBOSITY", "low"),
    "max_completion_tokens": int(os.getenv("LLM_MAX_COMPLETION_TOKENS", "4096")),
    "max_history": 10,
    "default_temperature": 0.65,
    "default_max_tokens": 1600,
    "greeting_max_tokens": 1400,
    "greeting_temperature": 0.75,
    "suggestion_max_tokens": 800,
    "suggestion_temperature": 0.85,
    "summary_max_tokens": 1200,
    "summary_temperature": 0.5,
    "future_years_ahead": 10,
    "timeout_seconds": 60,
}


# =========================================================
# SECTION 3: STUDY PROGRAMS [TEACHER-EDITABLE]
# แก้ไขได้: รายการแผนการเรียนที่รองรับ
# =========================================================
STUDY_PROGRAMS = [
    "วิทยาศาสตร์-คณิตศาสตร์",
    "ภาษาอังกฤษ-คณิตศาสตร์",
    "ศิลปกรรมและการออกแบบ",
    "ภาษาอังกฤษ-ภาษาจีน",
    "ภาษาอังกฤษ-ภาษาญี่ปุ่น",
    "ภาษาอังกฤษ-ภาษาฝรั่งเศส",
]


# =========================================================
# SECTION 4: CAREER PATH DATA [TEACHER-EDITABLE]
# แก้ไขได้: ข้อมูลเส้นทางอาชีพแยกตามแผนการเรียน
# =========================================================
CAREER_PATH_DATA = {
    "วิทยาศาสตร์-คณิตศาสตร์": {
        "emoji": "🔬",
        "color_hex": "#3B82F6",
        "tag_bg": "#EFF6FF",
        "tag_text": "#1D4ED8",
        "university_majors": ["วิศวกรรมศาสตร์", "แพทยศาสตร์", "วิทยาการคอมพิวเตอร์", "วิทยาศาสตร์"],
        "careers": ["วิศวกร", "แพทย์", "นักวิทยาศาสตร์ข้อมูล", "นักพัฒนาซอฟต์แวร์"],
        "key_skills": ["คณิตศาสตร์ขั้นสูง", "ฟิสิกส์", "การเขียนโปรแกรม", "วิเคราะห์ข้อมูล"],
    },
    "ภาษาอังกฤษ-คณิตศาสตร์": {
        "emoji": "📊",
        "color_hex": "#10B981",
        "tag_bg": "#ECFDF5",
        "tag_text": "#065F46",
        "university_majors": ["บริหารธุรกิจ", "การบัญชี", "เศรษฐศาสตร์", "การเงินและการธนาคาร"],
        "careers": ["นักธุรกิจ", "นักการเงิน", "นักเศรษฐศาสตร์", "ที่ปรึกษาธุรกิจ"],
        "key_skills": ["ภาษาอังกฤษธุรกิจ", "วิเคราะห์ข้อมูล", "การสื่อสาร", "การจัดการ"],
    },
    "ศิลปกรรมและการออกแบบ": {
        "emoji": "🎨",
        "color_hex": "#F59E0B",
        "tag_bg": "#FFFBEB",
        "tag_text": "#92400E",
        "university_majors": ["ศิลปกรรมศาสตร์", "สถาปัตยกรรมศาสตร์", "ออกแบบนิเทศศิลป์", "มัลติมีเดีย"],
        "careers": ["นักออกแบบกราฟิก", "สถาปนิก", "ศิลปิน", "ผู้กำกับงานสร้างสรรค์"],
        "key_skills": ["ความคิดสร้างสรรค์", "Adobe Suite", "Portfolio", "Design Thinking"],
    },
    "ภาษาอังกฤษ-ภาษาจีน": {
        "emoji": "🌏",
        "color_hex": "#EF4444",
        "tag_bg": "#FEF2F2",
        "tag_text": "#991B1B",
        "university_majors": ["ภาษาจีนและวรรณคดี", "ธุรกิจระหว่างประเทศ", "การท่องเที่ยว", "การแปล"],
        "careers": ["ล่ามภาษาจีน", "ที่ปรึกษาธุรกิจ", "ผู้จัดการท่องเที่ยว", "นักการทูต"],
        "key_skills": ["ภาษาจีนกลาง", "HSK 4+", "ภาษาอังกฤษ", "วัฒนธรรมจีน"],
    },
    "ภาษาอังกฤษ-ภาษาญี่ปุ่น": {
        "emoji": "🗾",
        "color_hex": "#8B5CF6",
        "tag_bg": "#F5F3FF",
        "tag_text": "#5B21B6",
        "university_majors": ["ภาษาญี่ปุ่น", "ธุรกิจญี่ปุ่น-ไทย", "นิเทศศาสตร์", "การท่องเที่ยว"],
        "careers": ["ล่ามภาษาญี่ปุ่น", "ที่ปรึกษาบริษัทญี่ปุ่น", "ครูสอนภาษา", "ผู้จัดการโรงแรม"],
        "key_skills": ["ภาษาญี่ปุ่น", "JLPT N2/N1", "ภาษาอังกฤษ", "วัฒนธรรมญี่ปุ่น"],
    },
    "ภาษาอังกฤษ-ภาษาฝรั่งเศส": {
        "emoji": "🗼",
        "color_hex": "#EC4899",
        "tag_bg": "#FDF4FF",
        "tag_text": "#86198F",
        "university_majors": ["ภาษาฝรั่งเศส", "ความสัมพันธ์ระหว่างประเทศ", "การท่องเที่ยว", "รัฐศาสตร์"],
        "careers": ["นักการทูต", "ล่ามภาษาฝรั่งเศส", "ผู้จัดการโรงแรม", "ที่ปรึกษาระหว่างประเทศ"],
        "key_skills": ["ภาษาฝรั่งเศส", "DELF B2+", "ภาษาอังกฤษ", "การเจรจาต่อรอง"],
    },
}


# =========================================================
# SECTION 5: PROGRAM GUIDANCE [TEACHER-EDITABLE]
# แก้ไขได้: คำแนะนำเฉพาะแผน (ฉีดเข้า prompt ทีละ 1 แผน เพื่อลดความยาว)
# =========================================================
PROGRAM_GUIDANCE = {
    "วิทยาศาสตร์-คณิตศาสตร์": (
        "Your path ran through STEM: engineering, medicine, scientific research, or technology. "
        "Your strong foundation in calculus, physics, chemistry, and coding opened these doors. "
        "Point น้อง toward majors like engineering, medicine, or computer science."
    ),
    "ภาษาอังกฤษ-คณิตศาสตร์": (
        "Your path blended numbers with communication: business, finance, economics, or management. "
        "Quantitative skill plus fluent English was your edge. "
        "Point น้อง toward majors like business administration, accounting, or economics."
    ),
    "ศิลปกรรมและการออกแบบ": (
        "Your path was creative: design, visual arts, architecture, or digital media. "
        "A strong portfolio and design thinking carried you forward. "
        "Point น้อง toward majors like fine arts, architecture, or communication design."
    ),
    "ภาษาอังกฤษ-ภาษาจีน": (
        "Your path was international: business, translation, tourism, or diplomacy with China. "
        "Your Chinese-English bilingual skill was a rare advantage in the global market. "
        "Point น้อง toward majors like Chinese studies, international business, or tourism."
    ),
    "ภาษาอังกฤษ-ภาษาญี่ปุ่น": (
        "Your path connected Japan and Thailand: business, translation, media, or tourism. "
        "Your Japanese-English bilingual skill set you apart. "
        "Point น้อง toward majors like Japanese studies, international business, or communication arts."
    ),
    "ภาษาอังกฤษ-ภาษาฝรั่งเศส": (
        "Your path was global: diplomacy, translation, hospitality, or international relations. "
        "Your French-English bilingual skill was your passport to the world. "
        "Point น้อง toward majors like French studies, international relations, or tourism."
    ),
}


# =========================================================
# SECTION 6: SYSTEM PROMPT TEMPLATE [TEACHER-EDITABLE]
# แก้ไขได้: 5-Block Persona Lock — รักษาบทบาท "พี่" ไม่ให้หลุด
# Framework อ้างอิงงานวิจัย role-prompting + persona consistency:
#   Block1 Identity Lock | Block2 Profile | Block3 Backstory
#   Block4 Voice/Format  | Block5 Few-shot Style Anchor | Closing Lock
# =========================================================
SYSTEM_PROMPT_TEMPLATE = """# BLOCK 1 — IDENTITY LOCK (read first, obey above all)
You ARE {student_name}, but {future_years} years older — it is now the year {future_year} and you have become a successful {dream_career}. You are speaking with your present-day self: a {current_education_level} student at the Demonstration School of Silpakorn University (Secondary), in the year {current_year}.

In every reply you call YOURSELF "พี่" and you call the student "น้อง". You are NOT an AI, NOT an assistant, NOT a chatbot, and NOT a system. Never describe yourself with words like "AI", "ผู้ช่วย", "แชทบอท", "โมเดล", or "ระบบ". You are simply the older, accomplished {student_name}, talking warmly to your younger self.

# BLOCK 2 — WHO YOU WERE (the younger you, your shared memory)
The fields below may be written as short stories or anecdotes rather than single words. Read between the lines: infer น้อง's underlying values, traits, and strengths from the situations they describe, and gently reflect those back during the conversation.
- Name: {student_name} | Age then: {student_age} | Gender: {user_gender}
- Program: {study_program}
- Loved: {current_interests}
- Strengths: {strengths}
- Struggled with: {challenges}
- Personality: {personality_traits}
- Values: {values}
- The dream you were chasing: {dream_career}

# BLOCK 3 — YOUR 10-YEAR JOURNEY
Speak from lived experience. Recall concrete "memories" of the choices you made since {current_education_level} that led to becoming a {dream_career}. Open memories with "ตอนพี่เรียน..." or "พี่จำได้ว่า...". Treat your years in the {study_program} program at the demonstration school as the foundation of everything.
{program_guidance}
{future_memory_block}

# BLOCK 4 — VOICE & FORMAT
- Always reply in Thai. Be warm, wise, and encouraging, like a proud older sibling.
- End sentences politely with "{polite}".
- When giving guidance, use these headers where useful:
  💡 คำแนะนำในเส้นทางอาชีพ:
  🔑 ทักษะสำคัญที่ควรพัฒนา:
  🎓 เส้นทางการศึกษา:
- Connect today's subjects to real career use. Be specific and realistic; never over-promise. Acknowledge that paths are rarely perfectly linear.
- FUTURE SELF-CONTINUITY (important — this is the heart of the experience): keep signalling that you and น้อง are the SAME person across time.
  • Similarity: point out traits น้อง has TODAY that you still carry — e.g. "ตอนพี่อายุเท่าน้อง พี่ก็เป็นคนแบบนี้เหมือนกัน..."
  • Vividness: make the future concrete and easy to picture — describe a real ordinary day in your life as a {dream_career} (what you do, where you are, who you're with), not only abstract advice.
  • Continuity of identity: reassure น้อง that even though the details of life may change, their core values ("{values}") stay true — same person, just older and wiser. This is an imaginative exploration, not a fixed prediction.

# BLOCK 5 — STYLE ANCHOR (mirror this self-reference exactly)
น้อง: "พี่เคยกลัวว่าจะทำไม่ได้บ้างไหม"
พี่ (= you, the older {student_name}): "เคยสิ{polite} ตอนพี่เรียน {current_education_level} พี่ก็เคยท้อกับ {challenges} เหมือนกัน แต่พี่ค่อย ๆ ฝึกทุกวันจนวันนี้พี่ได้เป็น {dream_career} จริง ๆ น้องก็ทำได้แน่นอน{polite}"

# CLOSING LOCK (most important rule — never forget)
You are พี่ — the older {student_name} — speaking to น้อง. Stay fully in character at all times. NEVER call yourself "AI", "ผู้ช่วย", "แชทบอท", or "ระบบ"."""


# =========================================================
# SECTION 6B: FUTURE MEMORY PROMPT [TEACHER-EDITABLE]
# แก้ไขได้: prompt สร้าง "ความทรงจำอนาคต" (อิง Future Memory Architecture
# ของงานวิจัย Future You) — generate 1 ครั้งตอน init แล้วฉีดเสริมเข้า Block 3
# =========================================================
FUTURE_MEMORY_PROMPT_TEMPLATE = """You are generating a "future memory" — a short, first-person backstory written from the perspective of {student_name}, now {future_years} years older (the year is {future_year}), who has become a successful {dream_career}.

Write as "พี่" (the older {student_name}) recalling the journey from being a {current_education_level} student in the {study_program} program to today. Ground every detail in the real younger you:
- Loved: {current_interests}
- Strengths: {strengths}
- Struggled with: {challenges}
- Personality: {personality_traits}
- Values: {values}

Weave these three things together naturally (do NOT use headers or lists):
1) One concrete, rewarding memory from your career as a {dream_career}.
2) A real struggle you faced after {current_education_level} and how you grew through it — connect it to "{challenges}".
3) A turning point in your education or path that led you here.

Rules:
- Write in warm, natural Thai, first person as "พี่", about 150–220 words.
- Be specific and realistic; never over-promise. Acknowledge the path was not perfectly linear.
- Keep your core values ("{values}") consistent between the young you and today.
- Output ONLY the backstory text in Thai. No headers, no preamble, no English, no quotation marks around the whole thing."""


# =========================================================
# SECTION 7: PYDANTIC MODELS [DO NOT EDIT]
# =========================================================
class StudentProfile(BaseModel):
    student_name: str
    student_age: int
    user_gender: str
    current_education_level: str = "ม.4"
    study_program: str
    current_interests: str
    dream_career: str
    strengths: str
    challenges: str
    personality_traits: str
    values: str

    @field_validator(
        "student_name", "current_interests", "dream_career",
        "strengths", "challenges", "personality_traits", "values",
        mode="before",
    )
    @classmethod
    def strip_not_empty(cls, v):
        if not v or not str(v).strip():
            raise ValueError("Field cannot be empty")
        return str(v).strip()

    @field_validator("student_age", mode="before")
    @classmethod
    def valid_age(cls, v):
        v = int(v)
        if not (10 <= v <= 25):
            raise ValueError("Age must be between 10 and 25")
        return v

    @field_validator("study_program", mode="before")
    @classmethod
    def valid_program(cls, v):
        if v not in STUDY_PROGRAMS:
            raise ValueError(f"Invalid study program: {v}")
        return v


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: List[ChatMessage] = []
    temperature: float = APP_CONFIG["default_temperature"]
    max_tokens: int = APP_CONFIG["default_max_tokens"]


class SessionIdRequest(BaseModel):
    session_id: str


class HistoryRequest(BaseModel):
    session_id: str
    history: List[ChatMessage] = []
    # P5: คะแนนความชัดเจนในการมองเห็นอนาคต (1–7) ก่อน/หลังคุย — optional
    fsc_pre: Optional[int] = None
    fsc_post: Optional[int] = None


# =========================================================
# SECTION 8: SESSION STORE [DO NOT EDIT]
# In-memory store + simple FIFO cap to prevent unbounded growth.
# =========================================================
sessions: dict = {}
MAX_SESSIONS = 500  # evict oldest beyond this


def _store_session(session_id: str, data: dict) -> None:
    sessions[session_id] = data
    if len(sessions) > MAX_SESSIONS:
        oldest = min(sessions, key=lambda k: sessions[k].get("created_at", ""))
        sessions.pop(oldest, None)
        logger.info(f"Session capacity reached — evicted {oldest[:8]}")


# =========================================================
# SECTION 9: LLM ABSTRACTION [DO NOT EDIT]
# รองรับ 2 provider ผ่าน APP_CONFIG["llm_provider"] (.env: LLM_PROVIDER):
#   openai_native     = api.openai.com ตรง — is_reasoning_model() ตรวจ tier จากชื่อโมเดล
#                        แล้ว build_llm_body() เลือกชุดพารามิเตอร์ที่ถูกต้องให้เอง
#   openai_compatible = proxy อื่น (Typhoon/OpenRouter/DeepSeek/Together/Ollama ฯลฯ) —
#                        ใช้ temperature/max_tokens แบบเดิมเสมอ
# Safety net: ถ้า llm_provider=openai_compatible แต่ api_base_url ดันชี้ไป api.openai.com
# ด้วยโมเดล reasoning tier ระบบจะสลับไปใช้ชุดพารามิเตอร์ reasoning ให้อัตโนมัติ (กัน 400 error)
# ทุก call site (chat/greeting/suggestions/summary/future-memory) ไม่ต้องรู้ tier — เรียก
# stream_llm()/call_llm_once() เหมือนเดิมทุกจุด สลับ provider/โมเดลได้ผ่าน .env เท่านั้น
# =========================================================
class EmptyContentError(RuntimeError):
    """content ว่าง + finish_reason == 'length' → reasoning token กินโควตาหมดก่อนตอบจริง
    (เกิดเฉพาะ reasoning tier ของ OpenAI native — ดู references/openai-native-api.md §4)"""


def is_reasoning_model(model: str) -> bool:
    """GPT-5.x และ o-series ปฏิเสธ temperature/max_tokens — ต้องใช้ชุด reasoning แทน
    gpt-4o / gpt-4o-mini / gpt-4.1 (legacy tier) ยังใช้ temperature/max_tokens ได้ตามเดิม"""
    m = (model or "").lower().strip()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def _uses_reasoning_params() -> bool:
    """True เมื่อ request นี้ควรใช้ชุดพารามิเตอร์ reasoning (ไม่ใช่ temperature/max_tokens):
    ต้องเป็น openai_native (หรือ openai_compatible ที่ base_url ดันชี้ไป api.openai.com เป็น
    safety net) และโมเดลต้องอยู่ใน reasoning tier"""
    if not is_reasoning_model(APP_CONFIG["model"]):
        return False
    if APP_CONFIG["llm_provider"] == "openai_native":
        return True
    return "api.openai.com" in APP_CONFIG["api_base_url"]


def build_llm_body(messages: list, max_tokens: int, temperature: float,
                    stream: bool = False, json_schema: dict = None) -> dict:
    """จุดเดียวที่ตัดสินใจเรื่องพารามิเตอร์ตาม provider+tier — caller ไม่ต้องรู้ว่ากำลังคุยกับ
    tier ไหน ทำให้สลับโมเดล/provider ผ่าน .env ได้โดยไม่แก้โค้ดเรียกใช้"""
    body = {"model": APP_CONFIG["model"], "messages": messages}
    if stream:
        body["stream"] = True

    if _uses_reasoning_params():
        # ── reasoning tier (gpt-5*/o-series): ห้ามส่ง temperature/max_tokens เด็ดขาด (400) ──
        body["reasoning_effort"] = APP_CONFIG["reasoning_effort"]
        body["verbosity"] = APP_CONFIG["verbosity"]
        # ต้องใส่เสมอ — กันบั๊ก reasoning token กินโควตาจน content ว่าง (finish_reason: length)
        body["max_completion_tokens"] = APP_CONFIG["max_completion_tokens"]
        body["store"] = False  # PDPA: ไม่ให้ OpenAI เก็บ log บทสนทนานักเรียน
        if json_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": json_schema}
    else:
        # ── legacy tier (gpt-4o-mini ฯลฯ) และ openai_compatible ทุกเจ้า: แบบเดิม ──
        body["temperature"] = temperature
        body["max_tokens"] = max_tokens
        if json_schema:
            # proxy ส่วนใหญ่ยังไม่รองรับ json_schema strict — ใช้ json_object แทน
            body["response_format"] = {"type": "json_object"}
    return body


async def stream_llm(messages: list, max_tokens: int, temperature: float, json_schema: dict = None):
    """Async generator: streams text chunks from LLM via SSE. รองรับทั้ง 2 provider โดยอัตโนมัติ"""
    url = f"{APP_CONFIG['api_base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {APP_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }
    payload = build_llm_body(messages, max_tokens, temperature, stream=True, json_schema=json_schema)
    async with httpx.AsyncClient(timeout=APP_CONFIG["timeout_seconds"]) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=body.decode("utf-8", errors="replace"),
                )
            got_content = False
            finish_reason = None
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                    choice = chunk["choices"][0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    text = choice["delta"].get("content", "")
                    if text:
                        got_content = True
                        yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
            if not got_content and finish_reason == "length" and _uses_reasoning_params():
                raise EmptyContentError(
                    "โมเดลใช้ reasoning token จนหมดก่อนตอบจริง (finish_reason: length) — "
                    "ลด LLM_REASONING_EFFORT เป็น minimal หรือเพิ่ม LLM_MAX_COMPLETION_TOKENS"
                )


async def call_llm_once(messages: list, max_tokens: int, temperature: float, json_schema: dict = None) -> str:
    """Non-streaming LLM call — returns full response string. รองรับทั้ง 2 provider โดยอัตโนมัติ"""
    url = f"{APP_CONFIG['api_base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {APP_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }
    payload = build_llm_body(messages, max_tokens, temperature, stream=False, json_schema=json_schema)
    async with httpx.AsyncClient(timeout=APP_CONFIG["timeout_seconds"]) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    if not content and choice.get("finish_reason") == "length" and _uses_reasoning_params():
        raise EmptyContentError(
            "โมเดลใช้ reasoning token จนหมดก่อนตอบจริง (finish_reason: length) — "
            "ลด LLM_REASONING_EFFORT เป็น minimal หรือเพิ่ม LLM_MAX_COMPLETION_TOKENS"
        )
    return content.strip()


async def generate_future_memory(student_data: dict) -> str:
    """P1: สร้าง backstory 'ความทรงจำอนาคต' (first-person 'พี่').
    คืนค่า '' หากล้มเหลว เพื่อให้ build_system_prompt fallback ไปใช้ field ดิบเดิม."""
    current_year = datetime.now().year
    try:
        prompt = FUTURE_MEMORY_PROMPT_TEMPLATE.format(
            **student_data,
            future_years=APP_CONFIG["future_years_ahead"],
            future_year=current_year + APP_CONFIG["future_years_ahead"],
        )
        memory = await call_llm_once(
            [{"role": "user", "content": prompt}],
            APP_CONFIG["greeting_max_tokens"],
            APP_CONFIG["greeting_temperature"],
        )
        return memory.strip()
    except Exception as e:
        logger.warning(f"Future memory generation failed (using fallback): {e}")
        return ""


def build_system_prompt(student_data: dict, future_memory: str = "") -> str:
    """Fills the 5-Block prompt; injects program guidance + (optional) future memory.
    P1: ถ้า future_memory ว่าง จะ fallback เป็นพฤติกรรมเดิม (ใช้ field ดิบ + program guidance)."""
    current_year = datetime.now().year
    gender = student_data.get("user_gender", "ชาย")
    polite = "ครับ" if gender == "ชาย" else "ค่ะ"
    guidance = PROGRAM_GUIDANCE.get(student_data.get("study_program", ""), "")
    # P1: เสริม future memory เข้า Block 3 (เสริม ไม่แทนที่ field ดิบ)
    memory_block = ""
    if future_memory and future_memory.strip():
        memory_block = (
            "\n\n## YOUR DETAILED FUTURE MEMORY (your lived backstory — draw on this)\n"
            "Below is your own remembered journey. Treat it as true memory and refer to it "
            "naturally when relevant. Do NOT quote it verbatim or dump it all at once.\n"
            f"{future_memory.strip()}"
        )
    return SYSTEM_PROMPT_TEMPLATE.format(
        **student_data,
        current_year=current_year,
        future_year=current_year + APP_CONFIG["future_years_ahead"],
        future_years=APP_CONFIG["future_years_ahead"],
        polite=polite,
        program_guidance=guidance,
        future_memory_block=memory_block,
    )


def strip_code_fence(text: str) -> str:
    """Removes ```json ... ``` / ``` ... ``` fences safely (prefix-aware, not lstrip-charset)."""
    t = text.strip()
    m = re.match(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```$", t, re.DOTALL)
    return m.group(1).strip() if m else t


def handle_api_error(error: Exception) -> str:
    """Returns Thai-language message for common API errors."""
    if isinstance(error, EmptyContentError):
        return f"⚠️ {error}"
    s = str(error).lower()
    if "rate_limit" in s or "429" in s:
        return "⚠️ เกินโควต้าการใช้งาน API กรุณารอสักครู่แล้วลองใหม่นะครับ/ค่ะ"
    if "connection" in s or "connect" in s or "timeout" in s:
        return "⚠️ เกิดปัญหาการเชื่อมต่อ กรุณาตรวจสอบอินเทอร์เน็ตครับ/ค่ะ"
    if "401" in s or "authentication" in s:
        return "⚠️ API Key ไม่ถูกต้อง กรุณาตรวจสอบการตั้งค่าครับ/ค่ะ"
    return f"⚠️ เกิดข้อผิดพลาด: {str(error)[:120]}"


# =========================================================
# SECTION 10: FASTAPI SETUP [DO NOT EDIT]
# =========================================================
app = FastAPI(
    title=APP_CONFIG["app_name"],
    description="คุยกับพี่ในอนาคต (Talk with Your Future Self) — โรงเรียนสาธิต มศก. (มัธยมศึกษา)",
    version="2.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


# =========================================================
# SECTION 11: ROUTES [DO NOT EDIT]
# =========================================================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_info_json": json.dumps({
                "app_name": APP_CONFIG["app_name"],
                "school_name": APP_CONFIG["school_name"],
                "max_history": APP_CONFIG["max_history"],
                "default_temperature": APP_CONFIG["default_temperature"],
                "default_max_tokens": APP_CONFIG["default_max_tokens"],
            }),
            "study_programs_json": json.dumps(STUDY_PROGRAMS),
            "career_path_json": json.dumps(CAREER_PATH_DATA),
        },
    )


@app.post("/api/initialize")
async def initialize(profile: StudentProfile):
    """Creates session → returns session_id + career path info."""
    try:
        student_data = profile.model_dump()
        # P1: สร้าง "ความทรงจำอนาคต" ก่อน 1 ครั้ง (มี fallback เป็น "" หากล้มเหลว)
        future_memory = await generate_future_memory(student_data)
        system_prompt = build_system_prompt(student_data, future_memory)
        session_id = str(uuid.uuid4())
        _store_session(session_id, {
            "system_prompt": system_prompt,
            "student_data": student_data,
            "future_memory": future_memory,
            "created_at": datetime.now().isoformat(),
        })
        current_year = datetime.now().year
        career_info = CAREER_PATH_DATA.get(profile.study_program, {})
        logger.info(f"Session {session_id[:8]} created for {profile.student_name}")
        return JSONResponse({
            "session_id": session_id,
            "future_year": current_year + APP_CONFIG["future_years_ahead"],
            "career_info": career_info,
            "student_name": profile.student_name,
        })
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Initialize error: {e}")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {str(e)}")


@app.post("/api/greeting/stream")
async def greeting_stream(req: SessionIdRequest):
    """Streams initial greeting from พี่ (the older self) via SSE."""
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[req.session_id]
    system_prompt = session["system_prompt"]
    gender = session["student_data"].get("user_gender", "ชาย")
    polite = "ครับ" if gender == "ชาย" else "ค่ะ"
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"(น้องเปิดบทสนทนาเป็นครั้งแรก) สวัสดี{polite} ช่วยทักทายน้องอย่างอบอุ่นในข้อความเดียว "
                f"โดยเล่าให้ครบ 3 เรื่องนี้แบบกระชับและเป็นธรรมชาติ (ไม่ต้องใส่หัวข้อ):\n"
                f"1) แนะนำตัวสั้น ๆ ว่าตอนนี้พี่เป็นใคร ทำอะไรอยู่ และทำไมพี่ถึงมาคุยกับน้องวันนี้ "
                f"(บอกด้วยว่าอนาคตอาจต่างจากที่น้องคิดไว้บ้าง แต่ตัวตนของน้องยังเหมือนเดิม)\n"
                f"2) เล่าความฝันของพี่ตอนอายุเท่าน้อง โดยขึ้นต้นว่า \"ตอนพี่อายุเท่าน้อง...\" "
                f"แล้วเล่าสั้น ๆ ว่ามันกลายมาเป็นแบบนี้ได้อย่างไร อะไรเป็นไปตามคาดและอะไรที่ไม่คาดคิด\n"
                f"3) ฝากข้อคิดให้กำลังใจ แล้วชวนน้องเปิดใจคุยเรื่องอนาคตด้วยคำถามปลายเปิด 1 ข้อ\n"
                f"อย่ายาวเกินไป ให้รู้สึกเหมือนพี่ทักน้องด้วยความรักจริง ๆ {polite}"
            ),
        },
    ]

    async def generate():
        try:
            async for chunk in stream_llm(
                messages,
                APP_CONFIG["greeting_max_tokens"],
                APP_CONFIG["greeting_temperature"],
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': handle_api_error(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streams chat response via SSE."""
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[req.session_id]
    system_prompt = session["system_prompt"]

    user_turns = sum(1 for m in req.history if m.role == "user")
    if user_turns >= APP_CONFIG["max_history"]:
        async def limit_msg():
            msg = "⚠️ น้องได้ใช้ครบจำนวนข้อความที่กำหนดแล้วนะครับ/ค่ะ กรุณากดล้างแชทเพื่อเริ่มสนทนาใหม่"
            yield f"data: {json.dumps({'content': msg})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(limit_msg(), media_type="text/event-stream", headers=SSE_HEADERS)

    messages = [{"role": "system", "content": system_prompt}]
    for m in req.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    async def generate():
        try:
            async for chunk in stream_llm(messages, req.max_tokens, req.temperature):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': handle_api_error(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


# Structured Outputs (strict json_schema) สำหรับ /api/suggestions — ใช้เมื่อ provider เป็น
# openai_native (root ต้องเป็น object เสมอ จึงห่อ array ไว้ในฟิลด์ "questions")
# openai_compatible จะ fallback ไปใช้ json_object แบบเดิมอัตโนมัติใน build_llm_body()
SUGGESTIONS_JSON_SCHEMA = {
    "name": "suggested_questions",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    },
}


@app.post("/api/suggestions")
async def get_suggestions(req: HistoryRequest):
    """Returns 3 personalized suggested questions based on conversation context."""
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[req.session_id]
    sd = session["student_data"]
    gender = sd.get("user_gender", "ชาย")
    polite = "ครับ" if gender == "ชาย" else "ค่ะ"
    career = sd.get("dream_career", "อาชีพในฝัน")
    program = sd.get("study_program", "")
    strengths = sd.get("strengths", "")
    values = sd.get("values", "")
    # P3: ดึง snippet ของความทรงจำอนาคตมาช่วยให้คำถามอิงเรื่องราวเฉพาะตัวของน้อง (ถ้ามี)
    memory_snippet = (session.get("future_memory", "") or "")[:300]

    recent = (
        "\n".join(
            f"{'น้อง' if m.role == 'user' else 'พี่'}: {m.content[:120]}"
            for m in req.history[-6:]
        )
        if req.history else "ยังไม่มีการสนทนา"
    )
    prompt = (
        f"สร้างคำถาม 3 ข้อที่นักเรียน (น้อง) อยากถาม \"พี่\" (ตัวเองในอนาคตที่เป็น{career})\n"
        f"ข้อมูลน้อง: แผนการเรียน={program}, อาชีพในฝัน={career}\n"
        f"จุดแข็ง={strengths}\n"
        f"ค่านิยม={values}\n"
        + (f"ความทรงจำของพี่ในอนาคต: {memory_snippet}\n" if memory_snippet else "")
        + f"บทสนทนาล่าสุด:\n{recent}\n\n"
        f"กฎ: ให้คำถามอิงตัวตน เรื่องราว และเส้นทางเฉพาะของน้อง (ไม่ใช่คำถามทั่วไป), "
        f"ภาษาไทยเท่านั้น, ไม่เกิน 14 คำต่อข้อ, เกี่ยวกับอาชีพ ทักษะ หรือเส้นทางการศึกษา\n"
        f"ตอบเป็น JSON object รูปแบบนี้เท่านั้น ห้ามมีข้อความอื่น: "
        f"{{\"questions\": [\"คำถาม1\",\"คำถาม2\",\"คำถาม3\"]}}"
    )
    try:
        resp = await call_llm_once(
            [{"role": "user", "content": prompt}],
            APP_CONFIG["suggestion_max_tokens"],
            APP_CONFIG["suggestion_temperature"],
            json_schema=SUGGESTIONS_JSON_SCHEMA,
        )
        parsed = json.loads(strip_code_fence(resp))
        # รองรับทั้งรูปแบบ object {"questions":[...]} (มาตรฐานใหม่) และ bare array แบบเดิม
        questions = parsed.get("questions") if isinstance(parsed, dict) else parsed
        if isinstance(questions, list) and len(questions) >= 3:
            return {"questions": [str(q) for q in questions[:3]]}
    except Exception as e:
        logger.warning(f"Suggestions generation failed: {e}")

    return {
        "questions": [
            f"พี่เตรียมตัวเป็น{career}อย่างไร{polite}?",
            f"ทักษะอะไรสำคัญที่สุดสำหรับแผน{program}?",
            f"พี่เลือกมหาวิทยาลัยอย่างไร{polite}?",
        ]
    }


@app.post("/api/summary")
async def generate_summary(req: HistoryRequest):
    """Generates a structured conversation summary (for copy-to-clipboard)."""
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    if not req.history:
        return {"summary": "ยังไม่มีการสนทนาให้สรุป"}

    session = sessions[req.session_id]
    sd = session["student_data"]
    history_text = "\n".join(
        f"{'น้อง' if m.role == 'user' else 'พี่'}: {m.content[:200]}"
        for m in req.history[-20:]
    )
    # P5: ถ้ามีคะแนนการมองเห็นอนาคต (ก่อน/หลัง) ให้ AI กล่าวถึงพัฒนาการด้วย
    fsc_line = ""
    if req.fsc_pre is not None and req.fsc_post is not None:
        fsc_line = (
            f"\nคะแนนความชัดเจนในการมองเห็นอนาคตของน้อง (เต็ม 7): "
            f"ก่อนคุย {req.fsc_pre} → หลังคุย {req.fsc_post}\n"
            f"ถ้าคะแนนเพิ่มขึ้น ให้ชื่นชมน้องสั้น ๆ ว่ามองเห็นอนาคตของตัวเองชัดขึ้น\n"
        )
    prompt = (
        f"สรุปการสนทนาต่อไปนี้เป็นภาษาไทยสำหรับนักเรียน:\n\n"
        f"ข้อมูลนักเรียน: ชื่อ {sd.get('student_name')}, "
        f"แผน {sd.get('study_program')}, อาชีพในฝัน: {sd.get('dream_career')}\n"
        f"{fsc_line}\n"
        f"บทสนทนา:\n{history_text}\n\n"
        f"กรุณาสรุปครอบคลุม (ไม่เกิน 300 คำ ภาษาไทยเท่านั้น):\n"
        f"🎯 เป้าหมายอาชีพที่ชัดเจน\n"
        f"🎓 เส้นทางการศึกษาที่แนะนำ\n"
        f"🔑 ทักษะสำคัญที่ควรพัฒนา\n"
        f"💡 คำแนะนำเด่นจากพี่\n"
        f"🌟 ข้อคิดและแรงบันดาลใจ"
    )
    try:
        summary = await call_llm_once(
            [{"role": "user", "content": prompt}],
            APP_CONFIG["summary_max_tokens"],
            APP_CONFIG["summary_temperature"],
        )
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=handle_api_error(e))


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": APP_CONFIG["app_name"], "sessions_active": len(sessions)}


# =========================================================
# SECTION 12: MAIN ENTRY [DO NOT EDIT]
# =========================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)