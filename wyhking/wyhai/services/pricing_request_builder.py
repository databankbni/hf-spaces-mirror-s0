from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List

from .geo_resolver import resolve_city
from .interaction_state import hash_price_request
from .vehicle_slot_extractor_v2 import COMMON_CITIES


class PricingRequestBuilder:
    REQUIRED_FIELDS = ["city", "mileage_wan_km", "transfer_count", "color"]
    COLOR_TOKENS = (
        "白", "黑", "灰", "银", "红", "蓝", "绿", "棕", "咖啡", "橙", "香槟",
        "金", "米", "黄", "紫", "其他",
    )
    COLOR_TOKENS_EN = (
        "white", "black", "gray", "grey", "silver", "red", "blue", "green",
        "brown", "orange", "gold", "beige", "yellow", "purple",
    )

    @staticmethod
    def _clean_identity_text(value: Any) -> str:
        text = str(value or "").strip()
        patterns = [
            r"[，,、]?\s*(?:19|20)\d{2}\s*[-/.]\s*\d{1,2}(?:\s*[-/.]\s*\d{1,2})?\s*(?:上牌|登记|落户)?",
            r"[，,、]?\s*(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?\s*(?:上牌|登记|落户)?",
            r"[，,、]?\s*-?\s*(?:0?[1-9]|1[0-2])\s*月?\s*(?:上牌|登记|落户)",
            r"[，,、]?\s*\d+(?:\.\d+)?\s*万\s*公里",
            r"[，,、]?\s*\d+(?:\.\d+)?\s*公里",
            r"[，,、]?\s*\d+\s*次\s*过户",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text)
        return re.sub(r"\s+", " ", text).strip(" ，,、;；")

    @staticmethod
    def _first_license_parts(slots: Dict[str, Any]) -> tuple[Any, Any, str]:
        raw_date = str(slots.get("first_license_date") or slots.get("reg_date") or "").strip()
        year = slots.get("first_license_year")
        month = slots.get("first_license_month")
        day = None
        if raw_date:
            parts = raw_date.replace("/", "-").split("-")
            if not year and parts and parts[0].isdigit():
                year = int(parts[0])
            if not month and len(parts) > 1 and parts[1].isdigit():
                month = int(parts[1])
            if len(parts) > 2 and parts[2].isdigit():
                day = max(1, min(31, int(parts[2])))
        if month not in (None, ""):
            try:
                month = max(1, min(12, int(month)))
            except Exception:
                month = None
        reg_date = ""
        if year not in (None, ""):
            reg_date = f"{int(year)}-{int(month or 1):02d}"
            if day is not None:
                reg_date = f"{reg_date}-{day:02d}"
        return year, month, reg_date

    @staticmethod
    def _validation_errors(
        slots: Dict[str, Any],
        vehicle_match: Dict[str, Any],
    ) -> Dict[str, str]:
        errors: Dict[str, str] = {}
        now = datetime.now()
        license_year, license_month, _ = PricingRequestBuilder._first_license_parts(slots)
        try:
            if license_year not in (None, ""):
                year = int(license_year)
                month = int(license_month or 1)
                if year > now.year or (year == now.year and month > now.month):
                    errors["first_license_date"] = "上牌时间不能晚于当前月份"
                elif year < 1980:
                    errors["first_license_date"] = "上牌年份不在合理范围内"
        except (TypeError, ValueError):
            errors["first_license_date"] = "上牌时间格式无效"

        model_year = slots.get("model_year") or vehicle_match.get("model_year")
        try:
            if model_year not in (None, "") and int(float(model_year)) > now.year + 1:
                errors["model_year"] = "款型年份不能明显晚于当前年份"
        except (TypeError, ValueError):
            errors["model_year"] = "款型年份格式无效"

        city = str(slots.get("city") or "").strip()
        if city and resolve_city(city, COMMON_CITIES) is None:
            errors["city"] = "暂不支持该城市；请选择国内已支持城市后再估价"

        color = str(slots.get("color") or "").strip()
        normalized_color = color.lower()
        if color and not (
            any(token in color for token in PricingRequestBuilder.COLOR_TOKENS)
            or any(token in normalized_color for token in PricingRequestBuilder.COLOR_TOKENS_EN)
        ):
            errors["color"] = "颜色无法识别；请填写真实车身颜色，例如白色、黑色、灰色或蓝色"

        for field, label in (("mileage_wan_km", "里程"), ("transfer_count", "过户次数")):
            value = slots.get(field)
            if value in (None, ""):
                continue
            try:
                if float(value) < 0:
                    errors[field] = f"{label}不能为负数"
            except (TypeError, ValueError):
                errors[field] = f"{label}格式无效"
        return errors

    def missing_fields(self, slots: Dict[str, Any], vehicle_match: Dict[str, Any], task: str) -> List[str]:
        missing: List[str] = []
        has_structured_vehicle = bool(
            vehicle_match.get("model_id")
            or vehicle_match.get("model_name")
            or slots.get("standard_vehicle")
            or slots.get("raw_vehicle_text")
            or slots.get("trim")
        )
        if not ((slots.get("brand") or vehicle_match.get("brand_name")) and (slots.get("series") or vehicle_match.get("series_name"))) and not has_structured_vehicle:
            missing.append("series")
        license_year, _, _ = self._first_license_parts(slots)
        if not license_year:
            missing.append("first_license_date")
        for field in self.REQUIRED_FIELDS:
            value = slots.get(field)
            if value is None or value == "":
                missing.append(field)
        # 车况允许不填：线上无法替用户完成实车检测。未填写时由 build()
        # 明确标成“系统默认良好、未检测”，继续报价但降低执行置信度。
        if task not in {"C2B", "B2C", "BOTH"}:
            missing.append("task")
        user_confirmed_vehicle = bool(
            slots.get("trim")
            or (
                vehicle_match.get("matched")
                and not vehicle_match.get("need_manual_confirm")
                and (vehicle_match.get("model_id") or vehicle_match.get("model_name"))
            )
        )
        if (not vehicle_match.get("matched") or vehicle_match.get("need_manual_confirm")) and not user_confirmed_vehicle:
            if "vehicle_confirm" not in missing:
                missing.append("vehicle_confirm")
        return missing

    def build(self, slots: Dict[str, Any], vehicle_match: Dict[str, Any], task: str, session_id: str) -> Dict[str, Any]:
        city = str(slots.get("city") or "").strip()
        city_resolution = resolve_city(city, COMMON_CITIES) if city else None
        if city_resolution:
            slots["city"] = city_resolution.city
        explicit_condition = bool(
            slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition")
        )
        if not explicit_condition:
            slots["condition_group"] = "B"
            slots["inspection_grade"] = "B"
            slots["condition"] = "系统默认良好车况（未检测）"
            slots["condition_is_default"] = True
        else:
            slots["condition_is_default"] = False
        missing = self.missing_fields(slots, vehicle_match, task)
        validation_errors = self._validation_errors(slots, vehicle_match)
        should_call = not missing and not validation_errors
        vehicle_model_year = slots.get("model_year") or vehicle_match.get("model_year")
        trim_text = self._clean_identity_text(
            slots.get("trim")
            or slots.get("standard_vehicle")
            or slots.get("raw_vehicle_text")
            or vehicle_match.get("model_name")
            or ""
        )
        fallback_model_name = " ".join(str(x) for x in [slots.get("brand") or vehicle_match.get("brand_name") or "", slots.get("series") or vehicle_match.get("series_name") or "", trim_text] if x).strip()
        fallback_model_name = self._clean_identity_text(fallback_model_name)
        license_year, license_month, reg_date = self._first_license_parts(slots)
        price_request = {
            "modelId": vehicle_match.get("model_id") or "",
            "standardModelId": vehicle_match.get("model_id") or "",
            "brand": vehicle_match.get("brand_name") or slots.get("brand") or "",
            "series": vehicle_match.get("series_name") or slots.get("series") or "",
            "model": vehicle_match.get("model_name") or fallback_model_name or slots.get("series") or "",
            "modelName": vehicle_match.get("model_name") or fallback_model_name or slots.get("series") or "",
            "trim": trim_text,
            "rawModelText": self._clean_identity_text(slots.get("raw_vehicle_text") or slots.get("standard_vehicle") or fallback_model_name or ""),
            "modelYear": str(vehicle_model_year or ""),
            "model_year": str(vehicle_model_year or ""),
            "vehicle_model_year": str(vehicle_model_year or ""),
            "firstLicenseYear": str(license_year or ""),
            "firstLicenseMonth": str(license_month or ""),
            "firstLicenseDate": reg_date,
            "licenseYear": str(license_year or ""),
            "regDate": reg_date,
            "reg_date": reg_date,
            "mileage": slots.get("mileage_wan_km"),
            "transfer": slots.get("transfer_count"),
            "color": slots.get("color") or "",
            "condition_grade": slots.get("condition_group") or slots.get("inspection_grade") or "",
            "inspection_grade": slots.get("condition_group") or slots.get("inspection_grade") or "",
            "condition": slots.get("condition") or "",
            "condition_is_default": bool(slots.get("condition_is_default")),
            "city": slots.get("city") or "",
            "sessionId": session_id,
            "businessIntent": "MEDIA_PRICING",
            "is_custom_model": not bool(vehicle_match.get("model_id")),
            "catalogSource": vehicle_match.get("catalog_source") or "",
            "catalogSourceUrl": vehicle_match.get("catalog_source_url") or "",
            "catalogCoverageLevel": vehicle_match.get("catalog_coverage_level") or "",
            "catalogOfficialPriceMin": vehicle_match.get("official_price_min"),
            "catalogOfficialPriceMax": vehicle_match.get("official_price_max"),
            "task": task.lower() if task in {"C2B", "B2C"} else "both",
        }
        return {
            "should_call_price": should_call,
            "price_request": price_request if should_call else {},
            "missing_fields": missing,
            "validation_errors": validation_errors,
            "price_request_hash": hash_price_request(price_request) if should_call else "",
        }
