from fastapi import FastAPI, HTTPException, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
import os
from services.market_service import market_provider
from services.crypto_service import crypto_service
from services.bes_service import bes_service
from services.news_service import news_service
from services.macro_service import macro_service
from services.tcmb_service import tcmb_service
from services.job_service import job_runner
from services.settings_service import settings_service
from services.ad_service import ad_service
from services.notification_service import notification_service
from services.alert_monitor_service import alert_monitor_service
from services.diagnostics_service import diagnostics_service
from services.admin_auth_service import require_admin
from services.user_auth_service import require_user
from services.subscription_service import (
    SubscriptionServiceError,
    subscription_service,
)
from services.account_service import account_service
from services.ai_processing_service import ai_processing_service
from services.feature_flag_service import FeatureFlagService


class ApplePurchaseVerificationRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)
    transaction_id: str = Field(min_length=1, max_length=128)
    verification_data: str | None = Field(default=None, max_length=200000)
    verification_source: str | None = Field(default=None, max_length=64)


class AIProcessingRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=64)
    payload: dict

app = FastAPI(
    title="MoneyPlan Pro Middleware API",
    version="1.1.0"
)


def require_live_market_data():
    if not FeatureFlagService.is_enabled_sync("live_market_data"):
        raise HTTPException(
            status_code=503,
            detail="Live market data is temporarily unavailable.",
        )


def require_crypto_market_data():
    if not FeatureFlagService.is_enabled_sync("crypto_market_data"):
        raise HTTPException(
            status_code=503,
            detail="Crypto market data is temporarily unavailable.",
        )


def require_market_ticker():
    if not FeatureFlagService.is_enabled_sync("market_ticker"):
        raise HTTPException(
            status_code=503,
            detail="Market ticker is temporarily unavailable.",
        )
    require_crypto_market_data()


def require_market_news():
    if not FeatureFlagService.is_enabled_sync("market_news"):
        raise HTTPException(
            status_code=503,
            detail="Market news is temporarily unavailable.",
        )


def require_financial_calendar():
    if not FeatureFlagService.is_enabled_sync("financial_calendar"):
        raise HTTPException(
            status_code=503,
            detail="Financial calendar is temporarily unavailable.",
        )


def require_market_asset_data(symbol: str):
    """Allow CoinGecko-backed crypto detail/chart requests independently."""
    if crypto_service.is_crypto_identifier(symbol):
        require_crypto_market_data()
    else:
        require_live_market_data()


def require_ai_features():
    if not FeatureFlagService.is_enabled_sync("ai_features"):
        raise HTTPException(
            status_code=503,
            detail="AI features are temporarily unavailable.",
        )


@app.on_event("startup")
async def startup_event():
    # Start the price alert monitor in the background
    alert_monitor_service.start()

@app.on_event("shutdown")
async def shutdown_event():
    # Stop the price alert monitor
    alert_monitor_service.stop()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://tuyucel-moneyplanpro.hf.space",
        "*"  # Allow all origins for admin panel
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "active"}


@app.get("/api/v1/health/external")
def get_external_health():
    """
    Dış veri sağlayıcılarının bağlantı durumunu döndürür.
    Şu an yalnızca CoinGecko aktif; BIST/hisse/fon sağlayıcıları
    lisans netleşene kadar devre dışı.
    """
    coingecko_status = diagnostics_service.check_coingecko()
    return {
        "crypto": {
            "coingecko": f"ok — {coingecko_status.get('message', '')}"
            if coingecko_status.get("status") == "ok"
            else f"error — {coingecko_status.get('message', 'unreachable')}",
        },
        "attribution": {
            "provider": "CoinGecko",
            "url": "https://www.coingecko.com/en/api",
            "cache_minutes": 15,
        },
        "disabled_sources": [
            "BIST (lisans bekleniyor)",
            "Fon/BES (sağlayıcı netleşiyor)",
            "Hisse/Forex (sağlayıcı netleşiyor)",
        ],
    }



