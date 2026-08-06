
import os
import sys
sys.path.append(".")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import uuid
import edge_tts
from fastapi.responses import FileResponse
import requests
from agent import get_agent_response
load_dotenv()


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://khushiagarwal-portfolio.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TTSRequest(BaseModel):
    text: str

class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    message: str
class ChatRequest(BaseModel):
    message: str


@app.get("/")
def home():
    return {"message": "Portfolio backend is running"}

@app.post("/tts")
async def tts(data: TTSRequest):
    try:
        filename = f"tts_{uuid.uuid4().hex}.mp3"

        communicate = edge_tts.Communicate(
            text=data.text,
            voice="en-US-JennyNeural"
        )

        await communicate.save(filename)

        return FileResponse(
            filename,
            media_type="audio/mpeg",
            filename="speech.mp3"
        )

    except Exception as e:
        print("TTS ERROR:", e)
        return {
            "success": False,
            "message": str(e)
        }
    
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
TO_EMAIL = os.getenv("TO_EMAIL")

@app.post("/chat")
async def chat(data: ChatRequest):
    print("🔥 CHAT ENDPOINT HIT")
    print("MESSAGE:", data.message)

    response = get_agent_response(data.message)

    print("RESPONSE:", response)

    return response

@app.post("/contact")
def contact_form(data: ContactRequest):

    try:
        print("🔥 CONTACT ROUTE HIT")
        print("RESEND KEY EXISTS:", bool(RESEND_API_KEY))
        print("TO_EMAIL:", TO_EMAIL)

        if not RESEND_API_KEY or not TO_EMAIL:
            return {
                "success": False,
                "message": "Missing Resend env variables",
            }

        payload = {
            "from": "Portfolio <onboarding@resend.dev>",
            "to": TO_EMAIL,
            "subject": f"New Portfolio Message from {data.name}",
            "text": f"""
New message from your portfolio:

Name: {data.name}
Email: {data.email}

Message:
{data.message}
"""
        }

        print("🚀 Sending request to Resend...")

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        print("📩 RESEND STATUS:", response.status_code)
        print("📩 RESEND RESPONSE:", response.text)

        if response.status_code in [200, 202]:
            return {
                "success": True,
                "message": "Email sent successfully",
            }
        else:
            return {
                "success": False,
                "message": response.text,
            }

    except Exception as e:
        print("❌ CONTACT ERROR:", repr(e))
        return {
            "success": False,
            "message": str(e),
        }