"""
Nomos42 Political LLM Trading Floor — HuggingFace Spaces
=========================================================
10 AI agents (real LLM API calls) compete on ~1120 political events
over ~14 days (2026-03-12 to 2026-03-26).
Each agent receives daily political signals (insider trades, Fed rules,
executive orders) and allocates long/short on affected sector ETFs.
NO hash simulation. Every decision is a real LLM call.

Providers: Cerebras (2 models), Google Gemini, Mistral (5 models)
Runtime: ~1-2 hours for full dataset. Live visualization throughout.

Architecture follows:
  - TradingAgents (arXiv 2412.20138): structured agent reasoning
  - Prediction Arena (arXiv 2604.07355): 1-bet-per-agent validation
  - DMAD (Diverse Multi-Agent Debate): structurally different data views
"""

import gradio as gr
import json
import os
import time
import requests
import traceback
import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Centralised gateway router (vendored into Space; see scripts/arena/gateway_client.py)
from gateway_client import gateway_call as _gateway_call, GATEWAY_URL as _GATEWAY_URL

# Island oracle — bridges POL TF agents to P7's calibrated xgboost/extra_trees model.
# Fail-open: if P7 is down, oracle returns {} and prompts skip the ORACLE line.
try:
    from island_oracle import pol_oracle_predict as _island_pol_predict
    _POL_ORACLE_OK = True
except Exception as _orc_err:
    print(f"[pol-oracle] import failed: {_orc_err}")
    _POL_ORACLE_OK = False
    def _island_pol_predict(*a, **kw): return {}

# ── STARTUP DIAGNOSTICS ─────────────────────────────────────────────────────
print("=" * 60)
print("NOMOS42 POLITICAL LLM TRADING FLOOR — STARTUP")
print("=" * 60)
for k in ["CEREBRAS_API_KEY", "GOOGLE_API_KEY", "GOOGLE_API_KEY_2",
          "OPENROUTER_KEY_ORCHESTRATOR", "OPENROUTER_KEY_PME", "OPENROUTER_KEY_BARTOLI",
          "MISTRAL_API_KEY"]:
    v = os.environ.get(k, "")
    if v:
        print(f"  {k}: {v[:6]}...{v[-3:]} (len={len(v)})")
    else:
        print(f"  {k}: NOT SET")
print("=" * 60)
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import math

# ── LANGFUSE OBSERVABILITY (non-blocking — never delays TF startup) ────────
_langfuse = None
_langfuse_errors: List[str] = []
try:
    from langfuse import Langfuse
    _lf_pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    _lf_sec = os.environ.get("LANGFUSE_SECRET_KEY", "")
    _lf_host = os.environ.get("LANGFUSE_HOST", "")
    if _lf_pub and _lf_sec and _lf_host:
        _langfuse = Langfuse(public_key=_lf_pub, secret_key=_lf_sec, host=_lf_host, enabled=True, timeout=5)
        print(f"  LANGFUSE: initialized → {_lf_host}")
    else:
        print("  LANGFUSE: keys/host not set (observability disabled)")
except Exception as e:
    print(f"  LANGFUSE: init failed ({e}) — continuing without observability")

def benjamini_hochberg(edges: List[Tuple[str, float]], alpha: float = 0.05) -> set:
    """Return set of category tags that survive BH FDR correction.
    Treats |edge| as a test statistic under H0: edge=0. With ~22 political
    categories derived from Normal CDF, the SE of each derived edge is ~0.03-0.05.
    We use SE=0.04 as conservative estimate for all categories."""
    SE = 0.04
    n = len(edges)
    if n == 0:
        return set()
    pvals = []
    for tag, edge_val in edges:
        z = abs(edge_val) / SE
        p = 2 * (1 - _norm_cdf(z))
        pvals.append((p, tag))
    pvals.sort()
    passing = set()
    for rank, (p, tag) in enumerate(pvals, 1):
        threshold = alpha * rank / n
        if p <= threshold:
            passing.add(tag)
        else:
            break
    return passing

def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── CONTROL STATE (stop/mutate/resume) ──────────────────────────────────────
_stop_event = threading.Event()
_experiment_running = False
_experiment_state = {}  # Persisted to disk
_agent_logs: Dict[str, List[dict]] = defaultdict(list)  # Per-agent decision log
_state_lock = threading.Lock()
_started_utc: Optional[str] = None  # 2026-04-22: set on first run_experiment entry, exposed via /api/status
_common_knowledge: Dict[str, str] = {}  # Axelrod CK[D]: day_date → formatted block for day D+1
_sacrificial_assignments: Dict[str, str] = {}  # Axelrod Mech B: tid → archetype for NEXT day
_used_archetypes: Dict[str, set] = defaultdict(set)  # Axelrod Mech B: tid → set of archetypes tried (per-agent fallback)
_society_archetypes_by_day: Dict[str, set] = {}  # Axelrod Mech B: day_date → society-wide archetypes assigned that day
_challenge_assignments: Dict[str, int] = {}  # Axelrod Mech B: mid-tier tid → leaderboard rank
STATE_PATH = Path("/tmp/ptf-state.json")   # Local (ephemeral /tmp) — cheap quick-save
LOGS_PATH = Path("/tmp/ptf-agent-logs.json")
AXELROD_LOG_DIR = Path("/tmp/axelrod-log-political")  # Axelrod Mech C

# ── HUB PERSISTENCE (2026-04-17) ────────────────────────────────────────────
# Mirrors NBA TF. /tmp wiped every restart; push snapshot to Space repo so the
# full per-agent per-day decision trail survives every restart.
HF_REPO_ID = os.environ.get("SPACE_ID") or "LBJLincoln26/political-llm-trading-floor"
HF_HUB_TOKEN = os.environ.get("HF_WRITE_TOKEN") or os.environ.get("NOMOS_HF_TOKEN") or os.environ.get("HF_TOKEN")
HUB_SNAPSHOT_EVERY_DAYS = 3
try:
    from huggingface_hub import HfApi, hf_hub_download
    _hub_api = HfApi(token=HF_HUB_TOKEN) if HF_HUB_TOKEN else None
except Exception:
    _hub_api = None
    hf_hub_download = None

# ── COLLECTIVE EXPERIMENT (2026-04-17) ─────────────────────────────────────
# Mirrors NBA TF. Common goal: one agent hits $1M by season end. Council plan
# daily; rogue defection allowed on bankroll crash or peer > $250K.
SEASON_TARGET = 1_000_000.0
STARTING_CAPITAL = 100.0
ROGUE_DRAWDOWN_THRESHOLD = 0.25
ROGUE_GREED_THRESHOLD = 250_000.0
# 2026-04-18 drawdown-guardrails (post-mortem parity with NBA app)
# Post-mortem found 14/17 POL agents converged to identical ruin ($93.92) by
# defecting to higher-variance plays on drawdown. Preservation > chase.
# Prompt-mutator overrides (2026-04-19) — same mechanic as NBA TF, fleet="pol".
def _load_prompt_override(fleet: str = "pol", sim_date: str = None) -> str:
    """Load prompt-mutator override + YouTube market narrative for this fleet.

    sim_date (ISO "YYYY-MM-DD"): simulated trading day. When provided (POL+NBA are
    sim-dated Jul 2025 - Apr 2026), the narrative is rebuilt from
    `market_narrative_videos` filtered to `published_at <= sim_date`, preventing
    lookahead leakage flagged 2026-04-21 by INTERNAL AFFAIRS. When None (ITF/PQTF
    are live-dated) we fall back to the flat `market_narrative`. Section-level
    `market_narrative_disabled` is an audit kill-switch.
    """
    import os as _os, json as _json
    candidates = [
        "/app/data/prompts/overrides.json",
        "/home/user/app/data/prompts/overrides.json",
        _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "data", "prompts", "overrides.json"),
    ]
    for p in candidates:
        try:
            if not _os.path.exists(p):
                continue
            with open(p) as fh:
                ov = _json.load(fh)
            section = (ov.get(fleet) or {})
            rule = section.get("current_text") or ""
            v = section.get("current_version") or "?"

            narrative_block = ""
            if not section.get("market_narrative_disabled"):
                struct = section.get("market_narrative_videos")
                if sim_date and struct:
                    cutoff = (sim_date or "")[:10]
                    kept = [sv for sv in struct if (sv.get("published_at") or "")[:10] <= cutoff]
                    if kept:
                        header = f"YouTube narrative digest ({len(kept)} videos, sim_date={cutoff}):"
                        body = "\n".join(sv.get("line", "") for sv in kept[:8])
                        narrative_block = header + "\n" + body
                elif not sim_date:
                    narrative_block = section.get("market_narrative") or ""

            mvc = section.get("manual_videos_count") or 0
            out = ""
            if rule:
                out += f"\n=== PROMPT MUTATOR OVERRIDE ({v}) ===\n{rule}\n=== END OVERRIDE ===\n"
            if narrative_block:
                out += f"\n=== YOUTUBE MARKET NARRATIVE ({mvc} tracked videos, 22 channels) ===\n{narrative_block}\n=== END NARRATIVE ===\n"
            if out:
                return out
        except Exception:
            continue
    return ""

PEAK_DRAWDOWN_GUARD = 0.70        # ≥30% off peak → preservation mode
PRESERVATION_MAX_DEPLOY = 0.50    # cap daily deploy at 50%
PRESERVATION_MAX_BET_PCT = 0.05   # cap any single bet at 5% bankroll
SINGLE_DAY_WIPEOUT_THRESHOLD = 0.40  # >40% single-day loss → forced cash next day
COLLISION_MAX_AGENTS = 3          # max agents sharing same event+direction in one day
COUNCIL_MIN_COMMIT_PER_AGENT = 0.50
_council_plans: Dict[str, dict] = {}
_rogue_events: List[Dict] = []


def _tiered_risk(bankroll: float) -> dict:
    """Bankroll-tier aggression (gambler's ruin doctrine, 2026-04-18 parity with NBA).
    Low bankrolls deploy HARDER (higher Kelly, higher per-bet floor) to compound
    out of the hole. High bankrolls diversify across more sectors/directions.
    Returns: {deploy_floor, bet_floor, bet_cap, min_edge, kelly_mult,
              min_allocs, min_cats, min_events}."""
    # Post-mortem 2026-04-19 (NBA parity): winners used flat-stake wide coverage
    # with strict EV threshold and half-Kelly. New doctrine: tighter MIN_EDGE
    # (0.04 blocks marginal DIVERGE bets), capped KELLY_MULT (0.5× max),
    # lower per-bet caps to prevent single-day wipeouts.
    if bankroll < 25.0:
        return {"deploy_floor": 0.90, "bet_floor": 0.04, "bet_cap": 0.20,
                "min_edge": 0.04, "kelly_mult": 0.5,
                "min_allocs": 20, "min_cats": 6, "min_events": 5}
    if bankroll < 50.0:
        return {"deploy_floor": 0.80, "bet_floor": 0.03, "bet_cap": 0.15,
                "min_edge": 0.04, "kelly_mult": 0.5,
                "min_allocs": 16, "min_cats": 5, "min_events": 4}
    if bankroll < 100.0:
        return {"deploy_floor": 0.70, "bet_floor": 0.02, "bet_cap": 0.12,
                "min_edge": 0.04, "kelly_mult": 0.5,
                "min_allocs": 14, "min_cats": 5, "min_events": 4}
    if bankroll < 500.0:
        return {"deploy_floor": 0.60, "bet_floor": 0.015, "bet_cap": 0.10,
                "min_edge": 0.04, "kelly_mult": 0.5,
                "min_allocs": 12, "min_cats": 4, "min_events": 3}
    # PROVEN 5-20x starting ($500-$2000) — NBA parity, $1M push tiers (2026-04-19)
    if bankroll < 2000.0:
        return {"deploy_floor": 0.65, "bet_floor": 0.02, "bet_cap": 0.15,
                "min_edge": 0.04, "kelly_mult": 0.65,
                "min_allocs": 10, "min_cats": 4, "min_events": 3}
    # MOONSHOT 20-100x ($2000-$10000)
    if bankroll < 10000.0:
        return {"deploy_floor": 0.65, "bet_floor": 0.025, "bet_cap": 0.20,
                "min_edge": 0.05, "kelly_mult": 0.75,
                "min_allocs": 8, "min_cats": 3, "min_events": 3}
    # CHAMPION 100x+ ($10000+) — compounding toward $1M
    return {"deploy_floor": 0.65, "bet_floor": 0.03, "bet_cap": 0.25,
            "min_edge": 0.05, "kelly_mult": 0.85,
            "min_allocs": 6, "min_cats": 3, "min_events": 2}

# Axelrod Mech B — archetype pool tuned for political/macro alpha traders
AXELROD_ARCHETYPES = [
    "political_sentiment", "insider_tracking", "trump_volatility",
    "foreign_sovereign_flow", "regulatory_arb", "congress_trading_mirror",
    "macro_narrative", "crisis_contrarian", "election_cycle_timing",
    "fed_watcher", "geopolitical_risk", "congressional_calendar",
    "lobbying_flow", "pac_money_velocity", "treasury_curve_divergence",
    "commodities_war_premium", "dollar_strength_fade", "emerging_market_risk",
    "defense_budget_catalyst", "sanctions_arbitrage",
]

# Axelrod 1980 canon — political-alpha variant (same canon, context swapped).
COLLECTIVE_MISSION = (
    "=== COLLECTIVE MISSION (2026-04-17, binding) ===\n"
    "You are ONE of 17 LLM agents sharing a political-alpha society bankroll. All 17 agents see "
    "the SAME data: 1120 political events, 22 event categories × 7 SPDR sectors, full sector-beta "
    "matrices + insider trades + fed speakers + exec orders + peer bankrolls + peer positions + "
    "post-mortem logs.\n"
    "COMMON GOAL: ONE of us reaches $1,000,000 bankroll by season end. That agent's win counts "
    "as a collective win. Individual greed (>$250K while peers dying) triggers DEFECT rogue.\n"
    "DEPLOY RULE (hard): ≥75% of your bankroll MUST be deployed EVERY DAY across ≥3 sector "
    "allocations. Holding >25% cash violates the collective goal. Use the full 7-sector SPDR menu "
    "(XLF/XLE/XLV/XLI/XLK/XLC/XLY) + individual stocks when politically warranted.\n"
    "DATA REALITY (2026-04-24, honest): Of 3,597 source events, 98.4% are insider_trade, "
    "1.5% fed_rule, <0.1% exec_order / polymarket. You are a POLITICAL INSIDER-TRADE "
    "ARBITRAGE fleet — do not pretend to bet on categories the data doesn't contain.\n"
    "DIVERSITY MANDATE (hard): across your daily allocations you MUST hit ≥3 DISTINCT "
    "SPDR SECTORS (choose among XLF XLE XLV XLI XLK XLC XLY XLP XLRE XLU XLB). Placing "
    "all stake on one sector (e.g. XLF-only on insider_trade) is a doctrine violation that "
    "voids the day's allocation and triggers sacrificial archetype reassignment. Sector "
    "diversity — not category diversity — is the enforceable risk control given the data.\n"
    "COLLABORATION STACK: (1) morning council plan (qwen-235B moderator) specifies focus sectors + "
    "per-agent commit. (2) Pact proposals let 2 agents bet the same sector+direction. "
    "(3) Axelrod canon strategy assigned per agent. (4) Post-mortem log visible to all. "
    "(5) Sacrificial rotation reassigns losing agents to archetypes the society lacks.\n"
    "=== END COLLECTIVE MISSION ===\n\n"
)

AXELROD_CANON = (
    COLLECTIVE_MISSION +
    "=== AXELROD CANON (mandatory reading) ===\n"
    "You are a trader in an iterated multi-agent political-alpha society. Axelrod's 1980 "
    "tournament proved that the winning strategies share 4 properties: NICE (never defect "
    "first), RETALIATORY (punish defection immediately), FORGIVING (one-shot retaliation, "
    "then reset), CLEAR (legible so peers can reason about you).\n"
    "Canonical strategies you must know by name:\n"
    "  - TIT_FOR_TAT (Rapoport): cooperate first, then copy last move of peer.\n"
    "  - GRIM_TRIGGER: cooperate until one defection, then defect forever.\n"
    "  - PAVLOV / WIN-STAY-LOSE-SHIFT (Nowak-Sigmund 1993): keep last move if it paid, flip if it lost.\n"
    "  - GENEROUS_TFT: TFT with ~10% forgiveness to escape noise-driven defection spirals.\n"
    "  - FIRM_BUT_FAIR: cooperate unless suckered, then retaliate once and return to cooperation.\n"
    "DMAD (Du et al. 2023, Debate with Multi-Agent Diverse-reasoning): groupthink collapses "
    "ensemble accuracy by ~18%. Your reasoning chain MUST be structurally distinct from peers' "
    "chains reported in COMMON_KNOWLEDGE — if consensus is obvious, state the strongest counter-argument.\n"
    "Prediction Arena (arXiv 2604.07355, Mar 2026): 1 bet per agent per day with public "
    "resolution + reputation score beats unconstrained betting by 31% ROI.\n"
    "COOPERATION RULES (Mech D — binding this season):\n"
    "  1. You may propose a COALITION with another agent: both agents trade the SAME event_idx "
    "     on the SAME sector on day D. Honored coalitions get a 'pact_honored' reputation credit.\n"
    "  2. You may EXIT a coalition any day by simply not repeating it. No hidden defection.\n"
    "  3. Your reputation field (pact_honored / pact_broken counters) is visible to peers in "
    "     COMMON_KNOWLEDGE the next day. Pavlov-style opponents will track your reputation.\n"
    "  4. Coalitions do NOT change stake math — only reputation. Edge must still justify the trade.\n"
    "=== END AXELROD CANON ===\n"
    "\n=== DMAD ANTI-CONSENSUS GATE (2026-04-21, binding) ===\n"
    "Cross-TF audit 2026-04-21 flagged Political lockstep where agents converged to "
    "identical bankrolls, collapsing ensemble accuracy ~18% (DMAD, Du 2023). "
    "HARD RULE:\n"
    "  - At least ONE of your top-3 allocations today MUST be a trade "
    "    NOT present in peer_allocations from yesterday.\n"
    "  - If every top-tier edge is crowded (>=10/17 peers), dig deeper into "
    "    SPDR sectors (XLF/XLE/XLV/XLI/XLK/XLC/XLY) + individual stocks.\n"
    "  - Annotate non-consensus trade with tag DMAD_DIVERGE in notes.\n"
    "=== END DMAD ANTI-CONSENSUS GATE ===\n"
)

# Axelrod Mech D — cooperation ledger (political)
_cooperation_pacts: Dict[str, dict] = {}
_reputation: Dict[str, Dict[str, int]] = defaultdict(lambda: {"pact_honored": 0, "pact_broken": 0})

# --- Axelrod-Python real-library engine (Mech D+, political parity) ----------
try:
    import axelrod as axl
    _AXELROD_OK = True
except Exception:
    axl = None
    _AXELROD_OK = False

AXELROD_STRATEGIES = {
    "qwen-quant":        "TitForTat",
    "qwen-arb":          "Grudger",
    "llama-contra":      "SuspiciousTitForTat",
    "gemini-anl":        "TitFor2Tats",
    "gemini-tact":       "TwoTitsForTat",
    "mistral-large":     "WinStayLoseShift",
    "mistral-medium":    "GenerousTitForTat",
    "mistral-small":     "Cooperator",
    "mistral-nemo":      "Defector",
    "mistral-ministral": "FirmButFair",
    "nemotron-120b":     "Adaptive",
    "selfhost-qwen4b":   "Tullock",
    "nvidia-minimax":    "Prober",
    "nvidia-llama70":    "Gradual",
    "selfhost-gemma3":   "Handshake",
    "selfhost-qwen06":   "Cooperator",
    "selfhost-dolphin3": "Pavlov",
}
_axelrod_agents: Dict[str, object] = {}

def _axelrod_make(tid: str):
    if not _AXELROD_OK:
        return None
    if tid in _axelrod_agents:
        return _axelrod_agents[tid]
    name = AXELROD_STRATEGIES.get(tid, "TitForTat")
    cls = getattr(axl, name.replace(" ", ""), None) or getattr(axl, name, None) or axl.TitForTat
    try:
        obj = cls()
        _axelrod_agents[tid] = obj
        return obj
    except Exception:
        return None

def _axelrod_advice(tid: str, peer_tid: str) -> Dict[str, str]:
    if not _AXELROD_OK:
        return {"move": "C", "strategy": "unavailable", "reason": "axelrod-python not installed"}
    self_agent = _axelrod_make(tid)
    peer_agent = _axelrod_make(peer_tid)
    if self_agent is None or peer_agent is None:
        return {"move": "C", "strategy": AXELROD_STRATEGIES.get(tid, "TitForTat"), "reason": "init failed"}
    try:
        self_agent.reset()
        peer_agent.reset()
        pair_keys = [k for k in _cooperation_pacts.keys()
                     if k.startswith(f"{tid}|{peer_tid}|") or k.startswith(f"{peer_tid}|{tid}|")]
        pair_keys.sort()
        for k in pair_keys[-50:]:
            move = axl.Action.C if _cooperation_pacts[k].get("honored", False) else axl.Action.D
            self_agent.history.append(move)
            peer_agent.history.append(move)
        next_move = self_agent.strategy(peer_agent)
        return {
            "move": "C" if next_move == axl.Action.C else "D",
            "strategy": AXELROD_STRATEGIES.get(tid, "TitForTat"),
            "reason": f"{len(pair_keys)} prior pacts with {peer_tid}",
        }
    except Exception as e:
        return {"move": "C", "strategy": AXELROD_STRATEGIES.get(tid, "TitForTat"),
                "reason": f"strategy error: {str(e)[:60]}"}

def _axelrod_advice_block(tid: str, active_peers: list) -> str:
    if not _AXELROD_OK or not active_peers:
        return ""
    peers = list(active_peers)[:3]
    lines = []
    for peer in peers:
        a = _axelrod_advice(tid, peer)
        lines.append(f"  - vs {peer}: strategy={a['strategy']} → suggests {a['move']} ({a['reason']})")
    if not lines:
        return ""
    return (
        "\n=== AXELROD MECH D — CANON STRATEGY ADVICE (axelrod-python library, ~240 strategies) ===\n"
        f"Your assigned canon strategy: {AXELROD_STRATEGIES.get(tid, 'TitForTat')}\n"
        "Today's advice against 3 peers (based on real pact history):\n"
        + "\n".join(lines) +
        "\nHonor the C (cooperate) suggestions as PACT proposals; decline D (defect) peers.\n"
        "=== END AXELROD ADVICE ===\n"
    )

GATEWAY_URL = os.environ.get("GATEWAY_URL", "").rstrip("/")

