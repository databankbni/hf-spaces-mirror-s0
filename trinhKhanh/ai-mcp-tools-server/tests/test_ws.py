import asyncio
import websockets
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

USER_ID = "fa8e2f90-9e57-4455-9dae-39c86595524f"
URI = f"ws://localhost:8000/ws/robot/{USER_ID}"


async def test():
    print(f"Connecting to: {URI}")
    try:
        async with websockets.connect(URI, open_timeout=10) as ws:
            print("✅ CONNECTED OK")

            msg = "Chào chú Robot! Tên con là Minh Anh."
            await ws.send(msg)
            print(f"📤 SENT: {msg}")

            for _ in range(5):
                try:
                    r = await asyncio.wait_for(ws.recv(), timeout=30)
                    if isinstance(r, bytes):
                        print(f"🔊 AUDIO received: {len(r)} bytes")
                    else:
                        data = json.loads(r)
                        print(f"💬 TEXT response: {data.get('message', r)}")
                        break
                except asyncio.TimeoutError:
                    print("⏰ TIMEOUT - no response in 30s")
                    break
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")


asyncio.run(test())