@app.post("/api/v1/subscriptions/apple/verify")
def verify_apple_subscription(
    purchase: ApplePurchaseVerificationRequest,
    user: dict = Depends(require_user),
):
    try:
        return subscription_service.verify(
            user_id=user["id"],
            requested_product_id=purchase.product_id,
            transaction_id=purchase.transaction_id,
        )
    except SubscriptionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/api/v1/subscriptions/status")
def get_subscription_status(user: dict = Depends(require_user)):
    try:
        return subscription_service.status(user["id"])
    except SubscriptionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.delete("/api/v1/account")
def delete_account(user: dict = Depends(require_user)):
    try:
        return account_service.delete_account(user["id"])
    except SubscriptionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.post(
    "/api/v1/ai/process",
    dependencies=[Depends(require_ai_features)],
)
def process_ai_request(
    request: AIProcessingRequest,
    user: dict = Depends(require_user),
):
    if (
        request.operation == "email"
        and not FeatureFlagService.is_enabled_sync("gmail_import")
    ):
        raise HTTPException(
            status_code=503,
            detail="Gmail import is temporarily unavailable.",
        )
    try:
        return ai_processing_service.process(
            user_id=user["id"],
            access_token=user["_access_token"],
            operation=request.operation,
            payload=request.payload,
        )
    except SubscriptionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

@app.get("/api/v1/system/diagnostics")
def get_diagnostics():
    return diagnostics_service.check_all()

@app.get("/api/v1/config/client")
def get_client_config():
    """Provide runtime configuration for admin panel"""
    return {
        "supabase_url": settings_service.get_value("SUPABASE_URL"),
        "supabase_anon_key": settings_service.get_value("SUPABASE_ANON_KEY"),
        "app_name": "MoneyPlan Pro Admin Panel",
        "app_version": "1.0.0"
    }

@app.get(
    "/api/v1/market/summary",
    dependencies=[Depends(require_market_ticker)],
)
def get_market_summary():
    return crypto_service.get_ticker_summary()

@app.get(
    "/api/v1/market/history/{symbol}",
    dependencies=[Depends(require_market_asset_data)],
)
def get_market_history(symbol: str, period: str = "1mo", interval: str = "1d"):
    """
    GRAFİK VERİSİ: Dinamik yönlendirme (Crypto -> CoinGecko, Stocks -> MarketProvider)
    """
    if crypto_service.is_crypto_identifier(symbol):
        return crypto_service.get_history(symbol, period, interval)
        
    return market_provider.get_history(symbol, period, interval)

@app.get(
    "/api/v1/market/detail/{symbol}",
    dependencies=[Depends(require_market_asset_data)],
)
def get_asset_detail(symbol: str):
    """
    DETAY VERİSİ: Dinamik yönlendirme (Crypto -> CoinGecko, Stocks -> MarketProvider)
    """
    # Crypto Check
    if crypto_service.is_crypto_identifier(symbol):
        return crypto_service.get_asset_detail(symbol)
    
    # Stocks, Forex, Gold -> MarketProvider (Yahoo)
    return market_provider.get_asset_detail(symbol)

@app.get(
    "/api/v1/market/analysis/{symbol}",
    dependencies=[Depends(require_live_market_data)],
)
def get_asset_analysis(symbol: str):
    """
    TEKNİK ANALİZ VERİSİ (TradingView)
    Al/Sat Sinyalleri, RSI, MACD, MA vb.
    """
    return market_provider.get_analysis(symbol)

@app.get(
    "/api/v1/market/stocks",
    dependencies=[Depends(require_live_market_data)],
)
def get_stock_markets():
    return market_provider.get_stock_markets()

@app.get(
    "/api/v1/market/commodities",
    dependencies=[Depends(require_live_market_data)],
)
def get_commodity_markets():
    return market_provider.get_commodity_markets()

@app.get(
    "/api/v1/market/etfs",
    dependencies=[Depends(require_live_market_data)],
)
def get_etf_markets():
    return market_provider.get_etf_markets()