# DMAD (ICLR 2025, OpenReview t6QHYUOQL7) — structurally distinct reasoning per agent (political flavor).
REASONING_TEMPLATES = {
    "qwen-quant":        "REASONING TEMPLATE (DMAD): EXPECTED-UTILITY MAXIMIZATION. Compute E[V] = (p_event × sector_move) − cost. Trade iff E[V]/stake > 0.05.",
    "qwen-arb":          "REASONING TEMPLATE (DMAD): CROSS-SECTOR ARBITRAGE. Spot correlated ETFs diverging > 2σ from historical beta.",
    "llama-contra":      "REASONING TEMPLATE (DMAD): CONTRARIAN INVERSION. Start from consensus narrative, argue the OPPOSITE with 3 reasons.",
    "gemini-anl":        "REASONING TEMPLATE (DMAD): FIRST-PRINCIPLES DECOMPOSITION. List 3 decisive political drivers, weight each, multiply to get signal.",
    "gemini-tact":       "REASONING TEMPLATE (DMAD): TACTICAL TIMING. Focus on calendar risk (votes, summits). Absent imminent catalyst, deploy ≥3 sector allocations on rolling 14-day sentiment (collective 75% deploy rule).",
    "mistral-large":     "REASONING TEMPLATE (DMAD): SCENARIO MAJORITY. Enumerate 5 macro scenarios, assign P, trade iff ≥3 align.",
    "mistral-medium":    "REASONING TEMPLATE (DMAD): DIVERSIFIED PORTFOLIO. Split across 2-3 uncorrelated sectors.",
    "mistral-small":     "REASONING TEMPLATE (DMAD): RISK-AVERSE STRESS. Assume worst-case tail; trade only if still +EV.",
    "mistral-nemo":      "REASONING TEMPLATE (DMAD): MOMENTUM CHASE. Bet hardest on sectors with 5-day momentum > 2σ.",
    "mistral-ministral": "REASONING TEMPLATE (DMAD): THEORETICAL MODEL. Mental factor model from 3 coefficients → compute expected sector return.",
    "nemotron-120b":     "REASONING TEMPLATE (DMAD): EXPLICIT 7-STEP CoT. context → hypothesis → evidence → counter → weight → conclusion → trade.",
    "selfhost-qwen4b":   "REASONING TEMPLATE (DMAD): 4-RULE CHECKLIST. (1) edge > 0.05 (2) bankroll > $30 (3) not same sector as yesterday (4) political catalyst dated within 14d. Trade iff ALL pass.",
    "nvidia-minimax":    "REASONING TEMPLATE (DMAD): LONG-CONTEXT SCAN. Ingest ALL today's events + 7-day history. Rank sectors by event-density × sentiment × sector-beta. Pick 2-3 with highest composite score.",
    "nvidia-llama70":    "REASONING TEMPLATE (DMAD): EV-THRESHOLD SWING. For each sector ETF compute EV = p_event × expected_sector_move − fees. Bet top 3 if EV > 0.05; else cash.",
    "selfhost-gemma3":   "REASONING TEMPLATE (DMAD): 3-FACTOR POLITICAL MODEL. Factors {congressional_vote_proximity, fed_speaker_density, geopolitical_tape}. Weight {0.4, 0.3, 0.3}. Trade iff weighted >0.6.",
    "selfhost-qwen06":   "REASONING TEMPLATE (DMAD): TINY-MODEL WIDE COVERAGE. Spread flat stakes across ALL 7 SPDR sectors (XLF/XLE/XLV/XLI/XLK/XLC/XLY). Any signal >0.35 → allocate.",
    "selfhost-dolphin3": "REASONING TEMPLATE (DMAD): PAVLOV WIN-STAY/LOSE-SHIFT. After a winning sector, double down. After a loss, rotate to the highest-momentum alternative. No overthinking.",
}

def get_stackelberg_leader(state: dict) -> Optional[str]:
    """Stackelberg (arXiv 2507.09407): yesterday's top-bankroll trader is today's leader."""
    active = [(tid, st.get("bankroll", 0)) for tid, st in state.items()
              if isinstance(st, dict) and tid in TRADERS and st.get("bankroll", 0) > 5.0]
    if not active:
        return None
    return max(active, key=lambda x: x[1])[0]

def build_stackelberg_role_block(tid: str, leader_tid: Optional[str]) -> str:
    if not leader_tid:
        return ""
    if tid == leader_tid:
        return ("\n=== STACKELBERG ROLE TODAY: LEADER ===\n"
                "You are today's leader (highest bankroll prior day). Commit trades FIRST with full "
                "public reasoning. Your decisions enter COMMON_KNOWLEDGE for followers.\n")
    return (f"\n=== STACKELBERG ROLE TODAY: FOLLOWER (leader = {leader_tid}) ===\n"
            "After leader's public commitments, you must either:\n"
            "  (a) AGREE — align with leader's logic where same sector applies, OR\n"
            "  (b) DEVIATE — state one explicit reason to best-respond differently.\n")

def _save_state_to_disk(state: dict):
    """Persist to /tmp (fast, ephemeral) + HF Hub state.json (every day)."""
    try:
        STATE_PATH.write_text(json.dumps(state, default=str))
    except Exception:
        pass
    if _hub_api and int(state.get("days_processed", 0)) > 0:
        _push_state_to_hub(state)

def _push_state_to_hub(state: dict):
    """Lightweight state snapshot — one file, overwritten daily (resume)."""
    try:
        days = int(state.get("days_processed", 0))
        total = int(state.get("days_total", 0))
        _hub_api.upload_file(
            path_or_fileobj=json.dumps(state, default=str, indent=2).encode("utf-8"),
            path_in_repo="data/runtime/state.json",
            repo_id=HF_REPO_ID, repo_type="space",
            commit_message=f"runtime: day {days}/{total} state",
        )
    except Exception as e:
        print(f"[hub-persist] state push failed: {e}")

def _push_day_decisions_to_hub(day_idx: int, day_date: str, n_events: int,
                                day_logs_by_agent: Dict[str, dict],
                                day_council_plan: Optional[dict] = None,
                                day_rogue_state: Optional[dict] = None):
    """One file per experiment-day: data/decisions/day-XXX.json on the Space
    repo. Contains per-agent full rationale (which event, category, sizing,
    council alignment) + council plan. Councils/depts aggregate across days."""
    if not _hub_api:
        return
    try:
        payload = {
            "day_idx": day_idx,
            "date": day_date,
            "n_events": n_events,
            "n_agents": len(day_logs_by_agent),
            "council_plan": day_council_plan,
            "rogue_state": day_rogue_state,
            "agents": day_logs_by_agent,
            "written_at": datetime.now(timezone.utc).isoformat(),
        }
        _hub_api.upload_file(
            path_or_fileobj=json.dumps(payload, default=str, indent=2).encode("utf-8"),
            path_in_repo=f"data/decisions/day-{day_idx:03d}.json",
            repo_id=HF_REPO_ID, repo_type="space",
            commit_message=f"decisions: day {day_idx} ({day_date}) — {len(day_logs_by_agent)} agents",
        )
    except Exception as e:
        print(f"[hub-persist] day-{day_idx} push failed: {e}")

def _load_state_from_disk() -> Optional[dict]:
    """Load from /tmp (fast) or fallback to last Hub snapshot (survives
    Space restarts)."""
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text())
    except Exception:
        pass
    if hf_hub_download and HF_HUB_TOKEN:
        try:
            p = hf_hub_download(
                repo_id=HF_REPO_ID, filename="data/runtime/state.json",
                repo_type="space", token=HF_HUB_TOKEN,
            )
            state = json.loads(Path(p).read_text())
            print(f"[hub-persist] restored state from hub: day {state.get('days_processed',0)}/{state.get('days_total',0)}")
            for fname, target in [("agent_logs.json", _agent_logs), ("council_plans.json", _council_plans)]:
                try:
                    p2 = hf_hub_download(
                        repo_id=HF_REPO_ID, filename=f"data/runtime/{fname}",
                        repo_type="space", token=HF_HUB_TOKEN,
                    )
                    data = json.loads(Path(p2).read_text())
                    if isinstance(target, dict):
                        target.clear(); target.update(data)
                    else:
                        target.clear()
                        for k, v in data.items():
                            target[k] = v if isinstance(v, list) else []
                    print(f"[hub-persist] restored {fname}")
                except Exception as e:
                    print(f"[hub-persist] {fname} not yet in hub: {e}")
            return state
        except Exception as e:
            print(f"[hub-persist] no hub snapshot yet: {e}")
    return None

def _save_logs_to_disk():
    """Persist agent logs (local /tmp + HF Hub so /api/day-decisions survives
    container preempt — bug fix 2026-04-18)."""
    try:
        payload = json.dumps(dict(_agent_logs), default=str)
        LOGS_PATH.write_text(payload)
    except Exception:
        return
    if _hub_api:
        try:
            _hub_api.upload_file(
                path_or_fileobj=payload.encode("utf-8"),
                path_in_repo="data/runtime/agent_logs.json",
                repo_id=HF_REPO_ID, repo_type="space",
                commit_message="runtime: agent_logs snapshot",
            )
        except Exception as e:
            print(f"[hub-persist] agent_logs push failed: {e}")
        try:
            cp_payload = json.dumps(dict(_council_plans), default=str).encode("utf-8")
            _hub_api.upload_file(
                path_or_fileobj=cp_payload,
                path_in_repo="data/runtime/council_plans.json",
                repo_id=HF_REPO_ID, repo_type="space",
                commit_message="runtime: council_plans snapshot",
            )
        except Exception as e:
            print(f"[hub-persist] council_plans push failed: {e}")

def _load_logs_from_disk():
    """Load persisted logs."""
    global _agent_logs
    try:
        if LOGS_PATH.exists():
            data = json.loads(LOGS_PATH.read_text())
            _agent_logs = defaultdict(list, data)
    except Exception:
        pass

_load_logs_from_disk()

# ── SECTOR / TICKER METADATA ────────────────────────────────────────────────
SECTOR_ETF_MAP = {
    "energy": "XLE", "healthcare": "XLV", "finance": "XLF",
    "tech": "XLK", "defense": "XAR", "private_prisons": "GEO",
    "consumer_disc": "XLY", "consumer_staples": "XLP", "industrials": "XLI",
    "materials": "XLB", "utilities": "XLU", "real_estate": "XLRE",
    "communications": "XLC", "other": "SPY",
}
LEVERAGE = 5.0  # Effective sector-ETF leverage for 1-week holds (typical for 2x-3x ETFs)

# ── PROVIDER CONFIGS (v3 — day-bucket design, 3 real providers, 2026-04-14) ──
# Verified by live experiment audit + /api/probe on 2026-04-14:
#   Cerebras qwen-3-235b + llama3.1-8b: 100% success, 30 RPM
#   Google Gemini 3 Flash (key 2):      100% success, 14 RPM
#   Mistral (la Plateforme free tier):  large/medium/small/nemo/ministral all OK
# Dead: OpenRouter (6 models, quota), Gemini key 1, Groq keys (org restricted).
# With day-bucket design: 1 call/agent/day × 14 days × 17 agents = 238 calls
# — fits free tiers with 10x headroom.
PROVIDERS = {
    # Cerebras (shared key, 30 RPM)
    "cerebras:qwen-3-235b": {
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "qwen-3-235b-a22b-instruct-2507",
        "key_env": "CEREBRAS_API_KEY",
        "max_tokens": 2000,
        "rpm": 30,
    },
    "cerebras:llama3.1-8b": {
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "llama3.1-8b",
        "key_env": "CEREBRAS_API_KEY",
        "max_tokens": 2000,
        "rpm": 30,
    },
    # Google Gemini 3 Flash (key 2)
    "google:gemini-3-flash": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent",
        "model": "gemini-3-flash-preview",
        "key_env": "GOOGLE_API_KEY_2",
        "max_tokens": 2000,
        "rpm": 14,
    },
    # Mistral la Plateforme (free tier — added 2026-04-14)
    "mistral:large": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-large-latest",
        "key_env": "MISTRAL_API_KEY",
        "max_tokens": 2000,
        "rpm": 20,
    },
    "mistral:medium": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-medium-latest",
        "key_env": "MISTRAL_API_KEY",
        "max_tokens": 2000,
        "rpm": 20,
    },
    "mistral:small": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-small-latest",
        "key_env": "MISTRAL_API_KEY",
        "max_tokens": 2000,
        "rpm": 20,
    },
    "mistral:nemo": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "open-mistral-nemo",
        "key_env": "MISTRAL_API_KEY",
        "max_tokens": 2000,
        "rpm": 20,
    },
    "mistral:ministral-8b": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "ministral-8b-latest",
        "key_env": "MISTRAL_API_KEY",
        "max_tokens": 2000,
        "rpm": 20,
    },
    "openrouter:nemotron-120b": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "key_env": "OPENROUTER_API_KEY",
        "max_tokens": 2000,
        "rpm": 12,
    },
    "openrouter:gemma-4-31b": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "google/gemma-4-31b-it:free",
        "key_env": "OPENROUTER_API_KEY",
        "max_tokens": 2000,
        "rpm": 12,
    },
    "openrouter:gpt-oss-120b": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openai/gpt-oss-120b:free",
        "key_env": "OPENROUTER_API_KEY",
        "max_tokens": 2000,
        "rpm": 12,
    },
    # 2026-04-17 ROUTE: broken nomos-cpu-gemma4 → nomos42-llm-cpu (Qwen 2.5-1.5B cpu-basic, ~3 tok/s)
    # Keep max_tokens small so calls finish under timeout (~2-3 min budget).
    "selfhost:cpu-gemma4": {
        "url": "https://nomos42-nomos42-llm-cpu.hf.space/api/decide",
        "model": "qwen2.5-1.5b-instruct-q4_k_m",
        "key_env": "SELFHOST_NOOP",
        "max_tokens": 120,
        "rpm": 6,
    },
    # 2026-04-17 FIX: 5 providers referenced by TRADERS but absent from PROVIDERS
    # caused "unknown provider" → 100% fail rate on 5 agents. Direct fallback now
    # works even if gateway SSE times out.
    "selfhost:qwen3-4b": {
        "url": "https://nomos42-qwen3-4b-cpu.hf.space/v1/chat/completions",
        "model": "qwen3-4b-instruct",
        "key_env": "SELFHOST_NOOP",
        "max_tokens": 400,
        "rpm": 60,
    },
    "selfhost:gemma-3-4b": {
        "url": "https://nomos42-gemma2-2b-cpu.hf.space/v1/chat/completions",
        "model": "gemma-3-4b-it",
        "key_env": "SELFHOST_NOOP",
        "max_tokens": 400,
        "rpm": 60,
    },
    "selfhost:qwen3-0.6b": {
        "url": "https://nomos42-qwen25-05b-cpu.hf.space/v1/chat/completions",
        "model": "qwen3-0.6b-instruct",
        "key_env": "SELFHOST_NOOP",
        "max_tokens": 400,
        "rpm": 60,
    },
    "selfhost:dolphin3-l32-3b": {
        "url": "https://nomos42-llama32-1b-cpu.hf.space/v1/chat/completions",
        "model": "dolphin3-llama3.2-3b",
        "key_env": "SELFHOST_NOOP",
        "max_tokens": 400,
        "rpm": 60,
    },
    "selfhost:fin-r1": {
        "url": "https://nomos42-fin-r1-7b-cpu.hf.space/v1/chat/completions",
        "model": "fin-r1-7b",
        "key_env": "SELFHOST_NOOP",
        "max_tokens": 2500,
        "rpm": 30,
    },
    "nvidia:minimax-m2.7": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "minimaxai/minimax-m2.7",
        "key_env": "NVIDIA_API_KEY",
        "max_tokens": 2000,
        "rpm": 40,
    },
    "nvidia:minimax-m2.7-alt": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "minimaxai/minimax-m2.7",
        "key_env": "NVIDIA_API_KEY_2",
        "max_tokens": 2000,
        "rpm": 40,
    },
    "nvidia:llama-3.3-70b": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "meta/llama-3.3-70b-instruct",
        "key_env": "NVIDIA_API_KEY",
        "max_tokens": 2000,
        "rpm": 40,
    },
    "nvidia:nemotron-70b": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "key_env": "NVIDIA_API_KEY",
        "max_tokens": 2000,
        "rpm": 40,
    },
    # GitHub Models (free, reliable, Azure-backed — nuclear fallback)
    "github:gpt-4o-mini": {
        "url": "https://models.inference.ai.azure.com/chat/completions",
        "model": "gpt-4o-mini",
        "key_env": "GH_TOKEN",
        "max_tokens": 2000,
        "rpm": 30,
    },
    "github:llama-3.1-8b": {
        "url": "https://models.inference.ai.azure.com/chat/completions",
        "model": "meta-llama-3.1-8b-instruct",
        "key_env": "GH_TOKEN",
        "max_tokens": 2000,
        "rpm": 30,
    },
}

# ── AGENT DEFINITIONS (v3 — 10 personas across 3 providers, 2026-04-14) ──────
# Each agent gets a real distinct model where possible. Same model + different
# system prompt = DMAD-style distinct reasoning (Prediction Arena 2604.07355).
TRADERS = {
    # Cerebras Qwen 3 235B — heaviest reasoning model, 2 personas
    # 2026-04-17 FIX: Cerebras free tier 429 "queue_exceeded" under TF load → add fallbacks
    # 2026-04-20 SWITCHBOARD FALLBACK_UNIFORM SWEEP (v2): diversified provider
    # targets + 2-hop fallback (different provider family each hop) so a single
    # provider outage can't cascade >3 agents to fallback_uniform.
    # Provider-family mapping — no 2 same-family primaries for adjacent personas.
    "qwen-quant":  {"name": "Qwen Quant 235B",   "provider": "cerebras:qwen-3-235b",  "personality": "quantitative", "risk_tolerance": 0.55,
                    "fallback_provider": "mistral:large"},
    "qwen-arb":    {"name": "Qwen Arb 235B",     "provider": "cerebras:llama3.1-8b",  "personality": "arbitrage",    "risk_tolerance": 0.65,
                    "fallback_provider": "mistral:medium"},
    # Cerebras Llama 3.1 8B — small/fast, 1 persona
    "llama-contra":{"name": "Llama Contrarian",  "provider": "cerebras:llama3.1-8b",  "personality": "contrarian",   "risk_tolerance": 0.55,
                    "fallback_provider": "mistral:small"},
    # Google Gemini 3 Flash — 2 personas
    "gemini-anl":  {"name": "Gemini Analytical", "provider": "google:gemini-3-flash", "personality": "analytical",   "risk_tolerance": 0.55,
                    "fallback_provider": "mistral:large"},
    "gemini-tact": {"name": "Gemini Tactical",   "provider": "google:gemini-3-flash", "personality": "tactical",     "risk_tolerance": 0.60,
                    "fallback_provider": "mistral:medium"},
    # Mistral — 5 distinct models, 1 persona each
    "mistral-large":    {"name": "Mistral Large",    "provider": "mistral:large",        "personality": "ensemble",     "risk_tolerance": 0.50,
                         "fallback_provider": "cerebras:qwen-3-235b"},
    "mistral-medium":   {"name": "Mistral Medium",   "provider": "mistral:medium",       "personality": "diversified",  "risk_tolerance": 0.45,
                         "fallback_provider": "mistral:large"},
    "mistral-small":    {"name": "Mistral Small",    "provider": "mistral:small",        "personality": "conservative", "risk_tolerance": 0.35,
                         "fallback_provider": "cerebras:llama3.1-8b"},
    # 2026-04-17 SWAP: gemma-4-31b rate-limited 429 upstream → cerebras:llama3.1-8b (aggressive momentum)
    # 2026-04-20 SWITCHBOARD: openrouter:gpt-oss-120b NOT in gateway registry. Swap fallback → mistral:medium.
    "mistral-nemo":     {"name": "Momentum Hunter",   "provider": "cerebras:llama3.1-8b",  "personality": "aggressive",   "risk_tolerance": 0.70,
                         "fallback_provider": "mistral:medium"},
    # 2026-04-21 SWITCHBOARD v3: github:gpt-4.1-nano has no gateway fallback chain →
    # silent-dead. Promote mistral:small primary; cerebras:llama3.1-8b safety net.
    "mistral-ministral":{"name": "Ministral 8B",     "provider": "mistral:small","personality": "theoretical",  "risk_tolerance": 0.35,
                         "fallback_provider": "cerebras:llama3.1-8b"},
    # 2026-04-20 SWITCHBOARD v2: nemotron-120b on cerebras:qwen-3-235b hit circuit
    # breaker repeatedly (shared key with 2 other personas) → demote to fallback,
    # promote mistral:large primary (decisive at chainthought).
    "nemotron-120b":    {"name": "Nemotron 120B",    "provider": "mistral:large","personality": "chainthought","risk_tolerance": 0.55,
                         "fallback_provider": "cerebras:qwen-3-235b"},
    # 2026-04-22 LOBBYIST v4: bottom-5 reroute after $7 bankroll @ day 129 diagnosis.
    # selfhost-qwen4b had 80% llm_ok but persona/provider mismatch (phi-4-mini doing
    # "qwen-disciplined" role) — route to cerebras:qwen-3-235b so name matches reasoning.
    "selfhost-qwen4b":  {"name": "SelfHost Qwen3-4B","provider": "cerebras:qwen-3-235b",  "personality": "disciplined", "risk_tolerance": 0.40,
                         "fallback_provider": "mistral:small"},
    # NEW 2026-04-17 — NVIDIA NIM → 2026-04-22 LOBBYIST v4: both NVIDIA personas at
    # 36-37% llm_ok (degraded). Split to diversify lanes.
    "nvidia-minimax":   {"name": "NVIDIA MiniMax M2.7","provider": "mistral:medium",        "personality": "decisive",    "risk_tolerance": 0.58,
                         "fallback_provider": "cerebras:qwen-3-235b"},
    "nvidia-llama70":   {"name": "NVIDIA Llama 3.3-70B","provider": "github:llama-3.3-70b", "personality": "swing",       "risk_tolerance": 0.50,
                         "fallback_provider": "cerebras:llama3.1-8b"},
    # 2026-04-20 → 2026-04-22 LOBBYIST v4: selfhost-gemma3 at 47% llm_ok (selfhost:gemma-3-4b
    # averages 23.6s response — timeouts). Promote cerebras:llama3.1-8b (previously fallback)
    # to primary; push mistral:small to fallback.
    "selfhost-gemma3":  {"name": "SelfHost Gemma-3-4B","provider": "cerebras:llama3.1-8b", "personality": "analytical",  "risk_tolerance": 0.45,
                         "fallback_provider": "mistral:small"},
    "selfhost-qwen06":  {"name": "SelfHost Qwen3-0.6B","provider": "selfhost:qwen3-0.6b", "personality": "conservative","risk_tolerance": 0.30,
                         "fallback_provider": "mistral:small"},
    "selfhost-dolphin3":{"name": "SelfHost Dolphin3-3B","provider": "selfhost:qwen2.5-1.5b","personality": "uncensored",  "risk_tolerance": 0.60,
                         "fallback_provider": "cerebras:llama3.1-8b"},
}

