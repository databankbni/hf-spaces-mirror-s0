from __future__ import annotations

import base64
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SECTION_ALIASES = {
    "new_car": ("新车发布", "新车上市", "预售", "改款"),
    "discount": ("新车降价", "降价", "优惠", "促销", "价格战"),
    "policy": ("政策速递", "政策", "补贴", "以旧换新", "法规"),
    "industry_data": ("行情数据", "二手车市场", "成交", "上架", "库存", "周转"),
    "industry_news": ("行业动态", "车企动态", "行业新闻"),
    "suggestion": ("经营建议", "业务建议", "收车策略", "库存管理"),
}


@dataclass(frozen=True)
class ReportDocument:
    report_date: str
    filename: str
    text: str
    pages: list[str]
    sections: dict[str, list[str]]
    source_path: str


class DailyReportContentService:
    """Read uploaded reports into an auditable, date-bound retrieval context."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1]
        self.cache_dir = self.root / "data" / "runtime" / "daily_report_content_cache"

    def load(self, report_date: str) -> ReportDocument | None:
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", str(report_date or "")):
            return None
        source = self._find_report_file(report_date)
        if source is None:
            return None
        stat = source.stat()
        cache = self.cache_dir / f"{report_date}.json"
        if cache.exists():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                if payload.get("source_mtime_ns") == stat.st_mtime_ns and payload.get("source_size") == stat.st_size:
                    return self._from_payload(payload)
            except (OSError, ValueError, TypeError):
                pass
        pages = self._extract_pages(source)
        if not pages:
            return None
        text = "\n\n".join(pages)
        sections = self._build_sections(pages)
        payload = {
            "report_date": report_date,
            "filename": source.name.removesuffix(".b64"),
            "source_path": str(source.relative_to(self.root)),
            "source_mtime_ns": stat.st_mtime_ns,
            "source_size": stat.st_size,
            "pages": pages,
            "text": text,
            "sections": sections,
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return self._from_payload(payload)

    def available_dates(self) -> list[str]:
        dates: set[str] = set()
        for directory in (self.root / "uploaded_reports", self.root / "outputs"):
            if not directory.is_dir():
                continue
            for path in directory.iterdir():
                match = re.search(r"daily_report_(20\d{2}-\d{2}-\d{2})\.pdf(?:\.b64)?$", path.name)
                if match and path.is_file():
                    dates.add(match.group(1))
        return sorted(dates, reverse=True)

    def latest_date(self) -> str | None:
        dates = self.available_dates()
        return dates[0] if dates else None

    def latest_card_payload(self) -> dict[str, Any] | None:
        report_date = self.latest_date()
        return self.card_payload(report_date) if report_date else None

    def card_payload(self, report_date: str) -> dict[str, Any] | None:
        document = self.load(report_date)
        if document is None:
            return None
        curated = self._curated_digest(report_date)
        if curated:
            new_car = curated.get("new_car") if isinstance(curated.get("new_car"), list) else []
            summaries = [
                {"key": "new_car", "title": "新车事件", "summary": "；".join(str(item) for item in new_car) or "当日没有可核验的新车事件。", "evidence_count": len(new_car)},
                {"key": "discount", "title": "新车降价", "summary": str(curated.get("discount") or "当日没有新的可用降价榜结构化结果。"), "evidence_count": 1},
                {"key": "policy", "title": "政策速递", "summary": str(curated.get("policy") or "日报未检索到明确政策变化。"), "evidence_count": 1},
                {"key": "industry_news", "title": "行业动态", "summary": str(curated.get("industry") or "日报未检索到明确行业事件。"), "evidence_count": 1},
                {"key": "industry_data", "title": "行情数据", "summary": str(curated.get("market") or "月度数据仅用于全国方向校验。"), "evidence_count": 1},
            ]
            return {
                "report_date": document.report_date,
                "filename": document.filename,
                "source_path": document.source_path,
                "page_count": len(document.pages),
                "data_range": curated.get("window"),
                "core_conclusions": [
                    "新车事件用于判断旧款残值与客户比价锚点，不直接改写单车收车价。",
                    str(curated.get("policy") or "").strip(),
                    "月度行情、当日事件和内部经营信号分开使用，避免把不同周期数据混为实时行情。",
                ],
                "sections": summaries,
                "is_generated": False,
                "source_type": "uploaded_report_curated",
                "privacy_level": "desensitized",
                "source_label": str(curated.get("source_label") or "汽车行业每日采集·最新脱敏版"),
            }
        summaries = []
        for key, title in (
            ("new_car", "新车发布"),
            ("discount", "新车降价"),
            ("policy", "政策速递"),
            ("industry_data", "行情数据"),
            ("industry_news", "行业动态"),
        ):
            excerpts = document.sections.get(key) or []
            summaries.append({
                "key": key,
                "title": title,
                "summary": self._clean_excerpt(excerpts[0] if excerpts else "原文未检索到明确条目。", 260),
                "evidence_count": len(excerpts),
            })
        return {
            "report_date": document.report_date,
            "filename": document.filename,
            "source_path": document.source_path,
            "page_count": len(document.pages),
            "core_conclusions": self._core_conclusions(document),
            "sections": summaries,
            "is_generated": False,
            "source_type": "uploaded_report_extracted",
            "privacy_level": "desensitized",
            "source_label": "汽车行业每日采集·最新脱敏版",
        }

    def _curated_digest(self, report_date: str) -> dict[str, Any]:
        metadata = self.root / "uploaded_reports" / f"national_market_{report_date}.json"
        if not metadata.exists():
            return {}
        try:
            payload = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        digest = payload.get("daily_digest")
        return digest if isinstance(digest, dict) else {}

    def retrieve(self, report_date: str, query: str, section: str | None = None, limit: int = 6) -> list[dict[str, Any]]:
        document = self.load(report_date)
        if document is None:
            return []
        candidates: list[tuple[int, int, str]] = []
        query_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9.+%-]+", str(query or "")))
        section_terms = set(SECTION_ALIASES.get(section or "", ()))
        for page_no, page in enumerate(document.pages, start=1):
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n|(?<=[。！？])\s+", page) if len(part.strip()) >= 12]
            for paragraph in paragraphs:
                score = sum(3 for term in query_terms if term in paragraph)
                score += sum(4 for term in section_terms if term in paragraph)
                if score:
                    candidates.append((score, page_no, paragraph))
        candidates.sort(key=lambda item: (-item[0], item[1], len(item[2])))
        seen: set[str] = set()
        rows = []
        for score, page_no, paragraph in candidates:
            fingerprint = re.sub(r"\s+", "", paragraph)[:160]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append({"page": page_no, "score": score, "text": self._clean_excerpt(paragraph, 900)})
            if len(rows) >= limit:
                break
        return rows

    def _find_report_file(self, report_date: str) -> Path | None:
        names = [f"daily_report_{report_date}.pdf", f"daily_report_{report_date}.pdf.b64"]
        for directory in (self.root / "uploaded_reports", self.root / "outputs"):
            for name in names:
                path = directory / name
                if path.exists() and path.is_file():
                    return path
        return None

    @staticmethod
    def _extract_pages(source: Path) -> list[str]:
        try:
            from pypdf import PdfReader
        except ImportError:
            return []
        data_path = source
        temporary: Path | None = None
        if source.suffix == ".b64":
            try:
                decoded = base64.b64decode(source.read_text(encoding="utf-8"))
                handle = tempfile.NamedTemporaryFile(prefix="daily-report-", suffix=".pdf", delete=False)
                handle.write(decoded)
                handle.close()
                temporary = Path(handle.name)
                data_path = temporary
            except (OSError, ValueError):
                return []
        try:
            reader = PdfReader(str(data_path))
            pages = [DailyReportContentService._normalize_text(page.extract_text() or "") for page in reader.pages]
            return [page for page in pages if page.strip()]
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        replacements = {"⽇": "日", "⻋": "车", "⽉": "月", "⾄": "至", "⼆": "二", "⼀": "一", "⾼": "高", "⾏": "行", "⻘": "青"}
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"懂车帝(?:\s+懂车帝){1,}", "", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _build_sections(pages: list[str]) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
        for page in pages:
            for key, aliases in SECTION_ALIASES.items():
                if any(alias in page for alias in aliases):
                    sections[key].append(page)
        return sections

    @staticmethod
    def _clean_excerpt(text: str, limit: int) -> str:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"

    def _core_conclusions(self, document: ReportDocument) -> list[str]:
        first = document.pages[0] if document.pages else ""
        conclusions = []
        for marker in ("今日必读", "政策速递", "行情数据"):
            match = re.search(rf"{marker}.{{0,260}}", first, flags=re.S)
            if match:
                conclusions.append(self._clean_excerpt(match.group(0), 220))
        return conclusions[:3] or [f"已读取 {document.report_date} 上传日报原文，共 {len(document.pages)} 页。"]

    @staticmethod
    def _from_payload(payload: dict[str, Any]) -> ReportDocument:
        return ReportDocument(
            report_date=str(payload.get("report_date") or ""),
            filename=str(payload.get("filename") or ""),
            text=str(payload.get("text") or ""),
            pages=list(payload.get("pages") or []),
            sections={str(k): list(v or []) for k, v in (payload.get("sections") or {}).items()},
            source_path=str(payload.get("source_path") or ""),
        )
