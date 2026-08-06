from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

from .global_intent_classifier_v2 import GlobalIntentClassifierV2
from .intent_schema_v2 import SUPPORTED_MODULES
from .intent_system import (
    CANDIDATE_EVIDENCE_REQUEST,
    DAILY_REPORT_READ_INTENT,
    EXPLANATION_INTENTS,
    HISTORY_QUOTE_REFERENCE,
    PRICE_ADJUSTMENT_INTENT,
    PRICE_FEEDBACK_CLARIFICATION,
    PRICE_EXPLANATION_REQUEST,
    PRICE_QUOTE_REQUEST,
    REPORT_DETAIL_QUESTION,
    RESET_VEHICLE,
    SELL_CAR_VALUATION_INTENT,
    VALUATION_INTENTS,
    WHY_LOW_CONFIDENCE,
)
from .module_guard_v2 import ModuleGuardV2

try:  # LangGraph is the production path; the fallback keeps local audits importable.
    from langgraph.graph import END, START, StateGraph
    from langgraph.checkpoint.memory import MemorySaver
except Exception:  # pragma: no cover - exercised only in dependency failure mode.
    END = "__end__"
    START = "__start__"
    MemorySaver = None  # type: ignore[assignment]
    StateGraph = None  # type: ignore[assignment]


GRAPH_VERSION = "enterprise_agent_graph_v2.0"


class EnterpriseAgentState(TypedDict, total=False):
    message: str
    selected_module: str
    client_state: Dict[str, Any]
    session_id: str
    classifier_result: Dict[str, Any]
    guarded_result: Dict[str, Any]
    intent_result: Dict[str, Any]
    task_contract: Dict[str, Any]
    tool_plan: Dict[str, Any]
    state_policy: Dict[str, Any]
    execution_route: str
    node_trace: List[Dict[str, Any]]
    errors: List[str]


def _trace(state: EnterpriseAgentState, node: str, status: str, detail: Dict[str, Any] | None = None) -> None:
    state.setdefault("node_trace", []).append(
        {
            "node": node,
            "status": status,
            "detail": detail or {},
            "at": datetime.now().isoformat(timespec="seconds"),
        }
    )


def _normalize_module(module: str | None) -> str:
    module = str(module or "media_pricing")
    return module if module in SUPPORTED_MODULES else "media_pricing"


def _task_family(intent_result: Dict[str, Any]) -> str:
    internal = intent_result.get("internal_intent") or ""
    category = intent_result.get("business_category") or ""
    # “降价最多”读取的是懂车帝公开降价榜证据，不是日报正文。
    # 必须在 DAILY_REPORT 大类判断之前分流，否则会稳定走错工具。
    if internal == "DAILY_REPORT_DISCOUNT_QUERY":
        return "market_report"
    if internal in {DAILY_REPORT_READ_INTENT, REPORT_DETAIL_QUESTION} or category == "DAILY_REPORT":
        return "daily_report"
    if internal in {"COMPOUND_SELECTION_PRICING", "COMPOUND_MARKET_REPORT_ADVICE"}:
        return "compound_market_task"
    if internal == "COMPOUND_PRICING_MARKET_EXPLANATION":
        return "compound_pricing_task"
    if category == "MARKET_STATE" or internal.startswith("MARKET_"):
        module_intent = str(intent_result.get("module_intent") or "")
        if module_intent == "car_selection":
            return "selection"
        if module_intent == "market_report":
            return "market_report"
        return "market_state"
    if category == "GENERAL_AUTOMOTIVE_QA" or internal == "GENERAL_AUTOMOTIVE_QA":
        return "general_automotive_qa"
    if internal in {
        PRICE_EXPLANATION_REQUEST,
        PRICE_FEEDBACK_CLARIFICATION,
        CANDIDATE_EVIDENCE_REQUEST,
        WHY_LOW_CONFIDENCE,
        HISTORY_QUOTE_REFERENCE,
    }:
        return "pricing_explanation"
    if internal == PRICE_ADJUSTMENT_INTENT or category == "PRICE_ADJUSTMENT":
        return "pricing_adjustment"
    if internal in set(VALUATION_INTENTS) | {
        PRICE_QUOTE_REQUEST, SELL_CAR_VALUATION_INTENT, "BUY_CAR_PRICE", "BOTH_PRICE",
        "PURCHASE_PRICE_JUDGEMENT", "SALE_PRICE_ADVICE", "BOTH_PRICE_ADVICE",
    }:
        return "pricing_quote"
    if internal == RESET_VEHICLE:
        return "reset_context"
    return "information_collection"