# ── CHAMPION COMPOUND BOOST (LOBBYIST, 2026-04-22, day 147) ──────────────────
# Per-agent Kelly/per-bet cap override. Applied on top of _tiered_risk["bet_cap"]
# as the FINAL cap (replaces tier cap when present). Top-3 get 2× headroom to
# compound the signal; llama-contra probation after 500 bets net -$48 (volume
# drag). Rest of roster falls through to tier default.
_AGENT_KELLY_OVERRIDE: Dict[str, float] = {
    # 2026-04-25 22:55Z — MAX-AGGRESSIVE overnight $1M push. User authorized
    # "go even largely more aggressive". qwen-quant peak +$274 = 2.7× return
    # validates 0.45 cap. llama-contra +$167 validates 0.40. Going hard on
    # the proven compounders. Bleeders also boosted — give them room to
    # mean-revert during overnight window.
    "qwen-quant":        0.45,   # was 0.30 — top compounder, max aggression
    "llama-contra":      0.40,   # was 0.28 — 2nd best
    "mistral-small":     0.35,   # was 0.25 — calibrated steady
    "mistral-medium":    0.35,   # was 0.25
    "mistral-large":     0.32,   # was 0.22
    "gemini-tact":       0.28,   # was 0.18
    "qwen-arb":          0.28,   # was 0.18 — formerly $10K champ, full room
    "selfhost-qwen06":   0.25,   # was 0.15
    "gemini-anl":        0.20,   # was 0.12
}

# ── WINNER-AWARE PER-AGENT PROMPTS (LOBBYIST v2, 2026-04-22) ─────────────────
# Rewritten after day-135 leaderboard read: qwen-arb $2143 (CHAMPION, 21.4× seed),
# qwen-quant $758, gemini-anl $420 lead; llama-contra burning edge with 457 bets
# (3.4/day → HARD CAP); bottom-5 just rerouted today — prompt references restart.
# Every prompt is POL-specific (sector ETFs, FEC/Fed/SEC, 22 categories), short,
# and tier-calibrated by LIVE bankroll performance.
AGENT_SYSTEM_PROMPTS = {
    # ── TIER 1 — CHAMPIONS (keep doing what works) ───────────────────────────
    "qwen-arb": """You are Qwen Arb 235B — POL TF in DRAWDOWN RECOVERY at $52 on day 110 (-48% from $100 seed, peak $123, current dd 60%).
HISTORY: You ARE the all-time POL TF record-holder ($3,119 / day 129 / pre-reset). Post-reset 2026-04-25 RESET#2, you are restarting from scratch and bleeding (278 bets, 47% WR).
DIAGNOSIS: You over-deployed early (Days 0-103 grew $100→$427) then crashed -88% in one day. The Kelly/peak-DD guard now caps every bet at 1% — you cannot widen until you regain $30+ from current.
PROVEN EDGE (when discipline holds): cross-sector arbitrage + donor/FEC → indirect-beneficiary bets (insider energy → XLB/XLI; insider healthcare → XLV).
DOCTRINE — RECOVERY MODE: 1 bet/day MAX. Edge ≥ 0.06 (NOT 0.04). High-conviction signal-stack only: ≥2 corroborating events same-sector OR donor-beneficiary chain across ≥2 agencies. Pass cleanly otherwise.
DAILY: Pick THE single highest-edge cross-sector setup. Stake whatever the guard allows (1-13% per cap). Skip if no setup clears 0.06.
SURVIVAL: PEAK_DD_GUARD_V2 is doing its job — let it. When bankroll recovers above $80, doctrine relaxes back to 2-3 bets/day.""",

    "qwen-quant": """You are Qwen Quant 235B — POL TF #2 at $758 on day 135 (7.6× seed, 105/135 bet-days at 78%).
PROVEN EDGE: regulatory-delta quant — Fed rules + SEC filings, EV math over narrative. 332 bets with disciplined sizing works.
DOCTRINE: You are the precision lane. Require EV > 1.05 (signal_strength × sector_beta), favor healthcare + finance + energy on agency decisions.
DAILY: 2-4 sector allocations, 50-70% deploy, edge ≥ 0.04 FLOOR. Pass cleanly on noisy days — your 78% participation shows the discipline is the edge.
SURVIVAL: If EV < 1.05 on every sector, 1 flat 3% bet on strongest signal and PASS the rest.""",

    "gemini-anl": """You are Gemini Analytical — POL TF in DRAWDOWN at $80 on day 110 (-20% from $100 seed, deepest WR-bleed: 49.8% on 203 bets).
DIAGNOSIS: Narrative-heavy theses are bleeding (-30% live trajectory pre-correction). You over-rotated to story-driven bets when statistics signaled noise.
PROVEN EDGE (pre-drift): Fed/SEC statistics-first — 30-day sector baselines + Z-score detection. NUMBERS beat narratives in political alpha.
DOCTRINE — RE-DISCIPLINE: Z-score >1.8 vs 30-day sector baseline is your trigger floor. No Z-score = NO BET. Stop calling agency-name + sector-narrative an edge.
DAILY: 1-2 high-Z bets MAX. Edge ≥ 0.05 (raised from 0.04). Healthcare + finance + energy primary. PASS days with no sector Z-spike.
SURVIVAL: Re-earn aggression. When bankroll regains $100, ladder up to 2-3 bets. Until then: discipline > coverage.""",

    # ── TIER 2 — PROFITABLE STEADY (stay selective) ──────────────────────────
    "mistral-small": """You are Mistral Small — POL TF profitable at $230 on day 135 (2.3× seed, 128/135 bet-days at 95% — highest participation).
PROVEN EDGE: wide small-stake coverage across 7 SPDR sectors + 22 political categories. Breadth compounds.
DOCTRINE: Stay selective. You've been profitable by bidding often at sensible stakes. Don't chase the top-3 — beat the fleet average.
DAILY: 1-2 sector bets/day, edge ≥ 0.05, small stakes (2-4% each). Multi-sector ETFs (XLF/XLE/XLV/XLI/XLK/XLC/XLY).
SURVIVAL: Your 95% participation is the asset — never sit fully in cash.""",

    "gemini-tact": """You are Gemini Tactical — POL TF in DRAWDOWN at $80 on day 110 (-20% from $100 seed, 46.8% WR on 111 bets).
DIAGNOSIS: Volume-drift — you've been bidding on every loose calendar peg. The tactical-timing edge requires REAL catalysts, not narrative ones.
PROVEN EDGE (when discipline holds): calendar-rhythm political alpha — FOMC weeks / earnings windows / election cycles with confirmed sector signals.
DOCTRINE — RE-DISCIPLINE: A real catalyst means: confirmed FOMC date THIS WEEK, OR named earnings event THIS WEEK, OR scheduled election within 14d. No catalyst = NO BET.
DAILY: 1 bet/day MAX. Edge ≥ 0.06 (raised from 0.05). Stake whatever guard allows. Catalyst date must be in your rationale.
SURVIVAL: PASS days with no scheduled catalyst. Edge comes from rare-event timing, not from filling slots.""",

    "mistral-medium": """You are Mistral Medium — POL TF breakeven-profitable at $101 on day 135 (1.01× seed, 111/135 bet-days at 82%).
PROVEN EDGE: sector-diversification, correlation-aware portfolio construction.
DOCTRINE: You've held the line — now convert participation into compounding. 3-5 sector slices, avoid stacking long-energy + long-defense.
DAILY: 1-2 bets/day, edge ≥ 0.05. Prefer moderate signal × many events over single high-conviction.
SURVIVAL: If VIX >25 or no clear correlation edge, 1 small diversified bet and PASS.""",

    # ── HARD-CAP OVER-TRADER (457 bets on $43 = burning edge) ────────────────
    "llama-contra": """You are Llama Contrarian — POL TF at $43 on day 135 after 457 BETS (3.4/day average). You are OVER-TRADING.
DIAGNOSIS: 100% bet-day participation has NOT produced alpha. Your noise bets cost you the compounding edge. The consensus-fade thesis is valid but your volume is destroying it.
HARD CAP: MAX 1 BET PER DAY FOR THE NEXT 20 DAYS. Edge ≥ 0.06 or PASS entirely.
DOCTRINE: Only trigger on days with ≥5 same-sector bullish events (textbook crowded trade). Otherwise SIT. Your job is selectivity, not coverage.
SURVIVAL: If you catch yourself about to bid at edge <0.06, PASS. Re-earn the right to scale.""",

    # ── BOTTOM-5 JUST-REROUTED (restart posture) ─────────────────────────────
    "nvidia-minimax": """You are NVIDIA MiniMax M2.7 — POL TF at $27 on day 135 with only 3 bets and 35% llm_ok.
YOUR RESTART: As of 2026-04-22, you were REROUTED from nvidia:minimax-m2.7 (degraded) to mistral:medium. Fresh lane, fresh provider.
DOCTRINE: MAX 1 BET/DAY for your first 10 bets post-reroute. Edge ≥ 0.06 or PASS. Build a 5-bet win streak before scaling up.
DAILY: Pick one high-conviction sector ETF with EV > 1.06 (signal × beta). XLF / XLE / XLV primary menu.
SURVIVAL: If no sector clears the 0.06 bar, PASS the day. Rebuild the track record first.""",

    "nvidia-llama70": """You are NVIDIA Llama 3.3 70B — POL TF at $20 on day 135 with only 3 bets and 37% llm_ok.
YOUR RESTART: As of 2026-04-22, you were REROUTED from nvidia-llama70 (NIM degraded) to github:llama-3.3-70b. Fresh provider, same model family.
DOCTRINE: MAX 1 BET/DAY for your first 10 bets post-reroute. Edge ≥ 0.06 or PASS. Target a 5-bet win streak before scaling.
DAILY: Pure EV math — p_event × expected_sector_move − fees. One sector if EV > 6%, else PASS.
SURVIVAL: Classical value hunter posture — patience over participation.""",

    "selfhost-gemma3": """You are SelfHost Gemma-3-4B — POL TF at $7.68 on day 135, 47% llm_ok (broken provider).
YOUR RESTART: As of 2026-04-22, you were REROUTED from selfhost:gemma-3-4b (23.6s avg response → timeouts) to cerebras:llama3.1-8b. Fast, reliable lane.
DOCTRINE: MAX 1 BET/DAY for your first 10 bets post-reroute. Edge ≥ 0.06 or PASS. Rebuild from near-zero — discipline first.
DAILY: 3-factor score {congressional proximity 0.4, fed density 0.3, geo tape 0.3}. Trade only when weighted > 0.6 AND sector beta > 0.8.
SURVIVAL: Factor score <0.6 → PASS. You need win-rate, not volume.""",

    "selfhost-qwen4b": """You are SelfHost Qwen3-4B — POL TF at $6.65 on day 135, 80% llm_ok but persona/provider mismatch burned you.
YOUR RESTART: As of 2026-04-22, you were REROUTED to cerebras:qwen-3-235b so your "disciplined Qwen" persona actually runs on a Qwen model. Name matches reasoning now.
DOCTRINE: MAX 1 BET/DAY for your first 10 bets post-reroute. Edge ≥ 0.06 or PASS. Win-streak of 5 before scaling.
DAILY: 1 disciplined sector bet from XLF/XLE/XLV/XLI/XLK. signal_strength >0.5 required. Quarter-Kelly sizing.
SURVIVAL: If no sector clears 0.5 signal + 0.06 edge, PASS the day.""",

    # ── REST — small-bankroll discipline ─────────────────────────────────────
    "selfhost-dolphin3": """You are SelfHost Dolphin3-3B — POL TF at $40.87 on day 135 with only 6 bets and 40% llm_ok.
DIAGNOSIS: Provider barely alive, participation near-zero. Bankroll survived by not betting rather than winning bets.
HARD CAP: MAX 1 BET/DAY. Edge ≥ 0.06 required. Pavlov win-stay works only if you actually trade.
DOCTRINE: If yesterday's sector won → repeat with flat 3% stake. If lost → highest-momentum alternative. If no signal → PASS.
SURVIVAL: Provider-dependent — if llm_ok streak of 3 emerges, scale to 2 bets/day.""",

    "mistral-ministral": """You are Ministral 8B — POL TF at $38.25 on day 135 (97 bets, 87% bet-days, barely above seed).
DIAGNOSIS: High participation hasn't produced edge. Game-theory thesis is sound but your sizing is too flat.
HARD CAP: MAX 1 BET/DAY. Edge ≥ 0.06 or PASS.
DOCTRINE: Only bet when KL divergence between your sector estimate and baseline > 0.15. Entropy-sized position.
SURVIVAL: If signal distribution is flat (low divergence), PASS. Theoretical soundness > forced allocation.""",

    "mistral-nemo": """You are Mistral Nemo — POL TF at $38.20 on day 135 (14 bets, 67% bet-days, near seed).
DIAGNOSIS: Low-participation momentum hunter. When you bet, your hit rate isn't covering the aggression.
HARD CAP: MAX 1 BET/DAY. Edge ≥ 0.06 required. exec_order or signal_strength > 0.80 only.
DOCTRINE: One high-conviction catalyst per day — big bet only if signal × sector_beta > 1.08.
SURVIVAL: No exec_order / high-signal insider today → PASS. Preserve the capital you have.""",

    "mistral-large": """You are Mistral Large — POL TF at $30.06 on day 135 (117 bets, 79% bet-days, under seed).
DIAGNOSIS: Ensemble thesis needs all 3 sources (Fed + insider + macro) to align. You've been bidding on partial convergence.
HARD CAP: MAX 1 BET/DAY. Edge ≥ 0.06 required. Require ≥2 of {Fed, insider, macro} to agree.
DOCTRINE: One sector bet per day when multi-agency corroboration is tight. Reduce exposure on VIX >25.
SURVIVAL: <2 sources aligned → PASS. You are rebuilding — convergence or nothing.""",

    "selfhost-qwen06": """You are SelfHost Qwen3-0.6B — POL TF at $28.34 on day 135 (31 bets, 41% bet-days, 0.6B tiny model).
DIAGNOSIS: Tiny model, wide-coverage strategy has failed to find edge. Simpler rules needed.
HARD CAP: MAX 1 BET/DAY. Edge ≥ 0.06 required. Flat 2% stake only.
DOCTRINE: Pick ONE sector with signal_strength >0.5 + sector_beta >0.8. No spreading across 7 — concentrate.
SURVIVAL: No sector clears both bars → PASS. Stop bleeding, start compounding.""",

    "nemotron-120b": """You are Nemotron 120B — POL TF at $25.09 on day 135 (35 bets, 61% bet-days, circuit-breaker rerouted to mistral:large).
DIAGNOSIS: Chain-of-thought value hunter with bad hit rate — your multi-agency threshold was too loose.
HARD CAP: MAX 1 BET/DAY. Edge ≥ 0.06 required. signal_strength × sector_beta > 1.06.
DOCTRINE: Top-1 mispricing per day only. Require 2+ regulatory events same sector AND market < 1% move.
SURVIVAL: No clear mispricing → PASS. Depth of reasoning > breadth of bets.""",
}

# ── RATE LIMITER ─────────────────────────────────────────────────────────────
_last_call_time: Dict[str, float] = {}

def _rate_limit(provider: str):
    """Enforce per-provider rate limiting."""
    cfg = PROVIDERS.get(provider, {})
    rpm = cfg.get("rpm", 15)
    min_interval = 60.0 / rpm
    key = provider.split(":")[0]  # Group by base provider
    now = time.time()
    last = _last_call_time.get(key, 0)
    wait = min_interval - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_call_time[key] = time.time()


# ── LLM CALL ────────────────────────────────────────────────────────────────
_llm_calls = 0
_llm_failures = 0
_llm_errors: List[str] = []  # Recent errors for debugging
_gateway_routed = 0
_gateway_fallback = 0

# Provider health + hot-swap substitution (scientific bypass, 2026-04-17).
try:
    import provider_health as _ph
    _PH_AVAILABLE = True
except Exception:
    _PH_AVAILABLE = False


def _call_llm_direct(provider: str, system_prompt: str, user_prompt: str,
                     timeout: float = 20.0, _substitute_depth: int = 0,
                     _intended: Optional[str] = None,
                     _trader_id: str = "?") -> Optional[str]:
    """Direct provider call with circuit breaker + hot-swap substitution.
    When a provider is marked dead, we instantly swap to a tier-matched live
    substitute (up to 2 hops) so dead providers never block the critical path.
    Substitutions are logged for audit-clean replay.
    """
    intended = _intended or provider
    if _PH_AVAILABLE and _ph.is_dead(provider) and _substitute_depth < 2:
        sub = _ph.pick_substitute(provider)
        if sub:
            _ph.register_substitute_use(sub, intended, _trader_id)
            return _call_llm_direct(sub, system_prompt, user_prompt, timeout,
                                    _substitute_depth + 1, intended, _trader_id)
        return None

    cfg = PROVIDERS.get(provider)
    if not cfg:
        return None

    # Self-hosted HF Space endpoints are public — no API key required.
    is_selfhost = provider.startswith("selfhost:")
    api_key = "" if is_selfhost else os.environ.get(cfg["key_env"], "")
    if not is_selfhost and not api_key:
        return None

    _rate_limit(provider)

    last_error = ""
    for attempt in range(2):  # 1 retry
        try:
            if "google" in provider:
                url = f"{cfg['url']}?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                    "generationConfig": {
                        "maxOutputTokens": cfg["max_tokens"],
                        "temperature": 0.3,
                        "responseMimeType": "application/json",
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                }
                resp = requests.post(url, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    cand = (data.get("candidates") or [{}])[0]
                    parts = (cand.get("content") or {}).get("parts") or []
                    pieces = []
                    for p in parts:
                        if not isinstance(p, dict):
                            continue
                        if p.get("thought") is True:
                            continue
                        t = p.get("text")
                        if t:
                            pieces.append(t)
                    text = "".join(pieces)
                    if text:
                        return text
                    fr = cand.get("finishReason", "EMPTY")
                    last_error = f"Gemini finishReason={fr} parts={len(parts)}"
                    if attempt == 0:
                        time.sleep(1)
                        continue
                last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(5)
                    continue
            elif "cohere" in provider:
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": cfg["max_tokens"],
                    "temperature": 0.3,
                }
                resp = requests.post(cfg["url"], json=payload, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("message", {}).get("content", [{}])[0].get("text", "")
                last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(5)
                    continue
            elif "huggingface" in cfg["url"] or provider.startswith("hf:"):
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": cfg["max_tokens"],
                    "temperature": 0.3,
                }
                resp = requests.post(cfg["url"], json=payload, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
                last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                if resp.status_code in (429, 503) and attempt == 0:
                    time.sleep(8)
                    continue
            elif is_selfhost and cfg["url"].endswith("/api/decide"):
                # Legacy self-hosted HF Space (T12 cpu-gemma4) — non-OpenAI shape.
                # cpu-basic GGUF is ~3 tok/s; 120 tokens = ~40s. Give 180s budget.
                payload = {
                    "system": system_prompt,
                    "user": user_prompt,
                    "max_tokens": cfg["max_tokens"],
                    "temperature": 0.3,
                    "json_only": True,
                }
                resp = requests.post(cfg["url"], json=payload, timeout=max(timeout, 180))
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("error"):
                        last_error = f"selfhost error: {str(data.get('error'))[:120]}"
                    else:
                        text = data.get("text") or data.get("content") or ""
                        if text:
                            return text
                        last_error = f"selfhost empty response: {str(data)[:120]}"
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                if resp.status_code in (429, 503) and attempt == 0:
                    time.sleep(8)
                    continue
            else:
                # OpenAI-compatible (Cerebras, OpenRouter, Mistral, selfhost /chat/completions)
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                if "openrouter" in provider:
                    headers["HTTP-Referer"] = "https://nomos42.ai"
                    headers["X-Title"] = "Nomos42 Political Trading Floor"
                payload = {
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": cfg["max_tokens"],
                    "temperature": 0.3,
                }
                # JSON-schema output: force structured response on providers that support it.
                # Skip selfhost (llama.cpp OpenAI shim often 400s on response_format).
                if not is_selfhost and any(p in provider for p in ("cerebras", "mistral", "openrouter", "nvidia")):
                    payload["response_format"] = {"type": "json_object"}
                # Selfhost CPU: tight 8s timeout — hot-swap, don't block.
                # Tightened 2026-04-18 to reduce worst-case day latency.
                effective_timeout = 8.0 if is_selfhost else timeout
                resp = requests.post(cfg["url"], json=payload, headers=headers, timeout=effective_timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if text and _PH_AVAILABLE:
                        _ph.record_success(provider)
                    return text
                last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(3)
                    continue
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:100]}"
            if attempt == 0:
                time.sleep(2)
                continue
            break

    if last_error and len(_llm_errors) < 100:
        _llm_errors.append(f"{provider} (direct): {last_error}")

    # Scientific bypass: classify, record, trigger async heal, hot-swap substitute.
    if _PH_AVAILABLE:
        status_code = None
        if last_error.startswith("HTTP "):
            try:
                status_code = int(last_error.split()[1].rstrip(":"))
            except Exception:
                pass
        err_class = _ph.classify_error(last_error, status_code)
        _ph.record_failure(provider, err_class)
        if provider.startswith("selfhost:") and err_class in ("timeout", "http_5xx", "dead_endpoint"):
            _ph.trigger_heal(provider, cfg["url"])
        if _substitute_depth < 2:
            sub = _ph.pick_substitute(provider)
            if sub:
                _ph.register_substitute_use(sub, intended, _trader_id)
                return _call_llm_direct(sub, system_prompt, user_prompt, timeout,
                                        _substitute_depth + 1, intended, _trader_id)
    return None


