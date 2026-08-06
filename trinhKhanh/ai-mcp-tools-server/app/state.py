import os
import logging
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Robot_Main")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

gemini_client = genai.Client()

db_pool = None
mcp_sessions: dict = {}
mcp_tools_registry: list = []
exit_stack = AsyncExitStack()
outbound_connections: dict = {}

# DB chính (users/chat/media) — dùng CHUNG một Neon với why_questions/subscriptions
# ("chỉ 1 DB"): nếu không set DB_* thì fallback sang WHY_DB_*.
# KHÔNG hardcode credential — phải cung cấp qua .env (local) hoặc HF Secrets (deploy).
# Nếu thiếu, DSN sẽ không hợp lệ và pool không tạo được → app vẫn chạy, DB tắt.
DB_USER = os.getenv("DB_USER") or os.getenv("WHY_DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("WHY_DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST") or os.getenv("WHY_DB_HOST")
DB_PORT = os.getenv("DB_PORT") or os.getenv("WHY_DB_PORT") or "5432"
DB_NAME = os.getenv("DB_NAME") or os.getenv("WHY_DB_NAME")
# Neon (và mọi Postgres cloud) bắt buộc SSL. Đặt DB_SSL=disable nếu dùng Postgres
# local không bật SSL. Áp dụng khi tạo pool trong main.py.
DB_SSL = os.getenv("DB_SSL", "require")
DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

preference_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="update_preferences",
            description="Sử dụng công cụ này KHI VÀ CHỈ KHI trẻ em chủ động kể về sở thích, đồ vật yêu thích, ước mơ, hoặc những thứ trẻ không thích. Trích xuất thông tin đó để hệ thống ghi nhớ.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "category": types.Schema(type="STRING",
                                             description="Phân loại sở thích (snake_case). Ví dụ: 'favorite_food'"),
                    "value": types.Schema(type="STRING",
                                         description="Giá trị cụ thể mà trẻ nhắc đến. Ví dụ: 'xúc xích'")
                },
                required=["category", "value"]
            )
        )
    ]
)


def json_schema_to_gemini(schema: dict) -> types.Schema:
    if not schema:
        return types.Schema(type="OBJECT")
    t_map = {
        "string": "STRING", "integer": "INTEGER", "number": "NUMBER",
        "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT"
    }
    gemini_type = t_map.get(schema.get("type", "object").lower(), "STRING")
    if gemini_type == "OBJECT":
        props = {k: json_schema_to_gemini(v) for k, v in schema.get("properties", {}).items()}
        return types.Schema(type="OBJECT", properties=props,
                            required=schema.get("required", []),
                            description=schema.get("description", ""))
    if gemini_type == "ARRAY":
        return types.Schema(type="ARRAY",
                            items=json_schema_to_gemini(schema.get("items", {})),
                            description=schema.get("description", ""))
    return types.Schema(type=gemini_type, description=schema.get("description", ""))
