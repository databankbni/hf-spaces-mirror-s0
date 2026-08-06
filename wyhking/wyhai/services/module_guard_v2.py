from __future__ import annotations

from typing import Any, Dict

from .intent_schema_v2 import SUPPORTED_MODULES, validate_intent_result


class ModuleGuardV2:
    """Enforce module ownership after classification.

    Explicit module switches are the only operation allowed to leave the
    selected module.  Vehicle words alone never move a daily-report or market
    conversation into pricing.
    """

    def guard(
        self,
        *,
        selected_business_module: str,
        message: str,
        classifier_result: Dict[str, Any],
        client_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        selected = selected_business_module if selected_business_module in SUPPORTED_MODULES else "media_pricing"
        result = dict(classifier_result)
        if result.get("internal_intent") == "MODULE_SWITCH":
            target = result.get("target_module")
            if target not in SUPPORTED_MODULES:
                target = selected
            result["selected_module"] = target
            reason = f"explicit module switch: {selected} -> {target}"
        elif result.get("explicit_cross_module_intent") and result.get("selected_module") in SUPPORTED_MODULES:
            reason = f"explicit business intent route: {selected} -> {result['selected_module']}"
        else:
            result["selected_module"] = selected
            reason = f"{selected} module overrides generic cross-module interpretation"

        if result["selected_module"] in {"daily_report", "market_state"}:
            result["should_call_pricing"] = False
            result["should_invalidate_quote"] = False
        validate_intent_result(result)
        return {
            "final_module": result["selected_module"],
            "final_intent": result["internal_intent"],
            "guard_reason": reason,
            "intent_result": result,
        }
