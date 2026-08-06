from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, Iterable, List, Tuple

from .feedback_schema import FeedbackRecord, ReflectionMemory, ReflectionScope


class ReflectionStore:
    def __init__(self, base_dir: str | None = None) -> None:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.base_dir = base_dir or os.environ.get("REFLEXION_DIR") or os.path.join(root, "data", "reflexion")
        os.makedirs(self.base_dir, exist_ok=True)
        self.feedback_path = os.path.join(self.base_dir, "feedback.jsonl")
        self.reflection_path = os.path.join(self.base_dir, "reflections.jsonl")

    def save_feedback(self, feedback: FeedbackRecord) -> Dict[str, Any]:
        record = feedback.to_dict()
        self._append(self.feedback_path, record)
        return record

    def save_reflection(self, reflection: ReflectionMemory) -> Dict[str, Any]:
        record = reflection.to_dict()
        self._append(self.reflection_path, record)
        return record

    def list_feedback(self, filters: Dict[str, Any] | None = None, limit: int = 500) -> List[Dict[str, Any]]:
        return self._filter(self._read(self.feedback_path), filters or {}, limit)

    def list_reflections(self, filters: Dict[str, Any] | None = None, limit: int = 500) -> List[Dict[str, Any]]:
        return self._filter(self._read(self.reflection_path), filters or {}, limit)

    def retrieve_reflections(self, context: Dict[str, Any], top_k: int = 5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        active_records = self.list_reflections(limit=0)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        ignored: List[Dict[str, Any]] = []
        for record in active_records:
            ok, reason = self._eligible(record, context)
            if not ok:
                ignored.append({"reflection_id": record.get("reflection_id"), "reason": reason})
                continue
            score = self._score(record, context)
            if score <= 0:
                ignored.append({"reflection_id": record.get("reflection_id"), "reason": "相似度不足"})
                continue
            scored.append((score, record))
        scored.sort(key=lambda pair: (-pair[0], pair[1].get("created_at") or ""))
        selected = []
        for score, record in scored[:top_k]:
            selected.append({**record, "match_score": round(score, 3)})
        return selected, ignored[:20]

    def disable_reflection(self, reflection_id: str) -> bool:
        records = self._read(self.reflection_path)
        changed = False
        for record in records:
            if record.get("reflection_id") == reflection_id:
                record["is_active"] = False
                changed = True
        if changed:
            self._rewrite(self.reflection_path, records)
        return changed

    def export_feedback_jsonl(self) -> str:
        return "\n".join(json.dumps(item, ensure_ascii=False) for item in self._read(self.feedback_path)) + "\n"

    def export_feedback_csv(self) -> str:
        records = self._read(self.feedback_path)
        output = StringIO()
        fieldnames = [
            "created_at", "feedback_id", "module", "task_type", "trace_id", "task_id",
            "brand", "series", "city", "tags", "business_outcome", "comment",
            "purchase_price", "purchase_price_upper", "sale_price",
            "adopted_purchase_price", "adopted_sale_price", "actual_reconditioning_cost",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            slots = record.get("vehicle_slots") if isinstance(record.get("vehicle_slots"), dict) else {}
            writer.writerow({
                "created_at": record.get("created_at", ""),
                "feedback_id": record.get("feedback_id", ""),
                "module": record.get("module", ""),
                "task_type": record.get("task_type", ""),
                "trace_id": record.get("trace_id", ""),
                "task_id": record.get("task_id", ""),
                "brand": slots.get("brand", ""),
                "series": slots.get("series", ""),
                "city": slots.get("city", ""),
                "tags": "、".join(record.get("tags") or []),
                "business_outcome": record.get("business_outcome", ""),
                "comment": record.get("comment", ""),
                "purchase_price": record.get("purchase_price", ""),
                "purchase_price_upper": record.get("purchase_price_upper", ""),
                "sale_price": record.get("sale_price", ""),
                "adopted_purchase_price": record.get("adopted_purchase_price", ""),
                "adopted_sale_price": record.get("adopted_sale_price", ""),
                "actual_reconditioning_cost": record.get("actual_reconditioning_cost", ""),
            })
        return output.getvalue()

    def _eligible(self, record: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        if not record.get("is_active", True):
            return False, "已禁用"
        if self._expired(record):
            return False, "已过期"
        if record.get("module") and context.get("module") and record.get("module") != context.get("module"):
            return False, "模块不同"
        if record.get("task_type") and context.get("task_type") and record.get("task_type") != context.get("task_type"):
            return False, "任务不同"
        scope = record.get("scope")
        if record.get("series") and context.get("series") and record.get("series") != context.get("series"):
            return False, "车系不同"
        if record.get("brand") and context.get("brand") and record.get("brand") != context.get("brand"):
            return False, "品牌不同"
        if scope == ReflectionScope.CITY_SERIES.value and record.get("city") and context.get("city") and record.get("city") != context.get("city"):
            return False, "城市不同"
        return True, ""

    def _score(self, record: Dict[str, Any], context: Dict[str, Any]) -> float:
        score = 0.0
        if record.get("module") == context.get("module"):
            score += 2.0
        if record.get("task_type") == context.get("task_type"):
            score += 2.0
        if record.get("brand") and record.get("brand") == context.get("brand"):
            score += 1.5
        if record.get("series") and record.get("series") == context.get("series"):
            score += 3.0
        if record.get("city") and record.get("city") == context.get("city"):
            score += 1.5
        if record.get("price_band") and record.get("price_band") == context.get("price_band"):
            score += 1.0
        if set(record.get("tags") or []).intersection(set(context.get("tags") or [])):
            score += 1.0
        score += min(float(record.get("confidence") or 0.5), 1.0)
        return score

    def _expired(self, record: Dict[str, Any]) -> bool:
        created_at = str(record.get("created_at") or "")
        if not created_at:
            return False
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            return False
        if created.tzinfo:
            created = created.replace(tzinfo=None)
        return datetime.now() > created + timedelta(days=int(record.get("decay_days") or 30))

    def _filter(self, records: List[Dict[str, Any]], filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        kept = []
        for record in records:
            ok = True
            for key in ("module", "task_type", "city", "brand", "series", "scope", "business_outcome"):
                expected = filters.get(key)
                if expected and str(record.get(key) or "") != str(expected):
                    ok = False
                    break
            tag = filters.get("tag")
            if ok and tag and str(tag) not in [str(item) for item in (record.get("tags") or [])]:
                ok = False
            if ok:
                kept.append(record)
        kept.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return kept[:limit] if limit else kept

    def _read(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        return records

    def _append(self, path: str, record: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _rewrite(self, path: str, records: Iterable[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
