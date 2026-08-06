import logging
import time
from datetime import datetime, timezone

import httpx
import jwt
import requests

from database import get_db_connection
from services.settings_service import settings_service

logger = logging.getLogger(__name__)


class NotificationService:
    """First-party inbox delivery with direct Apple Push Notification service."""

    def __init__(self):
        self._apns_jwt = None
        self._apns_jwt_created_at = 0

    def _supabase_config(self):
        return (
            settings_service.get_value("SUPABASE_URL"),
            settings_service.get_value("SUPABASE_SERVICE_ROLE_KEY"),
        )

    @staticmethod
    def _supabase_headers(key, return_representation=False):
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if return_representation:
            headers["Prefer"] = "return=representation"
        return headers

    def get_history(self, limit=50):
        url, key = self._supabase_config()
        if url and key:
            response = requests.get(
                f"{url}/rest/v1/notifications",
                headers=self._supabase_headers(key),
                params={
                    "select": "id,title,message,image_url,action_url,target_segment,status,recipient_count,delivered_count,failed_count,error_message,created_at,sent_at",
                    "order": "created_at.desc",
                    "limit": str(min(max(int(limit), 1), 200)),
                },
                timeout=15,
            )
            if response.status_code == 200:
                return response.json()
            logger.error("Notification history query failed: %s", response.text)

        # Keep local development compatible before the Supabase migration is applied.
        conn = get_db_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _create_notification(self, payload):
        url, key = self._supabase_config()
        if not url or not key:
            raise RuntimeError("Supabase service role key is not configured")
        response = requests.post(
            f"{url}/rest/v1/notifications",
            headers=self._supabase_headers(key, return_representation=True),
            json=payload,
            timeout=15,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Notification could not be created: {response.text}")
        return response.json()[0], url, key

    def _recipient_ids(self, url, key, segment, target_user_id):
        params = {
            "select": "id",
            "is_active": "eq.true",
            "is_banned": "eq.false",
            "deleted_at": "is.null",
        }
        if target_user_id:
            params["id"] = f"eq.{target_user_id}"
        elif segment == "premium":
            params["is_premium"] = "eq.true"
        elif segment == "free":
            params["is_premium"] = "eq.false"

        response = requests.get(
            f"{url}/rest/v1/users",
            headers=self._supabase_headers(key),
            params=params,
            timeout=20,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Recipients could not be selected: {response.text}")
        return [row["id"] for row in response.json()]

    def _insert_inboxes(self, url, key, notification_id, user_ids):
        headers = self._supabase_headers(key)
        headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
        for start in range(0, len(user_ids), 500):
            rows = [
                {"notification_id": notification_id, "user_id": user_id}
                for user_id in user_ids[start:start + 500]
            ]
            response = requests.post(
                f"{url}/rest/v1/user_notifications",
                headers=headers,
                json=rows,
                timeout=20,
            )
            if response.status_code not in (200, 201, 204):
                raise RuntimeError(f"Notification inboxes could not be created: {response.text}")

    def _get_devices(self, url, key, user_ids):
        devices = []
        for start in range(0, len(user_ids), 100):
            batch = user_ids[start:start + 100]
            response = requests.get(
                f"{url}/rest/v1/push_devices",
                headers=self._supabase_headers(key),
                params={
                    "select": "id,user_id,platform,token,environment",
                    "is_active": "eq.true",
                    "user_id": f"in.({','.join(batch)})",
                },
                timeout=20,
            )
            if response.status_code != 200:
                raise RuntimeError(f"Push devices could not be selected: {response.text}")
            devices.extend(response.json())
        return devices

    def _get_apns_jwt(self):
        key_id = settings_service.get_value("APNS_KEY_ID")
        team_id = settings_service.get_value("APNS_TEAM_ID")
        private_key = settings_service.get_value("APNS_PRIVATE_KEY")
        if not key_id or not team_id or not private_key:
            return None

        now = int(time.time())
        if self._apns_jwt and now - self._apns_jwt_created_at < 50 * 60:
            return self._apns_jwt

        private_key = private_key.replace("\\n", "\n")
        self._apns_jwt = jwt.encode(
            {"iss": team_id, "iat": now},
            private_key,
            algorithm="ES256",
            headers={"alg": "ES256", "kid": key_id},
        )
        self._apns_jwt_created_at = now
        return self._apns_jwt

    def _send_apns(self, device, title, message, image_url, action_url, notification_id):
        try:
            auth_token = self._get_apns_jwt()
            bundle_id = settings_service.get_value("APNS_BUNDLE_ID", "pro.moneyplan.app")
            if not auth_token or not bundle_id:
                return False, "APNs credentials are not configured", False

            host = (
                "https://api.sandbox.push.apple.com"
                if device.get("environment") == "sandbox"
                else "https://api.push.apple.com"
            )
            payload = {
                "aps": {
                    "alert": {"title": title, "body": message},
                    "sound": "default",
                    "badge": 1,
                },
                "notification_id": notification_id,
            }
            if action_url:
                payload["action_url"] = action_url
            if image_url:
                payload["image_url"] = image_url

            with httpx.Client(http2=True, timeout=15) as client:
                response = client.post(
                    f"{host}/3/device/{device['token']}",
                    headers={
                        "authorization": f"bearer {auth_token}",
                        "apns-topic": bundle_id,
                        "apns-push-type": "alert",
                        "apns-priority": "10",
                    },
                    json=payload,
                )
            if response.status_code == 200:
                return True, None, False
            try:
                reason = response.json().get("reason", f"HTTP {response.status_code}")
            except ValueError:
                reason = f"HTTP {response.status_code}"
            invalid = response.status_code == 410 or reason in {"BadDeviceToken", "Unregistered"}
            return False, reason, invalid
        except Exception as exc:
            return False, str(exc), False

    def _update_delivery(self, url, key, notification_id, user_id, success):
        payload = {"delivery_status": "sent" if success else "failed"}
        if success:
            payload["delivered_at"] = datetime.now(timezone.utc).isoformat()
        requests.patch(
            f"{url}/rest/v1/user_notifications",
            headers=self._supabase_headers(key),
            params={
                "notification_id": f"eq.{notification_id}",
                "user_id": f"eq.{user_id}",
            },
            json=payload,
            timeout=10,
        )

    def send_push(
        self,
        title,
        message,
        image_url=None,
        action_url=None,
        segment="all",
        created_by=None,
    ):
        title = (title or "").strip()
        message = (message or "").strip()
        if not title or not message:
            return False, "Title and message are required"

        target_user_id = None
        normalized_segment = segment
        if segment.startswith("user_"):
            normalized_segment = "user"
            target_user_id = segment.removeprefix("user_")
        if normalized_segment not in {"all", "premium", "free", "user"}:
            return False, "Unsupported target segment"

        try:
            notification, url, key = self._create_notification({
                "title": title[:120],
                "message": message[:500],
                "image_url": image_url or None,
                "action_url": action_url or None,
                "target_segment": normalized_segment,
                "target_user_id": target_user_id,
                "created_by": created_by,
                "status": "sending",
            })
            notification_id = notification["id"]
            user_ids = self._recipient_ids(url, key, normalized_segment, target_user_id)
            self._insert_inboxes(url, key, notification_id, user_ids)

            apns_configured = all([
                settings_service.get_value("APNS_KEY_ID"),
                settings_service.get_value("APNS_TEAM_ID"),
                settings_service.get_value("APNS_PRIVATE_KEY"),
                settings_service.get_value("APNS_BUNDLE_ID"),
            ])
            devices = self._get_devices(url, key, user_ids) if user_ids else []
            sent_users = set()
            failed_devices = 0
            last_error = None
            for device in devices:
                if device.get("platform") != "ios":
                    continue
                success, error, invalid = self._send_apns(
                    device, title, message, image_url, action_url, notification_id
                )
                if success:
                    sent_users.add(device["user_id"])
                else:
                    failed_devices += 1
                    last_error = error
                if invalid:
                    requests.patch(
                        f"{url}/rest/v1/push_devices",
                        headers=self._supabase_headers(key),
                        params={"id": f"eq.{device['id']}"},
                        json={"is_active": False},
                        timeout=10,
                    )

            for user_id in sent_users:
                self._update_delivery(url, key, notification_id, user_id, True)

            if not apns_configured:
                status = "queued"
                info = "In-app inbox created; APNs credentials are not configured yet"
            elif failed_devices:
                status = "partial" if sent_users else "failed"
                info = f"Inbox created; APNs accepted {len(sent_users)} user deliveries"
            else:
                status = "sent"
                info = f"Inbox created for {len(user_ids)} users; APNs accepted {len(sent_users)} deliveries"

            requests.patch(
                f"{url}/rest/v1/notifications",
                headers=self._supabase_headers(key),
                params={"id": f"eq.{notification_id}"},
                json={
                    "status": status,
                    "recipient_count": len(user_ids),
                    "delivered_count": len(sent_users),
                    "failed_count": failed_devices,
                    "error_message": last_error,
                    "sent_at": datetime.now(timezone.utc).isoformat() if status != "queued" else None,
                },
                timeout=10,
            )
            return True, info
        except Exception as exc:
            logger.exception("First-party notification delivery failed")
            return False, str(exc)


notification_service = NotificationService()
