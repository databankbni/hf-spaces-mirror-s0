from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .business_market_workbook_loader import normalize_text


ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_DIR = ROOT / "runtime" / "selection_taxonomy"
DEFAULT_TAXONOMY_INDEX = TAXONOMY_DIR / "selection_vehicle_taxonomy_index.csv"
DEFAULT_RANKING_SIGNALS = ROOT / "data" / "external" / "dongchedi_rankings" / "current" / "normalized_ranking_signals.csv"
DEFAULT_RAW_RANKING = ROOT / "data" / "external" / "dongchedi_rankings" / "current" / "raw_ranking_records.csv"
TRAINING_GLOB = "训练1*90天*.csv"

SELECTION_FILTERS = ("全部", "轿车", "SUV", "MPV", "新能源")
BODY_FILTERS = {"轿车", "SUV", "MPV"}
OTHER_BODY_TYPES = {"其他"}
NON_PASSENGER_CATEGORIES = {"皮卡", "轻客", "微卡", "微面", "卡车", "客车", "房车"}
DETAILED_VEHICLE_CATEGORIES = {"轿车", "SUV", "MPV", "皮卡", "微面", "轻客", "微卡"}
ENERGY_SUBTYPES = {"燃油", "新能源", "纯电", "插混", "增程"}
MANUFACTURER_ATTRIBUTES = {"自主", "合资", "豪华", "进口"}
LEGACY_FILTER_MAP = {
    "总计": "全部",
    "综合新能源": "新能源",
    "新能源": "新能源",
    "电车": "新能源",
    "纯电": "新能源",
    "插混": "新能源",
    "增程": "新能源",
    "自主燃油": "全部",
    "合资燃油": "全部",
    "豪华燃油": "全部",
}

BODY_ALIASES = {
    "轿车": "轿车",
    "sedan": "轿车",
    "car": "轿车",
    "suv": "SUV",
    "SUV": "SUV",
    "mpv": "MPV",
    "MPV": "MPV",
}

ENERGY_ALIASES = {
    "新能源": "新能源",
    "纯电": "新能源",
    "插混": "新能源",
    "增程": "新能源",
    "电车": "新能源",
    "燃油": "燃油车",
    "油车": "燃油车",
    "汽油": "燃油车",
    "柴油": "燃油车",
}