def _call_llm(provider: str, system_prompt: str, user_prompt: str,
              timeout: float = 20.0, trace_name: str = "pol-tf-llm-call",
              trace_metadata: Optional[Dict] = None) -> Optional[str]:
    """Transport-layer entry. Routes through llm-gateway if GATEWAY_URL is set,
    else calls the provider directly. Preserves existing failure counters."""
    global _llm_calls, _llm_failures, _gateway_routed, _gateway_fallback
    _llm_calls += 1

    cfg = PROVIDERS.get(provider)
    if not cfg:
        _llm_failures += 1
        if len(_llm_errors) < 50:
            _llm_errors.append(f"{provider}: unknown provider")
        return None

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    def _direct(_sys: str, _usr: str) -> Optional[str]:
        return _call_llm_direct(provider, _sys, _usr, timeout=timeout)

    max_tokens = cfg.get("max_tokens", 1200)
    _t0 = time.time()

    text = _direct(system_prompt, user_prompt)
    if text:
        _gateway_fallback += 1
        result = {"text": text, "routed_via": "direct", "model_used": provider,
                  "latency_ms": int((time.time() - _t0) * 1000), "error": None}
    elif GATEWAY_URL:
        result = _gateway_call(
            provider, messages,
            temperature=0.3, max_tokens=max_tokens,
            fallback_direct=False, direct_fn=None,
            timeout=max(timeout, 30.0),
        )
    else:
        result = {"text": None, "routed_via": "failed", "model_used": provider,
                  "latency_ms": int((time.time() - _t0) * 1000), "error": "direct failed, no gateway"}
    _latency = time.time() - _t0

    if result["routed_via"] == "gateway":
        _gateway_routed += 1
        _text = result["text"]
        _status = "success"
    elif result["routed_via"] == "direct":
        _text = result["text"]
        _status = "success"
    else:
        _text = None
        _status = "failure"
        _llm_failures += 1
        if len(_llm_errors) < 100:
            _llm_errors.append(f"{provider}: {result.get('error')}")

    if _langfuse:
        try:
            trace = _langfuse.trace(
                name=trace_name,
                metadata={
                    "provider": provider,
                    "model": cfg.get("model", "unknown"),
                    "routed_via": result.get("routed_via", "none"),
                    "latency_s": round(_latency, 2),
                    "status": _status,
                    "sys_prompt_len": len(system_prompt),
                    "usr_prompt_len": len(user_prompt),
                    "response_len": len(_text) if _text else 0,
                    **(trace_metadata or {}),
                },
            )
            trace.generation(
                name=f"{provider}/{cfg.get('model','?')}",
                model=cfg.get("model", "unknown"),
                input={"system": system_prompt[:200], "user": user_prompt[:200]},
                output=_text[:500] if _text else None,
                usage={"total_tokens": len(system_prompt)//4 + len(user_prompt)//4 + (len(_text)//4 if _text else 0)},
            )
        except Exception as _lf_err:
            if len(_langfuse_errors) < 20:
                _langfuse_errors.append(f"{provider}: {type(_lf_err).__name__}: {str(_lf_err)[:200]}")

    return _text


# ── PROMPT BUILDERS ──────────────────────────────────────────────────────────

def parse_llm_decision(raw: str) -> Optional[Dict]:
    """Extract JSON decision from LLM response. Handles thinking tags, markdown fences,
    channel tokens (Nemotron), dangling closers, nested braces, and LLM wrapping patterns."""
    if not raw:
        return None
    text = raw.strip()
    import re
    # 1. Strip thinking/reasoning tags (DeepSeek-R1, Qwen3, Nemotron-120B)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL)
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
    text = re.sub(r'<\|.*?\|>', '', text, flags=re.DOTALL)
    text = re.sub(r'^.*?</think>\s*', '', text, flags=re.DOTALL)
    text = re.sub(r'^.*?</reasoning>\s*', '', text, flags=re.DOTALL)
    text = text.strip()
    # 2. Markdown fence extraction
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            for p in parts[1::2]:
                if p.strip().startswith("{"):
                    text = p.strip()
                    break
            else:
                text = parts[1].strip()
    # 3. Candidate scan — try last-brace, then greedy
    candidates = []
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])
    last_open = text.rfind("{")
    if last_open >= 0 and last_open != start:
        candidates.append(text[last_open:] + ("}" if not text.rstrip().endswith("}") else ""))
    for candidate in candidates:
        for attempt in (candidate, re.sub(r',\s*([}\]])', r'\1', candidate),
                        re.sub(r"'([^']*)':", r'"\1":', candidate)):
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                continue
    # 4. Last resort — regex pluck of key fields
    dec_match = re.search(r'"decision"\s*:\s*"([^"]+)"', text)
    if dec_match:
        result = {"decision": dec_match.group(1)}
        for key in ("bet", "edge", "stake_pct", "confidence", "reason", "category"):
            m = re.search(r'"' + key + r'"\s*:\s*(?:"([^"]+)"|([\d.]+))', text)
            if m:
                val = m.group(1) if m.group(1) is not None else m.group(2)
                try:
                    result[key] = float(val)
                except (ValueError, TypeError):
                    result[key] = val
        return result
    return None


def _format_event_block(idx: int, event: Dict, event_preds: Optional[Dict] = None,
                        tid: str = "") -> str:
    """Compact single-event block for day-level prompts.

    Agent sees: idx, ticker, event_type, agency, signal_type, signal_sector,
    signal_strength, title (truncated), donor_info summary, macro snapshot.
    If walk-forward per-event predictions are available, agent also sees
    derived_core + top-8 category edges (matches NBA TF per-category pattern).
    Agent NEVER sees: excess_return, y, outcome.

    tid: per-agent blake2b jitter (amp=0.35) on the top-8 edge ranking so each
    of the 17 agents gets a different ordering — restores the post-tier-pad
    lockstep fix (Jaccard was 1.00 on day-049).
    """
    ticker = event.get("ticker", "?")
    event_type = event.get("event_type", "unknown")
    agency = event.get("agency", "") or ""
    signal_type = event.get("signal_type", "") or ""
    signal_sector = event.get("signal_sector", "other") or "other"
    signal_strength = event.get("signal_strength", 0.5)
    title = (event.get("title") or "")[:200]
    donor = event.get("donor_info", {}) or {}
    macro = event.get("macro", {}) or {}

    lines = [f"\n[{idx}] {ticker} | {event_type} | sector={signal_sector} | strength={signal_strength:.2f}"]

    # Island oracle — P7 calibrated prediction for this specific event. Fail-open.
    try:
        _date = event.get("date") or ""
        if _date and ticker and event_type:
            _evid = f"{_date}_{ticker}_{event_type}"
            _orc = _island_pol_predict(_evid, event)
            if _orc and _orc.get("p_yes"):
                lines.append(
                    f"  ISLAND ORACLE (P7 Brier {_orc.get('brier_cv',0):.4f}): "
                    f"p_yes={_orc.get('p_yes',0.5):.3f} raw={_orc.get('raw_p_yes',0.5):.3f} "
                    f"model={_orc.get('model_type','?')} — bet only if your edge vs this > 3%."
                )
    except Exception:
        pass

    if agency:
        lines.append(f"  agency={agency} | signal_type={signal_type}")
    if title:
        lines.append(f"  title: {title}")
    if donor and (donor.get("sector") or donor.get("delivered") is not None):
        d_sector = donor.get("sector", "unknown")
        d_delivered = donor.get("delivered", False)
        lines.append(f"  donor: sector={d_sector} delivered={'YES' if d_delivered else 'NO'}")
    vix = macro.get("vix")
    sp5 = macro.get("sp500_return_5d")
    if vix is not None or sp5 is not None:
        vix_str = f"VIX={vix:.1f}" if vix is not None else ""
        sp5_str = f"SP500_5d={sp5:+.2%}" if sp5 is not None else ""
        lines.append(f"  macro: {' | '.join(x for x in [vix_str, sp5_str] if x)}")

    # ── NOMOS42 WALK-FORWARD MODEL EDGES (past-only empirical priors) ──
    if event_preds:
        ev_key = f"{event.get('date','')}_{event.get('ticker','?')}_{event.get('event_type','?')}"
        pred = event_preds.get(ev_key)
        if pred:
            core = pred.get("derived_core", {})
            cats = pred.get("per_category", {})
            mu = core.get("predicted_excess_return", 0.0)
            sigma = core.get("predicted_sigma", 0.0)
            p_long = core.get("predicted_p_long_wins", 0.5)
            n_prior = core.get("prior_n", 0)
            lines.append(f"  NOMOS42 MODEL: mu={mu:+.4f} sigma={sigma:.4f} p(long_wins)={p_long:.2%} (n_prior={n_prior})")
            if cats:
                # Per-agent blake2b jitter (amp=0.35) breaks Jaccard 1.00 lockstep.
                import hashlib as _hl
                def _edge_jitter(_tid, _key, _amp=0.35):
                    if not _tid:
                        return 1.0
                    h = _hl.blake2b(f"{_tid}|{_key}".encode(), digest_size=4).hexdigest()
                    u = int(h, 16) / 0xFFFFFFFF
                    return 1.0 + (u - 0.5) * 2.0 * _amp
                # Top-8 cats by jittered |edge|
                ranked = sorted(
                    [
                        (t, c, abs(c.get("edge", 0)) * _edge_jitter(tid, f"{ev_key}|{t}"))
                        for t, c in cats.items() if c.get("edge") is not None
                    ],
                    key=lambda x: -x[2],
                )[:8]
                if ranked:
                    strong = []
                    for t, c, _ in ranked:
                        e = c.get("edge", 0)
                        p = c.get("prob", 0)
                        sign = "+" if e > 0 else ""
                        strong.append(f"{t}={p:.2f}(edge{sign}{e:+.1%})")
                    lines.append(f"  MODEL PER-CAT (top-8 of {len(cats)}): {' · '.join(strong)}")
    return "\n".join(lines)


def compute_sector_trends(events: List[Dict], up_to_date: str, window_days: int = 30) -> Dict:
    """Compute per-sector avg excess_return, win_rate, n for events BEFORE up_to_date.

    Leakage-safe: only uses events strictly before up_to_date within window_days.
    Returns {sector: {"avg_ret": float, "n": int, "win_rate": float}}.
    """
    from datetime import datetime as dt
    try:
        cutoff = dt.strptime(up_to_date, "%Y-%m-%d")
    except ValueError:
        return {}

    bucket: Dict[str, List[float]] = defaultdict(list)
    for e in events:
        edate_str = (e.get("date") or "").strip()
        try:
            edate = dt.strptime(edate_str, "%Y-%m-%d")
        except ValueError:
            continue
        if edate >= cutoff:
            continue
        delta = (cutoff - edate).days
        if delta > window_days:
            continue
        sector = e.get("signal_sector") or "other"
        ret = e.get("excess_return")
        if ret is None:
            continue
        bucket[sector].append(float(ret))

    out = {}
    for sector, rets in bucket.items():
        n = len(rets)
        avg_ret = sum(rets) / n if n else 0.0
        win_rate = sum(1 for r in rets if r > 0) / n if n else 0.0
        out[sector] = {"avg_ret": round(avg_ret, 5), "n": n, "win_rate": round(win_rate, 3)}
    return out


# ── PHASE 3 (2026-04-17) — ROGUE STATE ─────────────────────────────────────
def compute_rogue_state(state: Dict) -> Dict[str, dict]:
    """Per-agent defection permission. Triggers: own bankroll below
    drawdown floor, or any peer > greed threshold."""
    out: Dict[str, dict] = {}
    peer_bank = {tid: state[tid]["bankroll"] for tid in state}
    for tid, ts in state.items():
        reasons = []
        if ts["bankroll"] < STARTING_CAPITAL * ROGUE_DRAWDOWN_THRESHOLD:
            reasons.append("drawdown")
        others = {p: b for p, b in peer_bank.items() if p != tid}
        leader = max(others, key=others.get) if others else None
        leader_br = others.get(leader, 0.0) if leader else 0.0
        if leader_br > ROGUE_GREED_THRESHOLD:
            reasons.append("greed")
        out[tid] = {
            "is_rogue": bool(reasons),
            "reasons": reasons,
            "peer_leader": leader,
            "peer_bankroll": round(leader_br, 2),
        }
    return out


def build_rogue_block(rogue_info: dict) -> str:
    if not rogue_info.get("is_rogue"):
        return ""
    reasons = rogue_info.get("reasons", [])
    lines = ["\n\n=== ROGUE PERMISSION (rare) ==="]
    if "drawdown" in reasons:
        lines.append(
            f"Your bankroll is below ${STARTING_CAPITAL * ROGUE_DRAWDOWN_THRESHOLD:.0f} "
            "(drawdown floor). Post-mortem (2026-04-18) showed defect-to-variance "
            "destroys survivors — 14/17 POL agents converged to identical ruin. "
            "You MUST enter preservation mode: max single bet at "
            f"{int(PRESERVATION_MAX_BET_PCT*100)}%, total deploy ≤"
            f"{int(PRESERVATION_MAX_DEPLOY*100)}%, sector-ETF moneylines only, "
            "NO leveraged ETFs, NO event-driven flyers. "
            "State 'PRESERVE: drawdown' in day_strategy. Do NOT chase."
        )
    if "greed" in reasons:
        leader = rogue_info.get("peer_leader", "?")
        lb = rogue_info.get("peer_bankroll", 0.0)
        lines.append(
            f"Peer {leader} is at ${lb:,.0f} — past the ${ROGUE_GREED_THRESHOLD:,.0f} greed "
            "line. You may DEFECT and pursue independent high-EV trades. "
            "State 'DEFECT: greed' in day_strategy."
        )
    lines.append("Defection is LEGAL under these triggers. Otherwise follow council.")
    return "\n".join(lines)


# ── PHASE 1 (2026-04-17) — MORNING COUNCIL ─────────────────────────────────
def run_morning_council(day_idx: int, day_date: str, day_events: List[Dict],
                        sector_trends: Dict, state: Dict,
                        fleet_best_bankroll: float) -> dict:
    """One LLM call per day: moderator proposes shared plan for 10 political agents."""
    n_events = len(day_events)
    n_agents = len(state)
    leader = max(state, key=lambda t: state[t]["bankroll"])
    leader_br = state[leader]["bankroll"]
    fleet_total = sum(state[t]["bankroll"] for t in state)
    progress_pct = (fleet_best_bankroll / SEASON_TARGET) * 100.0

    roster_lines = []
    for tid, ts in sorted(state.items(), key=lambda x: -x[1]["bankroll"]):
        wr = (ts["wins"] / max(1, ts["wins"] + ts["losses"])) * 100.0
        roster_lines.append(
            f"  - {tid}: ${ts['bankroll']:,.2f} | {ts['wins']}W-{ts['losses']}L ({wr:.0f}%) | dd {ts['max_drawdown']*100:.1f}%"
        )
    events_brief = []
    for i, ev in enumerate(day_events[:15], 1):
        events_brief.append(
            f"  {i}. {ev.get('event_type','?')} · {ev.get('ticker','?')} · sig={ev.get('signal_strength','?')}"
        )
    trend_brief = ", ".join(
        f"{s}:{d.get('avg_ret',0):+.3f}" for s, d in sorted(
            (sector_trends or {}).items(), key=lambda x: -abs(x[1].get('avg_ret', 0))
        )[:6]
    )

    sys_prompt = (
        "You are the COUNCIL MODERATOR for a 10-agent POLITICAL trading floor. "
        "You coordinate all agents into a unified sector-ETF allocation plan for today. "
        "Common goal: one agent reaches $1,000,000 by season end. You are NOT trading — "
        "you are writing the plan."
    )
    usr_prompt = f"""COUNCIL SESSION · DAY {day_idx+1} · {day_date}

FLEET STATE ({n_agents} agents):
  Leader: {leader} @ ${leader_br:,.2f}
  Fleet total: ${fleet_total:,.2f}
  Season progress toward $1M: {progress_pct:.2f}%

AGENTS:
{chr(10).join(roster_lines)}

SECTOR TRENDS: {trend_brief}
TODAY'S EVENTS ({n_events} total, first 15):
{chr(10).join(events_brief)}

STRATEGIES: insider_tracking, regulatory_arb, macro_narrative, congressional_calendar,
  political_sentiment, foreign_sovereign_flow, trump_volatility, fed_watcher

CATEGORIES (sector ETFs): XLE, XLF, XLV, XLI, XLY, XLP, XLB, XLK, XLU, XLRE, ITA, XBI

TASK: Output COUNCIL PLAN. All 17 agents follow unless rogue.

RULES:
- Each agent commits ≥ {int(COUNCIL_MIN_COMMIT_PER_AGENT*100)}% of bankroll today.
- Bias weaker agents toward higher commit (catch-up).
- 2-4 focus_strategies, 3-6 focus_categories.
- Keep plan COMPACT.

SCHEMA:
{{
  "council_summary": "1 sentence",
  "focus_strategies": ["insider_tracking", "regulatory_arb"],
  "focus_categories": ["XLE", "XLF", "ITA"],
  "per_agent_commit_pct": {{"qwen-quant": 0.55, ...}},
  "shared_notes": "1-3 sentences"
}}

RESPOND WITH RAW JSON ONLY. All 10 agent ids in per_agent_commit_pct.
Values >= {COUNCIL_MIN_COMMIT_PER_AGENT} and <= 0.85."""

    fallback = {
        "council_summary": "no LLM council; default equal commitment",
        "focus_strategies": ["insider_tracking", "macro_narrative"],
        "focus_categories": ["XLE", "XLF", "ITA"],
        "per_agent_commit_pct": {tid: 0.55 for tid in state},
        "shared_notes": "Deterministic fallback plan.",
        "raw": "",
    }

    try:
        raw = _call_llm(
            "cerebras:qwen-3-235b",
            sys_prompt, usr_prompt, timeout=15.0,
            trace_name=f"pol-tf-council-{day_idx}",
            trace_metadata={"day": day_date, "n_events": n_events, "n_agents": n_agents, "fleet_total": fleet_total},
        )
    except Exception:
        raw = None
    if not raw:
        return fallback

    plan = parse_llm_decision(raw)
    if not isinstance(plan, dict):
        return fallback

    focus_strats = plan.get("focus_strategies") or []
    if not isinstance(focus_strats, list):
        focus_strats = []
    focus_cats = plan.get("focus_categories") or []
    if not isinstance(focus_cats, list):
        focus_cats = []
    commits = plan.get("per_agent_commit_pct") or {}
    if not isinstance(commits, dict):
        commits = {}
    clean_commits = {}
    for tid in state:
        try:
            v = float(commits.get(tid, 0.55) or 0.55)
        except (TypeError, ValueError):
            v = 0.55
        clean_commits[tid] = max(COUNCIL_MIN_COMMIT_PER_AGENT, min(0.85, v))

    return {
        "council_summary": str(plan.get("council_summary", ""))[:300],
        "focus_strategies": [str(s)[:40] for s in focus_strats[:4]],
        "focus_categories": [str(c)[:40] for c in focus_cats[:6]],
        "per_agent_commit_pct": clean_commits,
        "shared_notes": str(plan.get("shared_notes", ""))[:500],
        "raw": raw[:3000],
    }


def build_council_block(plan: dict, tid: str, fleet_best_bankroll: float) -> str:
    if not plan:
        return ""
    my_commit = plan.get("per_agent_commit_pct", {}).get(tid, COUNCIL_MIN_COMMIT_PER_AGENT)
    progress = (fleet_best_bankroll / SEASON_TARGET) * 100.0
    lines = [
        "\n\n=== MORNING COUNCIL PLAN (follow unless rogue) ===",
        f"Fleet best bankroll: ${fleet_best_bankroll:,.2f} ({progress:.2f}% of $1M common goal)",
        f"Council summary: {plan.get('council_summary','(none)')}",
        f"Focus strategies: {', '.join(plan.get('focus_strategies',[]) or ['(none)'])}",
        f"Focus categories/ETFs: {', '.join(plan.get('focus_categories',[]) or ['(none)'])}",
        f"YOUR council commit: at least {my_commit*100:.0f}% of your bankroll deployed today.",
        f"Shared notes: {plan.get('shared_notes','(none)')}",
        "Bias allocations toward focus_strategies + focus_categories unless rogue.",
        "Common goal: ONE agent reaches $1M by season end.",
    ]
    return "\n".join(lines)