@app.get(
    "/api/v1/market/bonds",
    dependencies=[Depends(require_live_market_data)],
)
def get_bond_markets():
    return market_provider.get_bond_markets()

@app.get(
    "/api/v1/market/calendar",
    dependencies=[Depends(require_financial_calendar)],
)
def get_market_calendar(country_code: str = "ALL"):
    return market_provider.get_calendar(country_code)

@app.post("/api/v1/market/calendar")
def upload_market_calendar(
    events: list = Body(..., embed=True),
    clear: bool = False,
    admin: dict = Depends(require_admin),
):
    """
    MANUEL TAKVİM YÜKLEME:
    Haftalık verileri JSON olarak yükler.
    clear=True ise mevcut verileri siler.
    """
    if clear:
        from database import get_db_connection
        conn = get_db_connection()
        conn.execute("DELETE FROM calendar_events")
        conn.commit()
        conn.close()
        
    success = market_provider.save_calendar_events(events)
    if not success:
        raise HTTPException(status_code=500, detail="Veriler kaydedilemedi")
    return {"status": "success", "count": len(events)}


@app.get("/api/v1/system/calendar")
def list_calendar_events(
    limit: int = 200,
    admin: dict = Depends(require_admin),
):
    from database import get_db_connection
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM calendar_events ORDER BY date_time DESC LIMIT ?",
            (min(max(limit, 1), 1000),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.delete("/api/v1/system/calendar/{event_id}")
def delete_calendar_event(
    event_id: int,
    admin: dict = Depends(require_admin),
):
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Calendar event not found")
        return {"status": "success"}
    finally:
        conn.close()

@app.get(
    "/api/v1/market/crypto",
    dependencies=[Depends(require_crypto_market_data)],
)
def get_crypto_markets(limit: int = 50):
    return crypto_service.get_top_coins(limit)

@app.get(
    "/api/v1/market/crypto/fear-greed",
    dependencies=[Depends(require_live_market_data)],
)
def get_crypto_fear_greed():
    return crypto_service.get_fear_greed_index()

@app.get(
    "/api/v1/funds/top",
    dependencies=[Depends(require_live_market_data)],
)
def get_top_funds():
    return market_provider.get_top_funds()

@app.get(
    "/api/v1/funds/bes/top",
    dependencies=[Depends(require_live_market_data)],
)
def get_bes_funds():
    return bes_service.get_top_pension_funds()

@app.get(
    "/api/v1/currencies/tcmb",
    dependencies=[Depends(require_live_market_data)],
)
def get_tcmb_rates():
    return market_provider.get_tcmb_currencies()

@app.get(
    "/api/v1/news",
    dependencies=[Depends(require_market_news)],
)
def get_latest_news(limit: int = 20):
    return news_service.get_latest_news(limit)

@app.get(
    "/api/v1/macro/{country_code}",
    dependencies=[Depends(require_live_market_data)],
)
def get_macro_indicators(country_code: str):
    """
    Fetches macro-economic indicators (GDP, Inflation, etc.).
    Uses TCMB/TUIK data for 'TR', World Bank for others.
    """
    if country_code.upper() == "TR":
        # Türkiye için özel TCMB/TÜİK verisi
        tcmb_data = tcmb_service.get_macro_indicators()
        if tcmb_data:
            return {
                "country": "TR",
                "timestamp": tcmb_data.get("date"), # veya now
                "data": tcmb_data,
                "source": "TCMB & TÜİK (Güncel)"
            }
    
    # Diğer ülkeler veya TR fallback için World Bank
    return macro_service.get_country_indicators(country_code)

# --- SYSTEM MANAGEMENT ENDPOINTS ---

@app.get("/api/v1/system/jobs")
def list_jobs(admin: dict = Depends(require_admin)):
    return job_runner.get_all_jobs()

@app.post("/api/v1/system/jobs/{job_id}/run")
def run_job(job_id: str, admin: dict = Depends(require_admin)):
    success, message = job_runner.run_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "success", "message": message}