KNOWN_BODY_BY_SERIES = {
    # SUV / crossover, high-volume or common user-facing series.
    "modely": "SUV",
    "modelx": "SUV",
    "fj酷路泽": "SUV",
    "212": "SUV",
    "212t01": "SUV",
    "212经典": "SUV",
    "ds6": "SUV",
    "ds7": "SUV",
    "icar03": "SUV",
    "icar03t": "SUV",
    "icarv23": "SUV",
    "id6crozz": "SUV",
    "cs55erock": "SUV",
    "ex3功夫牛": "SUV",
    "enp1极湃1": "SUV",
    "enp2极湃2": "SUV",
    "evos": "SUV",
    "mgzs": "SUV",
    "mghs": "SUV",
    "mghsphev": "SUV",
    "mgone": "SUV",
    "pathfinder": "SUV",
    "stelvio": "SUV",
    "stelvio斯坦维": "SUV",
    "kx跨界": "SUV",
    "kxcross": "SUV",
    "mattu": "SUV",
    "本田crv": "SUV",
    "crv": "SUV",
    "rav4荣放": "SUV",
    "锋兰达": "SUV",
    "途观l": "SUV",
    "探岳": "SUV",
    "汉兰达": "SUV",
    "宝马x1": "SUV",
    "宝马x3": "SUV",
    "宝马x5": "SUV",
    "奥迪q3": "SUV",
    "奥迪q5l": "SUV",
    "奥迪q7": "SUV",
    "奔驰glc": "SUV",
    "奔驰gle": "SUV",
    "理想l6": "SUV",
    "理想l7": "SUV",
    "理想l8": "SUV",
    "理想l9": "SUV",
    "问界m5": "SUV",
    "问界m7": "SUV",
    "问界m9": "SUV",
    "蔚来es6": "SUV",
    "蔚来es8": "SUV",
    "小鹏g6": "SUV",
    "小鹏g9": "SUV",
    "宋plus": "SUV",
    "宋pro": "SUV",
    "元plus": "SUV",
    "元up": "SUV",
    "宋": "SUV",
    "唐": "SUV",
    "哈弗h6": "SUV",
    "哈弗m6": "SUV",
    "博越l": "SUV",
    "星越l": "SUV",
    "缤越": "SUV",
    "瑞虎8": "SUV",
    "瑞虎9": "SUV",
    "捷途旅行者": "SUV",
    "坦克300": "SUV",
    "坦克500": "SUV",
    "豹5": "SUV",
    "岚图free": "SUV",
    "zeekr7x": "SUV",
    "极氪7x": "SUV",
    "领克02": "SUV",
    # MPV.
    "别克gl8": "MPV",
    "gl8": "MPV",
    "腾势d9": "MPV",
    "传祺m8": "MPV",
    "传祺m6": "MPV",
    "赛那": "MPV",
    "奥德赛": "MPV",
    "艾力绅": "MPV",
    "威然": "MPV",
    "极氪009": "MPV",
    "岚图梦想家": "MPV",
    "理想mega": "MPV",
    # Sedan / hatchback used by the selection board.
    "model3": "轿车",
    "models": "轿车",
    "polo": "轿车",
    "altima": "轿车",
    "atenza": "轿车",
    "artreon": "轿车",
    "arteon": "轿车",
    "amggt": "轿车",
    "918spyder": "轿车",
    "919hybrid": "轿车",
    "alfa147": "轿车",
    "alfa156": "轿车",
    "alfa159": "轿车",
    "alfa166": "轿车",
    "alfa4c": "轿车",
    "alfa8c": "轿车",
    "aventador": "轿车",
    "boxster": "轿车",
    "cayman": "轿车",
    "californiat": "轿车",
    "c4世嘉": "轿车",
    "c4毕加索": "MPV",
    "clever": "轿车",
    "ctrek蔚领": "轿车",
    "ds3经典": "轿车",
    "ds4": "轿车",
    "ds4s": "轿车",
    "ds5": "轿车",
    "ds5ls": "轿车",
    "ds5进口": "轿车",
    "ds9": "轿车",
    "egolf": "轿车",
    "emira": "轿车",
    "evora": "轿车",
    "gallardo": "轿车",
    "ghibli": "轿车",
    "giulia": "轿车",
    "grancabrio": "轿车",
    "gransport": "轿车",
    "granturismo": "轿车",
    "huracán": "轿车",
    "insight": "轿车",
    "legacy力狮": "轿车",
    "leon": "轿车",
    "lite": "轿车",
    "mg3": "轿车",
    "mg4ev": "轿车",
    "mg5天蝎座": "轿车",
    "mg6phev": "轿车",
    "mgcyberster": "轿车",
    "miniclubman": "轿车",
    "minicountryman": "SUV",
    "minicoupe": "轿车",
    "minipaceman": "SUV",
    "miniroadster": "轿车",
    "mustang": "轿车",
    "passat领驭": "轿车",
    "portofino": "轿车",
    "pt漫步者": "轿车",
    "qq冰淇淋": "轿车",
    "saab93": "轿车",
    "saab95": "轿车",
    "s5turbo": "轿车",
    "sls赛威": "轿车",
    "smartforfour": "轿车",
    "smartfortwo": "轿车",
    "ssdol,phin": "轿车",
    "ssdolhpin": "轿车",
    "ssdolfin": "轿车",
    "supra": "轿车",
    "仰望u9": "轿车",
    "小米su7": "轿车",
    "小鹏monam03": "轿车",
    "小鹏p7": "轿车",
    "宝马3系": "轿车",
    "宝马5系": "轿车",
    "奔驰c级": "轿车",
    "奔驰e级": "轿车",
    "奥迪a4l": "轿车",
    "奥迪a6l": "轿车",
    "雅阁": "轿车",
    "凯美瑞": "轿车",
    "天籁": "轿车",
    "轩逸": "轿车",
    "朗逸": "轿车",
    "速腾": "轿车",
    "迈腾": "轿车",
    "帕萨特": "轿车",
    "福克斯": "轿车",
    "科鲁泽": "轿车",
    "海豚": "轿车",
    "秦plus": "轿车",
    "秦l": "轿车",
    "汉": "轿车",
    "海豹": "轿车",
    "领克07emp": "轿车",
    "长安univ": "轿车",
    "五菱星光": "轿车",
    "五菱星光phev": "轿车",
    "五菱宏光miniev": "轿车",
    "熊猫": "轿车",
    "星愿": "轿车",
    "零跑a10": "轿车",
    "零跑t03": "轿车",
    "长安lumin": "轿车",
    "奔腾小马": "轿车",
    "冰淇淋": "轿车",
    "小蚂蚁": "轿车",
    "zeekr001": "轿车",
    "极氪001": "轿车",
    "哪吒gt": "轿车",
    "远景": "轿车",
    "享域": "轿车",
    "沃尔沃v40": "轿车",
    "极狐t1": "轿车",
    "东风纳米ex1": "SUV",
    "长安unit": "SUV",
    "长安unik": "SUV",
    "理想i6": "SUV",
    "五菱宏光": "其他",
    "五菱宏光v": "其他",
    "五菱之光ev": "其他",
    "五菱扬光": "其他",
}