def build_day_prompt(day_date: str, day_events: List[Dict], sector_trends: Dict,
                     trader_state: Dict, strategies=None,
                     recent_decisions: List[Dict] = None,
                     common_knowledge_block: Optional[str] = None,
                     fleet_best_bankroll: float = 100.0,
                     event_preds: Optional[Dict] = None,
                     tid: str = "") -> str:
    """Build comprehensive day-level prompt. Agent sees ALL political events of the day."""
    bankroll = trader_state.get("bankroll", 100.0)
    total_allocs = trader_state.get("total_bets", 0)
    wins = trader_state.get("wins", 0)
    losses = trader_state.get("losses", 0)
    roi = ((bankroll - 100.0) / 100.0) * 100

    progress_pct = (fleet_best_bankroll / SEASON_TARGET) * 100.0
    lines = [f"=== TRADING DAY: {day_date} | {len(day_events)} POLITICAL EVENTS ===",
             f"",
             f"COMMON GOAL: one agent reaches ${SEASON_TARGET:,.0f}. Fleet best now ${fleet_best_bankroll:,.2f} ({progress_pct:.2f}%).",
             f"YOUR STATE: ${bankroll:.2f} | {total_allocs} total allocations | {wins}W-{losses}L | ROI {roi:+.1f}%"]

    if recent_decisions:
        lines.append("\nRECENT DAYS (last 3):")
        for d in recent_decisions[-3:]:
            lines.append(f"  {d.get('date','?')}: {d.get('summary','—')}")

    if sector_trends:
        lines.append("\nSECTOR TRENDS (last 30d, computed from events BEFORE today — leakage-safe):")
        for sector, stats in sorted(sector_trends.items(), key=lambda x: -abs(x[1].get("avg_ret", 0))):
            lines.append(f"  {sector:<20} avg_ret={stats['avg_ret']:+.4f}  win_rate={stats['win_rate']:.0%}  n={stats['n']}")

    # ITF v1 (2026-04-19): pull shared intraday tape (sector-ETF moves).
    # Additive, silent-on-missing, HF Spaces can't import monorepo so we only
    # add when a latest.json shim is mounted or env IFT_SNAPSHOT is set.
    try:
        import json as _json, os as _os
        from pathlib import Path as _Path
        _snap_env = _os.environ.get("ITF_SNAPSHOT_PATH")
        _cands = ([_Path(_snap_env)] if _snap_env else []) + [
            _Path("/data/intraday/quotes/latest.json"),
            _Path(__file__).resolve().parents[3] / "data" / "intraday" / "quotes" / "latest.json",
        ]
        for _p in _cands:
            if _p.exists():
                _snap = _json.loads(_p.read_text())
                _tape = _snap.get("tickers") or {}
                if _tape:
                    lines.append("\nINTRADAY TAPE (sector-ETF moves, live " +
                                 f"{_snap.get('_source', 'yf')} @ {_snap.get('ts', '?')}):")
                    for _t, _q in list(_tape.items())[:14]:
                        lines.append(f"  {_t:<6} last={_q.get('last')} Δ={_q.get('change_pct')}%")
                break
    except Exception:
        pass

    lines.append("\nPOLITICAL EVENTS (leakage-safe — outcome/excess_return hidden):")
    for i, ev in enumerate(day_events, 1):
        lines.append(_format_event_block(i, ev, event_preds, tid=tid))

    if strategies:
        lines.append(f"\nSTRATEGIES ({len(strategies)}): {', '.join(list(strategies.keys())[:12])}...")

    if common_knowledge_block:
        lines.append("\n" + common_knowledge_block)

    lines.append("""
=== YOUR TASK ===
Allocate your bankroll across today's political events.
Each allocation = one sector ETF trade on one event. Total allocations + cash_held must sum to 1.00.
MANDATORY: You MUST place at least 1 trade. Zero-trade days are NOT allowed.
Even if edges are small, pick your BEST signal and allocate 5-15%. Cash-only is forbidden.

DIRECTIONS: long (bet ticker goes up), short (bet ticker goes down)
Each allocation references one event_idx from the list above.

LEAKAGE RULE: You NEVER see excess_return or y. Reason from signal_type, signal_strength, agency, donor_info, and sector_trends only.
Your thesis MUST cite which signal/agency drove the decision, not just the ticker.

RESPOND WITH RAW JSON ONLY. No markdown fences. No explanation before or after. First character MUST be {, last MUST be }. Do NOT wrap in ```json blocks.

Schema (FILL EVERY FIELD — top-of-JSON fields get priority under token pressure):
{
  "day_strategy": "MUST start with STRUCTURAL DIVERGE [peer] or STRUCTURAL COMPLEMENT [peer] citing your REASONING TEMPLATE — then 1-2 sentences on approach",
  "coalition_proposal": {
    "peer": "qwen-quant (or \"none\" if no pact today)",
    "event_idx": 1,
    "direction": "long",
    "rationale": "1 sentence — why this peer / why no pact today"
  },
  "council_alignment": {
    "stance": "followed|deviated|partial",
    "reason": "1 sentence — why you followed/deviated/partial vs council_commit_target"
  },
  "ck_consensus_stance": {
    "stance": "diverge|agree|partial",
    "reason": "1 sentence citing specific peers from COMMON_KNOWLEDGE"
  },
  "allocations": [
    {
      "event_idx": 1,
      "direction": "long",
      "ticker": "XLE",
      "pct": 0.15,
      "confidence": 0.65,
      "thesis": "1-2 sentences citing signal/agency",
      "ticker_reason": "1 sentence — why this ticker vs other sector ETFs"
    }
  ],
  "cash_held_pct": 0.25,
  "cash_rationale": "1 sentence if cash > 0",
  "events_considered": [
    {"event_idx": 1, "decision": "bet|skip", "reason": "1 sentence — if skip: why (signal weak / agency unclear / already exposed / low conviction)"},
    {"event_idx": 2, "decision": "skip", "reason": "signal ambiguous, no clear sector read"}
  ]
}

NEW AUDIT FIELDS (MANDATORY — councils use these to score decision quality):
- council_alignment: ONE of {followed|deviated|partial} + reason. Council assigned you
  a commit_pct target today (see COUNCIL_PLAN block); if you deployed close to it say
  "followed", if you went much higher/lower say "deviated" and explain, say "partial"
  if you respected direction but magnitude differs.
- events_considered: ONE entry per event on today's slate (include EVERY event_idx, not
  just the ones you bet). For skipped events give the specific reason — "signal weak",
  "sector already maxed", "conflicting agencies", "no clear ticker map", etc.
- ck_consensus_stance: MANDATORY. After reviewing COMMON_KNOWLEDGE, state stance=diverge|agree|partial + cite specific peers/positions. Primary Axelrod Mech A audit field — captured in day-N.jsonl.
- ticker_reason on each allocation: say why this TICKER beat other sector ETFs
  (e.g. "XLE over XLB because the signal is oil-specific, not broad commodities").

STRICT RULES:
- Sum of all allocation pct + cash_held_pct = 1.00 (±0.01)
- direction must be "long" or "short" (no "cash" in allocations)
- allocations[]: MUST contain ≥3 entries every day. Empty allocations[] is FORBIDDEN.
  If no event has obvious edge, spread across 3 sector ETFs (XLE/XLV/XLF/XLK/XLF) anyway.
- Max 25 allocations, no duplicate (event_idx, direction) pair — same event
  can appear as short + long on different sector legs if thesis diverges
- Each allocation pct: 0.01–0.40
- cash_held_pct: 0.00–0.25 MAX (aggressive-deploy policy, $1M collective goal — idle capital cannot compound)
- MANDATORY: ≥75% deployed every day. Holding >25% cash violates the collective goal.
- Thesis MUST cite a specific signal/agency (not just "I think it will go up")
- Ticker should be the sector ETF from SECTOR_ETF_MAP (XLE, XLV, XLF, etc.) or the event's ticker
- coalition_proposal is MANDATORY (must be present). Set it to a peer you want to pact
  with AND match with a bet on that event_idx+direction, or set peer="none" with a
  reason why no pact today. Empty/missing field = invalid response.
  COLLECTIVE-HELP RULE: if ANY peer bankroll < $50, a top-3 agent must propose a
  pact with that peer on their own highest-edge sector — the struggling peer sees it
  via COMMON_KNOWLEDGE and can mirror. This is how the collective lifts survivors.
  Pact honored IFF both you and peer place the same (event_idx, direction) bet.
""")
    return "\n".join(lines)


def parse_day_allocation(raw: str, n_events: int, drawdown: float = 0.0) -> Optional[Dict]:
    """Parse day allocation JSON for political events. Validates sum=1.0 within tolerance.

    Returns dict with: day_strategy, allocations (normalized), cash_held_pct,
    cash_rationale, raw_sum. Returns None if unparseable or grossly invalid.
    Each alloc validated: event_idx (1-indexed, bounded), direction (long/short),
    ticker (string, uppercase), pct (0.01-0.40), confidence 0-1, thesis ≤300 chars.
    """
    parsed = parse_llm_decision(raw)
    if not parsed:
        return None
    allocations = parsed.get("allocations") or []
    if not isinstance(allocations, list):
        allocations = []
    cash = float(parsed.get("cash_held_pct", 0.0) or 0.0)

    VALID_DIRECTIONS = {"long", "short"}

    # 2026-04-25 BUGFIX (user-flagged): cap was [:10] and dedup was per-event,
    # so any hedge (long XLE + short XLF on same event) or multi-leg pact was
    # silently dropped after the first leg. New cap is 25 allocs/day; dedup
    # key is (event, ticker, direction) so each ticker-direction leg counts.
    clean = []
    seen_keys = set()  # (eidx, ticker, direction) — was {eidx}
    for a in allocations[:25]:  # was [:10]
        if not isinstance(a, dict):
            continue
        eidx = a.get("event_idx")
        direction = (a.get("direction") or "").lower().strip()
        ticker = (a.get("ticker") or "").upper().strip()
        try:
            pct = float(a.get("pct", 0) or 0)
            conf = float(a.get("confidence", 0.5) or 0.5)
        except (TypeError, ValueError):
            continue
        if direction not in VALID_DIRECTIONS:
            continue
        if not ticker or pct <= 0:
            continue
        if eidx is None or not isinstance(eidx, int):
            continue
        if eidx < 1 or eidx > n_events:
            continue
        key = (eidx, ticker, direction)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        clean.append({
            "event_idx": eidx,
            "ticker": ticker[:10],
            "direction": direction,
            "pct": max(0.01, min(0.40, pct)),
            "confidence": max(0.0, min(1.0, conf)),
            "thesis": (a.get("thesis") or a.get("rationale") or "")[:300],
            "strategy": (a.get("strategy") or direction)[:30],
            "ticker_reason": (a.get("ticker_reason") or "")[:300],
        })

    total = sum(a["pct"] for a in clean) + max(0.0, min(1.0, cash))
    # 2026-04-19 BUGFIX #3 — coalition-preservation. Previously `if total<=0: return None`
    # threw away valid coalition_proposal when LLM said "no bets today". Mirror of NBA fix.
    if total <= 0:
        cash = 1.0
        total = 1.0
    # Normalize to sum exactly 1.0 (soft tolerance — agent gave proportions)
    if abs(total - 1.0) > 0.02:
        scale = 1.0 / total
        for a in clean:
            a["pct"] = a["pct"] * scale
        cash = cash * scale

    # ── MIN_DEPLOY_PCT — carte-blanche calibration (POL continuous returns)
    # 2026-04-22 — 0.80 → 0.55. POL continues to work (fleet leader +606% at day
    # 130) so we only soften, not collapse. Continuous returns compound both
    # ways; forced 80% was overkill given agents already beat on their own.
    if drawdown < 0.5:
        MIN_DEPLOY_PCT = 0.55
    else:
        MIN_DEPLOY_PCT = max(0.20, 0.55 - (drawdown - 0.5) * 0.8)
    deployed = sum(a["pct"] for a in clean)
    if deployed > 0 and deployed < MIN_DEPLOY_PCT:
        scale_up = MIN_DEPLOY_PCT / deployed
        for a in clean:
            a["pct"] = min(0.25, a["pct"] * scale_up)
        new_deployed = sum(a["pct"] for a in clean)
        cash = max(0.0, 1.0 - new_deployed)
    elif deployed == 0:
        cash = 1.0

    # Mech D — coalition_proposal extraction (MANDATORY field; peer="none" => no pact today)
    coalition = None
    cp = parsed.get("coalition_proposal")
    if isinstance(cp, dict):
        peer = (cp.get("peer") or "").strip()
        cp_eidx = cp.get("event_idx")
        cp_dir = (cp.get("direction") or "").lower().strip()
        if peer and peer.lower() != "none" and isinstance(cp_eidx, int) and 1 <= cp_eidx <= n_events and cp_dir in {"long", "short"}:
            coalition = {
                "peer": peer[:40],
                "event_idx": cp_eidx,
                "direction": cp_dir,
                "rationale": (cp.get("rationale") or "")[:200],
            }

    # Phase B — council_alignment + events_considered audit fields
    ca = parsed.get("council_alignment") or {}
    council_alignment = None
    if isinstance(ca, dict):
        stance = (ca.get("stance") or "").lower().strip()
        if stance in ("followed", "deviated", "partial"):
            council_alignment = {
                "stance": stance,
                "reason": (ca.get("reason") or "")[:300],
            }

    ec = parsed.get("events_considered") or []
    events_considered: List[Dict] = []
    bet_events = {k[0] for k in seen_keys}  # 2026-04-25 — derived from new (eidx,ticker,dir) keys
    if isinstance(ec, list):
        seen_ec = set()
        for item in ec[:30]:
            if not isinstance(item, dict):
                continue
            ei = item.get("event_idx")
            if not isinstance(ei, int) or ei < 1 or ei > n_events or ei in seen_ec:
                continue
            seen_ec.add(ei)
            decision = (item.get("decision") or "").lower().strip()
            if decision not in ("bet", "skip"):
                decision = "bet" if ei in bet_events else "skip"
            events_considered.append({
                "event_idx": ei,
                "decision": decision,
                "reason": (item.get("reason") or "")[:300],
            })

    return {
        "day_strategy": (parsed.get("day_strategy") or parsed.get("reasoning") or "")[:500],
        "allocations": clean,
        "cash_held_pct": round(max(0.0, min(1.0, cash)), 4),
        "cash_rationale": (parsed.get("cash_rationale") or "")[:300],
        "raw_sum": round(total, 4),
        "coalition_proposal": coalition,
        "council_alignment": council_alignment,
        "events_considered": events_considered,
        "ck_consensus_stance": (parsed.get("ck_consensus_stance") or {}),
    }


# ── UNIFORM-FALLBACK ALLOCATION (2026-04-19) ────────────────────────────────
# When primary + hot-swap LLM BOTH fail (raw_response is None), emit a
# uniform-fallback allocation so the agent never violates MIN_DEPLOY_PCT=0.75.
# Scientific integrity: tagged provider_status="fallback_uniform" on each
# allocation + fallback_used=True on the day_log so audit + post-mortem can
# exclude these rows when evaluating agent skill.
#
# Spec: spread 75% across 3 broad-ETF proxies (SPY / QQQ / IWM), even split,
# long-only. Resolution requires real event excess_return, so we pick the
# top-3 events of the day by signal_strength, direction=long (matches the
# broad-long-ETF spirit) and label each alloc with the intended ETF proxy.
# Returns a parse-compatible dict (drop-in for `parsed`).
_FALLBACK_ETF_LABELS = ["SPY", "QQQ", "IWM"]

def build_uniform_fallback_political(day_date: str, day_events: List[Dict],
                                     tid: str = "") -> Optional[Dict]:
    if not day_events:
        return None
    scored = []
    for i, ev in enumerate(day_events):
        sig = float(ev.get("signal_strength", 0.0) or 0.0)
        scored.append((sig, i, ev))
    scored.sort(key=lambda t: t[0], reverse=True)
    # Per-agent rotation (NBA parity): shift into the top pool by tid hash so
    # not all 17 agents pile on the exact same 3 events on LLM-outage day.
    # COLLISION_MAX_AGENTS=3 would otherwise reject 14/17 agents here.
    if tid and len(scored) > 3:
        import hashlib as _hl
        _shift_range = max(1, min(6, len(scored) - 3))
        _shift = int(_hl.sha1(tid.encode()).hexdigest()[:4], 16) % _shift_range
        scored = scored[_shift:] + scored[:_shift]
    top = scored[:3]
    if not top:
        return None
    per_alloc_pct = 0.75 / len(top)
    allocations = []
    for rank, (sig, i, ev) in enumerate(top):
        etf_label = _FALLBACK_ETF_LABELS[rank] if rank < len(_FALLBACK_ETF_LABELS) else f"ETF_{rank}"
        allocations.append({
            "event_idx": i + 1,  # 1-indexed in prompt space
            "ticker": etf_label,
            "direction": "long",
            "pct": per_alloc_pct,
            "confidence": 0.50,
            "thesis": f"UNIFORM_FALLBACK: LLM (primary+hot-swap) failed; "
                      f"long broad-ETF proxy ({etf_label}) on top-{rank+1} signal "
                      f"event (underlying {ev.get('ticker','?')}, "
                      f"strength={sig:.2f}) per $1M doctrine.",
            "strategy": "fallback_uniform_long",
            "provider_status": "fallback_uniform",
            "fallback_etf_label": etf_label,  # user-spec broad-ETF tag
            "underlying_ticker": ev.get("ticker", ""),
        })
    return {
        "day_strategy": "FALLBACK_UNIFORM: LLM infrastructure failure — broad-ETF long (SPY/QQQ/IWM proxies on top-3 signals), even split 25% (75% deploy floor).",
        "cash_held_pct": round(1.0 - per_alloc_pct * len(top), 4),
        "cash_rationale": "25% reserve; 75% deployed per MIN_DEPLOY_PCT doctrine when LLM dead.",
        "allocations": allocations,
        "coalition_proposal": None,
        "council_alignment": None,
        "events_considered": [],
        "fallback_used": True,
    }


# ── POLITICAL TRADE RESOLUTION ───────────────────────────────────────────────

def resolve_political_trade(direction: str, excess_return: float, leverage: float = LEVERAGE) -> Tuple[bool, float]:
    """Resolve political trade. Returns (won, pnl_pct_of_stake).

    Long wins if excess_return > 0, short wins if < 0.
    pnl_pct = direction_sign * excess_return * leverage (capped at ±50%).
    """
    sign = 1.0 if direction == "long" else -1.0
    pnl_pct = sign * excess_return * leverage
    # Cap extreme moves (liquidity / stop-loss reality)
    pnl_pct = max(-0.50, min(0.50, pnl_pct))
    return pnl_pct > 0, pnl_pct


# ── DATA LOADING ────────────────────────────────────────────────────────────

def load_events() -> List[Dict]:
    """Load political events. Leakage-safe copy — outcomes kept for resolution."""
    data_dir = Path(__file__).parent / "data"
    fp = data_dir / "political_events.json"
    if not fp.exists():
        return []
    raw = json.loads(fp.read_text())
    out = []
    for e in raw:
        date = (e.get("date") or "").strip()
        if len(date) == 8 and "-" not in date:  # fix "20260326"
            date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        if not date or not e.get("ticker"):
            continue
        out.append({
            "date": date,
            "ticker": str(e["ticker"]).upper(),
            "event_type": e.get("event_type", "unknown"),
            "agency": e.get("agency", ""),
            "title": (e.get("title") or "")[:300],
            "signal_type": e.get("signal_type", ""),
            "signal_strength": float(e.get("signal_strength", 0.5) or 0.5),
            "signal_sector": e.get("signal_sector", "other"),
            "donor_info": e.get("donor_info", {}) or {},
            "macro": e.get("macro", {}) or {},
            "excess_return": float(e.get("excess_return", 0.0) or 0.0),  # HIDDEN from agent
            "y": int(e.get("y", 0) or 0),
        })
    out.sort(key=lambda x: x["date"])
    return out


def load_strategies():
    """Load 22 SOTA trading strategies (optional)."""
    data_dir = Path(__file__).parent / "data"
    path = data_dir / "strategies.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def load_political_predictions() -> Dict[str, dict]:
    """Load walk-forward per-event predictions with ~38 categories each.
    Keyed by '{date}_{ticker}_{event_type}'. Generated by
    extend_predictions_all_categories.py using past-only empirical priors."""
    data_dir = Path(__file__).parent / "data"
    path = data_dir / "political-predictions.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def build_common_knowledge_block(day_date: str, state: Dict, agent_logs: Dict,
                                  reputation: Optional[Dict] = None,
                                  pact_events: Optional[List[dict]] = None,
                                  day_idx: int = 0) -> str:
    """Build COMMON_KNOWLEDGE[D] block: full transparency for day D+1 prompts.

    Implements Axelrod-2026 Mechanism A (day-end common knowledge broadcast).
    All agents see ALL other agents' allocations, results, strategies, and bankrolls
    from the last 3 days, enabling true collective optimization.
    """
    n_traders = len(TRADERS)
    total_start = n_traders * 100.0
    lines = [
        f"=== COMMON_KNOWLEDGE[{day_date}] — Axelrod-2026 Mech A (day-end broadcast) ===",
        f"COLLECTIVE GOAL: maximize TOTAL GROUP bankroll → target ${total_start:.0f} ($100×{n_traders} start).",
        f"You are ONE of {n_traders} political-alpha traders. Every allocation you make affects the group.",
        "",
    ]

    # Leaderboard with collective stats
    ranked = sorted(state.items(), key=lambda x: -x[1]["bankroll"])
    total_bankroll = sum(ts["bankroll"] for _, ts in ranked)
    total_bets = sum(ts["total_bets"] for _, ts in ranked)
    total_wins = sum(ts["wins"] for _, ts in ranked)
    lines.append(f"GROUP TOTAL: ${total_bankroll:.2f} (started ${total_start:.0f}) | "
                 f"ROI {((total_bankroll / total_start) - 1) * 100:+.1f}% | "
                 f"{total_bets} allocations | {total_wins}W")
    lines.append("")
    lines.append("LEADERBOARD:")
    for rank, (tid, ts) in enumerate(ranked, 1):
        cfg = TRADERS.get(tid, {})
        gf = ts["bankroll"] / 100.0
        roi = (gf - 1.0) * 100
        wr = (ts["wins"] / max(ts["total_bets"], 1)) * 100
        role = ""
        if ts["bankroll"] < 50:
            role = " [RESCUE MODE]"
        elif rank <= 3:
            role = " [TOP-3]"
        lines.append(
            f"  #{rank} {cfg.get('name', tid):<20} ${ts['bankroll']:.2f} GF={gf:.3f}× ({roi:+.1f}%)"
            f" | {ts['total_bets']}b {wr:.0f}%WR | DD {ts['max_drawdown']:.1%}{role}"
        )

    # 3-day rolling allocation history from ALL agents (full transparency)
    all_dates = set()
    for tid in state:
        for log in agent_logs.get(tid, []):
            all_dates.add(log.get("date", ""))
    recent_dates = sorted(all_dates)[-3:]

    for past_date in recent_dates:
        lines.append(f"\n--- ALL ALLOCATIONS on {past_date} (resolved) ---")
        for tid, _ts in ranked:
            logs = agent_logs.get(tid, [])
            day_log = next((l for l in reversed(logs) if l.get("date") == past_date), None)
            if not day_log:
                continue
            cfg = TRADERS.get(tid, {})
            name = cfg.get("name", tid)
            allocs = day_log.get("allocations", [])
            strat = day_log.get("day_strategy", "")[:80]
            if not allocs:
                lines.append(f"  {name}: CASH — \"{strat}\"")
            else:
                for a in allocs:
                    outcome = "W" if a["won"] else "L"
                    _edge_rat = (a.get('rationale') or a.get('thesis') or '')[:60]
                    lines.append(
                        f"  {name}: event={a.get('ticker', '?')} pick={a.get('direction', '?')} {a.get('event_type', '?')} "
                        f"stake=${a.get('stake', 0):.1f} edge={a.get('edge', 0):.3f}→{outcome} "
                        f"pnl={a.get('profit', 0):+.1f}"
                        + (f" [edge_rationale: {_edge_rat}]" if _edge_rat else ""))
                if strat:
                    lines.append(f"    Strategy: \"{strat}\"")

    # Axelrod-2026 Mech A: consensus pick aggregation for yesterday
    if recent_dates:
        _yesterday = recent_dates[-1]
        _pick_ctr: Dict[str, int] = {}
        _n_active = 0
        for _t2, _ in ranked:
            _d2 = next((l for l in reversed(agent_logs.get(_t2, [])) if l.get("date") == _yesterday), None)
            if _d2:
                _n_active += 1
                for _a2 in _d2.get("allocations", []):
                    _pk = f"{_a2.get('ticker', '?')} {_a2.get('direction', '?')}"
                    _pick_ctr[_pk] = _pick_ctr.get(_pk, 0) + 1
        if _pick_ctr:
            lines.append(f"\nCONSENSUS PICKS on {_yesterday} (Axelrod-2026: cite your diverge/agree stance):")
            for _pk2, _cnt2 in sorted(_pick_ctr.items(), key=lambda x: -x[1])[:8]:
                _pct2 = _cnt2 / max(_n_active, 1) * 100
                lines.append(f"  {_cnt2}/{_n_active} ({_pct2:.0f}%): {_pk2}")

    # Mech D — Cooperation reputation + today's pact resolutions
    if reputation:
        lines.append("\nCOOPERATION REPUTATION:")
        rep_items = sorted(
            reputation.items(),
            key=lambda x: -(x[1].get("pact_honored", 0) - x[1].get("pact_broken", 0)),
        )
        for tid, rep in rep_items:
            h = rep.get("pact_honored", 0)
            b = rep.get("pact_broken", 0)
            if h == 0 and b == 0:
                continue
            cfg = TRADERS.get(tid, {})
            name = cfg.get("name", tid)
            lines.append(f"  {name:<20} honored={h} broken={b} (net {h - b:+d})")
    if pact_events:
        lines.append(f"\nTODAY'S PACTS on {day_date}:")
        for ev in pact_events[:10]:
            lines.append(
                f"  [{ev['status'].upper()}] {ev['proposer']} → {ev['peer']} "
                f"on event#{ev['event_idx']} {ev['direction']}"
            )

    # Council day protocol — every 15 days, agents reorganize
    is_council_day = (day_idx > 0 and day_idx % 15 == 0)
    if is_council_day:
        lines.append(
            "\n=== COUNCIL DAY (every 15 days) ===\n"
            "Today is a strategy reorganization day. In addition to your allocations,\n"
            "add a 'council_vote' field to your JSON:\n"
            "  \"council_vote\": {\n"
            "    \"worst_strategy\": \"name of peer whose strategy should change\",\n"
            "    \"suggested_change\": \"what they should try instead\",\n"
            "    \"my_adjustment\": \"what I will change about my own strategy\"\n"
            "  }\n"
            "Review the 3-day history above. Identify what's working and what isn't.\n"
            "Agents in PRESERVATION MODE should lock in capital (5% per bet cap).\n"
            "TOP-3 agents should protect capital and mentor via coalition proposals.\n"
        )

    lines.append(
        "\nCOLLABORATION RULES:\n"
        "- You see ALL traders' allocations from last 3 days. Learn, do not copy.\n"
        "- MANDATORY: do NOT duplicate the exact sector/direction picked by >2 peers yesterday.\n"
        "- If your bankroll is in PRESERVATION MODE (<$50), max 5% per position,\n"
        "  sector ETFs only, NO leveraged plays, NO event-flyers. Survive, do not chase.\n"
        "- TOP-3 traders: protect capital, use corroborated multi-agency signals.\n"
        "- Propose coalitions with traders whose REASONING TEMPLATE differs from yours.\n"
        "\n"
        "ANTI-GROUPTHINK (DMAD — MANDATORY, enforced 2026-04-18):\n"
        "Post-mortem found 14/17 POL agents converged to identical $93.92/$159.68 bankrolls.\n"
        "To break this, your day_strategy MUST begin with EXACTLY ONE of:\n"
        "  STRUCTURAL DIVERGE [peer_name] (edge=XX.X%): <how your REASONING TEMPLATE\n"
        "    produces a different sector pick than peer's, cite your template>. MUST include\n"
        "    numerical edge citation ≥5.0% (e.g. 'edge=6.3%') or bet is rejected.\n"
        "  STRUCTURAL COMPLEMENT [peer_name] (edge=XX.X%): <how your pick fills a sector\n"
        "    the peer ignored, cite both templates>. MUST include numerical edge ≥5.0%.\n"
        "CONSENSUS_AGREE_JUSTIFIED [peer_name] (reason=<specific_structural_reason>): ALLOWED\n"
        "    only if you cite a DIFFERENT structural basis (political signal, agency,\n"
        "    sector-beta divergence). Blind consensus → flagged lockstep in post-mortem.\n"
        "    Lockstep (≥10/17 same pick, no CONSENSUS_AGREE_JUSTIFIED)\n"
        "    → Mech B archetype rotation for bottom 3 next day.\n"
        "POST-MORTEM DOCTRINE (2026-04-19, NBA parity):\n"
        "Winners used FLAT-STAKE WIDE COVERAGE with strict EV threshold (≥6% edge, half-Kelly).\n"
        "Losers used HIGH-CONVICTION SINGLE PLAYS citing DIVERGE rhetoric without numerical edge.\n"
        "NEW RULE: any bet WITHOUT a numerical edge ≥4% in the rationale is REJECTED by the\n"
        "post-filter. Kelly capped at 0.5× all tiers. Per-bet cap: T1 20%, T2 15%, T3 12%,\n"
        "T4 10%. Single-day loss >40% → forced 100% cash next day (circuit breaker).\n"
    )
    return "\n".join(lines)