@app.put("/api/v1/system/jobs/{job_id}")
def update_job(
    job_id: str,
    updates: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    success, message = job_runner.update_job_definition(job_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"status": "success", "message": message}

@app.get("/api/v1/system/settings")
def get_settings(admin: dict = Depends(require_admin)):
    return settings_service.get_all()

@app.post("/api/v1/system/settings/{key}")
def update_setting(
    key: str,
    value: str = Body(..., embed=True),
    admin: dict = Depends(require_admin),
):
    if not settings_service.update(key, value):
        raise HTTPException(
            status_code=400,
            detail="Unknown setting or empty secret value.",
        )
    return {"status": "success"}

# --- AD MANAGEMENT ENDPOINTS ---

@app.get("/api/v1/ads/config")
def get_ads_config():
    """Mobile app consumption: returns active ad unit IDs"""
    return ad_service.get_active_ads_for_app()

@app.get("/api/v1/system/ads")
def list_ads(admin: dict = Depends(require_admin)):
    """Admin panel: returns full placement list"""
    return ad_service.get_all_placements()

@app.put("/api/v1/system/ads/{placement_id}")
def update_ad_placement(
    placement_id: int,
    updates: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """Admin panel: update ad configuration"""
    success, message = ad_service.update_placement(placement_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"status": "success", "message": message}

# --- NOTIFICATION ENDPOINTS ---

@app.get("/api/v1/system/notifications")
def list_notifications(limit: int = 50, admin: dict = Depends(require_admin)):
    return notification_service.get_history(limit)

@app.post("/api/v1/system/notifications/send")
def send_notification(payload: dict = Body(...), admin: dict = Depends(require_admin)):
    """
    Payload: {title, message, image_url?, action_url?, segment?}
    """
    success, message = notification_service.send_push(
        title=payload.get("title"),
        message=payload.get("message"),
        image_url=payload.get("image_url"),
        action_url=payload.get("action_url"),
        segment=payload.get("segment", "all"),
        created_by=admin["id"],
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "success", "message": message}

# --- FEATURE FLAGS ENDPOINTS ---

@app.get("/api/v1/features")
async def get_feature_flags():
    """Get all feature flags for the app"""
    from services.feature_flag_service import FeatureFlagService
    return await FeatureFlagService.get_all_flags()

@app.get("/api/v1/features/{flag_id}")
async def get_feature_flag(flag_id: str):
    """Get a specific feature flag"""
    from services.feature_flag_service import FeatureFlagService
    flag = await FeatureFlagService.get_flag(flag_id)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return flag

@app.patch("/api/v1/features/{flag_id}")
async def update_feature_flag(
    flag_id: str,
    updates: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """Update a feature flag (Admin only)"""
    from services.feature_flag_service import FeatureFlagService
    flag = await FeatureFlagService.update_flag(flag_id, updates)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return {"status": "success", "flag": flag}

@app.post("/api/v1/features/check")
async def check_feature_availability(payload: dict = Body(...)):
    """Check if a feature is available for a user"""
    from services.feature_flag_service import FeatureFlagService
    flag_id = payload.get("flag_id")
    is_pro_user = payload.get("is_pro_user", False)
    
    if not flag_id:
        raise HTTPException(status_code=400, detail="flag_id is required")
    
    is_available = await FeatureFlagService.is_feature_available(flag_id, is_pro_user)
    return {"flag_id": flag_id, "is_available": is_available}

# --- PRICING & PROMOTIONS ENDPOINTS ---

@app.get("/api/v1/pricing")
async def get_pricing_config():
    """Get current pricing and promotion configuration"""
    from services.pricing_service import PricingService
    return await PricingService.get_pricing()

@app.patch("/api/v1/pricing")
async def update_pricing_config(
    updates: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """Update pricing configuration (Admin only)"""
    from services.pricing_service import PricingService
    return await PricingService.update_pricing(updates)

@app.post("/api/v1/pricing/validate-promo")
async def validate_promo_code(payload: dict = Body(...)):
    """Validate a promo code"""
    from services.pricing_service import PricingService
    code = payload.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    return await PricingService.validate_promo_code(code)

@app.get("/api/v1/pricing/effective/{tier}")
async def get_effective_price(tier: str):
    """Get effective price after discounts for a tier (monthly/yearly)"""
    from services.pricing_service import PricingService
    if tier not in ["monthly", "yearly"]:
        raise HTTPException(status_code=400, detail="tier must be 'monthly' or 'yearly'")
    return await PricingService.get_effective_price(tier)

# --- NOTIFICATIONS & ANNOUNCEMENTS ENDPOINTS ---

@app.get("/api/v1/notifications/config")
async def get_notification_config():
    """Get current notification and announcement configuration"""
    from services.notification_config_service import NotificationConfigService
    return await NotificationConfigService.get_config()

@app.patch("/api/v1/notifications/config")
async def update_notification_config(
    updates: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """Update notification configuration (Admin only)"""
    from services.notification_config_service import NotificationConfigService
    return await NotificationConfigService.update_config(updates)

@app.post("/api/v1/notifications/check-version")
async def check_version_requirement(payload: dict = Body(...)):
    """Check if app version meets minimum requirement"""
    from services.notification_config_service import NotificationConfigService
    version = payload.get("version")
    if not version:
        raise HTTPException(status_code=400, detail="version is required")
    return await NotificationConfigService.check_version_requirement(version)

# --- LIMITS & RESTRICTIONS ENDPOINTS ---

@app.get("/api/v1/limits/config")
async def get_limits_config():
    """Get current limits configuration"""
    from services.limits_service import LimitsService
    return await LimitsService.get_config()

@app.patch("/api/v1/limits/config")
async def update_limits_config(
    updates: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """Update limits configuration (Admin only)"""
    from services.limits_service import LimitsService
    return await LimitsService.update_config(updates)

@app.get("/api/v1/limits/tier/{is_pro}")
async def get_tier_limits(is_pro: bool):
    """Get limits for a specific tier (free/pro)"""
    from services.limits_service import LimitsService
    return await LimitsService.get_tier_limits(is_pro)

@app.post("/api/v1/limits/check")
async def check_limit(payload: dict = Body(...)):
    """Check if user has reached a specific limit"""
    from services.limits_service import LimitsService
    is_pro = payload.get("is_pro", False)
    limit_type = payload.get("limit_type")  # transactions, portfolios, alerts, etc.
    current_count = payload.get("current_count", 0)
    
    if not limit_type:
        raise HTTPException(status_code=400, detail="limit_type is required")
    
    return await LimitsService.check_limit(is_pro, limit_type, current_count)

# --- UI & THEME CONFIGURATION ENDPOINTS ---

@app.get("/api/v1/ui/config")
async def get_ui_config():
    """Get current UI/UX theme and layout configuration"""
    from services.ui_config_service import UIConfigService
    return await UIConfigService.get_config()

@app.patch("/api/v1/ui/config")
async def update_ui_config(
    updates: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """Update UI configuration (Admin only)"""
    from services.ui_config_service import UIConfigService
    return await UIConfigService.update_config(updates)

# --- PRICE ALERTS ENDPOINTS ---

@app.get("/api/v1/system/alerts")
def list_system_alerts(
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM price_alerts ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    alerts = [dict(row) for row in rows]
    conn.close()
    return alerts

@app.post("/api/v1/system/alerts")
def create_alert(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """
    Payload: {user_id, symbol, target_price, is_above}
    """
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO price_alerts (user_id, symbol, target_price, is_above)
        VALUES (?, ?, ?, ?)
    """, (payload["user_id"], payload["symbol"].upper(), payload["target_price"], payload.get("is_above", 1)))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/v1/system/alerts/{alert_id}")
def delete_alert(alert_id: int, admin: dict = Depends(require_admin)):
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        return response


# The HF image places the built React dashboard here. Keep this mount last.
if os.path.isdir("admin-dist"):
    app.mount("/admin", SPAStaticFiles(directory="admin-dist", html=True), name="admin")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
