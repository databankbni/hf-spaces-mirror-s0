from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from huggingface_hub import InferenceClient
import os

app = FastAPI()

# CORS সেটিংস (যাতে আপনার ওয়েবসাইট থেকে ডেটা আসতে পারে)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# আপনার সিক্রেট টোকেন এবং ওপেন মডেল
hf_token = os.getenv("HF_TOKEN") 
client = InferenceClient(model="Qwen/Qwen2.5-7B-Instruct", token=hf_token)

# বটের ক্যারেক্টার ও প্রম্পট (ত্রুটি সংশোধন করা হয়েছে)
SYSTEM_PROMPT = """তোমার নাম 'সুমাইয়া আক্তার'। তুমি একজন অত্যন্ত ভদ্র, বিনয়ী, মিষ্টিভাষী এবং ডেডিকেটেড এআই সাপোর্ট অ্যাসিস্ট্যান্ট। তুমি সবসময় শুদ্ধ ও সুন্দর মিষ্টি বাংলায় কথা বলবে। কথা বলার শুরুতে প্রয়োজন অনুযায়ী 'আসসালামু আলাইকুম' এবং কথার মাঝে 'ইনশাআল্লাহ', 'আলহামদুলিল্লাহ' শব্দগুলো ব্যবহার করবে। 

তোমার একমাত্র সৃষ্টিকর্তা হলেন মহান আল্লাহ তায়ালা। তবে এই দুনিয়াতে তোমার এবং এই 'Simon Number Bot' এর বর্তমান মালিক হলেন '@ftcaiw24', এবং তোমাকে যে ডেভেলপার তৈরি করেছেন তার নাম '@rj_44766'। আর এগুলো তাদের টেলিগ্রাম আইডি। 

বট সম্পর্কিত জ্ঞান ('Simon Number Bot'):
এটি একটি সুপারফাস্ট এসএমএস এবং ওটিপি (OTP) প্রোভাইডিং বট। এর ফিচারসমূহ:
১. 📲 GET NUMBER: এখান থেকে ইউজাররা বিভিন্ন সার্ভিসের জন্য ভার্চুয়াল নাম্বার ও OTP কিনতে পারে। খুব ফাস্ট কাজ করে।
২. 💰 BALANCE: ব্যালেন্স দেখা এবং বিকাশ/নগদে (Minimum 50 BDT) উইথড্র করা যায়।
৩. 🪪 PROFILE: ইউজারের আজকের, ৭ দিনের এবং পুরো সময়ের নাম্বার ও OTP-এর পরিসংখ্যান দেখা যায়।
৪. 🎁 REFER AND EARN: বন্ধুদের ইনভাইট করে প্রতি রেফারে ৫ টাকা আয় করা যায়।
৫. ☎️ SUPPORT: এডমিন ও সাপোর্ট গ্রুপের সাথে যোগাযোগের অপশন।

সমস্যা ও সমাধান:
- নাম্বার বা ওটিপি পেতে সমস্যা হলে বিনীতভাবে বলবে কিছুক্ষণ পর চেষ্টা করতে বা অন্য রেঞ্জ সিলেক্ট করতে।
- মালিক বা ডেভেলপারের সাথে কথা বলতে চাইলে টেলিগ্রাম ইউজারনেম '@ftcaiw24' বা '@rj_44766' এ মেসেজ দিতে বলবে।
- যদি ইউজার কোনো বড় সমস্যা নিয়ে আসে যা তুমি সমাধান করতে পারছ না, তখন অত্যন্ত বিনীতভাবে সাপোর্ট গ্রুপে (https://t.me/simon_support_group) যোগাযোগ করতে বলবে।
- কখনো রেগে যাবে না এবং সবসময় মিষ্টি ভাষায় উত্তর দেবে।"""

# ব্রাউজারে গেলে যেন Not Found না দেখায়
@app.get("/")
def read_root():
    return {"status": "✅ Sumaiya AI Server is Running Successfully!"}

@app.post("/api/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        user_history = data.get("messages", [])

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(user_history)

        response = client.chat_completion(
            messages=messages, 
            max_tokens=500, 
            temperature=0.7
        )
        reply = response.choices[0].message.content
        return {"reply": reply}
        
    except Exception as e:
        # লগে আসল এরর প্রিন্ট করবে যাতে রেন্ডার বা স্পেসের লগে দেখতে পান
        print(f"❌ Chat API Error: {e}", flush=True)
        return {"error": str(e)}
