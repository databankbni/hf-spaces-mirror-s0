import base64
import json
from datetime import datetime, timezone

import requests
from appstoreserverlibrary.api_client import AppStoreServerAPIClient
from appstoreserverlibrary.models.Environment import Environment

from services.settings_service import settings_service


ALLOWED_PRODUCT_IDS = {
    "pro.moneyplan.app.pro.monthly",
    "pro.moneyplan.app.pro.yearly",
}


class SubscriptionServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class SubscriptionService:
    def _supabase_config(self):
        url = settings_service.get_value("SUPABASE_URL")
        service_key = settings_service.get_value("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not service_key:
            raise SubscriptionServiceError(
                "Abonelik veritabanı yapılandırılmamış", 503
            )
        return url, service_key

    def _rest_headers(self, service_key: str, prefer: str | None = None):
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _apple_client(self, environment: Environment):
        key_id = settings_service.get_value("APPLE_IAP_KEY_ID")
        issuer_id = settings_service.get_value("APPLE_IAP_ISSUER_ID")
        private_key = settings_service.get_value("APPLE_IAP_PRIVATE_KEY")
        bundle_id = settings_service.get_value(
            "APPLE_IAP_BUNDLE_ID", "pro.moneyplan.app"
        )
        if not key_id or not issuer_id or not private_key:
            raise SubscriptionServiceError(
                "App Store sunucu doğrulaması henüz yapılandırılmamış", 503
            )

        normalized_key = private_key.replace("\\n", "\n")
        return AppStoreServerAPIClient(
            normalized_key.encode("utf-8"),
            key_id,
            issuer_id,
            bundle_id,
            environment,
        )

    def _fetch_signed_transaction(self, transaction_id: str):
        last_error = None
        for environment in (Environment.PRODUCTION, Environment.SANDBOX):
            try:
                response = self._apple_client(environment).get_transaction_info(
                    transaction_id
                )
                return response.signedTransactionInfo, environment
            except SubscriptionServiceError:
                raise
            except Exception as exc:
                last_error = exc
        raise SubscriptionServiceError(
            "İşlem Apple tarafından doğrulanamadı", 422
        ) from last_error

    def _decode_jws_payload(self, signed_value: str) -> dict:
        try:
            payload = signed_value.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        except (IndexError, ValueError, json.JSONDecodeError) as exc:
            raise SubscriptionServiceError(
                "Apple işlem yanıtı okunamadı", 422
            ) from exc

    @staticmethod
    def _date_from_millis(value):
        if value is None:
            return None
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)

    @staticmethod
    def _iso(value: datetime | None):
        return value.isoformat() if value else None

    def verify(
        self,
        user_id: str,
        requested_product_id: str,
        transaction_id: str,
    ) -> dict:
        if requested_product_id not in ALLOWED_PRODUCT_IDS:
            raise SubscriptionServiceError("Bilinmeyen App Store ürünü")
        if not transaction_id or len(transaction_id) > 128:
            raise SubscriptionServiceError("Geçersiz App Store işlem numarası")

        signed_transaction, queried_environment = self._fetch_signed_transaction(
            transaction_id
        )
        transaction = self._decode_jws_payload(signed_transaction)

        product_id = transaction.get("productId")
        verified_transaction_id = str(transaction.get("transactionId") or "")
        original_transaction_id = str(
            transaction.get("originalTransactionId") or ""
        )
        bundle_id = transaction.get("bundleId")
        app_account_token = transaction.get("appAccountToken")
        expected_bundle_id = settings_service.get_value(
            "APPLE_IAP_BUNDLE_ID", "pro.moneyplan.app"
        )

        if (
            product_id != requested_product_id
            or product_id not in ALLOWED_PRODUCT_IDS
            or verified_transaction_id != transaction_id
            or not original_transaction_id
            or bundle_id != expected_bundle_id
        ):
            raise SubscriptionServiceError("Apple işlem bilgileri eşleşmiyor", 422)
        if app_account_token and str(app_account_token).lower() != user_id.lower():
            raise SubscriptionServiceError(
                "Bu satın alma başka bir kullanıcıya ait", 409
            )

        purchased_at = self._date_from_millis(transaction.get("purchaseDate"))
        expires_at = self._date_from_millis(transaction.get("expiresDate"))
        revoked_at = self._date_from_millis(transaction.get("revocationDate"))
        if expires_at is None:
            raise SubscriptionServiceError("Abonelik bitiş tarihi bulunamadı", 422)

        now = datetime.now(timezone.utc)
        active = revoked_at is None and expires_at > now
        status = "revoked" if revoked_at else ("active" if active else "expired")
        environment = transaction.get("environment")
        if environment not in {"Production", "Sandbox"}:
            environment = (
                "Production"
                if queried_environment == Environment.PRODUCTION
                else "Sandbox"
            )

        supabase_url, service_key = self._supabase_config()
        existing = requests.get(
            f"{supabase_url}/rest/v1/user_subscriptions",
            headers=self._rest_headers(service_key),
            params={
                "provider": "eq.apple",
                "original_transaction_id": f"eq.{original_transaction_id}",
                "select": "user_id",
                "limit": "1",
            },
            timeout=10,
        )
        if existing.status_code != 200:
            raise SubscriptionServiceError("Abonelik kaydı kontrol edilemedi", 503)
        rows = existing.json()
        if rows and rows[0]["user_id"] != user_id:
            raise SubscriptionServiceError(
                "Bu abonelik başka bir hesaba bağlı", 409
            )

        record = {
            "user_id": user_id,
            "provider": "apple",
            "product_id": product_id,
            "transaction_id": verified_transaction_id,
            "original_transaction_id": original_transaction_id,
            "status": status,
            "environment": environment,
            "purchased_at": self._iso(purchased_at),
            "expires_at": self._iso(expires_at),
            "revoked_at": self._iso(revoked_at),
            "raw_transaction": transaction,
        }
        saved = requests.post(
            f"{supabase_url}/rest/v1/user_subscriptions",
            headers=self._rest_headers(
                service_key, "resolution=merge-duplicates,return=representation"
            ),
            params={"on_conflict": "provider,original_transaction_id"},
            json=record,
            timeout=10,
        )
        if saved.status_code not in {200, 201}:
            raise SubscriptionServiceError("Abonelik kaydedilemedi", 503)

        self._update_profile_entitlement(
            supabase_url, service_key, user_id, active, purchased_at, expires_at
        )
        return {
            "active": active,
            "product_id": product_id,
            "expires_at": self._iso(expires_at),
            "environment": environment,
        }

    def status(self, user_id: str) -> dict:
        supabase_url, service_key = self._supabase_config()
        response = requests.get(
            f"{supabase_url}/rest/v1/user_subscriptions",
            headers=self._rest_headers(service_key),
            params={
                "user_id": f"eq.{user_id}",
                "select": "product_id,status,expires_at,environment",
                "order": "expires_at.desc",
                "limit": "1",
            },
            timeout=10,
        )
        profile_response = requests.get(
            f"{supabase_url}/rest/v1/users",
            headers={
                **self._rest_headers(service_key),
                "Accept": "application/vnd.pgrst.object+json",
            },
            params={"id": f"eq.{user_id}", "select": "role"},
            timeout=10,
        )
        if response.status_code != 200 or profile_response.status_code != 200:
            raise SubscriptionServiceError("Abonelik durumu alınamadı", 503)

        rows = response.json()
        profile = profile_response.json()
        if not rows:
            active = profile.get("role") in {"admin", "super_admin"}
            admin_expiry = (
                datetime(2100, 1, 1, tzinfo=timezone.utc) if active else None
            )
            return {
                "active": active,
                "product_id": None,
                "expires_at": self._iso(admin_expiry),
            }

        row = rows[0]
        expires_at = datetime.fromisoformat(
            row["expires_at"].replace("Z", "+00:00")
        )
        active = (
            row["status"] == "active"
            and expires_at > datetime.now(timezone.utc)
        )
        if profile.get("role") in {"admin", "super_admin"}:
            active = True
        self._update_profile_entitlement(
            supabase_url, service_key, user_id, active, None, expires_at
        )
        return {
            "active": active,
            "product_id": row["product_id"],
            "expires_at": self._iso(expires_at) if active else None,
            "environment": row["environment"],
        }

    def _update_profile_entitlement(
        self,
        supabase_url: str,
        service_key: str,
        user_id: str,
        active: bool,
        purchased_at: datetime | None,
        expires_at: datetime | None,
    ):
        payload = {
            "is_premium": active,
            "premium_expires_at": self._iso(expires_at),
        }
        if purchased_at:
            payload["premium_started_at"] = self._iso(purchased_at)
        response = requests.patch(
            f"{supabase_url}/rest/v1/users",
            headers=self._rest_headers(service_key),
            params={"id": f"eq.{user_id}"},
            json=payload,
            timeout=10,
        )
        if response.status_code not in {200, 204}:
            raise SubscriptionServiceError("Pro erişimi güncellenemedi", 503)


subscription_service = SubscriptionService()
