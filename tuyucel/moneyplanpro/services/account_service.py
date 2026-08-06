import requests

from services.settings_service import settings_service
from services.subscription_service import SubscriptionServiceError


class AccountService:
    def delete_account(self, user_id: str) -> dict:
        supabase_url = settings_service.get_value("SUPABASE_URL")
        service_key = settings_service.get_value("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not service_key:
            raise SubscriptionServiceError(
                "Hesap silme servisi yapılandırılmamış", 503
            )

        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

        # Audit rows deliberately use SET NULL for operational retention. For
        # a user-requested hard deletion, remove the user's rows explicitly.
        for field in ("user_id", "admin_id"):
            audit_response = requests.delete(
                f"{supabase_url}/rest/v1/audit_logs",
                headers=headers,
                params={field: f"eq.{user_id}"},
                timeout=10,
            )
            if audit_response.status_code not in {200, 204}:
                raise SubscriptionServiceError(
                    "Hesap geçmişi silinemedi; işlem iptal edildi", 503
                )

        # Deleting auth.users hard-deletes public.users and all owner-scoped
        # financial data through the schema's ON DELETE CASCADE constraints.
        response = requests.delete(
            f"{supabase_url}/auth/v1/admin/users/{user_id}",
            headers=headers,
            params={"should_soft_delete": "false"},
            timeout=15,
        )
        if response.status_code not in {200, 204}:
            raise SubscriptionServiceError("Hesap tamamen silinemedi", 503)
        return {"success": True}


account_service = AccountService()
