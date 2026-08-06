from dotenv import load_dotenv
load_dotenv()
import os

print("=== Testing Gemini ===")
import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content("Say hello in Sinhala")
print(response.text)

print("\n=== Testing OpenRouter ===")
import requests
response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"},
    json={
        "model": "openrouter/free",
        "messages": [{"role": "user", "content": "Say hello in Sinhala"}],
    },
)
print(response.json())