def _price_role(intent_result: Dict[str, Any]) -> str:
    task = (intent_result.get("task") or "").upper()
    internal = intent_result.get("internal_intent") or ""
    if task in {"B2C", "C2B", "BOTH"}:
        return task
    if internal == "BUY_CAR_PRICE":
        return "B2C"
    if internal == "SALE_PRICE_ADVICE":
        return "B2C"
    if internal == "BOTH_PRICE_ADVICE":
        return "BOTH"
    if internal in {"PURCHASE_PRICE_JUDGEMENT", "COMPOUND_PRICING_MARKET_EXPLANATION"}:
        return "C2B"
    if internal in {PRICE_QUOTE_REQUEST, SELL_CAR_VALUATION_INTENT}:
        return "C2B"
    return "NONE"


class EnterpriseAgentGraphV2:
    """Enterprise task graph for the assistant front door.

    The graph owns task understanding, module boundaries and state contracts.
    Pricing, report generation and market-state logic remain deterministic tools
    called by the existing services.  This deliberately keeps price math out of
    any LLM/router layer while giving every turn an auditable graph execution.
    """

    def __init__(
        self,
        *,
        intent_classifier: Optional[GlobalIntentClassifierV2] = None,
        module_guard: Optional[ModuleGuardV2] = None,
    ) -> None:
        self.intent_classifier = intent_classifier or GlobalIntentClassifierV2()
        self.module_guard = module_guard or ModuleGuardV2()
        self.graph = self._build_graph()

    def run_preflight(
        self,
        *,
        message: str,
        selected_module: str,
        client_state: Dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Dict[str, Any]:
        initial: EnterpriseAgentState = {
            "message": str(message or "").strip(),
            "selected_module": _normalize_module(selected_module),
            "client_state": dict(client_state or {}),
            "session_id": str(session_id or (client_state or {}).get("session_id") or "anonymous"),
            "node_trace": [],
            "errors": [],
        }
        if self.graph is None:
            state = self._normalize_context(initial)
            state = self._classify_intent(state)
            state = self._guard_module(state)
            state = self._build_task_contract(state)
            state = self._build_tool_plan(state)
            state = self._validate_state_policy(state)
            route = self._route_after_policy(state)
            state = self._dispatch_node(route)(state)
        else:
            state = self.graph.invoke(
                initial,
                config={"configurable": {"thread_id": initial["session_id"]}},
            )
        return {
            "graph_version": GRAPH_VERSION,
            "framework": "langgraph" if self.graph is not None else "python_fallback",
            "classifier_result": state.get("classifier_result") or {},
            "guarded_result": state.get("guarded_result") or {},
            "intent_result": state.get("intent_result") or {},
            "task_contract": state.get("task_contract") or {},
            "tool_plan": state.get("tool_plan") or {},
            "state_policy": state.get("state_policy") or {},
            "execution_route": state.get("execution_route") or "clarify_or_reply",
            "node_trace": state.get("node_trace") or [],
            "errors": state.get("errors") or [],
        }

    def _build_graph(self) -> Any:
        if StateGraph is None:
            return None
        graph = StateGraph(EnterpriseAgentState)
        graph.add_node("normalize_context", self._normalize_context)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("guard_module", self._guard_module)
        graph.add_node("build_task_contract", self._build_task_contract)
        graph.add_node("build_tool_plan", self._build_tool_plan)
        graph.add_node("validate_state_policy", self._validate_state_policy)
        for route in (
            "general_answer",
            "daily_report",
            "selection",
            "market_report",
            "pricing",
            "compound",
            "information_collection",
        ):
            graph.add_node(f"dispatch_{route}", self._dispatch_node(route))
        graph.add_edge(START, "normalize_context")
        graph.add_edge("normalize_context", "classify_intent")
        graph.add_edge("classify_intent", "guard_module")
        graph.add_edge("guard_module", "build_task_contract")
        graph.add_edge("build_task_contract", "build_tool_plan")
        graph.add_edge("build_tool_plan", "validate_state_policy")
        graph.add_conditional_edges(
            "validate_state_policy",
            self._route_after_policy,
            {
                route: f"dispatch_{route}"
                for route in (
                    "general_answer",
                    "daily_report",
                    "selection",
                    "market_report",
                    "pricing",
                    "compound",
                    "information_collection",
                )
            },
        )
        for route in (
            "general_answer",
            "daily_report",
            "selection",
            "market_report",
            "pricing",
            "compound",
            "information_collection",
        ):
            graph.add_edge(f"dispatch_{route}", END)
        if MemorySaver is not None:
            return graph.compile(checkpointer=MemorySaver())
        return graph.compile()

    def _normalize_context(self, state: EnterpriseAgentState) -> EnterpriseAgentState:
        state["selected_module"] = _normalize_module(state.get("selected_module"))
        state["client_state"] = dict(state.get("client_state") or {})
        _trace(
            state,
            "normalize_context",
            "ok",
            {
                "selected_module": state["selected_module"],
                "has_quote_context": bool(
                    state["client_state"].get("current_pricing_result")
                    or state["client_state"].get("last_price_result")
                    or state["client_state"].get("quote_history")
                ),
            },
        )
        return state

    def _classify_intent(self, state: EnterpriseAgentState) -> EnterpriseAgentState:
        result = self.intent_classifier.classify(
            message=state.get("message") or "",
            selected_module=state.get("selected_module") or "media_pricing",
            client_state=state.get("client_state") or {},
        )
        state["classifier_result"] = result
        _trace(
            state,
            "classify_intent",
            "ok",
            {
                "internal_intent": result.get("internal_intent"),
                "business_category": result.get("business_category"),
                "selected_module": result.get("selected_module"),
                "confidence": result.get("confidence"),
            },
        )
        return state

    def _guard_module(self, state: EnterpriseAgentState) -> EnterpriseAgentState:
        guarded = self.module_guard.guard(
            selected_business_module=state.get("selected_module") or "media_pricing",
            message=state.get("message") or "",
            classifier_result=state.get("classifier_result") or {},
            client_state=state.get("client_state") or {},
        )
        state["guarded_result"] = guarded
        state["intent_result"] = guarded.get("intent_result") or {}
        _trace(
            state,
            "guard_module",
            "ok",
            {
                "final_module": guarded.get("final_module"),
                "final_intent": guarded.get("final_intent"),
                "guard_reason": guarded.get("guard_reason"),
            },
        )
        return state

    def _build_task_contract(self, state: EnterpriseAgentState) -> EnterpriseAgentState:
        intent = state.get("intent_result") or {}
        task_family = _task_family(intent)
        module = intent.get("selected_module") or state.get("selected_module") or "media_pricing"
        quote_context = state.get("client_state") or {}
        has_quote = bool(
            quote_context.get("current_pricing_result")
            or quote_context.get("last_price_result")
            or quote_context.get("quote_history")
        )
        slots = intent.get("slots") or {}
        has_license_time = any(slots.get(key) not in (None, "") for key in ("first_license_date", "first_license_year", "reg_date"))
        complete_vehicle = (
            has_license_time
            and all(slots.get(key) not in (None, "") for key in ("series", "city", "mileage_wan_km", "transfer_count", "color"))
        )
        compound_allows_pricing = task_family in {"compound_market_task", "compound_pricing_task"} and complete_vehicle
        task_contract = {
            "schema": "enterprise_agent_task_contract_v2",
            "task_family": task_family,
            "module": module,
            "internal_intent": intent.get("internal_intent"),
            "business_category": intent.get("business_category"),
            "price_role": _price_role(intent),
            "slots": slots,
            "requires_quote_context": task_family == "pricing_explanation",
            "has_quote_context": has_quote,
            "allows_pricing_tool": (module == "media_pricing" and task_family in {"pricing_quote", "compound_pricing_task"}) or compound_allows_pricing,
            "allows_report_tool": task_family in {"daily_report", "compound_market_task", "compound_pricing_task"},
            "allows_market_tool": task_family in {"selection", "market_state", "market_report", "compound_market_task", "compound_pricing_task"},
            "forbidden_tools": [],
        }
        if module != "media_pricing" and not compound_allows_pricing:
            task_contract["forbidden_tools"].append("pricing_tool")
        if task_family == "pricing_explanation":
            task_contract["forbidden_tools"].append("pricing_tool_requote")
        if task_family in {"daily_report", "selection", "market_state", "market_report", "pricing_adjustment"}:
            task_contract["forbidden_tools"].append("vehicle_valuation_tool")
        state["task_contract"] = task_contract
        _trace(state, "build_task_contract", "ok", task_contract)
        return state

    def _build_tool_plan(self, state: EnterpriseAgentState) -> EnterpriseAgentState:
        contract = state.get("task_contract") or {}
        task_family = contract.get("task_family")
        module = contract.get("module")
        tool_name = "none"
        execution_mode = "clarify_or_reply"
        requires_fields = False
        read_only = False
        if task_family == "pricing_quote" and module == "media_pricing":
            tool_name = "price_quote_tool"
            execution_mode = "execute_when_slots_complete"
            requires_fields = True
        elif task_family == "pricing_explanation":
            tool_name = "quote_explanation_tool"
            execution_mode = "read_quote_context_only"
            read_only = True
        elif task_family == "daily_report":
            tool_name = "daily_report_tool"
            execution_mode = "read_or_render_report"
            read_only = True
        elif task_family == "selection":
            tool_name = "selection_strategy_tool"
            execution_mode = "execute_selection_contract"
            read_only = True
        elif task_family in {"market_state", "market_report"}:
            tool_name = "market_report_tool"
            execution_mode = "execute_market_report_contract"
            read_only = True
        elif task_family == "pricing_adjustment":
            tool_name = "pricing_adjustment_workflow_tool"
            execution_mode = "collect_adjustment_scope"
            read_only = True
        elif task_family == "general_automotive_qa":
            tool_name = "automotive_knowledge_tool"
            execution_mode = "answer_with_bounded_vehicle_knowledge"
            read_only = True
        elif task_family in {"compound_market_task", "compound_pricing_task"}:
            tool_name = "multi_tool_agent_workflow"
            execution_mode = "execute_contract_steps"
            requires_fields = task_family == "compound_pricing_task"
        tool_plan = {
            "schema": "enterprise_agent_tool_plan_v2",
            "tool_name": tool_name,
            "execution_mode": execution_mode,
            "requires_fields": requires_fields,
            "read_only": read_only,
            "device_agnostic": True,
            "api_contract_first": True,
            "mobile_app_reusable": True,
            "frontend_should_not_embed_business_logic": True,
        }
        state["tool_plan"] = tool_plan
        _trace(state, "build_tool_plan", "ok", tool_plan)
        return state

    @staticmethod
    def _route_after_policy(state: EnterpriseAgentState) -> str:
        family = str((state.get("task_contract") or {}).get("task_family") or "")
        if family == "general_automotive_qa":
            return "general_answer"
        if family == "daily_report":
            return "daily_report"
        if family == "selection":
            return "selection"
        if family in {"market_report", "market_state"}:
            return "market_report"
        if family in {"pricing_quote", "pricing_explanation", "pricing_adjustment"}:
            return "pricing"
        if family in {"compound_market_task", "compound_pricing_task"}:
            return "compound"
        return "information_collection"

    @staticmethod
    def _dispatch_node(route: str):
        def dispatch(state: EnterpriseAgentState) -> EnterpriseAgentState:
            state["execution_route"] = route
            _trace(
                state,
                f"dispatch_{route}",
                "ready",
                {
                    "tool_name": (state.get("tool_plan") or {}).get("tool_name"),
                    "task_family": (state.get("task_contract") or {}).get("task_family"),
                },
            )
            return state

        return dispatch

    def _validate_state_policy(self, state: EnterpriseAgentState) -> EnterpriseAgentState:
        intent = state.get("intent_result") or {}
        contract = state.get("task_contract") or {}
        task_family = contract.get("task_family")
        state_policy = {
            "schema": "enterprise_agent_state_policy_v2",
            "active_quote_reference": "latest_active_quote",
            "history_quote_reference": "allowed_by_explicit_reference",
            "must_not_reuse_previous_vehicle": False,
            "must_not_call_price": False,
            "must_not_overwrite_current_quote": False,
            "missing_fields_before_price": [],
            "quote_context_error": "",
        }
        if task_family in {"daily_report", "selection", "market_state", "market_report", "pricing_adjustment"}:
            state_policy["must_not_call_price"] = True
            state_policy["must_not_overwrite_current_quote"] = True
        if task_family == "compound_market_task" and not contract.get("allows_pricing_tool"):
            state_policy["must_not_call_price"] = True
            state_policy["must_not_overwrite_current_quote"] = True
        if intent.get("internal_intent") == RESET_VEHICLE:
            state_policy["must_not_reuse_previous_vehicle"] = True
            state_policy["must_not_call_price"] = True
        if task_family == "pricing_explanation":
            state_policy["must_not_call_price"] = True
            state_policy["must_not_overwrite_current_quote"] = True
            if not contract.get("has_quote_context"):
                state_policy["quote_context_error"] = "NO_ACTIVE_OR_HISTORY_QUOTE"
        if intent.get("internal_intent") in {"VEHICLE_INFO_ADD", "PRICE_QUOTE_REQUEST", SELL_CAR_VALUATION_INTENT}:
            slots = intent.get("slots") or {}
            if slots.get("brand") and not slots.get("series"):
                state_policy["must_not_reuse_previous_vehicle"] = True
        state["state_policy"] = state_policy
        _trace(state, "validate_state_policy", "ok", state_policy)
        return state