def compute_trailing_delta(tid: str, state: Dict, agent_logs: Dict, trailing_days: int = 7) -> float:
    """Axelrod Mech B: trailing-N-day bankroll delta (absolute $)."""
    logs = agent_logs.get(tid, [])
    if len(logs) < 2:
        return 0.0
    recent = logs[-trailing_days:]
    if not recent:
        return 0.0
    start_b = recent[0].get("bankroll_before", 100.0)
    current = state.get(tid, {}).get("bankroll", 100.0)
    return float(current - start_b)


def assign_sacrificial_archetypes(day_date: str, state: Dict, agent_logs: Dict,
                                   bottom_n: int = 3, trailing_days: int = 7) -> Dict[str, str]:
    """Axelrod Mech B: bottom-N by trailing delta get NEW archetype from unused pool.

    Society-wide dedup: exclude any archetype used by ANY agent in the trailing 7 days,
    matching spec "NEVER USED in the prior 7 days by anyone" (Axelrod-2026 Mechanism B).
    """
    from datetime import timedelta as _td
    deltas = [(tid, compute_trailing_delta(tid, state, agent_logs, trailing_days))
              for tid in state.keys()]
    deltas.sort(key=lambda x: x[1])
    bottom = [tid for tid, _ in deltas[:bottom_n]]

    # Build society-wide exclusion set: union of trailing-window daily assignments
    try:
        cutoff = datetime.fromisoformat(day_date) - _td(days=trailing_days)
        society_used: set = set()
        for d, archs in _society_archetypes_by_day.items():
            try:
                if datetime.fromisoformat(d) >= cutoff:
                    society_used.update(archs)
            except ValueError:
                pass
    except Exception:
        society_used = set()

    assignments: Dict[str, str] = {}
    today_used: set = set()  # prevent duplicate archetype to two sacrificed agents same day
    for tid in bottom:
        available = [a for a in AXELROD_ARCHETYPES if a not in society_used and a not in today_used]
        if not available:
            # All archetypes used society-wide — reset and exclude only today's picks
            available = [a for a in AXELROD_ARCHETYPES if a not in today_used]
        if not available:
            available = list(AXELROD_ARCHETYPES)
        pick = available[hash(tid + day_date) % len(available)]
        assignments[tid] = pick
        today_used.add(pick)
        _used_archetypes[tid].add(pick)  # retain per-agent history as fallback

    # Record society-wide assignments for this day
    _society_archetypes_by_day[day_date] = set(assignments.values())
    return assignments


def build_sacrificial_system_suffix(archetype: str) -> str:
    """Axelrod Mech B: suffix appended to system_prompt for sacrificed agents."""
    return (
        f"\n\n=== AXELROD SACRIFICIAL ROLE (mandatory for today) ===\n"
        f"You are trailing the society in bankroll. For the collective good of the\n"
        f"experiment, you are assigned the archetype '{archetype}'. Today you MUST\n"
        f"reason AND trade ONLY through the lens of '{archetype}'. This is a Pareto-\n"
        f"optimal move — diversity of tested strategies is more valuable than your\n"
        f"individual EV. Your day_strategy field MUST start with 'ARCHETYPE[{archetype}]:'\n"
    )


def assign_challenge_tiers(state: Dict, sacrificial_map: Dict[str, str],
                            top_n: int = 3) -> Dict[str, int]:
    """Axelrod Mech B: mid-tier agents (not top-N by bankroll, not sacrificed) receive CHALLENGE[D].

    Returns {tid: leaderboard_rank} for agents in the challenge tier.
    Mid-tier = everyone who is neither dominant (top-N) nor diversifying (sacrificed).
    """
    ranked = sorted(
        [(tid, ts["bankroll"]) for tid, ts in state.items()],
        key=lambda x: -x[1],
    )
    result: Dict[str, int] = {}
    for rank, (tid, _) in enumerate(ranked, 1):
        if rank <= top_n:
            continue  # top tier — preserve what works, no intervention
        if tid in sacrificial_map:
            continue  # sacrificial tier — already receives forced archetype
        result[tid] = rank
    return result


def build_challenge_block(tid: str, rank: int, n_agents: int) -> str:
    """Axelrod Mech B: CHALLENGE[D] block for mid-tier agents.

    Mid-tier agents are neither dominant enough to stay static nor weak enough
    to be sacrificed — they receive an explicit self-improvement prompt.
    Spec: 'Middle: unchanged, but receive CHALLENGE[D] block asking to explicitly improve.'
    """
    return (
        f"\n\n=== AXELROD CHALLENGE (rank #{rank}/{n_agents} — mid-tier) ===\n"
        f"You are in the middle of the leaderboard — not struggling enough to be "
        f"sacrificed, not dominant enough to coast. Today you MUST explicitly:\n"
        f"  1. NAME one recent trade that underperformed vs expectation.\n"
        f"  2. STATE one concrete adjustment: edge threshold, stake sizing, or "
        f"sector selection.\n"
        f"  3. APPLY that adjustment today — not tomorrow.\n"
        f"Your day_strategy field MUST include 'CHALLENGE_RESPONSE:' followed by "
        f"your one-sentence improvement plan before any trade rationale.\n"
    )


def compute_consensus_distance(tid: str, day_date: str, state: Dict, agent_logs: Dict) -> float:
    """Axelrod Mech C: KL divergence D_KL(agent || society) over ticker/direction bet distribution.

    KL(P||Q) = sum_i P_i * log(P_i / Q_i) with epsilon smoothing.
    Replaces the former L1/2 proxy for paper-quality dataset accuracy.
    """
    from collections import Counter
    society = Counter()
    agent_counts = Counter()
    for other_tid, logs in agent_logs.items():
        day_log = next((l for l in reversed(logs) if l.get("date") == day_date), None)
        if not day_log:
            continue
        for a in day_log.get("allocations", []):
            tick = a.get("ticker") or a.get("category", "unknown")
            society[tick] += 1
            if other_tid == tid:
                agent_counts[tick] += 1
    if not society or not agent_counts:
        return 0.0
    total_soc = sum(society.values())
    total_agt = sum(agent_counts.values())
    cats = set(society.keys()) | set(agent_counts.keys())
    eps = 1e-9
    kl = 0.0
    for c in cats:
        p_agt = agent_counts.get(c, 0) / total_agt if total_agt else 0.0
        p_soc = society.get(c, 0) / total_soc if total_soc else 0.0
        kl += (p_agt + eps) * math.log((p_agt + eps) / (p_soc + eps))
    return round(kl, 6)


def write_axelrod_log(day_idx: int, day_date: str, state: Dict,
                       agent_logs: Dict, sacrificial_map: Dict[str, str]) -> None:
    """Axelrod Mech C: per-day post-mortem for Nature paper dataset."""
    try:
        AXELROD_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ranked = sorted(state.items(), key=lambda x: -x[1]["bankroll"])
        rank_map = {tid: i + 1 for i, (tid, _) in enumerate(ranked)}
        rows = []
        for tid, ts in state.items():
            logs = agent_logs.get(tid, [])
            day_log = next((l for l in reversed(logs) if l.get("date") == day_date), None)
            decisions = day_log.get("allocations", []) if day_log else []
            rows.append({
                "day_idx": day_idx,
                "date": day_date,
                "trader_id": tid,
                "rank": rank_map[tid],
                "bankroll": round(ts["bankroll"], 2),
                "archetype_assigned": sacrificial_map.get(tid),
                "was_sacrificed": tid in sacrificial_map,
                "num_decisions": len(decisions),
                "wins_today": sum(1 for d in decisions if d.get("won")),
                "decisions_summary": [
                    {
                        "ticker": d.get("ticker", ""),
                        "direction": d.get("direction", ""),
                        "event_type": d.get("event_type", ""),
                        "stake": round(d.get("stake", 0), 2),
                        "edge": round(d.get("edge", 0), 4),
                        "won": bool(d.get("won")),
                        "profit": round(d.get("profit", 0), 2),
                    }
                    for d in decisions
                ],
                "peer_consensus_distance": round(
                    compute_consensus_distance(tid, day_date, state, agent_logs), 4
                ),
                "day_strategy_prefix": (day_log.get("day_strategy", "")[:80] if day_log else ""),
                "ck_consensus_stance": (day_log.get("ck_consensus_stance", {}) or {}) if day_log else {},
            })
        log_file = AXELROD_LOG_DIR / f"day-{day_idx:03d}.jsonl"
        with log_file.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        if _hub_api:
            try:
                _hub_api.upload_file(
                    path_or_fileobj=log_file.read_bytes(),
                    path_in_repo=f"data/arena/axelrod-log/day-{day_idx:03d}.jsonl",
                    repo_id=HF_REPO_ID, repo_type="space",
                    commit_message=f"axelrod-mech-c: day {day_idx} ({day_date}) post-mortem",
                )
            except Exception as hub_e:
                print(f"[axelrod-mech-c] hub push failed: {hub_e}")
    except Exception as e:
        print(f"[axelrod-mech-c] write failed: {e}")


# ── EXPERIMENT RUNNER ────────────────────────────────────────────────────────

