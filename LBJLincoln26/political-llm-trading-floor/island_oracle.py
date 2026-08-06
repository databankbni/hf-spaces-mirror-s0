"""Island Oracle — bridge TF agents ↔ island-trained models.

The 3 TFs (NBA / POL / ITF) reason with LLMs on narrative context.
The evolution islands (S18 / P7) train calibrated models on 7,213 raw
features and expose a /api/predict endpoint returning p(home_win) or
p(event_yes) with its CV Brier score.

Without this bridge the LLM agents never see the island model's
prediction — they invent a probability from narrative. This is the
scientific gap the whole Nomos42 stack was missing: feature engine
and trading floor were built as silos.

Usage (from any TF):

    from .shared.island_oracle import nba_oracle_predict, pol_oracle_predict
    o = nba_oracle_predict("Boston Celtics", "Miami Heat")
    # => {"p_home": 0.538, "brier_cv": 0.222, "model_type": "extra_trees", ...}
    # or {} if island is down / not ready (fail-open).

Cache: 10min TTL on (home, away) key for NBA; 10min TTL on event_id for POL.
Never raises — returns {} on any failure.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

# Islands exposing /api/predict. Keep URLs here so ops can swap in a second.
NBA_ORACLE_URL = os.environ.get(
    "NBA_ORACLE_URL",
    "https://testforge42-nba-evo-s18.hf.space/api/predict",
)
POL_ORACLE_URL = os.environ.get(
    "POL_ORACLE_URL",
    "https://lbjlincoln-political-alpha-7.hf.space/api/predict",
)

_HTTP_TIMEOUT_S = 12.0
_CACHE_TTL_S = 600  # 10min

_NBA_CACHE: Dict[str, Dict[str, Any]] = {}  # key = f"{home}||{away}"
_POL_CACHE: Dict[str, Dict[str, Any]] = {}  # key = event_id

# Meta health — lets callers skip the oracle when it's known-down.
_HEALTH: Dict[str, Dict[str, Any]] = {
    "nba": {"ok": True, "last_err": None, "last_ts": 0},
    "pol": {"ok": True, "last_err": None, "last_ts": 0},
}


def _post_json(url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Nomos42-Oracle/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _mark_health(which: str, ok: bool, err: Optional[str] = None) -> None:
    _HEALTH[which] = {"ok": ok, "last_err": err, "last_ts": int(time.time())}


def health() -> Dict[str, Dict[str, Any]]:
    return dict(_HEALTH)


def nba_oracle_predict(home_team: str, away_team: str) -> Dict[str, Any]:
    """Predict home-win probability for one NBA game via S18.

    Returns {} on any failure (fail-open).
    Callers treat empty dict as "oracle unavailable — use LLM reasoning alone".
    """
    if not home_team or not away_team:
        return {}
    key = f"{home_team.strip()}||{away_team.strip()}"
    now = time.time()
    cached = _NBA_CACHE.get(key)
    if cached and now - cached.get("_cached_ts", 0) < _CACHE_TTL_S:
        return cached["payload"]

    resp = _post_json(NBA_ORACLE_URL, {"games": [{"home_team": home_team, "away_team": away_team}]})
    if not resp or "predictions" not in resp:
        _mark_health("nba", False, "no-predictions")
        return {}

    preds = resp.get("predictions") or []
    if not preds:
        _mark_health("nba", False, "empty-predictions")
        return {}
    p = preds[0]
    if "error" in p:
        _mark_health("nba", False, p.get("error"))
        return {}

    model_meta = resp.get("model") or {}
    out = {
        "p_home": float(p.get("home_win_prob") or 0.5),
        "p_away": float(p.get("away_win_prob") or 0.5),
        "raw_p_home": float(p.get("raw_home_win_prob") or p.get("home_win_prob") or 0.5),
        "calibrated": bool(p.get("calibrated", False)),
        "confidence": float(p.get("confidence") or 0.0),
        "kelly_stake": float(p.get("kelly_stake") or 0.0),
        "model_type": p.get("model_type") or model_meta.get("type") or "unknown",
        "features_used": int(p.get("features_used") or model_meta.get("features") or 0),
        "brier_cv": float(p.get("brier_cv") or model_meta.get("brier_cv") or 0.0),
        "roi_cv": float(model_meta.get("roi_cv") or 0.0),
        "island": "S18",
        "oracle_ts": resp.get("timestamp"),
    }
    _NBA_CACHE[key] = {"_cached_ts": now, "payload": out}
    _mark_health("nba", True)
    return out


def nba_oracle_predict_many(games: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Predict multiple NBA games in one round-trip (preferred when >1).

    Each game: {"home_team": "...", "away_team": "..."}.
    Returns list parallel to input; failures become {} in the list.
    """
    if not games:
        return []

    # Split cached / uncached
    uncached: List[Dict[str, str]] = []
    results: List[Optional[Dict[str, Any]]] = [None] * len(games)
    now = time.time()
    for i, g in enumerate(games):
        home = (g.get("home_team") or "").strip()
        away = (g.get("away_team") or "").strip()
        if not home or not away:
            results[i] = {}
            continue
        key = f"{home}||{away}"
        c = _NBA_CACHE.get(key)
        if c and now - c.get("_cached_ts", 0) < _CACHE_TTL_S:
            results[i] = c["payload"]
        else:
            uncached.append({"home_team": home, "away_team": away, "_idx": i})

    if uncached:
        payload_games = [{"home_team": u["home_team"], "away_team": u["away_team"]} for u in uncached]
        resp = _post_json(NBA_ORACLE_URL, {"games": payload_games})
        preds = (resp or {}).get("predictions") or []
        model_meta = (resp or {}).get("model") or {}
        if not preds:
            _mark_health("nba", False, "batch-empty")
            for u in uncached:
                results[u["_idx"]] = {}
        else:
            for u, p in zip(uncached, preds):
                if "error" in p:
                    results[u["_idx"]] = {}
                    continue
                out = {
                    "p_home": float(p.get("home_win_prob") or 0.5),
                    "p_away": float(p.get("away_win_prob") or 0.5),
                    "raw_p_home": float(p.get("raw_home_win_prob") or p.get("home_win_prob") or 0.5),
                    "calibrated": bool(p.get("calibrated", False)),
                    "confidence": float(p.get("confidence") or 0.0),
                    "kelly_stake": float(p.get("kelly_stake") or 0.0),
                    "model_type": p.get("model_type") or model_meta.get("type") or "unknown",
                    "features_used": int(p.get("features_used") or model_meta.get("features") or 0),
                    "brier_cv": float(p.get("brier_cv") or model_meta.get("brier_cv") or 0.0),
                    "roi_cv": float(model_meta.get("roi_cv") or 0.0),
                    "island": "S18",
                    "oracle_ts": (resp or {}).get("timestamp"),
                }
                _NBA_CACHE[f"{u['home_team']}||{u['away_team']}"] = {"_cached_ts": now, "payload": out}
                results[u["_idx"]] = out
            _mark_health("nba", True)

    return [r if r is not None else {} for r in results]


