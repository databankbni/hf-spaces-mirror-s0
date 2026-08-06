from __future__ import annotations

import copy
import json
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from .llm_client import Qwen3LocalClient, extract_json_object


SELECTION_ANSWER_PROMPT = """
你是企业二手车 Agent 的回答组织器。只输出 JSON：{"text": "..."}。

输入包含用户问题和已经由确定性业务工具计算出的标题、结论、证据、风险与下一步。
你的职责只是把这些事实组织成自然、直接、适合一线业务员阅读的中文回答。

硬约束：
- 第一段直接回答用户问题，不要说“收到”“即将分析”。
- 不得新增、改写或推导输入中不存在的数字、排名、分数、车型、城市和数据源。
- 不得把候选榜名次说成严格推荐榜名次。
- 不得把代理指标说成真实线索转化率。
- 不得把车系级选品结论说成某台车的确定收车价。
- 根据 answer_mode 改变表达：排名直接给名次；未上榜先说是否命中及原因；建议收不收先给动作；算法问题先说主公式和门控；证据问题列数据源。
- task_card/建议类回答必须同时包含：明确动作、至少一条输入中已有的具体业务证据、下一步动作；不能只说“观察”或“暂不建议”。
- 面向一线业务员表达，不出现 opportunity_score、business_score、confidence、gate、route、task_card 等内部字段名或英文术语。
- 最多 180 个中文字符，避免空话和重复。
""".strip()


class GroundedAgentAnswerService:
    _LOCK = threading.Lock()
    _CACHE: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
    _TTL_SECONDS = 15 * 60
    _MAX_ITEMS = 512

    def __init__(self, llm_client: Qwen3LocalClient | None = None) -> None:
        self.llm_client = llm_client or Qwen3LocalClient()

    def enhance_selection_answer(
        self,
        *,
        query: str,
        answer_mode: str,
        deterministic_answer: dict[str, Any],
    ) -> dict[str, Any]:
        base = copy.deepcopy(deterministic_answer or {})
        if not base:
            return base
        payload = {
            "task_type": "light_reply",
            "purpose": "grounded_selection_answer",
            "answer_mode": answer_mode,
            "user_question": str(query or ""),
            "facts": {
                "title": base.get("title"),
                "conclusion": base.get("conclusion"),
                "evidence": base.get("evidence") or [],
                "caveats": base.get("caveats") or [],
                "next_action": base.get("next_action"),
            },
        }
        key = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        cached = self._get_cached(key)
        if cached:
            base.update(cached)
            base["llm_cache_hit"] = True
            base["llm_latency_ms"] = 0
            return base
        result = self.llm_client.rewrite_reply(
            SELECTION_ANSWER_PROMPT,
            payload,
            task_type="light_reply",
            max_tokens=320,
            temperature=0.15,
        )
        if not result.ok:
            base.update(
                {
                    "llm_used": False,
                    "llm_model": result.model,
                    "llm_latency_ms": result.latency_ms,
                    "llm_degraded_reason": result.fallback_reason,
                }
            )
            return base
        parsed = extract_json_object(result.content) or {}
        text = str(parsed.get("text") or "").strip()
        if (
            not text
            or not self._numbers_are_grounded(text, payload)
            or not self._frontline_contract_ok(text, answer_mode)
        ):
            base.update(
                {
                    "llm_used": False,
                    "llm_model": result.model,
                    "llm_latency_ms": result.latency_ms,
                    "llm_degraded_reason": "grounded_answer_validator_rejected",
                }
            )
            return base
        enhancement = {
            "text": text,
            "llm_used": True,
            "llm_model": result.model,
            "llm_latency_ms": result.latency_ms,
            "llm_fallback_used": result.fallback_used,
            "llm_fallback_reason": result.fallback_reason,
        }
        self._put_cached(key, enhancement)
        base.update(enhancement)
        return base

    @staticmethod
    def _numbers_are_grounded(text: str, payload: dict[str, Any]) -> bool:
        facts_text = json.dumps(payload.get("facts") or {}, ensure_ascii=False, default=str)
        output_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", text))
        fact_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", facts_text))
        return output_numbers.issubset(fact_numbers)

    @staticmethod
    def _frontline_contract_ok(text: str, answer_mode: str) -> bool:
        """Reject fluent rewrites that drop the business answer contract."""

        if re.search(
            r"opportunity_score|business_score|confidence|task_card|selection_|\bgate\b|\broute\b",
            text,
            flags=re.I,
        ):
            return False
        if answer_mode == "task_card":
            return bool(
                re.search(r"建议|不建议|可收|暂不|优先|观察", text)
                and re.search(r"\d", text)
                and re.search(r"下一步|先|再|补齐|找到|跟进", text)
            )
        return True

    @classmethod
    def _get_cached(cls, key: str) -> dict[str, Any] | None:
        now = time.time()
        with cls._LOCK:
            item = cls._CACHE.get(key)
            if not item:
                return None
            created_at, value = item
            if now - created_at > cls._TTL_SECONDS:
                cls._CACHE.pop(key, None)
                return None
            cls._CACHE.move_to_end(key)
            return copy.deepcopy(value)

    @classmethod
    def _put_cached(cls, key: str, value: dict[str, Any]) -> None:
        with cls._LOCK:
            cls._CACHE[key] = (time.time(), copy.deepcopy(value))
            cls._CACHE.move_to_end(key)
            while len(cls._CACHE) > cls._MAX_ITEMS:
                cls._CACHE.popitem(last=False)


_SERVICE: GroundedAgentAnswerService | None = None


def get_grounded_agent_answer_service() -> GroundedAgentAnswerService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = GroundedAgentAnswerService()
    return _SERVICE
