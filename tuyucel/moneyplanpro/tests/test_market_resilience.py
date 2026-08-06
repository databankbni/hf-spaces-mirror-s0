from services.crypto_service import CryptoService
from services.feature_flag_service import FeatureFlagService
from services import market_service
from copy import deepcopy
import database
import sys
import types


def test_crypto_identifier_accepts_symbols_and_coingecko_ids():
    service = CryptoService()

    assert service.is_crypto_identifier("BTC")
    assert service.is_crypto_identifier("BTCUSDT")
    assert service.is_crypto_identifier("bitcoin")
    assert service.is_crypto_identifier("ethereum")
    assert not service.is_crypto_identifier("THYAO")


def test_crypto_ticker_contains_only_preferred_crypto_symbols(monkeypatch):
    service = CryptoService()
    coins = [
        {
            "id": "tether",
            "symbol": "USDT",
            "price": 1.0,
            "change_24h": 0.01,
        },
        {
            "id": "bitcoin",
            "symbol": "BTC",
            "price": 100_000.0,
            "change_24h": 1.2,
        },
        {
            "id": "ethereum",
            "symbol": "ETH",
            "price": 4_000.0,
            "change_24h": -0.5,
        },
        {
            "id": "solana",
            "symbol": "SOL",
            "price": 200.0,
            "change_24h": 2.5,
        },
        {
            "id": "binancecoin",
            "symbol": "BNB",
            "price": 700.0,
            "change_24h": 0.8,
        },
        {
            "id": "ripple",
            "symbol": "XRP",
            "price": 3.0,
            "change_24h": -1.0,
        },
    ]
    monkeypatch.setattr(service, "get_top_coins", lambda limit: coins)

    result = service.get_ticker_summary()

    assert result["source"] == "CoinGecko"
    assert [item["symbol"] for item in result["items"]] == [
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "BNB/USD",
        "XRP/USD",
    ]


def test_release_policy_disables_unreviewed_news_and_calendar_once():
    flags = {
        "market_ticker": {
            **deepcopy(FeatureFlagService.DEFAULT_FLAGS["market_ticker"]),
            "metadata": {"source_scope": "approved_market_summary"},
        },
        "market_news": {
            **deepcopy(FeatureFlagService.DEFAULT_FLAGS["market_news"]),
            "is_enabled": True,
            "metadata": {"source_scope": "approved_news"},
        },
        "financial_calendar": {
            **deepcopy(FeatureFlagService.DEFAULT_FLAGS["financial_calendar"]),
            "is_enabled": True,
            "metadata": {"source_scope": "approved_calendar"},
        },
    }

    assert FeatureFlagService._apply_release_policy(flags)
    assert flags["market_ticker"]["is_enabled"]
    assert not flags["market_news"]["is_enabled"]
    assert not flags["financial_calendar"]["is_enabled"]

    flags["market_news"]["is_enabled"] = True
    assert not FeatureFlagService._apply_release_policy(flags)
    assert flags["market_news"]["is_enabled"]


def test_fxstreet_calendar_fallback_requires_its_own_flag(monkeypatch):
    class EmptyCalendarConnection:
        def cursor(self):
            return self

        def execute(self, _query, _params):
            return self

        def fetchall(self):
            return []

        def close(self):
            return None

    provider = market_service.MarketDataProvider()
    monkeypatch.setattr(
        database,
        "get_db_connection",
        lambda: EmptyCalendarConnection(),
    )
    monkeypatch.setattr(
        provider,
        "_generate_fallback_calendar",
        lambda _country: (_ for _ in ()).throw(
            AssertionError("disabled fallback must not run")
        ),
    )
    monkeypatch.setattr(
        provider,
        "_is_fxstreet_calendar_enabled",
        lambda: False,
    )

    assert provider.get_calendar() == []


def test_fxstreet_calendar_fallback_can_be_enabled_later(monkeypatch):
    class EmptyCalendarConnection:
        def cursor(self):
            return self

        def execute(self, _query, _params):
            return self

        def fetchall(self):
            return []

        def close(self):
            return None

    provider = market_service.MarketDataProvider()
    monkeypatch.setattr(
        database,
        "get_db_connection",
        lambda: EmptyCalendarConnection(),
    )
    monkeypatch.setattr(
        provider,
        "_is_fxstreet_calendar_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        provider,
        "_apply_calendar_fallback",
        lambda _events, _country: [{"title": "FXStreet test event"}],
    )

    assert provider.get_calendar() == [{"title": "FXStreet test event"}]


def test_top_funds_omits_unavailable_tefas_rows(monkeypatch):
    provider = market_service.MarketDataProvider()
    monkeypatch.setattr(market_service.cache, "get", lambda _key: None)
    monkeypatch.setattr(
        market_service.cache,
        "set",
        lambda _key, _value, ttl_seconds: None,
    )
    monkeypatch.setattr(
        provider,
        "_get_tefas_data",
        lambda _symbol, _direct_only: None,
    )

    funds = provider.get_top_funds()

    assert funds == []


def test_market_summary_never_manufactures_missing_prices(monkeypatch):
    provider = market_service.MarketDataProvider()
    monkeypatch.setattr(market_service.cache, "get", lambda _key: None)
    monkeypatch.setattr(
        market_service.cache,
        "set",
        lambda _key, _value, ttl_seconds: None,
    )
    monkeypatch.setattr(provider, "_fetch_all_from_mynet", lambda: None)
    monkeypatch.setattr(provider, "_fetch_yahoo", lambda _symbol: None)

    assert provider.get_market_summary() == {}


def test_gram_gold_requires_both_live_inputs():
    provider = market_service.MarketDataProvider()
    result = {}

    provider._calculate_gram_gold_if_needed(result)

    assert result == {}


def test_stock_market_omits_non_positive_prices(monkeypatch):
    class FakeTechnicalAnalysis:
        @staticmethod
        def get_multiple_analysis(_symbols):
            return [
                {"symbol": "AAPL", "price": 0},
                {"symbol": "MSFT", "price": 10},
            ]

    fake_ta_module = types.ModuleType("services.ta_service")
    fake_ta_module.ta_service = FakeTechnicalAnalysis()
    monkeypatch.setitem(sys.modules, "services.ta_service", fake_ta_module)

    fake_twelve_data_module = types.ModuleType("services.twelve_data_service")
    fake_twelve_data_module.twelve_data_service = types.SimpleNamespace(
        get_quotes=lambda _symbols: {},
    )
    monkeypatch.setitem(
        sys.modules,
        "services.twelve_data_service",
        fake_twelve_data_module,
    )

    result = market_service.MarketDataProvider().get_stock_markets()

    assert [item["symbol"] for item in result] == ["MSFT"]