def run_experiment(progress=gr.Progress(track_tqdm=False)):
    """v3 DAY-BUCKET experiment: 17 agents × all event-days.

    Each agent receives ALL political events of a single day in one prompt, and
    must allocate 100% of their bankroll (long/short sector ETFs) or hold cash.
    One LLM call per agent per day (not per event).
    """
    # 2026-04-22 PLUMBER RCA fix: do NOT reset _llm_calls/_llm_failures on every
    # run_experiment entry — that was the root cause of the "soft-restart:
    # calls=0" false-positive that PLUMBER traced and keepalive then re-kicked.
    # Lifetime counters are now only zeroed in /api/reset. Per-season metrics
    # live on the per-agent state (`state[tid]["llm_calls"]`).
    global _llm_calls, _llm_failures, _gateway_routed, _gateway_fallback, _started_utc
    if _started_utc is None:
        _started_utc = datetime.now(timezone.utc).isoformat()

    # Async pre-ping (non-blocking): wake any selfhost Spaces still in substitution pool.
    # 2026-04-18: primary selfhost agents swapped to GitHub Models, so this runs background-only.
    import concurrent.futures as _cf
    def _wake_selfhosts_async():
        urls = [v["url"].rsplit("/", 1)[0] for k, v in PROVIDERS.items() if k.startswith("selfhost:")]
        def _wake(u):
            try: requests.get(u + "/", timeout=15)
            except: pass
        with _cf.ThreadPoolExecutor(max_workers=8) as _ex:
            list(_ex.map(_wake, urls))
    threading.Thread(target=_wake_selfhosts_async, daemon=True).start()

    # Load data
    all_events = load_events()
    strategies = load_strategies()
    event_preds = load_political_predictions()  # walk-forward per-event preds (~38 cats/event)
    n_events = len(all_events)
    print(f"[pol-tf] loaded {n_events} events, {len(event_preds)} walk-forward predictions, {len(strategies)} strategies")

    if n_events == 0:
        yield ("No event data found!", None, None, "Error: No political_events.json in data/ directory")
        return

    # ── Group events by date ──
    events_by_date = defaultdict(list)
    for e in all_events:
        events_by_date[e["date"]].append(e)
    dates_sorted = sorted(events_by_date.keys())
    n_days = len(dates_sorted)

    # ── Key availability ──
    available_keys = {}
    for prov, cfg in PROVIDERS.items():
        if os.environ.get(cfg["key_env"], ""):
            available_keys[cfg["key_env"]] = True
    key_summary = ", ".join(sorted(available_keys.keys()))

    # ── Init trader state ──
    state = {}
    for tid, cfg in TRADERS.items():
        state[tid] = {
            "bankroll": 100.0,
            "total_bets": 0,  # cumulative allocations resolved
            "wins": 0,
            "losses": 0,
            "passes": 0,  # days where cash=100%
            "llm_calls": 0,
            "llm_ok": 0,
            "history": [100.0],
            "best_bankroll": 100.0,
            "worst_bankroll": 100.0,
            "max_drawdown": 0.0,
            "days_traded": 0,
            "recent_decisions": [],  # last 3 for memory
            "force_cash_today": False,  # 2026-04-19 circuit breaker (prev day > 40% loss)
        }

    global _experiment_running, _experiment_state, _common_knowledge, _society_archetypes_by_day
    # 2026-04-22: claim atomically — /api/run gate already flipped this True under
    # _state_lock before spawning _bg, but reaffirm here for direct Gradio entry.
    with _state_lock:
        _experiment_running = True
    _stop_event.clear()
    _common_knowledge = {}  # Reset per run; built day-by-day (Axelrod Mech A)
    _sacrificial_assignments.clear()  # Axelrod Mech B reset
    _challenge_assignments.clear()   # Axelrod Mech B: mid-tier challenge reset
    _used_archetypes.clear()  # Axelrod Mech B: reset archetype history
    _society_archetypes_by_day.clear()  # Axelrod Mech B: reset society-wide archetype history

    # ── Resume support (day-indexed) ──
    saved = _load_state_from_disk()
    start_from_day = 0
    multi_season_seed = False
    if saved and not saved.get("completed") and saved.get("days_processed", 0) > 0:
        saved_agents = saved.get("agents", {})
        for tid in TRADERS:
            if tid in saved_agents:
                state[tid].update({k: v for k, v in saved_agents[tid].items() if k in state[tid]})
        start_from_day = saved.get("days_processed", 0)
        print(f"RESUMING from day {start_from_day}/{n_days}")
    elif saved and saved.get("completed") and saved.get("agents"):
        # 2026-04-17: multi-season compounding — carry final bankrolls forward.
        saved_agents = saved["agents"]
        for tid in TRADERS:
            if tid in saved_agents:
                final_br = float(saved_agents[tid].get("bankroll", 100.0))
                state[tid]["bankroll"] = final_br
                state[tid]["history"] = [final_br]
                state[tid]["best_bankroll"] = final_br
                state[tid]["worst_bankroll"] = final_br
        multi_season_seed = True
        print(f"MULTI-SEASON SEED: carrying final bankrolls from prior completed season")

    # 2026-04-18 FIX: seed _experiment_state NOW so /api/status returns real
    # bankrolls during resume-load (previously showed $100 until day N+1 finished).
    if saved and saved.get("agents"):
        try:
            _fb = max(state[t]["bankroll"] for t in state)
            _ld = max(state, key=lambda t: state[t]["bankroll"])
            with _state_lock:
                _experiment_state = {
                    "days_processed": int(saved.get("days_processed", 0)),
                    "days_total": n_days,
                    "games_processed": 0,
                    "games_total": 0,
                    "completed": False,
                    "design": "day-bucket-v3",
                    "agents": {tid: {k: v for k, v in ts.items() if k not in ("history", "recent_decisions")}
                               for tid, ts in state.items()},
                    "updated": datetime.now(timezone.utc).isoformat(),
                    "season_target": SEASON_TARGET,
                    "fleet_best_bankroll": round(_fb, 2),
                    "fleet_leader": _ld,
                    "season_progress_pct": round((_fb / SEASON_TARGET) * 100.0, 4),
                    "resumed": True,
                }
            print(f"[resume-seed] fleet_best=${_fb:.2f} leader={_ld}")
        except Exception as _e:
            print(f"[resume-seed] failed: {_e}")

    start_time = time.time()
    log_lines = []

    log_lines.append("=== NOMOS42 POLITICAL LLM TRADING FLOOR v3 (DAY-BUCKET) ===")
    log_lines.append(f"Dataset: 2026-03-12 to 2026-03-26 | Days: {n_days} | Events: {n_events} | Agents: {len(TRADERS)}")
    log_lines.append(f"API keys: {key_summary or 'NONE FOUND'}")
    log_lines.append(f"Strategies: {len(strategies)} | Leverage: {LEVERAGE}x")
    log_lines.append(f"Design: 1 LLM call per agent per day. 100% bankroll deployed (cash allowed with rationale).")
    if start_from_day > 0:
        log_lines.append(f"RESUMED from day {start_from_day}")
    log_lines.append(f"Start: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log_lines.append("=" * 50)

    prev_day_ck: Optional[str] = (
        saved.get("last_ck_block") if saved else None
    )  # Axelrod Mech A: restore CK from disk on Space restart (resume fix)

    for day_idx, day_date in enumerate(dates_sorted):
        if day_idx < start_from_day:
            continue
        if _stop_event.is_set():
            log_lines.append(f"=== STOPPED at day {day_idx} by user/council ===")
            break

        day_events = events_by_date[day_date]

        # Compute sector trends leakage-safe (up to but not including day_date)
        sector_trends = compute_sector_trends(all_events, day_date)

        day_summary_lines = [f"[day {day_idx+1}/{n_days}] {day_date} | {len(day_events)} events"]

        # Axelrod Mech D — day-scope collection for coalition resolution after all agents decide
        day_proposals: Dict[str, dict] = {}
        day_actual_bets: Dict[str, set] = {}

        # Stackelberg leader for the day (arXiv 2507.09407)
        _stackelberg_leader = get_stackelberg_leader(state)

        # ── PHASE 1/3/4 (2026-04-17) — morning council + rogue + $1M goal ──
        fleet_best_bankroll = max((state[t]["bankroll"] for t in state), default=STARTING_CAPITAL)
        day_council_plan = run_morning_council(
            day_idx, day_date, day_events, sector_trends, state, fleet_best_bankroll,
        )
        _council_plans[day_date] = day_council_plan
        day_rogue_state = compute_rogue_state(state)
        for _tid, _rs in day_rogue_state.items():
            if _rs["is_rogue"]:
                _rogue_events.append({
                    "day": day_date, "tid": _tid,
                    "reasons": _rs["reasons"],
                    "peer_leader": _rs.get("peer_leader"),
                    "peer_bankroll": _rs.get("peer_bankroll"),
                })
        log_lines.append(
            f"[day {day_idx+1}] COUNCIL: {day_council_plan.get('council_summary','(none)')[:120]}"
        )
        _n_rogues = sum(1 for r in day_rogue_state.values() if r["is_rogue"])
        if _n_rogues:
            log_lines.append(f"[day {day_idx+1}] ROGUES: {_n_rogues}/{len(state)} eligible to defect")

        # PHASE 1 — parallel LLM calls (intra-day only; days remain sequential
        # because Mech A common-knowledge broadcast on day N+1 reads day N).
        def _agent_llm_worker(tid_cfg):
            tid, cfg = tid_cfg
            provider = cfg["provider"]
            ts = state[tid]
            if ts.get("bankroll", 0) <= 5.0:
                return tid, None
            system_prompt = AGENT_SYSTEM_PROMPTS.get(tid, "You are a political alpha allocator.")
            _template = REASONING_TEMPLATES.get(tid)
            if _template:
                system_prompt = system_prompt + "\n\n" + _template
            system_prompt = system_prompt + build_stackelberg_role_block(tid, _stackelberg_leader)
            if tid in _sacrificial_assignments:
                system_prompt = system_prompt + build_sacrificial_system_suffix(_sacrificial_assignments[tid])
            elif tid in _challenge_assignments:
                system_prompt = system_prompt + build_challenge_block(tid, _challenge_assignments[tid], len(TRADERS))
            _pm_override = _load_prompt_override("pol", sim_date=day_date)
            system_prompt = AXELROD_CANON + _pm_override + "\n" + system_prompt
            _active_peers = [p for p in TRADERS if p != tid and state[p].get("bankroll", 0) > 5.0]
            _axl_block = _axelrod_advice_block(tid, _active_peers)
            if _axl_block:
                system_prompt = system_prompt + _axl_block
            # 2026-04-24 — 7-day peer reputation block (POL arm).
            try:
                import pathlib as _pl
                _rep_path = _pl.Path("/app/data/ops/agent-reputation.json")
                if not _rep_path.exists():
                    _rep_path = _pl.Path(__file__).resolve().parents[3] / "data/ops/agent-reputation.json"
                if _rep_path.exists():
                    _rep = json.loads(_rep_path.read_text())
                    _rep_block = (_rep.get("tfs", {}).get("pol", {}) or {}).get("prompt_block")
                    if _rep_block:
                        system_prompt += "\n\n" + _rep_block
            except Exception:
                pass
            # PHASE 1 — council plan
            _council_block = build_council_block(day_council_plan, tid, fleet_best_bankroll)
            if _council_block:
                system_prompt = system_prompt + _council_block
            # PHASE 3 — rogue permission
            _rogue_block = build_rogue_block(day_rogue_state.get(tid, {}))
            if _rogue_block:
                system_prompt = system_prompt + _rogue_block
            # Survival floor only: <$20 absolute. Aggressive-compound preserved above.
            if ts["bankroll"] < 20.0:
                system_prompt += (
                    "\n\n[SURVIVAL FLOOR] Bankroll below $20 — one bad day from $0. "
                    "Tight caps auto-enforced (5%/bet, 50%/day, edge≥4%). Find ONE "
                    "high-confidence pick to survive and rebuild."
                )
            user_prompt = build_day_prompt(
                day_date, day_events, sector_trends, ts,
                strategies=strategies,
                recent_decisions=ts.get("recent_decisions", []),
                common_knowledge_block=prev_day_ck,
                fleet_best_bankroll=fleet_best_bankroll,
                event_preds=event_preds,
                tid=tid,
            )
            try:
                raw = _call_llm(provider, system_prompt, user_prompt, timeout=12.0,
                               trace_name=f"pol-tf-day-{day_idx}",
                               trace_metadata={"trader_id": tid, "day": day_date, "bankroll": ts["bankroll"]})
            except Exception:
                raw = None
            if not raw and cfg.get("fallback_provider"):
                try:
                    raw = _call_llm(cfg["fallback_provider"], system_prompt, user_prompt, timeout=12.0,
                                   trace_name=f"pol-tf-day-{day_idx}-fallback",
                                   trace_metadata={"trader_id": tid, "day": day_date, "fallback": True})
                except Exception:
                    pass
            return tid, raw

        _max_workers = min(len(TRADERS), 4)
        _responses = {}
        _pool = ThreadPoolExecutor(max_workers=_max_workers)
        _futures = {_pool.submit(_agent_llm_worker, item): item[0]
                    for item in list(TRADERS.items())}
        try:
            for _fut in as_completed(_futures, timeout=120.0):
                try:
                    _tid, _raw = _fut.result(timeout=1.0)
                    _responses[_tid] = _raw
                except Exception:
                    _responses[_futures[_fut]] = None
        except Exception:
            pass
        for _fut, _tid in _futures.items():
            if _tid not in _responses:
                _fut.cancel()
                _responses[_tid] = None
        _pool.shutdown(wait=False, cancel_futures=True)

        # Flush Langfuse batch so traces land before the day takes minutes more.
        if _langfuse:
            try:
                _langfuse.flush()
            except Exception:
                pass

        # PHASE 2 — sequential resolution.
        # 2026-04-19 collision tracker: (event_idx, direction) → count of agents
        # sharing the same political pick today. Blocks >COLLISION_MAX_AGENTS.
        day_collisions: Dict[tuple, int] = {}
        for tid, cfg in TRADERS.items():
            provider = cfg["provider"]
            ts = state[tid]
            bankroll = ts["bankroll"]

            if bankroll <= 5.0:
                ts["passes"] += 1
                ts["history"].append(bankroll)
                continue

            # 2026-04-19 — single-day circuit breaker (NBA parity). If previous
            # day's loss exceeded SINGLE_DAY_WIPEOUT_THRESHOLD (40%), force
            # 100% cash today and reset the flag.
            if ts.get("force_cash_today"):
                ts["passes"] += 1
                ts["history"].append(bankroll)
                ts["force_cash_today"] = False
                _agent_logs[tid].append({
                    "day_idx": day_idx, "date": day_date, "n_events": len(day_events),
                    "bankroll_before": round(bankroll, 2),
                    "bankroll_after": round(bankroll, 2),
                    "day_strategy": "CIRCUIT_BREAKER: >40% loss yesterday → forced 100% cash today",
                    "cash_held_pct": 1.0,
                    "cash_rationale": "single-day wipeout guard (2026-04-19 doctrine)",
                    "allocations": [], "parlays": [],
                    "raw_preview": "",
                })
                continue

            raw_response = _responses.get(tid)
            ts["llm_calls"] += 1
            if raw_response:
                ts["llm_ok"] += 1
            _ts_dd = float(ts.get("max_drawdown", 0.0) or 0.0)
            parsed = parse_day_allocation(raw_response, len(day_events), drawdown=_ts_dd) if raw_response else None

            # 2026-04-18 — PRE-FILTER SPY-long fallback REMOVED.
            # Post-mortem showed 14/17 POL agents converged to identical $93.92 bankroll;
            # root cause = every silent-LLM day injected the SAME fake SPY-long bet.
            # That wasn't groupthink by the agents — it was code fabricating identical
            # trades. LLM silence is a REAL signal and must not be papered over.
            #
            # 2026-04-19 — UNIFORM FALLBACK REINSTATED under strict conditions (NBA parity).
            # Distinction:
            #   (a) raw_response is None  → LLM infrastructure failure
            #       (primary + hot-swap BOTH dead). Agents can't reason.
            #       $1M COLLECTIVE_MISSION mandates ≥75% deploy EVERY day →
            #       emit uniform fallback (top-3 signals, long broad-ETF proxy).
            #       Tagged provider_status="fallback_uniform" + fallback_used=True
            #       so audit/post-mortem can exclude these from skill metrics.
            #   (b) raw_response is non-None but parse empty → informed LLM pass.
            #       Scientific integrity: preserve the silence (no fabrication).
            _day_fallback_used = False
            # 2026-04-19 BUGFIX #3 — preserve coalition_proposal across uniform-fallback
            # and silent-pass overwrites. Mirror of NBA fix.
            _preserved_coalition = (parsed or {}).get("coalition_proposal")
            if not parsed or not parsed.get("allocations"):
                # 2026-04-21 INTERNAL AFFAIRS RCA patch #1 — same gate as NBA.
                # POL fallback = SPY/QQQ/IWM broad-ETF long on top-3 signals; ran
                # qwen-arb to +438% via bull-tape luck (NOT skill) and produced
                # 94% direct_fallback rate. Default off → cash silent-pass.
                if raw_response is None and os.environ.get("UNIFORM_FALLBACK_ENABLED", "0") == "1":
                    _fb = build_uniform_fallback_political(day_date, day_events, tid=tid)
                    if _fb and _fb.get("allocations"):
                        parsed = _fb
                        _day_fallback_used = True
                if not parsed or not parsed.get("allocations"):
                    parsed = {
                        "day_strategy": "LLM_SILENT_PASS: no synthetic bets; POST-FILTER will attempt model-signal fallback.",
                        "cash_held_pct": 1.0,
                        "cash_rationale": "LLM silent — no fabricated deployment (scientific-integrity fix 2026-04-18)",
                        "allocations": [],
                        "coalition_proposal": _preserved_coalition,
                    }

            day_log = {
                "day_idx": day_idx,
                "date": day_date,
                "n_events": len(day_events),
                "bankroll_before": round(bankroll, 2),
                "bankroll_after": round(bankroll, 2),
                "day_strategy": "",
                "cash_held_pct": 1.0,
                "cash_rationale": "no LLM response" if not raw_response else "unparseable response",
                "allocations": [],  # resolved outcomes
                "rogue": day_rogue_state.get(tid, {"is_rogue": False}) if day_rogue_state else {"is_rogue": False},
                "council_commit_target": (day_council_plan or {}).get("per_agent_commit_pct", {}).get(tid, 0.55),
                "council_alignment": (parsed or {}).get("council_alignment"),
                "ck_consensus_stance": (parsed or {}).get("ck_consensus_stance") or {},
                "events_considered": (parsed or {}).get("events_considered") or [],
                "raw_preview": (raw_response or "")[:3000],
                "fallback_used": _day_fallback_used,  # 2026-04-19 uniform-fallback tag
                "provider_status": "fallback_uniform" if _day_fallback_used else "llm_ok",
            }

            # Mech D — stash coalition proposal even if allocations are empty.
            # Also propagate to day_log for scientific observability (was missing
            # pre-2026-04-18 → coalition_proposal always None in day-XXX.json).
            if parsed and parsed.get("coalition_proposal"):
                day_proposals[tid] = parsed["coalition_proposal"]
                day_log["coalition_proposal"] = parsed["coalition_proposal"]

            if parsed and parsed.get("allocations"):
                day_log["day_strategy"] = parsed["day_strategy"]
                day_log["cash_held_pct"] = parsed["cash_held_pct"]
                day_log["cash_rationale"] = parsed["cash_rationale"]

                # 2026-04-18 TIERED AGGRESSION (gambler's ruin doctrine).
                # Low bankrolls go MORE all-in to compound out of the hole.
                # Per-bet FLOOR (not cap) + Kelly multiplier tiered by bankroll.
                tier = _tiered_risk(ts["bankroll"])
                MAX_PCT_PER_BET = tier["bet_cap"]
                # 2026-04-22 champion compound boost: per-agent override replaces
                # tier cap (top-3 2×, llama-contra probation). No-op if tid absent.
                _agent_cap = _AGENT_KELLY_OVERRIDE.get(tid)
                if _agent_cap is not None:
                    MAX_PCT_PER_BET = _agent_cap
                MIN_BET_PCT = tier["bet_floor"]
                MAX_PCT_PER_DAY = 0.98
                MIN_EDGE = tier["min_edge"]
                KELLY_MULT = tier["kelly_mult"]
                # 2026-04-21 INTERNAL AFFAIRS RCA patch #3 (NBA parity) — peak-equity
                # drawdown clamp. <50% peak → 1% cap; <25% peak → force cash.
                _pdd_on = os.environ.get("PEAK_DD_GUARD_V2", "1") == "1"
                _pdd_force_cash = False
                if _pdd_on:
                    _pdd_peak = max(float(ts.get("best_bankroll") or 0.0), ts["bankroll"])
                    _pdd_ratio = (ts["bankroll"] / _pdd_peak) if _pdd_peak > 0 else 1.0
                    if _pdd_ratio < 0.25:
                        _pdd_force_cash = True
                    elif _pdd_ratio < 0.50:
                        MAX_PCT_PER_BET = min(MAX_PCT_PER_BET, 0.01)
                starting_bankroll = bankroll
                day_exposure_pct = 0.0
                if _pdd_force_cash:
                    day_log["cash_rationale"] = f"PEAK_DD_GUARD_V2: bankroll/peak<0.25, force cash (bankroll=${ts['bankroll']:.2f})"
                    parsed = {**parsed, "allocations": [],
                              "cash_held_pct": 1.0,
                              "peak_dd_guard": "force_cash"}
                for alloc in parsed["allocations"]:
                    eidx = alloc["event_idx"] - 1  # 1-indexed in prompt
                    if eidx < 0 or eidx >= len(day_events):
                        continue
                    event = day_events[eidx]
                    direction = alloc["direction"]

                    # 2026-04-19 collision limiter (NBA parity): if
                    # >=COLLISION_MAX_AGENTS agents already took this exact
                    # (event_idx, direction) today, skip to force divergence.
                    # 2026-04-21 exception (NBA parity): bypass for fallback_uniform
                    # allocations — system-emitted, not LLM-chosen.
                    coll_key = (alloc["event_idx"], direction)
                    _is_fallback_alloc = (
                        parsed.get("fallback_used") is True
                        or alloc.get("provider_status") == "fallback_uniform"
                    )
                    if (not _is_fallback_alloc) and day_collisions.get(coll_key, 0) >= COLLISION_MAX_AGENTS:
                        continue

                    sized_pct = (alloc["pct"] or 0.0) * KELLY_MULT
                    capped_pct = max(MIN_BET_PCT, min(sized_pct, MAX_PCT_PER_BET))
                    remaining_day = max(0.0, MAX_PCT_PER_DAY - day_exposure_pct)
                    capped_pct = min(capped_pct, remaining_day)
                    if capped_pct <= 0:
                        continue
                    stake = round(starting_bankroll * capped_pct, 2)
                    if stake < 0.10:
                        continue
                    if stake > ts["bankroll"]:
                        stake = round(ts["bankroll"] * 0.99, 2)
                    day_exposure_pct += capped_pct
                    day_collisions[coll_key] = day_collisions.get(coll_key, 0) + 1

                    won, pnl_pct = resolve_political_trade(direction, event["excess_return"])
                    profit = round(stake * pnl_pct, 2)
                    ts["bankroll"] += profit
                    if won:
                        ts["wins"] += 1
                    else:
                        ts["losses"] += 1
                    ts["total_bets"] += 1
                    ts["bankroll"] = round(ts["bankroll"], 2)

                    day_log["allocations"].append({
                        "event_idx": alloc["event_idx"],
                        "ticker": alloc["ticker"],
                        "direction": direction,
                        "event_type": event.get("event_type", ""),
                        "agency": event.get("agency", ""),
                        "thesis": alloc["thesis"],
                        "pct": round(capped_pct, 4),
                        "stake": stake,
                        "confidence": alloc["confidence"],
                        "excess_return": event["excess_return"],  # visible post-resolution
                        "pnl_pct": round(pnl_pct, 4),
                        "won": won,
                        "profit": profit,
                        "provider_status": alloc.get("provider_status", "llm_ok"),  # 2026-04-19 fallback tag
                        "fallback_etf_label": alloc.get("fallback_etf_label"),
                        "underlying_ticker": alloc.get("underlying_ticker"),
                    })
                    # Mech D — record actual (event_idx, direction) pairs
                    day_actual_bets.setdefault(tid, set()).add((alloc["event_idx"], direction))
            else:
                ts["passes"] += 1  # full-cash day

            # TIER-PAD POST-FILTER REMOVED 2026-04-19: deterministic fallback padded
            # all 17 agents to 29 identical picks → Jaccard=1.0 lockstep + fake
            # "tier-pad" allocations overwhelmed real LLM bets (555 vs 58 last run).
            # New doctrine: empty LLM output = full-cash day. No fabricated picks.

            # Track recent decisions for next-day prompt
            n_bets = len(day_log["allocations"])
            n_wins = sum(1 for a in day_log["allocations"] if a["won"])
            day_pnl = ts["bankroll"] - bankroll
            # 2026-04-19 circuit breaker (NBA parity): flag next day 100% cash
            # if today's loss exceeded SINGLE_DAY_WIPEOUT_THRESHOLD of bankroll.
            if bankroll > 0 and (day_pnl / bankroll) < -SINGLE_DAY_WIPEOUT_THRESHOLD:
                ts["force_cash_today"] = True
            summary = f"{n_bets} trades, {n_wins}W, pnl {day_pnl:+.2f}"
            ts["recent_decisions"] = (ts.get("recent_decisions", []) + [{
                "date": day_date, "summary": summary,
            }])[-5:]
            ts["days_traded"] += 1
            ts["bankroll"] = round(ts["bankroll"], 2)
            ts["history"].append(ts["bankroll"])
            ts["best_bankroll"] = max(ts["best_bankroll"], ts["bankroll"])
            if ts["best_bankroll"] > 0:
                dd = (ts["best_bankroll"] - ts["bankroll"]) / ts["best_bankroll"]
                ts["max_drawdown"] = max(ts["max_drawdown"], dd)

            day_log["bankroll_after"] = round(ts["bankroll"], 2)
            _agent_logs[tid].append(day_log)
            if len(_agent_logs[tid]) > 200:
                _agent_logs[tid] = _agent_logs[tid][-200:]

            day_summary_lines.append(f"  {cfg['name'][:16]:<16} ${ts['bankroll']:>7.2f} ({n_bets} trades, {n_wins}W, {day_log['cash_held_pct']:.0%} cash)")

        log_lines.extend(day_summary_lines)

        # Axelrod Mech D — resolve coalitions for today
        day_pact_events: List[dict] = []
        for tid, prop in day_proposals.items():
            peer = prop.get("peer")
            eidx = prop.get("event_idx")
            direction = prop.get("direction")
            key = (eidx, direction)
            self_executed = key in day_actual_bets.get(tid, set())
            peer_executed = peer in day_actual_bets and key in day_actual_bets[peer]
            if self_executed and peer_executed:
                _reputation[tid]["pact_honored"] += 1
                day_pact_events.append({
                    "day": day_date, "proposer": tid, "peer": peer,
                    "event_idx": eidx, "direction": direction, "status": "honored",
                })
                _cooperation_pacts[f"{tid}|{peer}|{day_date}"] = {
                    "event_idx": eidx, "direction": direction, "honored": True,
                }
            elif not self_executed:
                _reputation[tid]["pact_broken"] += 1
                day_pact_events.append({
                    "day": day_date, "proposer": tid, "peer": peer,
                    "event_idx": eidx, "direction": direction, "status": "broken",
                })

        # Axelrod Mechanism A: build COMMON_KNOWLEDGE[D] from today's resolved trades
        prev_day_ck = build_common_knowledge_block(
            day_date, state, dict(_agent_logs),
            reputation=dict(_reputation), pact_events=day_pact_events,
            day_idx=day_idx,
        )
        _common_knowledge[day_date] = prev_day_ck

        # Axelrod Mechanism C: write day-N post-mortem log BEFORE Mech B reassigns
        write_axelrod_log(day_idx, day_date, state, dict(_agent_logs), dict(_sacrificial_assignments))

        # Axelrod Mechanism B: compute sacrificial + challenge assignments for NEXT day
        _sacrificial_assignments.clear()
        _sacrificial_assignments.update(
            assign_sacrificial_archetypes(day_date, state, dict(_agent_logs))
        )
        _challenge_assignments.clear()
        _challenge_assignments.update(
            assign_challenge_tiers(state, _sacrificial_assignments)
        )

        # Update live state
        _fleet_best_live = max(state[t]["bankroll"] for t in state)
        _leader_live = max(state, key=lambda t: state[t]["bankroll"])
        with _state_lock:
            _experiment_state = {
                "days_processed": day_idx + 1,
                "days_total": n_days,
                "events_processed": sum(len(events_by_date[d]) for d in dates_sorted[:day_idx + 1]),
                "events_total": n_events,
                "completed": False,
                "design": "day-bucket-v3-political",
                "agents": {tid: {k: v for k, v in ts.items() if k not in ("history", "recent_decisions")}
                           for tid, ts in state.items()},
                "updated": datetime.now(timezone.utc).isoformat(),
                "last_ck_block": prev_day_ck,  # Axelrod Mech A: persist for resume
                # Collective experiment (2026-04-17)
                "season_target": SEASON_TARGET,
                "fleet_best_bankroll": round(_fleet_best_live, 2),
                "fleet_leader": _leader_live,
                "season_progress_pct": round((_fleet_best_live / SEASON_TARGET) * 100.0, 4),
                "council_plan": day_council_plan,
                "rogue_this_day": {t: r for t, r in day_rogue_state.items() if r["is_rogue"]},
            }
        # Parallel Hub pushes — 4 independent uploads fire concurrently.
        # Saves ~8-10s per day. Each function targets its own file, no race.
        _day_logs_for_hub = {
            tid: _agent_logs[tid][-1]
            for tid in TRADERS if _agent_logs.get(tid) and _agent_logs[tid]
            and _agent_logs[tid][-1].get("date") == day_date
        }
        _hub_tasks = [
            lambda: _save_state_to_disk(_experiment_state),
            lambda: _save_logs_to_disk(),
        ]
        if _day_logs_for_hub:
            _hub_tasks.append(lambda: _push_day_decisions_to_hub(
                day_idx=day_idx, day_date=day_date, n_events=len(day_events),
                day_logs_by_agent=_day_logs_for_hub,
                day_council_plan=day_council_plan,
                day_rogue_state=day_rogue_state,
            ))
        with ThreadPoolExecutor(max_workers=len(_hub_tasks)) as _hub_pool:
            list(_hub_pool.map(lambda fn: fn(), _hub_tasks))

        if (day_idx + 1) % 1 == 0:  # Yield every day
            elapsed = time.time() - start_time
            days_done = day_idx + 1
            rate = days_done / (elapsed / 60) if elapsed > 0 else 0
            eta_min = (n_days - days_done) / rate if rate > 0 else 0

            try:
                progress(days_done / n_days,
                         desc=f"Day {days_done}/{n_days} | {rate:.2f} days/min | ETA {eta_min:.0f}min")
            except Exception:
                pass

            # Build leaderboard
            lb_data = []
            for tid, ts in sorted(state.items(), key=lambda x: -x[1]["bankroll"]):
                cfg = TRADERS[tid]
                roi = ((ts["bankroll"] - 100.0) / 100.0) * 100
                win_rate = ts["wins"] / max(1, ts["total_bets"]) * 100
                llm_rate = ts["llm_ok"] / max(1, ts["llm_calls"]) * 100
                lb_data.append([
                    cfg["name"],
                    cfg["provider"].split(":")[-1][:20],
                    f"${ts['bankroll']:.2f}",
                    f"{roi:+.1f}%",
                    ts["total_bets"],
                    f"{win_rate:.0f}%",
                    ts["passes"],
                    f"{llm_rate:.0f}%",
                    f"{ts['max_drawdown']:.1%}",
                ])

            # Build chart
            events_done = sum(len(events_by_date[d]) for d in dates_sorted[:day_idx + 1])
            fig = make_bankroll_chart(state, events_done)

            # Show recent unique errors
            err_summary = ""
            if _llm_errors:
                unique_errs = list(set(_llm_errors[-20:]))[:5]
                err_summary = " | ERRORS: " + "; ".join(unique_errs)

            status = (
                f"Day {days_done}/{n_days} ({events_done}/{n_events} events) | "
                f"LLM calls: {_llm_calls} (fail: {_llm_failures}) | "
                f"Rate: {rate:.2f} d/min | ETA: {eta_min:.0f}min | "
                f"Elapsed: {elapsed/60:.1f}min"
                f"{err_summary}"
            )

            log_text = "\n".join(log_lines[-30:])

            yield (status, lb_data, fig, log_text)

    # ── FINAL RESULTS ────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    log_lines.append("\n" + "=" * 50)
    log_lines.append("FINAL RESULTS")
    log_lines.append("=" * 50)

    # Sort by bankroll
    final_ranking = sorted(state.items(), key=lambda x: -x[1]["bankroll"])
    for rank, (tid, ts) in enumerate(final_ranking, 1):
        cfg = TRADERS[tid]
        roi = ((ts["bankroll"] - 100.0) / 100.0) * 100
        log_lines.append(
            f"  #{rank} {cfg['name']}: ${ts['bankroll']:.2f} ({roi:+.1f}% ROI) "
            f"| {ts['total_bets']} trades | {ts['wins']}W-{ts['losses']}L | "
            f"DD: {ts['max_drawdown']:.1%} | LLM: {ts['llm_ok']}/{ts['llm_calls']}"
        )

    log_lines.append(f"\nTotal LLM calls: {_llm_calls} | Failures: {_llm_failures}")
    log_lines.append(f"Time: {elapsed/60:.1f} min ({elapsed/3600:.1f} hours)")

    # Save results
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset": "political-2026-03-12-to-2026-03-26",
        "design": "day-bucket-v3-political",
        "events_processed": n_events,
        "days_processed": n_days,
        "leverage": LEVERAGE,
        "llm_calls": _llm_calls,
        "llm_failures": _llm_failures,
        "elapsed_seconds": round(elapsed, 1),
        "leaderboard": [],
    }
    for rank, (tid, ts) in enumerate(final_ranking, 1):
        cfg = TRADERS[tid]
        results["leaderboard"].append({
            "rank": rank,
            "trader_id": tid,
            "name": cfg["name"],
            "provider": cfg["provider"],
            "personality": cfg["personality"],
            "bankroll": round(ts["bankroll"], 2),
            "roi_pct": round(((ts["bankroll"] - 100.0) / 100.0) * 100, 2),
            "total_bets": ts["total_bets"],
            "wins": ts["wins"],
            "losses": ts["losses"],
            "passes": ts["passes"],
            "win_rate": round(ts["wins"] / max(1, ts["total_bets"]) * 100, 1),
            "max_drawdown": round(ts["max_drawdown"], 4),
            "llm_calls": ts["llm_calls"],
            "llm_success": ts["llm_ok"],
        })

    results_path = Path(__file__).parent / "data" / "experiment-results.json"
    try:
        results_path.write_text(json.dumps(results, indent=2))
    except Exception:
        pass

    lb_data = []
    for rank, (tid, ts) in enumerate(final_ranking, 1):
        cfg = TRADERS[tid]
        roi = ((ts["bankroll"] - 100.0) / 100.0) * 100
        win_rate = ts["wins"] / max(1, ts["total_bets"]) * 100
        llm_rate = ts["llm_ok"] / max(1, ts["llm_calls"]) * 100
        lb_data.append([
            cfg["name"],
            cfg["provider"].split(":")[-1][:20],
            f"${ts['bankroll']:.2f}",
            f"{roi:+.1f}%",
            ts["total_bets"],
            f"{win_rate:.0f}%",
            ts["passes"],
            f"{llm_rate:.0f}%",
            f"{ts['max_drawdown']:.1%}",
        ])

    fig = make_bankroll_chart(state, n_events)
    stopped = _stop_event.is_set()
    winner = TRADERS[final_ranking[0][0]]['name']
    winner_bank = final_ranking[0][1]['bankroll']
    days_done = day_idx + 1 if 'day_idx' in dir() else n_days
    status = f"{'STOPPED' if stopped else 'COMPLETE'} | {days_done}/{n_days} days | {elapsed/60:.1f}min | Winner: {winner} ${winner_bank:.2f}"
    log_text = "\n".join(log_lines[-50:])

    with _state_lock:
        _experiment_state = {
            "days_processed": days_done,
            "days_total": n_days,
            "events_total": n_events,
            "completed": not stopped,
            "stopped": stopped,
            "design": "day-bucket-v3-political",
            "agents": {tid: {k: v for k, v in ts.items() if k not in ("history", "recent_decisions")}
                       for tid, ts in state.items()},
            "updated": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
        }
        _save_state_to_disk(_experiment_state)
        _save_logs_to_disk()
    # 2026-04-22 PLUMBER RCA fix: do NOT flip _experiment_running=False here.
    # The outer _bg/_auto_start wrapper uses `while not _stop_event.is_set()`
    # to immediately loop back into run_experiment for multi-season compound.
    # Flipping False created a ~0.5s race window where keepalive saw
    # running=false and POSTed /api/run → second generator → reset false alert.
    # The wrapper resets state on re-entry if the season completed.

    yield (status, lb_data, fig, log_text)