def pol_oracle_predict(event_id: str, event_features: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Predict p(event_yes) for one political event via P7.

    event_id is any stable identifier (used as cache key).
    event_features is the feature dict matching political_engine.py v3.19.
    Returns {} on any failure.
    """
    if not event_id:
        return {}
    now = time.time()
    cached = _POL_CACHE.get(event_id)
    if cached and now - cached.get("_cached_ts", 0) < _CACHE_TTL_S:
        return cached["payload"]

    # P7 expects {"events": [{"event_id": ..., ...}]} -- NOT a top-level event_id.
    # Previous shape returned {"error": "no events to predict"} silently.
    event_obj: Dict[str, Any] = {"event_id": event_id}
    if event_features:
        event_obj.update(event_features)
    payload = {"events": [event_obj]}

    resp = _post_json(POL_ORACLE_URL, payload)
    if not resp or "predictions" not in resp:
        _mark_health("pol", False, "no-predictions")
        return {}

    preds = resp.get("predictions") or []
    if not preds:
        _mark_health("pol", False, "empty")
        return {}
    p = preds[0]
    if "error" in p:
        _mark_health("pol", False, p.get("error"))
        return {}

    model_meta = resp.get("model") or {}
    out = {
        "p_yes": float(p.get("p_yes") or p.get("home_win_prob") or 0.5),
        "p_no": float(p.get("p_no") or p.get("away_win_prob") or 0.5),
        "raw_p_yes": float(p.get("raw_p_yes") or p.get("p_yes") or 0.5),
        "calibrated": bool(p.get("calibrated", False)),
        "confidence": float(p.get("confidence") or 0.0),
        "model_type": p.get("model_type") or model_meta.get("type") or "unknown",
        "features_used": int(p.get("features_used") or model_meta.get("features") or 0),
        "brier_cv": float(p.get("brier_cv") or model_meta.get("brier_cv") or 0.0),
        "roi_cv": float(model_meta.get("roi_cv") or 0.0),
        "island": "P7",
        "oracle_ts": resp.get("timestamp"),
    }
    _POL_CACHE[event_id] = {"_cached_ts": now, "payload": out}
    _mark_health("pol", True)
    return out


def oracle_block_for_prompt(nba_pred: Optional[Dict[str, Any]] = None,
                            pol_pred: Optional[Dict[str, Any]] = None) -> str:
    """Render island predictions as a short prompt block.

    Returns '' if both are empty — callers append unconditionally.
    Goal: LLM agents compare their bet thesis against the calibrated
    island model and bet only where they see a distinct edge.
    """
    lines: List[str] = []
    if nba_pred and nba_pred.get("p_home"):
        lines.append(
            "ISLAND ORACLE (S18 NBA, Brier {b:.4f}): p(home_win)={p:.3f}, "
            "raw={r:.3f}, model={m}, confidence={c:.2f}. "
            "Bet only if your edge vs this > 3%.".format(
                b=nba_pred.get("brier_cv", 0),
                p=nba_pred.get("p_home", 0.5),
                r=nba_pred.get("raw_p_home", 0.5),
                m=nba_pred.get("model_type", "?"),
                c=nba_pred.get("confidence", 0),
            )
        )
    if pol_pred and pol_pred.get("p_yes"):
        lines.append(
            "ISLAND ORACLE (P7 POL, Brier {b:.4f}): p(event_yes)={p:.3f}, "
            "model={m}, features={f}. Bet only if your edge vs this > 3%.".format(
                b=pol_pred.get("brier_cv", 0),
                p=pol_pred.get("p_yes", 0.5),
                m=pol_pred.get("model_type", "?"),
                f=pol_pred.get("features_used", 0),
            )
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    print("== island_oracle smoke test ==")
    r = nba_oracle_predict("Boston Celtics", "Miami Heat")
    print("NBA S18:", json.dumps(r, indent=2))
    print("HEALTH:", json.dumps(health(), indent=2))
    sys.exit(0 if r else 1)