BODY_REGEX = (
    ("其他", re.compile(r"皮卡|微卡|微面|轻客|货车|房车|全顺|福顺|顺达|依维柯|sprinter|crafter|ducato|jumper|jumpy|expert|boxer|hiace|hilux|tacoma|ranger|f[-\\s]?150|ram|d[-\\s]?max|pickup|pick\\s*up|truck|canyon|savana|promaster|frontier|landtrek|maverick|ridgeline|musso|炮|域虎|锐骐|宝典|瑞迈|游骑侠|货|van|cargo", re.I)),
    ("MPV", re.compile(r"gl8|gl6|mpv|m8|m6|d9|赛那|奥德赛|艾力绅|威然|梦想家|009|mega|宋max|嘉际|杰德|阁瑞斯|风行(?:cm7|f600|s500|游艇)|马自达[58]|奔驰b级|欧尚(?:a600|a800|科尚|长行)|长城v80", re.I)),
    ("SUV", re.compile(r"suv|cross|酷路泽|越野|牧马人|卫士|发现|揽胜|sportage|pathfinder|stelvio|tiguan|tonale|tribeca|t[-\\s]?roc|zr[-\\s]?v|xc\\s?classic|cr[-\\s]?v|rav4|途观|探岳|汉兰达|锋兰达|星越|博越|缤越|瑞虎|捷途|哈弗|坦克|问界m|理想(?:one|l|i6)|蔚来es|小鹏g|宋(?:$|plus|pro|dm)|元(?:plus|up|ev|pro)|岚图free|豹5|银河l7|昂科|翼虎|c[-\\s]?hr|c3[-\\s]?xr|奕泽|cx[-\\s]?[345678]|vv[567]|领克0[12569]|哪吒[uvl]|自由(?:光|侠)|长安(?:cs|uni[-\\s]?[tk])|欧尚x|欧尚cx|欧尚科赛|欧蓝德|远景x|传祺gs|宝骏510|eπ008|yeti|北京(?:ex3|x3|bj\\d+)|bj\\d+|东风纳米ex1|帝豪gs|ix25|宝沃bx|摩卡|rx5|探影|f[-\\s]?pace|科雷(?:嘉|傲)|qx60|奔腾t33|飞行家|雷克萨斯(?:ux|rx)|陆风x|风光(?:580|ix7|s580)|风行(?:sx6|t5l)|驭胜s|高合hiphi[xy]|魏牌vv|q[23578]|qx\\d+|x[13567]\\b|ds\\s?[67]|icar\\s?(?:03|v23)|东南dx\\d|东风风神ax\\d|中华v[3567]|众泰(?:2008|5008|sr[79]|t[235678]\\d{2})|vgv\\s?u\\d+|u[67]\\s?turbo|mg领航|冒险家|凌放|劲炫|傲虎|傲跑|享御|创界|凯翼昆仑|m[-\\s]?nv|x[-\\s]?nv", re.I)),
    ("轿车", re.compile(r"model\\s*[3s]|su7|m03|p[57]|polo|altima|atenza|art?eon|giulia|ghibli|mustang|supra|smart|mini|mg\\s?[3456]|amg\\s?gt|spyder|boxster|cayman|gallardo|hurac|aventador|gran\\s?turismo|portofino|california|英朗|飞度|星纪元es|阿特兹|迈锐宝|福睿斯|宝马1系|yaris|致炫|致享|科沃兹|ats[-\\s]?l|桑塔纳|帝豪(?:gl|l|l\\s?hip)?|捷豹xel|红旗h5|欧拉黑猫|菲斯塔|奔奔|凯越|领动|凌派|零跑c01|赛欧|金牛座|kiwi|奔驰a级|捷达|奕炫|max|雪铁龙c[2456]|荣威(?:ei5|i6|360)|领克0[347]|领克z10|威驰|xts|名图|z4|艾瑞泽|晶锐|瑞纳|朗动|索纳塔|世嘉|微蓝6|锐程cc|小鹏p5|标致508|博瑞|辉昂|ga[46]|mkz|朗行|阳光|雅力士|雅绅特|雨燕|马自达[236]|mx[-\\s]?5|rx[-\\s]?8|高尔夫|3系|5系|c级|e级|a4l|a6l|雅阁|凯美瑞|天籁|轩逸|朗逸|速腾|迈腾|帕萨特|福克斯|科鲁泽|海豚|秦|汉|海豹|07", re.I)),
)


