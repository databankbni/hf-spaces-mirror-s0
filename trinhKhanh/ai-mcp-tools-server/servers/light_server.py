import os
import sys
import logging
import requests
from fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger('LightServer')

if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

SMARTLIGHT_API_URL = os.getenv("SMARTLIGHT_API_URL", "http://localhost:5067")

mcp = FastMCP("LightServer")


@mcp.tool()
def control_light(device_code: str, is_on: bool, brightness: int = 100) -> dict:
    """
    Điều khiển đèn LED – bật, tắt hoặc điều chỉnh độ sáng của MỘT đèn LED duy nhất.
    Dùng tool này khi người dùng chỉ nhắc đến MỘT đèn cụ thể.

    Mapping tên đèn sang device_code:
    - "đèn số 1" hoặc "đèn 1" → device_code = "DEV-LAMP01"
    - "đèn số 2" hoặc "đèn 2" → device_code = "DEV-LAMP02"
    - "đèn số 3" hoặc "đèn 3" → device_code = "DEV-LAMP03"

    is_on: True để bật, False để tắt.
    brightness: độ sáng từ 0 đến 100. Mặc định 100 khi bật, tự động về 0 khi tắt.
    """
    brightness = max(0, min(100, brightness))
    if not is_on:
        brightness = 0

    try:
        resp = requests.post(
            f"{SMARTLIGHT_API_URL}/api/mqtt/control",
            json={"deviceCode": device_code, "isOn": is_on, "brightness": brightness},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"💡 [LIGHT] {device_code} → {'BẬT' if is_on else 'TẮT'} {brightness}%: {data.get('message', '')}")
        return {"success": True, "message": data.get("message", ""), "commandId": data.get("commandId")}
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ [LIGHT] Không kết nối được Smartlight API tại {SMARTLIGHT_API_URL}")
        return {"success": False, "error": "Không kết nối được hệ thống đèn."}
    except Exception as e:
        logger.error(f"❌ [LIGHT] Lỗi control_light: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def control_lights_batch(device_codes: list[str], is_on: bool, brightness: int = 100) -> dict:
    """
    Điều khiển đèn LED – bật, tắt hoặc điều chỉnh độ sáng của NHIỀU đèn LED cùng lúc.
    Dùng tool này khi người dùng nhắc đến NHIỀU đèn hoặc "tất cả đèn".

    Mapping tên đèn sang device_codes:
    - "tất cả đèn" hoặc "toàn bộ đèn" → device_codes = ["DEV-LAMP01", "DEV-LAMP02", "DEV-LAMP03"]
    - "đèn số 1 và 2" hoặc "đèn 1, 2"  → device_codes = ["DEV-LAMP01", "DEV-LAMP02"]
    - "đèn số 2 và 3" hoặc "đèn 2, 3"  → device_codes = ["DEV-LAMP02", "DEV-LAMP03"]
    - "đèn số 1 và 3"                   → device_codes = ["DEV-LAMP01", "DEV-LAMP03"]

    is_on: True để bật, False để tắt.
    brightness: độ sáng từ 0 đến 100. Mặc định 100 khi bật, tự động về 0 khi tắt.
    """
    brightness = max(0, min(100, brightness))
    if not is_on:
        brightness = 0

    try:
        resp = requests.post(
            f"{SMARTLIGHT_API_URL}/api/mqtt/control-batch",
            json={"deviceCodes": device_codes, "isOn": is_on, "brightness": brightness},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"💡 [LIGHT] Batch {len(device_codes)} đèn → {'BẬT' if is_on else 'TẮT'} {brightness}%")
        return {
            "success": True,
            "message": data.get("message", ""),
            "totalFound": data.get("totalFound", 0),
            "totalNotFound": data.get("totalNotFound", 0),
        }
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ [LIGHT] Không kết nối được Smartlight API tại {SMARTLIGHT_API_URL}")
        return {"success": False, "error": "Không kết nối được hệ thống đèn."}
    except Exception as e:
        logger.error(f"❌ [LIGHT] Lỗi control_lights_batch: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
