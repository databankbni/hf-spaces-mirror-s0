from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Mapping, Optional


class ToolContractError(ValueError):
    """Raised when a planned enterprise tool cannot accept the supplied input."""


@dataclass(frozen=True)
class ToolInputContract:
    properties: Mapping[str, str]
    required: tuple[str, ...] = ()
    defaults: Mapping[str, Any] | None = None
    max_lengths: Mapping[str, int] | None = None

    def validate(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        raw = dict(payload or {})
        unknown = sorted(set(raw) - set(self.properties))
        if unknown:
            raise ToolContractError(f"unexpected fields: {unknown}")
        result = dict(self.defaults or {})
        result.update(raw)
        missing = [field for field in self.required if result.get(field) in (None, "")]
        if missing:
            raise ToolContractError(f"missing required fields: {missing}")
        for field, expected in self.properties.items():
            value = result.get(field)
            if value is None:
                continue
            if expected == "string" and not isinstance(value, str):
                raise ToolContractError(f"{field} must be string")
            if expected == "object" and not isinstance(value, dict):
                raise ToolContractError(f"{field} must be object")
            limit = int((self.max_lengths or {}).get(field) or 0)
            if limit and isinstance(value, str) and len(value) > limit:
                raise ToolContractError(f"{field} exceeds {limit} characters")
        return result

    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                key: {"type": value}
                for key, value in self.properties.items()
            },
            "required": list(self.required),
            "additionalProperties": False,
        }


SelectionToolInput = ToolInputContract(
    properties={"query_text": "string", "selected_city": "string", "client_state": "object"},
    required=("query_text",),
    defaults={"selected_city": "全国", "client_state": {}},
    max_lengths={"query_text": 500, "selected_city": 30},
)
MarketReportToolInput = SelectionToolInput
AutomotiveKnowledgeToolInput = ToolInputContract(
    properties={"user_message": "string", "intent_v2": "object", "client_state": "object"},
    required=("user_message",),
    defaults={"intent_v2": {}, "client_state": {}},
    max_lengths={"user_message": 500},
)
DailyReportToolInput = ToolInputContract(
    properties={"message": "string", "intent_v2": "object", "daily_report_context": "object"},
    defaults={"message": "", "intent_v2": {}, "daily_report_context": {}},
    max_lengths={"message": 500},
)
PriceQuoteToolInput = ToolInputContract(
    properties={"price_request": "object", "slots": "object", "client_state": "object", "task_id": "string"},
    required=("price_request", "slots", "task_id"),
    defaults={"client_state": {}},
    max_lengths={"task_id": 100},
)


@dataclass(frozen=True)
class EnterpriseToolDefinition:
    name: str
    description: str
    input_model: ToolInputContract
    handler: Callable[..., Dict[str, Any]]
    output_contract: str
    read_only: bool = True


class EnterpriseToolRegistry:
    """Schema-first registry for business tools selected by the agent graph.

    The registry is deliberately independent from the UI and intent rules.  The
    graph chooses a tool name, this registry validates the exact payload and
    invokes one registered capability.  This makes an invalid plan fail loudly
    instead of silently falling through to another page's workflow.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, EnterpriseToolDefinition] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        input_model: ToolInputContract,
        handler: Callable[..., Dict[str, Any]],
        output_contract: str,
        read_only: bool = True,
    ) -> None:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ToolContractError("tool name is required")
        self._tools[clean_name] = EnterpriseToolDefinition(
            name=clean_name,
            description=str(description or "").strip(),
            input_model=input_model,
            handler=handler,
            output_contract=str(output_contract or "dict"),
            read_only=bool(read_only),
        )

    def definitions(self) -> Iterable[EnterpriseToolDefinition]:
        return tuple(self._tools.values())

    def manifest(self) -> Dict[str, Dict[str, Any]]:
        return {
            item.name: {
                "name": item.name,
                "description": item.description,
                "input_schema": item.input_model.json_schema(),
                "output_contract": item.output_contract,
                "read_only": item.read_only,
            }
            for item in self.definitions()
        }

    def invoke(
        self,
        tool_name: str,
        payload: Mapping[str, Any],
        *,
        runtime: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        definition = self._tools.get(str(tool_name or "").strip())
        if definition is None:
            raise ToolContractError(f"unregistered enterprise tool: {tool_name}")
        validated = definition.input_model.validate(dict(payload or {}))

        started_at = datetime.now().isoformat(timespec="milliseconds")
        output = definition.handler(
            **validated,
            **dict(runtime or {}),
        )
        if not isinstance(output, dict):
            raise ToolContractError(
                f"{definition.name} violated {definition.output_contract}: expected object"
            )
        return {
            "tool_name": definition.name,
            "status": "completed",
            "input": validated,
            "output": output,
            "output_contract": definition.output_contract,
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(timespec="milliseconds"),
        }


def build_default_tool_registry(
    *,
    selection_handler: Callable[..., Dict[str, Any]],
    market_handler: Callable[..., Dict[str, Any]],
    knowledge_handler: Callable[..., Dict[str, Any]],
    daily_report_handler: Callable[..., Dict[str, Any]],
    pricing_handler: Callable[..., Dict[str, Any]],
) -> EnterpriseToolRegistry:
    registry = EnterpriseToolRegistry()
    registry.register(
        name="selection_strategy_tool",
        description="按任意预算、城市、品牌属性、能源细分和车身分类生成动态候选集并运行选品策略。",
        input_model=SelectionToolInput,
        handler=selection_handler,
        output_contract="selection_strategy_response_v2",
    )
    registry.register(
        name="market_report_tool",
        description="读取与问题相关的车型、城市或价格带行情证据并生成经营结论。",
        input_model=MarketReportToolInput,
        handler=market_handler,
        output_contract="market_report_response_v2",
    )
    registry.register(
        name="automotive_knowledge_tool",
        description="回答车型身份和二手车业务知识问题，不触发选品或定价。",
        input_model=AutomotiveKnowledgeToolInput,
        handler=knowledge_handler,
        output_contract="automotive_knowledge_answer_v2",
    )
    registry.register(
        name="daily_report_tool",
        description="检索指定行业日报的原文事实并区分事实与建议。",
        input_model=DailyReportToolInput,
        handler=daily_report_handler,
        output_contract="daily_report_answer_v2",
    )
    registry.register(
        name="price_quote_tool",
        description="只在标准车型和七要素满足合同时调用定价模型链路。",
        input_model=PriceQuoteToolInput,
        handler=pricing_handler,
        output_contract="enterprise_price_quote_v2",
        read_only=False,
    )
    return registry
