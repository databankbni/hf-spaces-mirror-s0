from __future__ import annotations

import csv
import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any


NO_RANKING_EVIDENCE = "暂无匹配榜单证据"
FORBIDDEN_PRICE_FIELDS = {
    "suggested_purchase_price",
    "suggested_sale_price",
    "expected_transaction_price",
    "gross_profit",
    "gross_margin_rate",
    "chase_price_ceiling",
    "final_decision",
}

FILTER_LEVEL_PRIORITY = {
    "high_freq_quad": 5,
    "triple": 4,
    "pair": 3,
    "single": 2,
    "default": 1,
}

_SQL_SIGNAL_COLUMNS = (
    "signal_id",
    "rank_type",
    "signal_type",
    "scope_type",
    "filter_level",
    "filter_signature",
    "city",
    "brand",
    "series_name",
    "vehicle_category",
    "energy_type",
    "price_band",
    "month",
    "rank",
    "metric_name",
    "metric_value",
    "signal_strength",
    "evidence_text",
    "source_snapshot_date",
    "raw_record_id",
    "crawl_job_id",
)


class RankingSignalService:
    def __init__(self, signals_path: str | Path | None = None) -> None:
        self.signals_path = Path(signals_path) if signals_path else _default_signals_path()
        bundled_sqlite = _default_bundled_sqlite_path() if not self.signals_path.exists() else None
        self._use_sqlite = bool(
            bundled_sqlite
            or (
                self.signals_path.suffix.lower() == ".csv"
                and self.signals_path.exists()
                and self.signals_path.stat().st_size >= 5_000_000
            )
        )
        self._sqlite_path: Path | None = bundled_sqlite
        self._signals: list[dict[str, Any]] | None = None
        self._rank_index: dict[str, list[dict[str, Any]]] | None = None
        self._series_index: dict[tuple[str, str], list[dict[str, Any]]] | None = None
        self._brand_index: dict[tuple[str, str], list[dict[str, Any]]] | None = None
        self._query_cache: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        self._selection_score_cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    @property
    def signals(self) -> list[dict[str, Any]]:
        if self._signals is None:
            self._signals = _load_records(self.signals_path)
        return self._signals

    def _ensure_indexes(self) -> None:
        if self._rank_index is not None:
            return
        rank_index: dict[str, list[dict[str, Any]]] = {}
        series_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        brand_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in self.signals:
            rank_type = str(row.get("rank_type") or "")
            rank_index.setdefault(rank_type, []).append(row)
            series_key = _norm(row.get("series_name"))
            brand_key = _norm(row.get("brand")) or _norm(row.get("brand_name"))
            if series_key:
                series_index.setdefault((rank_type, series_key), []).append(row)
            if brand_key:
                brand_index.setdefault((rank_type, brand_key), []).append(row)
        self._rank_index = rank_index
        self._series_index = series_index
        self._brand_index = brand_index

    def _candidate_rows(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        if self._use_sqlite:
            return self._sqlite_candidate_rows(query)
        self._ensure_indexes()
        rank_type = str(query.get("rank_type") or "")
        series_key = _norm(query.get("series_name"))
        brand_key = _norm(query.get("brand"))
        if series_key and self._series_index is not None:
            exact = self._series_index.get((rank_type, series_key))
            if exact:
                return exact
        if brand_key and self._brand_index is not None:
            exact = self._brand_index.get((rank_type, brand_key))
            if exact:
                return exact
        if self._rank_index is not None and rank_type:
            return self._rank_index.get(rank_type, [])
        return self.signals

    def _sqlite_candidate_rows(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        db_path = self._ensure_sqlite_index()
        rank_type = str(query.get("rank_type") or "")
        series_key = _norm(query.get("series_name"))
        brand_key = _norm(query.get("brand"))
        base_where = ["rank_type = ?"] if rank_type else []
        base_params: list[Any] = [rank_type] if rank_type else []

        def fetch(extra_where: list[str], extra_params: list[Any], *, limit: int = 5000) -> list[dict[str, Any]]:
            where = base_where + extra_where
            sql = "SELECT " + ",".join(_SQL_SIGNAL_COLUMNS) + " FROM ranking_signals"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += (
                " ORDER BY CASE filter_level "
                "WHEN 'high_freq_quad' THEN 5 WHEN 'triple' THEN 4 WHEN 'pair' THEN 3 "
                "WHEN 'single' THEN 2 WHEN 'default' THEN 1 ELSE 0 END DESC, "
                "CAST(rank AS INTEGER) ASC LIMIT ?"
            )
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                records = connection.execute(sql, [*base_params, *extra_params, limit]).fetchall()
            return [dict(record) for record in records]

        if series_key:
            exact = fetch(["series_key = ?"], [series_key])
            if exact:
                return exact
        if brand_key:
            exact = fetch(["brand_key = ?"], [brand_key])
            if exact:
                return exact
        return fetch([], [])

    def _ensure_sqlite_index(self) -> Path:
        if self._sqlite_path is not None and self._sqlite_path.exists():
            return self._sqlite_path
        stat = self.signals_path.stat()
        token = f"{self.signals_path.stem}_{stat.st_size}_{stat.st_mtime_ns}"
        root = Path(__file__).resolve().parents[1] / "runtime" / "ranking_signal_index"
        root.mkdir(parents=True, exist_ok=True)
        db_path = root / f"{token}.sqlite3"
        if db_path.exists():
            self._sqlite_path = db_path
            return db_path
        tmp_path = root / f".{token}.{id(self)}.tmp.sqlite3"
        if tmp_path.exists():
            tmp_path.unlink()
        try:
            with sqlite3.connect(tmp_path) as connection:
                connection.execute("PRAGMA journal_mode=OFF")
                connection.execute("PRAGMA synchronous=OFF")
                connection.execute("PRAGMA temp_store=MEMORY")
                column_sql = ",".join(f'"{column}" TEXT' for column in _SQL_SIGNAL_COLUMNS)
                connection.execute(
                    f"CREATE TABLE ranking_signals ({column_sql}, series_key TEXT, brand_key TEXT)"
                )
                placeholders = ",".join("?" for _ in range(len(_SQL_SIGNAL_COLUMNS) + 2))
                insert_sql = f"INSERT INTO ranking_signals VALUES ({placeholders})"
                batch: list[tuple[Any, ...]] = []
                with self.signals_path.open(encoding="utf-8-sig", newline="") as handle:
                    for row in csv.DictReader(handle):
                        batch.append(
                            tuple(row.get(column) for column in _SQL_SIGNAL_COLUMNS)
                            + (_norm(row.get("series_name")), _norm(row.get("brand")))
                        )
                        if len(batch) >= 5000:
                            connection.executemany(insert_sql, batch)
                            batch.clear()
                    if batch:
                        connection.executemany(insert_sql, batch)
                connection.execute(
                    "CREATE INDEX idx_ranking_series ON ranking_signals(rank_type, series_key)"
                )
                connection.execute(
                    "CREATE INDEX idx_ranking_brand ON ranking_signals(rank_type, brand_key)"
                )
                connection.execute("CREATE INDEX idx_ranking_type ON ranking_signals(rank_type)")
                connection.commit()
            try:
                tmp_path.replace(db_path)
            except FileExistsError:
                tmp_path.unlink(missing_ok=True)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        self._sqlite_path = db_path
        return db_path

    def query_ranking_evidence(
        self,
        *,
        rank_type: str | None = None,
        city: str | None = None,
        brand: str | None = None,
        series: str | None = None,
        vehicle_category: str | None = None,
        energy_type: str | None = None,
        price_band: str | None = None,
        month: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        cache_key = (
            rank_type,
            city,
            brand,
            series,
            vehicle_category,
            energy_type,
            price_band,
            month,
            int(limit or 5),
        )
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]
        query = {
            "rank_type": rank_type,
            "city": city,
            "brand": brand,
            "series_name": series,
            "vehicle_category": vehicle_category,
            "energy_type": energy_type,
            "price_band": price_band,
            "month": month,
        }
        rows: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
        for row in self._candidate_rows(query):
            if not _matches(row, query):
                continue
            priority = FILTER_LEVEL_PRIORITY.get(str(row.get("filter_level") or ""), 0)
            specificity = _specificity(row, query)
            rank = _safe_int(row.get("rank")) or 9999
            # A requested dimension must beat an unrelated, more complex
            # crawler slice.  Previously a high_freq_quad row from another
            # city/brand could outrank an exact national or energy slice.
            rows.append(((specificity, priority, -rank), row))
        rows.sort(key=lambda item: item[0], reverse=True)
        evidence = [self._to_evidence(row) for _, row in rows[: max(1, int(limit or 5))]]
        if evidence:
            self._query_cache[cache_key] = evidence
            return evidence
        evidence = [{"evidence_text": NO_RANKING_EVIDENCE, "business_interpretation": NO_RANKING_EVIDENCE}]
        self._query_cache[cache_key] = evidence
        return evidence

    def get_discount_risk_evidence(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.query_ranking_evidence(rank_type="降价榜", **kwargs)

    def get_city_preference_evidence(self, **kwargs: Any) -> list[dict[str, Any]]:
        evidence = self.query_ranking_evidence(rank_type="城市榜", **kwargs)
        if evidence and evidence[0].get("evidence_text") != NO_RANKING_EVIDENCE:
            return evidence
        return self.query_ranking_evidence(rank_type="热门榜", **kwargs)

    def get_sales_liquidity_evidence(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.query_ranking_evidence(rank_type="销量榜", **kwargs)

    def get_popularity_evidence(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.query_ranking_evidence(rank_type="热门榜", **kwargs)

    def ranking_board(
        self,
        *,
        rank_type: str,
        filters: dict[str, Any] | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Build one coherent ranking board from materialized filter slices.

        Ranking evidence is crawled as separate filter boards.  Returning the
        globally most specific records mixes many unrelated rank-1 rows.  For
        the user-facing board we keep one base board (national or city), then
        intersect the series sets from every requested filter slice and retain
        the base-board order.  This makes combinations deterministic without
        pretending a cross-filter rank was directly published when it was not.
        """

        selected = {
            str(key): str(value).strip()
            for key, value in (filters or {}).items()
            if value not in (None, "", "全部")
        }
        db_path = self._ensure_sqlite_index()

        def fetch_signature(connection: sqlite3.Connection, signature: str) -> list[dict[str, Any]]:
            sql = (
                "SELECT " + ",".join(_SQL_SIGNAL_COLUMNS) +
                " FROM ranking_signals WHERE rank_type = ? AND filter_signature = ? "
                "ORDER BY CAST(rank AS INTEGER) ASC"
            )
            return [dict(row) for row in connection.execute(sql, [rank_type, signature]).fetchall()]

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            city = selected.pop("city", "全国")
            base_signature = f"city={city}" if city else "default"
            base_rows = fetch_signature(connection, base_signature)
            if not base_rows:
                base_signature = "default"
                base_rows = fetch_signature(connection, base_signature)

            eligible: set[str] | None = None
            applied_slices: list[str] = []
            for key, value in selected.items():
                signature = f"{key}={value}"
                slice_rows = fetch_signature(connection, signature)
                if not slice_rows:
                    continue
                names = {_norm(row.get("series_name")) for row in slice_rows if _norm(row.get("series_name"))}
                eligible = names if eligible is None else eligible & names
                applied_slices.append(signature)

        if eligible is not None:
            base_rows = [row for row in base_rows if _norm(row.get("series_name")) in eligible]
        output: list[dict[str, Any]] = []
        for board_rank, row in enumerate(base_rows[: max(1, int(limit or 30))], start=1):
            item = self._to_evidence(row)
            item["board_rank"] = board_rank
            item["published_rank"] = _safe_int(row.get("rank"))
            item["base_filter_signature"] = base_signature
            item["applied_filter_slices"] = list(applied_slices)
            output.append(item)
        return output

    def selection_signal_score(
        self,
        *,
        city: str | None = None,
        brand: str | None = None,
        series: str | None = None,
        vehicle_category: str | None = None,
        energy_type: str | None = None,
        price_band: str | None = None,
    ) -> dict[str, Any]:
        cache_key = (city, brand, series, vehicle_category, energy_type, price_band)
        if cache_key in self._selection_score_cache:
            return dict(self._selection_score_cache[cache_key])
        kwargs = {
            "city": city,
            "brand": brand,
            "series": series,
            "vehicle_category": vehicle_category,
            "energy_type": energy_type,
            "price_band": price_band,
            "limit": 1,
        }
        buckets = {
            rank_type: self.query_ranking_evidence(rank_type=rank_type, **kwargs)
            for rank_type in ("销量榜", "热门榜", "城市榜", "降价榜")
        }

        result = _selection_score_from_buckets(buckets)
        self._selection_score_cache[cache_key] = result
        return dict(result)

    def selection_signal_scores_bulk(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resolve series-level selection signals in one SQLite pass.

        A full selection board can contain hundreds of candidates. Opening the
        ranking SQLite database four times for every row made an uncached board
        take tens of seconds. This method preserves the same evidence matching
        and sorting rules for exact series hits, but batches all requested
        series and returns results in input order. Missing exact-series evidence
        stays neutral instead of borrowing an unrelated brand/global ranking.
        """
        if not requests:
            return []
        if not self._use_sqlite:
            return [self.selection_signal_score(**request) for request in requests]

        results: list[dict[str, Any] | None] = [None] * len(requests)
        pending: list[tuple[int, dict[str, Any], tuple[Any, ...], str]] = []
        for index, request in enumerate(requests):
            cache_key = (
                request.get("city"),
                request.get("brand"),
                request.get("series"),
                request.get("vehicle_category"),
                request.get("energy_type"),
                request.get("price_band"),
            )
            cached = self._selection_score_cache.get(cache_key)
            if cached is not None:
                results[index] = dict(cached)
                continue
            series_key = _norm(request.get("series"))
            if not series_key:
                neutral = _selection_score_from_buckets({})
                self._selection_score_cache[cache_key] = neutral
                results[index] = dict(neutral)
                continue
            pending.append((index, request, cache_key, series_key))

        if not pending:
            return [dict(item or _selection_score_from_buckets({})) for item in results]

        db_path = self._ensure_sqlite_index()
        rank_types = ("销量榜", "热门榜", "城市榜", "降价榜")
        candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}
        series_keys = sorted({item[3] for item in pending})
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            for start in range(0, len(series_keys), 400):
                chunk = series_keys[start : start + 400]
                placeholders = ",".join("?" for _ in chunk)
                type_placeholders = ",".join("?" for _ in rank_types)
                sql = (
                    "SELECT " + ",".join(_SQL_SIGNAL_COLUMNS) + ",series_key "
                    "FROM ranking_signals WHERE rank_type IN (" + type_placeholders + ") "
                    "AND series_key IN (" + placeholders + ")"
                )
                for record in connection.execute(sql, [*rank_types, *chunk]).fetchall():
                    row = dict(record)
                    candidates.setdefault((str(row.get("rank_type") or ""), str(row.get("series_key") or "")), []).append(row)

        for index, request, cache_key, series_key in pending:
            query = {
                "city": request.get("city"),
                "brand": request.get("brand"),
                "series_name": request.get("series"),
                "vehicle_category": request.get("vehicle_category"),
                "energy_type": request.get("energy_type"),
                "price_band": request.get("price_band"),
            }
            buckets: dict[str, list[dict[str, Any]]] = {}
            for rank_type in rank_types:
                matched: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
                for row in candidates.get((rank_type, series_key), []):
                    if not _matches(row, query):
                        continue
                    priority = FILTER_LEVEL_PRIORITY.get(str(row.get("filter_level") or ""), 0)
                    specificity = _specificity(row, query)
                    rank = _safe_int(row.get("rank")) or 9999
                    matched.append(((specificity, priority, -rank), row))
                matched.sort(key=lambda item: item[0], reverse=True)
                buckets[rank_type] = [self._to_evidence(matched[0][1])] if matched else []
            value = _selection_score_from_buckets(buckets)
            self._selection_score_cache[cache_key] = value
            results[index] = dict(value)
        return [dict(item or _selection_score_from_buckets({})) for item in results]

    def attach_ranking_evidence(self, result: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
        out = dict(result)
        before = {field: result.get(field) for field in FORBIDDEN_PRICE_FIELDS if field in result}
        out["ranking_evidence"] = evidence
        after = {field: out.get(field) for field in FORBIDDEN_PRICE_FIELDS if field in out}
        if before != after:
            raise RuntimeError("ranking_evidence_mutated_pricing_fields")
        return out

    def _to_evidence(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "rank_type": row.get("rank_type"),
            "city": row.get("city"),
            "energy_type": row.get("energy_type"),
            "vehicle_category": row.get("vehicle_category"),
            "filter_signature": row.get("filter_signature"),
            "filter_level": row.get("filter_level"),
            "rank": row.get("rank"),
            "series_name": row.get("series_name"),
            "brand_name": row.get("brand"),
            "metric_name": row.get("metric_name"),
            "metric_value": row.get("metric_value"),
            "price_range_text": row.get("price_range_text") or "",
            "rank_date_text": row.get("source_snapshot_date"),
            "evidence_text": row.get("evidence_text"),
            "business_interpretation": business_interpretation(row),
        }


def business_interpretation(row: dict[str, Any]) -> str:
    rank_type = str(row.get("rank_type") or "")
    if rank_type == "销量榜":
        return "新车端流通性较强，但仍需结合内部库存、成交周期和 DSI，不能单独作为推荐收依据。"
    if rank_type == "热门榜":
        return "关注度代表线索热度，不等于高利润；热度高时车主报价预期也可能偏高。"
    if rank_type == "降价榜":
        return "命中降价榜代表新车冲击风险，收车价、追价和周转预期需要保守。"
    if rank_type == "城市榜":
        return "本地关注度或偏好较强，但若内部城市行情弱，结论仍应谨慎。"
    return "公开排行榜仅作为外部市场证据，不能替代内部行情、DSI 和估价模型。"


def _selection_score_from_buckets(buckets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    def strength(rank_type: str) -> float:
        evidence = buckets.get(rank_type) or []
        if not evidence or evidence[0].get("evidence_text") == NO_RANKING_EVIDENCE:
            return 0.0
        rank = _safe_int(evidence[0].get("rank")) or 60
        return max(0.0, min(100.0, 100 * (1 - (rank - 1) / 59)))

    liquidity = strength("销量榜")
    demand = max(strength("热门榜"), strength("城市榜"))
    discount_risk = strength("降价榜")
    noise_penalty = max(0.0, demand - liquidity) * 0.18 + discount_risk * 0.12
    if liquidity == demand == discount_risk == 0:
        score = 50.0
        match_level = "missing"
    else:
        score = max(0.0, min(100.0, 50 + demand * 0.10 + liquidity * 0.28 - discount_risk * 0.24 - noise_penalty))
        match_level = next(
            (
                str(item[0].get("filter_level") or "series_fallback")
                for item in buckets.values()
                if item and item[0].get("evidence_text") != NO_RANKING_EVIDENCE
            ),
            "series_fallback",
        )
    return {
        "score": round(score, 3),
        "liquidity_score": round(liquidity, 3),
        "demand_score": round(demand, 3),
        "discount_risk_score": round(discount_risk, 3),
        "noise_penalty": round(noise_penalty, 3),
        "match_level": match_level,
    }


def _matches(row: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, value in query.items():
        if value in (None, ""):
            continue
        value_text = _norm(value)
        if key == "series_name":
            if value_text not in _norm(row.get("series_name")):
                return False
        elif key == "brand":
            row_brand = _norm(row.get("brand")) or _norm(row.get("brand_name"))
            if value_text not in row_brand and row_brand not in value_text:
                return False
        elif key == "city":
            row_city = _norm(row.get("city"))
            if row_city not in {"", "全国"} and row_city != value_text:
                return False
        elif _norm(row.get(key)) and _norm(row.get(key)) != value_text:
            return False
    return True


def _specificity(row: dict[str, Any], query: dict[str, Any]) -> int:
    score = 0
    for key, value in query.items():
        if value in (None, ""):
            continue
        if key == "series_name":
            score += int(_norm(value) in _norm(row.get("series_name")))
        elif key == "brand":
            score += int(_norm(value) in (_norm(row.get("brand")) or _norm(row.get("brand_name"))))
        elif _norm(row.get(key)) == _norm(value):
            score += 1
    return score


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _default_signals_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    current = root / "data/external/dongchedi_rankings/current/normalized_ranking_signals.csv"
    if current.exists():
        return current
    candidates = sorted(
        (root / "data/external/dongchedi_rankings").glob("*/normalized_ranking_signals.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else current


def _default_bundled_sqlite_path() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    candidates = [
        path
        for path in (root / "runtime/ranking_signal_index").glob("*.sqlite3")
        if path.is_file()
    ]
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name)) if candidates else None


def _safe_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except Exception:
        return None


def _norm(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip().lower()


def query_ranking_evidence(**kwargs: Any) -> list[dict[str, Any]]:
    return get_ranking_signal_service().query_ranking_evidence(**kwargs)


@lru_cache(maxsize=2)
def get_ranking_signal_service(signals_path: str = "") -> RankingSignalService:
    return RankingSignalService(signals_path or None)