def normalize_selection_filter(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "全部"
    text = LEGACY_FILTER_MAP.get(text, text)
    if text in SELECTION_FILTERS:
        return text
    lowered = text.lower()
    if lowered in BODY_ALIASES:
        return BODY_ALIASES[lowered]
    if "新" in text or "电" in text or "插混" in text or "增程" in text:
        return "新能源"
    return "全部"


def normalize_energy(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for key, label in ENERGY_ALIASES.items():
        if key.lower() in text.lower():
            return label
    return text


def normalize_energy_subtype(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if re.search(r"增程|erev", lowered, flags=re.I):
        return "增程"
    if re.search(r"插混|插电混|phev|dm-?i|emp", lowered, flags=re.I):
        return "插混"
    if re.search(r"纯电|bev|(^|[^a-z])ev([^a-z]|$)|电动车", lowered, flags=re.I):
        return "纯电"
    if re.search(r"新能源", text):
        return "新能源"
    if re.search(r"燃油|油车|汽油|柴油|ice", lowered, flags=re.I):
        return "燃油"
    return text if text in ENERGY_SUBTYPES else ""


def normalize_vehicle_category(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {"SUV", "MPV"}:
        return upper
    aliases = {"小货车": "微卡", "面包车": "微面", "厢式面包车": "微面", "商务车": "MPV"}
    text = aliases.get(text, text)
    return text if text in DETAILED_VEHICLE_CATEGORIES else ""


def normalize_manufacturer_attribute(value: Any) -> str:
    text = str(value or "").strip()
    aliases = {"国产": "自主", "自主品牌": "自主", "国产品牌": "自主", "进口车": "进口", "进口品牌": "进口"}
    text = aliases.get(text, text)
    return text if text in MANUFACTURER_ATTRIBUTES else ""


def normalize_body(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in BODY_FILTERS or text in OTHER_BODY_TYPES:
        return text
    if text in NON_PASSENGER_CATEGORIES:
        return "其他"
    return BODY_ALIASES.get(text.lower(), "")


def _latest_training_csv() -> Path | None:
    env_path = os.environ.get("SELECTION_90D_CSV_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    candidates = sorted(Path("/Users/bytedance/Downloads").glob(TRAINING_GLOB), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


class VehicleTaxonomyService:
    def __init__(self, index_path: str | Path | None = None) -> None:
        self.index_path = Path(index_path or os.environ.get("SELECTION_VEHICLE_TAXONOMY_INDEX") or DEFAULT_TAXONOMY_INDEX)
        self._by_series: dict[str, dict[str, Any]] = {}
        self.metadata: dict[str, Any] = {}
        self._load_or_build()

    def classify_series(self, *, brand: Any = "", series: Any = "", model: Any = "") -> dict[str, Any]:
        key = normalize_text(series)
        row = dict(self._by_series.get(key) or {})
        # Curated high-frequency corrections are authoritative over the
        # generated index.  The source index may infer a body type from a model
        # token alone (for example the “M6” in 哈弗M6 was mistaken for MPV),
        # which is unacceptable in a user-facing filter.
        forced_body = KNOWN_BODY_BY_SERIES.get(key)
        body = forced_body or normalize_body(row.get("body_type")) or _heuristic_body(series, model)
        energy = normalize_energy(row.get("energy_type"))
        categories = _split_memberships(row.get("vehicle_categories"))
        if forced_body:
            categories = [
                category for category in categories
                if category not in DETAILED_VEHICLE_CATEGORIES and category not in OTHER_BODY_TYPES
            ]
        if body and body in DETAILED_VEHICLE_CATEGORIES and body not in categories:
            categories.append(body)
        energy_subtypes = _split_memberships(row.get("energy_subtypes"))
        if energy == "新能源" and "新能源" not in energy_subtypes:
            energy_subtypes.append("新能源")
        if energy == "燃油车" and "燃油" not in energy_subtypes:
            energy_subtypes.append("燃油")
        return {
            "brand": row.get("brand") or brand,
            "series": row.get("series") or series,
            "body_type": body,
            "energy_type": energy,
            "vehicle_categories": categories,
            "energy_subtypes": energy_subtypes,
            "manufacturer_attributes": _split_memberships(row.get("manufacturer_attributes")),
            "taxonomy_source": row.get("taxonomy_source") or ("heuristic" if body else "unknown"),
            "taxonomy_confidence": row.get("taxonomy_confidence") or (0.72 if body else 0.0),
        }

    def matches_selection_filter(self, *, brand: Any = "", series: Any = "", model: Any = "", selected_filter: Any = "") -> bool:
        label = normalize_selection_filter(selected_filter)
        if label == "全部":
            return True
        info = self.classify_series(brand=brand, series=series, model=model)
        if label == "新能源":
            return normalize_energy(info.get("energy_type")) == "新能源"
        return normalize_body(info.get("body_type")) == label

    def matches_energy(self, *, brand: Any = "", series: Any = "", model: Any = "", energy_type: Any = "") -> bool:
        target = normalize_energy(energy_type)
        if not target:
            return True
        info = self.classify_series(brand=brand, series=series, model=model)
        current = normalize_energy(info.get("energy_type"))
        if target == "新能源":
            return current == "新能源"
        if target == "燃油车":
            return current == "燃油车"
        return bool(current and target in current)

    def matches_energy_subtype(self, *, brand: Any = "", series: Any = "", model: Any = "", energy_subtype: Any = "") -> bool:
        target = normalize_energy_subtype(energy_subtype)
        if not target:
            return True
        info = self.classify_series(brand=brand, series=series, model=model)
        memberships = set(info.get("energy_subtypes") or [])
        if target == "新能源":
            return bool(memberships.intersection({"新能源", "纯电", "插混", "增程"}))
        return target in memberships

    def matches_vehicle_category(self, *, brand: Any = "", series: Any = "", model: Any = "", vehicle_category: Any = "") -> bool:
        target = normalize_vehicle_category(vehicle_category)
        if not target:
            return True
        info = self.classify_series(brand=brand, series=series, model=model)
        return target in set(info.get("vehicle_categories") or [])

    def matches_manufacturer_attribute(self, *, brand: Any = "", series: Any = "", model: Any = "", manufacturer_attribute: Any = "") -> bool:
        target = normalize_manufacturer_attribute(manufacturer_attribute)
        if not target:
            return True
        info = self.classify_series(brand=brand, series=series, model=model)
        return target in set(info.get("manufacturer_attributes") or [])

    def build_index(self) -> dict[str, Any]:
        rows = _build_taxonomy_rows()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "series_key",
                    "brand",
                    "series",
                    "body_type",
                    "energy_type",
                    "vehicle_categories",
                    "energy_subtypes",
                    "manufacturer_attributes",
                    "taxonomy_source",
                    "taxonomy_confidence",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        self._load_index()
        return self.metadata

    def _load_or_build(self) -> None:
        if self.index_path.is_file():
            with self.index_path.open("r", encoding="utf-8") as handle:
                header = set(next(csv.reader(handle), []))
            required = {"vehicle_categories", "energy_subtypes", "manufacturer_attributes"}
            if required.issubset(header):
                self._load_index()
                return
        try:
            self.build_index()
        except Exception as exc:
            self.metadata = {"available": False, "error": f"taxonomy_build_failed: {exc}"}

    def _load_index(self) -> None:
        self._by_series = {}
        with self.index_path.open("r", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = row.get("series_key") or normalize_text(row.get("series"))
                if key:
                    self._by_series[key] = row
        body_count = Counter(row.get("body_type") or "unknown" for row in self._by_series.values())
        energy_count = Counter(row.get("energy_type") or "unknown" for row in self._by_series.values())
        detailed_body_count = Counter(
            item
            for row in self._by_series.values()
            for item in _split_memberships(row.get("vehicle_categories"))
        )
        subtype_count = Counter(
            item
            for row in self._by_series.values()
            for item in _split_memberships(row.get("energy_subtypes"))
        )
        self.metadata = {
            "available": True,
            "source_file": str(self.index_path),
            "series_count": len(self._by_series),
            "body_type_counts": dict(body_count),
            "energy_type_counts": dict(energy_count),
            "vehicle_category_counts": dict(detailed_body_count),
            "energy_subtype_counts": dict(subtype_count),
        }


def _build_taxonomy_rows() -> list[dict[str, Any]]:
    body_votes: dict[str, Counter[str]] = defaultdict(Counter)
    energy_votes: dict[str, Counter[str]] = defaultdict(Counter)
    names: dict[str, dict[str, str]] = {}
    sources: dict[str, set[str]] = defaultdict(set)
    vehicle_categories: dict[str, Counter[str]] = defaultdict(Counter)
    energy_subtypes: dict[str, Counter[str]] = defaultdict(Counter)
    manufacturer_attributes: dict[str, Counter[str]] = defaultdict(Counter)
    _consume_ranking_csv(DEFAULT_RANKING_SIGNALS, body_votes, energy_votes, names, sources, vehicle_categories, energy_subtypes, manufacturer_attributes)
    _consume_ranking_csv(DEFAULT_RAW_RANKING, body_votes, energy_votes, names, sources, vehicle_categories, energy_subtypes, manufacturer_attributes)
    _consume_training_energy(body_votes, energy_votes, names, sources)

    all_keys = set(names) | set(body_votes) | set(energy_votes)
    rows: list[dict[str, Any]] = []
    for key in sorted(all_keys):
        name = names.get(key) or {}
        body = _top_counter(body_votes.get(key))
        if not body:
            body = _heuristic_body(name.get("series"), "")
            if body:
                sources[key].add("heuristic_body")
        energy = _top_counter(energy_votes.get(key))
        detailed_category = _heuristic_detailed_category(name.get("series"), "")
        category_memberships = {body} if body in DETAILED_VEHICLE_CATEGORIES else set()
        if detailed_category:
            category_memberships = {detailed_category}
        subtype_memberships = _credible_memberships(energy_subtypes.get(key), minimum_count=5, ratio=0.15)
        if energy == "新能源":
            subtype_memberships.add("新能源")
            if len(subtype_memberships) > 1:
                subtype_memberships.discard("燃油")
        elif energy == "燃油车" and not subtype_memberships:
            subtype_memberships.add("燃油")
        manufacturer_memberships = _credible_memberships(
            manufacturer_attributes.get(key),
            minimum_count=3,
            ratio=0.15,
        )
        source_text = "+".join(sorted(sources.get(key) or {"unknown"}))
        confidence = 0.0
        if body or energy:
            confidence = 0.96 if "dcd_ranking" in source_text else 0.88 if "internal_90d" in source_text else 0.72
        rows.append(
            {
                "series_key": key,
                "brand": name.get("brand", ""),
                "series": name.get("series", ""),
                "body_type": body,
                "energy_type": energy,
                "vehicle_categories": "|".join(sorted(category_memberships)),
                "energy_subtypes": "|".join(sorted(subtype_memberships)),
                "manufacturer_attributes": "|".join(sorted(manufacturer_memberships)),
                "taxonomy_source": source_text,
                "taxonomy_confidence": round(confidence, 2),
            }
        )
    return rows


def _consume_ranking_csv(
    path: Path,
    body_votes: dict[str, Counter[str]],
    energy_votes: dict[str, Counter[str]],
    names: dict[str, dict[str, str]],
    sources: dict[str, set[str]],
    vehicle_categories: dict[str, Counter[str]],
    energy_subtypes: dict[str, Counter[str]],
    manufacturer_attributes: dict[str, Counter[str]],
) -> None:
    if not path.is_file():
        return
    usecols = {"brand", "brand_name", "series_name", "vehicle_category", "energy_type", "manufacturer_attribute", "raw_json"}
    for frame in pd.read_csv(path, usecols=lambda column: column in usecols, low_memory=False, chunksize=50000):
        for row in frame.itertuples(index=False):
            data = row._asdict()
            series = str(data.get("series_name") or "").strip()
            if not series:
                continue
            key = normalize_text(series)
            brand = str(data.get("brand") or data.get("brand_name") or "").strip()
            names.setdefault(key, {"brand": brand, "series": series})
            if brand and not names[key].get("brand"):
                names[key]["brand"] = brand
            category = str(data.get("vehicle_category") or "").strip()
            detailed_category = normalize_vehicle_category(category)
            if detailed_category:
                vehicle_categories[key][detailed_category] += 1
                if detailed_category in BODY_FILTERS:
                    body_votes[key][detailed_category] += 2
            subtype = normalize_energy_subtype(data.get("energy_type"))
            if subtype:
                energy_subtypes[key][subtype] += 1
            manufacturer = normalize_manufacturer_attribute(data.get("manufacturer_attribute"))
            if manufacturer:
                manufacturer_attributes[key][manufacturer] += 1
            body = _body_from_raw_json(data.get("raw_json"))
            if body:
                body_votes[key][body] += 3
                sources[key].add("dcd_outter_detail_type")
            if category == "新能源":
                energy_votes[key]["新能源"] += 1
                sources[key].add("dcd_ranking")
            energy = normalize_energy(data.get("energy_type"))
            if energy in {"新能源", "燃油车"}:
                energy_votes[key][energy] += 1
                sources[key].add("dcd_ranking")


def _split_memberships(value: Any) -> list[str]:
    return [item for item in str(value or "").split("|") if item]


def _credible_memberships(counter: Counter[str] | None, *, minimum_count: int, ratio: float) -> set[str]:
    if not counter:
        return set()
    peak = max(counter.values())
    threshold = max(minimum_count, int(math.ceil(peak * ratio)))
    return {label for label, count in counter.items() if count >= threshold}


def _consume_training_energy(
    body_votes: dict[str, Counter[str]],
    energy_votes: dict[str, Counter[str]],
    names: dict[str, dict[str, str]],
    sources: dict[str, set[str]],
) -> None:
    path = _latest_training_csv()
    if not path or not path.is_file():
        return
    usecols = {"品牌名称", "车系名称", "能源类型", "是否新能源"}
    for frame in pd.read_csv(path, usecols=lambda column: column in usecols, low_memory=False, chunksize=50000):
        for row in frame.itertuples(index=False):
            data = row._asdict()
            series = str(data.get("车系名称") or "").strip()
            if not series:
                continue
            key = normalize_text(series)
            brand = str(data.get("品牌名称") or "").strip()
            names.setdefault(key, {"brand": brand, "series": series})
            body = _heuristic_body(series, "")
            if body:
                body_votes[key][body] += 1
                sources[key].add("heuristic_body")
            energy = normalize_energy(data.get("能源类型"))
            if not energy:
                new_energy = str(data.get("是否新能源") or "").strip()
                if new_energy in {"是", "1", "true", "True"}:
                    energy = "新能源"
                elif new_energy in {"否", "0", "false", "False"}:
                    energy = "燃油车"
            if energy in {"新能源", "燃油车"}:
                energy_votes[key][energy] += 1
                sources[key].add("internal_90d")


def _top_counter(counter: Counter[str] | None) -> str:
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


def _body_from_raw_json(raw_json: Any) -> str:
    if not isinstance(raw_json, str) or "outter_detail_type" not in raw_json:
        return ""
    try:
        data = json.loads(raw_json)
    except Exception:
        return ""
    detail_type = data.get("outter_detail_type")
    try:
        code = int(detail_type)
    except Exception:
        return ""
    if 1 <= code <= 5:
        return "轿车"
    if 10 <= code <= 14:
        return "SUV"
    if 20 <= code <= 24:
        return "MPV"
    if 30 <= code <= 35:
        return "其他"
    return ""


def _heuristic_body(series: Any, model: Any) -> str:
    text = f"{series or ''} {model or ''}".strip()
    key = normalize_text(text)
    series_key = normalize_text(series)
    if series_key in KNOWN_BODY_BY_SERIES:
        return KNOWN_BODY_BY_SERIES[series_key]
    for known_key, body in KNOWN_BODY_BY_SERIES.items():
        if known_key and known_key in key:
            return body
    for body, pattern in BODY_REGEX:
        if pattern.search(text):
            return body
    return ""


def _heuristic_detailed_category(series: Any, model: Any) -> str:
    text = f"{series or ''} {model or ''}".strip()
    if re.search(r"皮卡|炮|域虎|锐骐|宝典|瑞迈|游骑侠|拓陆者|风骏|纳瓦拉|hilux|ranger|f[-\s]?150|d[-\s]?max|pickup", text, re.I):
        return "皮卡"
    if re.search(r"微卡|小卡|星卡|祥菱|途逸|缔途|恺达|福田时代|五菱荣光新卡", text, re.I):
        return "微卡"
    if re.search(r"轻客|全顺|福顺|图雅诺|依维柯|特顺|新世代全顺|大通v\d+|星锐|御风|欧胜", text, re.I):
        return "轻客"
    if re.search(r"MINI\s*EV|MINIEV", text, re.I):
        return ""
    if re.search(r"微面|面包车|五菱宏光|五菱之光|五菱荣光(?!新卡)|长安之星|东风小康|小海狮|优优|佳宝v", text, re.I):
        return "微面"
    return ""


@lru_cache(maxsize=2)
def get_vehicle_taxonomy_service(index_path: str = "") -> VehicleTaxonomyService:
    return VehicleTaxonomyService(index_path or None)