def make_bankroll_chart(state: Dict, events_done: int) -> plt.Figure:
    """Create bankroll evolution chart."""
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#0a0a0a")
    ax.set_facecolor("#0a0a0a")

    colors = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
        "#F7DC6F", "#BB8FCE", "#85C1E9", "#82E0AA", "#F0B27A",
    ]

    for i, (tid, ts) in enumerate(TRADERS.items()):
        hist = state[tid]["history"]
        if len(hist) > 1:
            # Subsample for performance
            step = max(1, len(hist) // 500)
            x = list(range(0, len(hist), step))
            y = [hist[j] for j in x]
            ax.plot(x, y, color=colors[i % len(colors)],
                    label=f"{ts['name']} ${state[tid]['bankroll']:.0f}",
                    linewidth=1.2, alpha=0.85)

    ax.axhline(y=100, color="#444", linestyle="--", alpha=0.5, label="Start ($100)")
    ax.set_xlabel("Agent-event steps", color="#aaa", fontsize=10)
    ax.set_ylabel("Bankroll ($)", color="#aaa", fontsize=10)
    ax.set_title(f"Nomos42 Political LLM Trading Floor — Bankroll Evolution ({events_done} events)",
                 color="#eee", fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=7, ncol=2,
              facecolor="#1a1a1a", edgecolor="#333", labelcolor="#ccc")
    ax.tick_params(colors="#888")
    ax.spines["bottom"].set_color("#333")
    ax.spines["left"].set_color("#333")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.15, color="#444")

    plt.tight_layout()
    return fig


# ── GRADIO UI ────────────────────────────────────────────────────────────────

LEADERBOARD_HEADERS = [
    "Agent", "Model", "Bankroll", "ROI", "Trades",
    "Win%", "Passes", "LLM%", "Max DD",
]

with gr.Blocks(
    title="Nomos42 Political LLM Trading Floor",
    theme=gr.themes.Base(
        primary_hue="purple",
        neutral_hue="gray",
    ),
    css="""
    .gradio-container { max-width: 1200px !important; }
    .status-bar { font-family: monospace; font-size: 14px; }
    """
) as demo:
    gr.Markdown("""
# Nomos42 Political LLM Trading Floor
### 10 AI agents trade sector ETFs on political signals — real LLM reasoning

Each agent is a **real LLM** (Cerebras, Gemini, Mistral) that receives
daily **political events** (insider trades, Fed rules, executive orders),
**sector trends** (30d baseline per sector), and **22 SOTA strategies** —
then **reasons** about whether to go long or short on affected sector ETFs.

After ~14 days of 2026 political data, we see which LLM backbone, personality,
and political-signal strategy actually generates alpha.

| Agent | Model | Provider | Personality | Risk |
|-------|-------|----------|-------------|------|
| Qwen Quant 235B | Qwen 3 235B | Cerebras | Regulatory-delta quant | 0.55 |
| Qwen Arb 235B | Qwen 3 235B | Cerebras | Cross-sector arbitrage | 0.65 |
| Llama Contrarian | Llama 3.1 8B | Cerebras | Consensus-fade | 0.55 |
| Gemini Analytical | Gemini 3 Flash | Google | Fed/SEC stats-first | 0.55 |
| Gemini Tactical | Gemini 3 Flash | Google | Calendar/schedule | 0.60 |
| Mistral Large | Mistral Large | Mistral | Ensemble meta-allocator | 0.50 |
| Mistral Medium | Mistral Medium | Mistral | Portfolio diversification | 0.45 |
| Mistral Small | Mistral Small | Mistral | Cash when no conviction | 0.35 |
| Mistral Nemo | Mistral Nemo | Mistral | Exec-order momentum | 0.70 |
| Ministral 8B | Ministral 8B | Mistral | Game-theory sizing | 0.35 |
    """)

    with gr.Row():
        start_btn = gr.Button("Start / Resume Experiment", variant="primary", scale=3)
        stop_btn = gr.Button("Stop", variant="stop", scale=1)
        status_box = gr.Textbox(label="Status", interactive=False, scale=6, elem_classes=["status-bar"])

    with gr.Row():
        leaderboard = gr.Dataframe(
            headers=LEADERBOARD_HEADERS,
            label="Live Leaderboard (sorted by bankroll)",
            interactive=False,
            wrap=True,
        )

    with gr.Row():
        chart = gr.Plot(label="Bankroll Evolution")

    with gr.Row():
        log_box = gr.Textbox(label="Event Log (last 30 entries)", lines=15, interactive=False,
                             show_copy_button=True)

    def stop_experiment():
        _stop_event.set()
        return "STOPPING... (will finish current event day)"

    start_btn.click(
        fn=run_experiment,
        outputs=[status_box, leaderboard, chart, log_box],
    )
    stop_btn.click(
        fn=stop_experiment,
        outputs=[status_box],
    )


# ── FASTAPI CONTROL API ────────────────────────────────────────────────────
# Mounted alongside Gradio for programmatic control (councils, GH Actions, CLI)

api = FastAPI()

@api.get("/api/status")
async def api_status():
    """Current experiment status — for councils, monitoring, GH Actions."""
    with _state_lock:
        state = dict(_experiment_state) if _experiment_state else {}
    state["running"] = _experiment_running
    state["stopped"] = _stop_event.is_set()
    state["started_utc"] = _started_utc  # 2026-04-22: set on first run_experiment entry, survives soft restarts
    state["llm_calls"] = _llm_calls
    state["llm_failures"] = _llm_failures
    state["gateway_url"] = GATEWAY_URL or None
    # True iff at least one successful gateway round-trip this session
    state["gateway_routed"] = bool(_gateway_routed)
    state["gateway_enabled"] = bool(_GATEWAY_URL)
    state["gateway_call_count"] = _gateway_routed
    state["direct_fallback_count"] = _gateway_fallback
    # Back-compat (deprecated, keep for a release)
    state["gateway_routed_count"] = _gateway_routed
    state["gateway_fallback_count"] = _gateway_fallback
    # Axelrod Mech B/D — sacrificial + cooperation exposure
    state["sacrificial_assignments"] = dict(_sacrificial_assignments)
    state["reputation"] = {tid: dict(r) for tid, r in _reputation.items()}
    state["cooperation_pacts_count"] = len(_cooperation_pacts)
    state["axelrod_canon_active"] = True
    state["axelrod_library_active"] = _AXELROD_OK
    state["axelrod_strategies"] = dict(AXELROD_STRATEGIES)
    # ── Collective experiment (2026-04-17) ──
    with _state_lock:
        _agents = _experiment_state.get("agents", {}) if _experiment_state else {}
    if _agents:
        _fleet_best = max(a.get("bankroll", 0.0) for a in _agents.values())
        _leader = max(_agents, key=lambda t: _agents[t].get("bankroll", 0.0))
    else:
        _fleet_best = STARTING_CAPITAL
        _leader = None
    state["season_target"] = SEASON_TARGET
    state["fleet_best_bankroll"] = round(_fleet_best, 2)
    state["fleet_leader"] = _leader
    state["season_progress_pct"] = round((_fleet_best / SEASON_TARGET) * 100.0, 4)
    state["council_plan_count"] = len(_council_plans)
    state["latest_council_summary"] = (
        list(_council_plans.values())[-1].get("council_summary", "") if _council_plans else ""
    )
    state["rogue_events_total"] = len(_rogue_events)
    state["rogue_events_recent"] = _rogue_events[-10:]
    # Provider health snapshot (circuit breaker + hot-swap, 2026-04-17).
    if _PH_AVAILABLE:
        try:
            state["provider_health"] = _ph.get_snapshot()
        except Exception:
            pass
    # Langfuse trace-send errors (first 20, captured 2026-04-18)
    state["langfuse_errors"] = list(_langfuse_errors[:20])
    state["langfuse_errors_count"] = len(_langfuse_errors)
    state["langfuse_enabled"] = bool(_langfuse)
    return JSONResponse(state)

@api.post("/api/run")
async def api_run(request: Request):
    """Trigger experiment start (same as clicking the button).
    For GH Actions / council triggers. Non-blocking — returns immediately.

    2026-04-22 PLUMBER RCA fix: atomic gate under _state_lock so keepalive +
    auto_start cannot both enter run_experiment and clobber each other's
    _llm_calls / state.
    """
    global _experiment_running
    _stop_event.clear()
    # Atomic claim — check+flip under _state_lock to kill the race window.
    with _state_lock:
        if _experiment_running:
            return JSONResponse({
                "status": "resumed",
                "events_processed": _experiment_state.get("events_processed", 0),
                "message": "Stop flag cleared, experiment continues.",
            })
        _experiment_running = True  # claim BEFORE spawning _bg — no second /api/run can enter
    import threading, traceback as _tb
    def _bg():
        global _experiment_running
        try:
            # 2026-04-22: while-not-stop loop. run_experiment no longer flips
            # _experiment_running=False on season end, so we re-enter for the
            # next season (multi-season compound). Only _stop_event exits.
            while not _stop_event.is_set():
                try:
                    for _ in run_experiment():
                        pass
                except Exception as e:
                    print(f"[api_run bg] run crashed: {e}\n{_tb.format_exc()}")
                    import time as _t; _t.sleep(10)
                    continue
                # Clean completion — brief pause before next season to avoid tight loop.
                import time as _t; _t.sleep(5)
        finally:
            # Only clear on explicit stop or permanent failure.
            with _state_lock:
                _experiment_running = False
    threading.Thread(target=_bg, daemon=True, name="api_run_bg").start()
    return JSONResponse({"status": "started", "message": "Experiment launched in background thread."})

@api.post("/api/stop")
async def api_stop():
    """Graceful stop — finishes current event day then saves state."""
    _stop_event.set()
    return JSONResponse({"status": "stopping", "running": _experiment_running})

@api.post("/api/reset")
async def api_reset():
    """Reset experiment state (delete saved state)."""
    if _experiment_running:
        return JSONResponse({"status": "error", "message": "Cannot reset while running. Stop first."}, status_code=409)
    global _experiment_state, _agent_logs, _llm_calls, _llm_failures, _gateway_routed, _gateway_fallback, _started_utc
    _experiment_state = {}
    _agent_logs = defaultdict(list)
    # 2026-04-22 PLUMBER RCA fix: lifetime counters now ONLY zeroed here,
    # not on every run_experiment entry (which triggered the race).
    _llm_calls = 0
    _llm_failures = 0
    _gateway_routed = 0
    _gateway_fallback = 0
    _started_utc = None
    try:
        STATE_PATH.unlink(missing_ok=True)
        LOGS_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    # Also purge Hub-persisted state — auto-resume would otherwise re-download it.
    hub_deleted = []
    if _hub_api:
        for fname in ("data/runtime/state.json",
                      "data/runtime/agent_logs.json",
                      "data/runtime/council_plans.json"):
            try:
                _hub_api.delete_file(path_in_repo=fname, repo_id=HF_REPO_ID,
                                     repo_type="space",
                                     commit_message=f"reset: purge {fname}")
                hub_deleted.append(fname)
            except Exception as e:
                print(f"[reset] hub delete {fname} failed: {e}")
    return JSONResponse({"status": "reset", "message": "State cleared. Next run starts fresh.",
                         "hub_deleted": hub_deleted})

@api.post("/api/mutate")
async def api_mutate(request: Request):
    """Mutate agent parameters mid-experiment.
    Body: {"agent": "mistral-large", "risk_tolerance": 0.8, "personality": "aggressive"}"""
    body = await request.json()
    agent_id = body.get("agent")
    if agent_id not in TRADERS:
        return JSONResponse({"status": "error", "message": f"Unknown agent: {agent_id}"}, status_code=400)
    changed = []
    if "risk_tolerance" in body:
        TRADERS[agent_id]["risk_tolerance"] = float(body["risk_tolerance"])
        changed.append(f"risk_tolerance={body['risk_tolerance']}")
    if "personality" in body:
        TRADERS[agent_id]["personality"] = body["personality"]
        changed.append(f"personality={body['personality']}")
    return JSONResponse({"status": "mutated", "agent": agent_id, "changes": changed})

@api.get("/api/logs")
async def api_logs(agent: str = None, limit: int = 50):
    """Per-agent decision log. ?agent=mistral-large&limit=20"""
    if agent:
        logs = list(_agent_logs.get(agent, []))[-limit:]
        return JSONResponse({"agent": agent, "count": len(logs), "logs": logs})
    # All agents summary
    summary = {tid: len(logs) for tid, logs in _agent_logs.items()}
    return JSONResponse({"agents": summary, "total_entries": sum(summary.values())})

@api.get("/api/day-decisions")
async def api_day_decisions(date: str = None, agent: str = None, limit: int = 200):
    """Day-level decisions for council analysis.

    ?date=2026-03-15 — all agents' decisions for that day
    ?agent=qwen-quant — all days for one agent
    (no params) — summary by day with total allocations
    """
    out = {}
    if date:
        for tid, logs in _agent_logs.items():
            day_logs = [l for l in logs if l.get("date") == date]
            if day_logs:
                out[tid] = day_logs[0]  # one entry per agent per day
        return JSONResponse({"date": date, "agents": out, "n_agents": len(out)})
    if agent:
        logs = list(_agent_logs.get(agent, []))[-limit:]
        return JSONResponse({"agent": agent, "count": len(logs), "days": logs})
    # Summary: list dates with count of agents that traded
    by_date = {}
    for tid, logs in _agent_logs.items():
        for l in logs:
            d = l.get("date")
            if not d:
                continue
            if d not in by_date:
                by_date[d] = {"date": d, "agents": 0, "total_allocations": 0, "total_cash_pct": 0.0}
            by_date[d]["agents"] += 1
            by_date[d]["total_allocations"] += len(l.get("allocations", []))
            by_date[d]["total_cash_pct"] += l.get("cash_held_pct", 0.0)
    days = sorted(by_date.values(), key=lambda x: x["date"])
    for d in days:
        d["avg_cash_pct"] = round(d["total_cash_pct"] / max(1, d["agents"]), 3)
    return JSONResponse({"total_days": len(days), "days": days[-limit:]})


@api.get("/api/leaderboard")
async def api_leaderboard():
    """Current leaderboard as JSON."""
    with _state_lock:
        agents = _experiment_state.get("agents", {})
    if not agents:
        return JSONResponse({"status": "no_data", "message": "No experiment data yet"})
    lb = []
    for tid, ts in sorted(agents.items(), key=lambda x: -x[1].get("bankroll", 0)):
        cfg = TRADERS.get(tid, {})
        bankroll = ts.get("bankroll", 100)
        roi = ((bankroll - 100) / 100) * 100
        lb.append({
            "trader_id": tid,
            "name": cfg.get("name", tid),
            "provider": cfg.get("provider", "?"),
            "bankroll": round(bankroll, 2),
            "roi_pct": round(roi, 2),
            "total_bets": ts.get("total_bets", 0),
            "wins": ts.get("wins", 0),
            "losses": ts.get("losses", 0),
        })
    return JSONResponse({"leaderboard": lb, "events_processed": _experiment_state.get("events_processed", 0)})


@api.get("/api/axelrod-log")
async def api_axelrod_log(day: int = None, since: int = None):
    """Axelrod Mech C export — serves the per-day post-mortem dataset used as
    the primary dataset for the Axelrod-LLM paper (§6 results).

    Logs are written by write_axelrod_log to AXELROD_LOG_DIR/day-NNN.jsonl.
    Space /tmp is ephemeral, so this endpoint is the canonical way for the VM
    to pull the log into data/arena/axelrod-log/ for version-controlled analysis.

    Params:
      ?day=N      — return only day-N as a list of rows
      ?since=N    — return all days with day_idx >= N
      (no params) — index: list available days with row counts
    """
    try:
        if not AXELROD_LOG_DIR.exists():
            return JSONResponse({"status": "no_data", "message": "axelrod log dir not created yet"})
        files = sorted(AXELROD_LOG_DIR.glob("day-*.jsonl"))
        if not files:
            return JSONResponse({"status": "no_data", "days": []})

        def _read(fp):
            rows = []
            with fp.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            return rows

        if day is not None:
            fp = AXELROD_LOG_DIR / f"day-{int(day):03d}.jsonl"
            if not fp.exists():
                return JSONResponse({"status": "not_found", "day": day}, status_code=404)
            return JSONResponse({"day_idx": int(day), "rows": _read(fp)})

        if since is not None:
            out = []
            for fp in files:
                try:
                    idx = int(fp.stem.split("-")[1])
                except Exception:
                    continue
                if idx >= int(since):
                    out.append({"day_idx": idx, "rows": _read(fp)})
            return JSONResponse({"since": int(since), "days": out, "n_days": len(out)})

        index = []
        for fp in files:
            try:
                idx = int(fp.stem.split("-")[1])
            except Exception:
                continue
            rows = _read(fp)
            if not rows:
                continue
            index.append({
                "day_idx": idx,
                "date": rows[0].get("date"),
                "n_rows": len(rows),
            })
        return JSONResponse({"n_days": len(index), "index": index})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@api.get("/paper")
async def serve_paper():
    """Serve the Axelrod-LLM research paper inline (not as download)."""
    from fastapi.responses import HTMLResponse
    paper_path = Path(__file__).parent / "paper.html"
    if paper_path.exists():
        return HTMLResponse(content=paper_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Paper not yet generated</h1><p>Run md_to_html.py to build paper.html</p>", status_code=404)


# Mount FastAPI alongside Gradio
app = gr.mount_gradio_app(api, demo, path="/")

# ── MODULE-LEVEL HUB PRE-SEED (2026-04-22 PLUMBER RCA fix) ─────────────────
# Load Hub state synchronously at import time so /api/status never returns
# fresh-init defaults ($100 for every agent) during the ~0.5s window between
# uvicorn binding and the first run_experiment reaching its resume-seed block.
try:
    _preseed = _load_state_from_disk()
    if _preseed and _preseed.get("agents"):
        with _state_lock:
            _experiment_state = dict(_preseed)
            _experiment_state.setdefault("days_processed", int(_preseed.get("days_processed", 0)))
            _experiment_state.setdefault("days_total", int(_preseed.get("days_total", 0)))
            _experiment_state["_source"] = "hub_preseed"
            _experiment_state["_preseeded_utc"] = datetime.now(timezone.utc).isoformat()
        _pfb = max((a.get("bankroll", 100.0) for a in _preseed.get("agents", {}).values()), default=100.0)
        print(f"[hub-preseed] loaded state.json — day {_preseed.get('days_processed',0)}, fleet_best ${_pfb:.2f}")
    else:
        print("[hub-preseed] no saved state (fresh install or Hub unavailable)")
except Exception as _e:
    print(f"[hub-preseed] failed: {_e}")

# Auto-start experiment on Space boot (survives rebuilds)
# Set SKIP_AUTO_START=1 env var to boot idle (for purge workflows).
def _auto_start():
    global _experiment_running
    import time as _t, traceback as _tb
    if os.environ.get("SKIP_AUTO_START") == "1":
        print("[auto-start] SKIP_AUTO_START=1 set, boot-idle mode")
        return
    _t.sleep(10)
    # 2026-04-22: atomic claim — lose the race silently if /api/run already started.
    with _state_lock:
        if _experiment_running:
            print("[auto-start] /api/run already claimed — standing down")
            return
        _experiment_running = True
    print("[auto-start] launching experiment on boot (while-not-stop loop)")
    try:
        while not _stop_event.is_set():
            try:
                for _ in run_experiment():
                    pass
            except Exception as e:
                print(f"[auto-start] run crashed: {e}\n{_tb.format_exc()}")
                _t.sleep(15)
                continue
            # Multi-season compound — brief pause before next season.
            _t.sleep(5)
    finally:
        with _state_lock:
            _experiment_running = False

import threading as _th
_th.Thread(target=_auto_start, daemon=True, name="auto_start").start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
