import os
import requests
import time
import jwt
from database import get_storage_status
from services.settings_service import settings_service

class DiagnosticsService:
    def check_all(self):
        results = {
            "storage": get_storage_status(),
            "coingecko": self.check_coingecko(),
            "notifications": self.check_notifications(),
            "supabase": self.check_supabase(),
            "twelve_data": self.check_twelve_data(),
            "tcmb": self.check_tcmb(),
        }
        return results

    def check_coingecko(self):
        key = settings_service.get_value("COINGECKO_API_KEY")
        try:
            headers = {"x-cg-demo-api-key": key} if key else {}
            resp = requests.get(
                "https://api.coingecko.com/api/v3/ping",
                headers=headers,
                timeout=5,
            )
            if resp.status_code == 200:
                mode = "demo key" if key else "public"
                return {"status": "ok", "message": f"API reachable ({mode})"}
            return {"status": "error", "message": f"Status {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": f"Connection failed: {str(e)}"}

    def check_notifications(self):
        key_id = settings_service.get_value("APNS_KEY_ID")
        team_id = settings_service.get_value("APNS_TEAM_ID")
        private_key = settings_service.get_value("APNS_PRIVATE_KEY")
        bundle_id = settings_service.get_value("APNS_BUNDLE_ID")
        if all([key_id, team_id, private_key, bundle_id]):
            try:
                jwt.encode(
                    {"iss": team_id, "iat": int(time.time())},
                    private_key.replace("\\n", "\n"),
                    algorithm="ES256",
                    headers={"alg": "ES256", "kid": key_id},
                )
            except Exception as exc:
                return {
                    "status": "error",
                    "message": f"APNs provider token signing failed: {str(exc)}",
                }
            return {
                "status": "ok",
                "message": "Supabase inbox ready; APNs provider token signing verified",
            }
        return {
            "status": "partial",
            "message": "Supabase inbox is ready; APNs secrets are not configured",
        }

    def check_supabase(self):
        url = settings_service.get_value("SUPABASE_URL")
        key = settings_service.get_value("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key: return {"status": "missing", "message": "Config missing"}
        
        try:
            # Try to list users (requires service_role)
            check_url = f"{url}/auth/v1/admin/users"
            headers = {"apikey": key, "Authorization": f"Bearer {key}"}
            resp = requests.get(check_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                return {"status": "ok", "message": "Admin access verified"}
            return {"status": "error", "message": f"Status {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def check_twelve_data(self):
        key = settings_service.get_value("TWELVEAPI_TOKEN")
        if not key: return {"status": "missing"}
        try:
            resp = requests.get(f"https://api.twelvedata.com/quote?symbol=AAPL&apikey={key}", timeout=5)
            if resp.status_code == 200: return {"status": "ok"}
            return {"status": "error"}
        except: return {"status": "error"}

    def check_tcmb(self):
        try:
            resp = requests.get("https://www.tcmb.gov.tr/kurlar/today.xml", timeout=5)
            if resp.status_code == 200 and b"Currency" in resp.content:
                return {"status": "ok", "message": "Official daily rates reachable"}
            return {"status": "error", "message": f"Status {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

diagnostics_service = DiagnosticsService()
