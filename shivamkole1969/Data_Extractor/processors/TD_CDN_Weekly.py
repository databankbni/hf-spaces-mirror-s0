"""
TD CDN Weekly Metals & Mining Processor

Extracts financial estimates data from TD Cowen CDN Weekly Metals & Mining PDF reports.
Contains embedded extraction logic (precious/base metal forecasts, company tables,
EPS/CFPS revisions) with all ticker maps and column definitions.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise SystemExit("Missing dependency: pip install pymupdf") from exc

from processors.base import BaseProcessor

# ---------------------------------------------------------------------------
# Constants & ticker maps
# ---------------------------------------------------------------------------

YEARS = [str(y) for y in range(2025, 2031)]

BASE_METALS_TICKER_MAP = {
    "cameco corp.": "CCO",
    "first quantum minerals ltd.": "FM",
    "ivanhoe mines ltd.": "IVN",
    "lundin mining corp.": "LUN",
    "teck resources ltd.": "TECK.B",
    "capstone copper corp.": "CS",
    "champion iron ltd.": "CIA",
    "ero copper corp.": "ERO",
    "hudbay minerals inc.": "HBM",
    "labrador iron ore royalty corp.": "LIF",
    "taseko mines ltd.": "TKO",
    "arizona sonoran": "ASCU",
    "atex resources": "ATX",
    "denison mines corp.": "DML",
    "entree resources ltd.": "ETG",
    "faraday copper": "FDY",
    "isoenergy ltd.": "ISO",
    "nexgen energy ltd.": "NXE",
    "talon metals corp.": "TLO",
    "trilogy metals inc.": "TMQ",
    "uranium energy corp.": "UEC",
    "altius minerals corp.": "ALS",
    "lithium americas corp.": "LAC",
    "lithium argentina corp.": "LAR",
    "lynas rare earths, ltd.": "LYC",
    "major drilling group international inc.": "MDI",
    "mp materials": "MP",
}

COMMODITY_TICKER_MAP = {
    "gold": "BGOLD",
    "silver": "BSILV",
    "copper": "BCOPP",
    "zinc": "BZINC",
    "nickel": "BNICK",
    "uranium": "BURAN",
    "iron ore": "BIRON",
    "lithium": "BLITH",
}

REVISION_TICKER_MAP = {
    "b2gold": "BTO",
    "b2gold corp.": "BTO",
    "equinox gold": "EQX",
    "altius minerals": "ALS",
    "iamgold": "IMG",
    "lundin gold": "LUG",
    "oceanagold": "OGC",
    "dpm metals": "DPM",
    "dundee precious metals": "DPM",
    "g mining ventures": "GMIN",
    "ssr mining": "SSRM",
    "torex gold resources": "TXG",
    "coeur mining": "CDE",
    "endeavour silver": "EDR",
    "hecla mining": "HL",
    "or royalties": "OR",
    "osisko gold royalties": "OR",
    "royal gold": "RGLD",
    "triple flag": "TFPM",
    "wheaton precious": "WPM",
    "ivanhoe mines": "IVN",
    "taseko mines": "TKO",
    "faraday copper": "FDY",
}

PRECIOUS_GROUPS = {
    "senior golds",
    "intermediate golds",
    "junior golds",
    "silvers",
    "royalties",
}
BASE_GROUPS = {
    "large cap.",
    "mid cap.",
    "developers",
    "other",
}
SKIP_ROW_LABELS = {
    "average",
    "median",
}

MAIN_OUTPUT_FIELDS = [
    "company_name",
    "ticker",
    "target_price",
    "rating",
]
MAIN_OUTPUT_FIELDS += [f"eps_{y}" for y in YEARS]
MAIN_OUTPUT_FIELDS += [f"cfps_{y}" for y in YEARS]
MAIN_OUTPUT_FIELDS += [
    "analyst",
    "unit",
    "notes",
]

REVISION_OUTPUT_FIELDS = [
    "company_name",
    "ticker",
]
REVISION_OUTPUT_FIELDS += [f"eps_{y}" for y in YEARS]
REVISION_OUTPUT_FIELDS += [f"cfps_{y}" for y in YEARS]
REVISION_OUTPUT_FIELDS += [
    "unit",
    "notes",
]

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_company_name(text: str) -> str:
    text = (text or "").replace("\u00a0", " ").strip()
    text = re.sub(r"[\*\^]+", "", text)
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)
    text = re.sub(r"(?<=[A-Za-z])\d{1,2}$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("Entre\u0301e", "Entree")
    return text


def empty_main_row() -> Dict[str, str]:
    return {field: "" for field in MAIN_OUTPUT_FIELDS}


def empty_revision_row() -> Dict[str, str]:
    return {field: "" for field in REVISION_OUTPUT_FIELDS}


def group_words_into_lines(words: Iterable[Tuple]) -> List[Dict]:
    """Cluster words into rows by baseline (y0) proximity.

    A 4pt tolerance keeps each visual row together without merging adjacent rows
    (rows are ~8.6pt apart; within-row baseline spread is ~1.2pt).
    """
    tol = 4.0
    ws_sorted = sorted(words, key=lambda w: (w[1], w[0]))
    clusters: List[List[Tuple]] = []
    anchor = None
    for w in ws_sorted:
        y0 = w[1]
        if anchor is None or y0 - anchor > tol:
            clusters.append([])
            anchor = y0
        clusters[-1].append(w)

    lines = []
    for ws in clusters:
        ws = sorted(ws, key=lambda w: w[0])
        y = min(w[1] for w in ws)
        text = " ".join(w[4] for w in ws)
        lines.append({"y": y, "words": ws, "text": text})
    lines.sort(key=lambda line: line["y"])
    return lines


def cell_text(line: Dict, x0: float, x1: float) -> str:
    parts = []
    for w in line["words"]:
        wx0, wy0, wx1, wy1, text, *_ = w
        cx = (wx0 + wx1) / 2.0
        if x0 <= cx < x1:
            parts.append(text)
    return " ".join(parts).strip()


def is_numericish(value: str) -> bool:
    if not value:
        return False
    value = value.strip()
    return bool(re.search(r"[0-9]", value)) or value.lower() in {"n/m", "neg"}


def clean_cell(value: str) -> str:
    value = (value or "").replace("\u00a0", " ").strip()
    value = re.sub(r"[\u2191\u2193\u2194]", "", value)
    value = re.sub(r"\s+", " ", value)
    value = value.replace("C$ ", "C$").replace("US$ ", "US$").replace("A$ ", "A$")
    value = re.sub(r"(?<=\d)\s+(?=[\d,])", "", value)
    return value.strip()


def page_has_spot_comps(page_text: str) -> bool:
    upper = (page_text or "").upper()
    return "SPOT COMPS" in upper or "SPOT PRICES USED" in upper or "SPOT PRICES:" in upper


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------


def extract_precious_forecast(page, source_pdf: str, page_num: int) -> List[Dict[str, str]]:
    rows = []
    lines = group_words_into_lines(page.get_text("words"))
    cols = {
        "name": (310, 360),
        "2026": (360, 389),
        "2027": (389, 418),
        "LT": (418, 460),
    }
    for line in lines:
        if not (33 <= line["y"] <= 60):
            continue
        name = clean_cell(cell_text(line, *cols["name"]))
        if normalize_key(name) not in {"gold", "silver"}:
            continue
        row = empty_main_row()
        row["company_name"] = clean_company_name(name)
        row["ticker"] = COMMODITY_TICKER_MAP.get(
            normalize_key(name), clean_company_name(name).upper()
        )
        row["unit"] = "US$/oz"
        row["eps_2026"] = clean_cell(cell_text(line, *cols["2026"]))
        row["eps_2027"] = clean_cell(cell_text(line, *cols["2027"]))
        row["target_price"] = clean_cell(cell_text(line, *cols["LT"]))
        row["notes"] = "LT value from forecast table placed under target_price; forecast years placed under EPS columns."
        rows.append(row)
    return rows


def extract_base_forecast(page, source_pdf: str, page_num: int) -> List[Dict[str, str]]:
    rows = []
    lines = group_words_into_lines(page.get_text("words"))
    cols = {
        "name": (168, 205),
        "2025": (205, 240),
        "2026": (240, 270),
        "2027": (270, 300),
        "2028": (300, 330),
        "2029": (330, 362),
        "LT": (362, 395),
    }
    commodity_names = {"copper", "zinc", "nickel", "uranium", "iron ore", "lithium"}
    for line in lines:
        if not (70 <= line["y"] <= 120):
            continue
        name = clean_company_name(clean_cell(cell_text(line, *cols["name"])))
        if normalize_key(name) not in commodity_names:
            continue
        row = empty_main_row()
        row["company_name"] = name
        row["ticker"] = COMMODITY_TICKER_MAP.get(normalize_key(name), name.upper())
        row["unit"] = "US$/lb"
        if normalize_key(name) in {"iron ore", "lithium"}:
            row["unit"] = "See PDF footnote: Iron Ore is 65% CFR China (US$/t); Lithium Carbonate is US$/t."
        for year in ["2025", "2026", "2027", "2028", "2029"]:
            row[f"eps_{year}"] = clean_cell(cell_text(line, *cols[year]))
        row["target_price"] = clean_cell(cell_text(line, *cols["LT"]))
        row["notes"] = "LT value from forecast table placed under target_price; forecast years placed under EPS columns."
        rows.append(row)
    return rows


def parse_company_line(
    line: Dict,
    cols: Dict[str, Tuple[float, float]],
    source_table: str,
    base_table: bool,
) -> Dict[str, str] | None:
    company = clean_company_name(clean_cell(cell_text(line, *cols["company"])))
    if not company:
        return None
    key = normalize_key(company)
    if key in SKIP_ROW_LABELS or key in PRECIOUS_GROUPS or key in BASE_GROUPS:
        return None

    current_price = clean_cell(cell_text(line, *cols["current_price"]))
    row_text = line["text"]
    has_restricted = "Restricted" in row_text
    if not is_numericish(current_price) and not has_restricted:
        return None

    row = empty_main_row()
    row["company_name"] = company

    if base_table:
        row["ticker"] = BASE_METALS_TICKER_MAP.get(key, "")
        if not row["ticker"]:
            row["notes"] = "Ticker missing from hardcoded BASE_METALS_TICKER_MAP."
    else:
        row["ticker"] = clean_cell(cell_text(line, *cols["ticker"]))

    row["target_price"] = clean_cell(cell_text(line, *cols["target_price"]))
    row["rating"] = clean_cell(cell_text(line, *cols["rating"]))
    row["eps_2026"] = clean_cell(cell_text(line, *cols["eps_2026"]))
    row["eps_2027"] = clean_cell(cell_text(line, *cols["eps_2027"]))
    row["cfps_2026"] = clean_cell(cell_text(line, *cols["cfps_2026"]))
    row["cfps_2027"] = clean_cell(cell_text(line, *cols["cfps_2027"]))
    row["analyst"] = clean_cell(cell_text(line, *cols["analyst"]))

    if has_restricted:
        for fld in ["target_price", "rating", "eps_2026", "eps_2027", "cfps_2026", "cfps_2027"]:
            if "Restricted" in row.get(fld, "") or "---" in row.get(fld, ""):
                row[fld] = ""
        row["notes"] = (row["notes"] + "; " if row["notes"] else "") + "Restricted row in PDF."

    return row


def extract_precious_company_table(page, source_pdf: str, page_num: int) -> List[Dict[str, str]]:
    rows = []
    lines = group_words_into_lines(page.get_text("words"))
    cols = {
        "company": (82, 150),
        "ticker": (150, 170),
        "current_price": (170, 202),
        "target_price": (202, 236),
        "rating": (264, 290),
        "eps_2026": (463, 486),
        "eps_2027": (486, 513),
        "cfps_2026": (513, 542),
        "cfps_2027": (542, 572),
        "analyst": (690, 710),
    }
    for line in lines:
        if not (125 <= line["y"] <= 525):
            continue
        label = normalize_key(clean_cell(cell_text(line, *cols["company"])))
        full_label = normalize_key(line["text"])
        if label in PRECIOUS_GROUPS or full_label in PRECIOUS_GROUPS:
            continue
        row = parse_company_line(line, cols, "PRECIOUS METALS", base_table=False)
        if row:
            row["cfps_2026"] = ""
            row["cfps_2027"] = ""
            rows.append(row)
    return rows


def extract_base_company_table(page, source_pdf: str, page_num: int) -> List[Dict[str, str]]:
    rows = []
    lines = group_words_into_lines(page.get_text("words"))
    cols = {
        "company": (20, 135),
        "current_price": (135, 168),
        "target_price": (168, 207),
        "rating": (265, 295),
        "eps_2026": (432, 458),
        "eps_2027": (458, 485),
        "cfps_2026": (488, 514),
        "cfps_2027": (514, 540),
        "analyst": (748, 768),
    }
    for line in lines:
        if not (160 <= line["y"] <= 488):
            continue
        label = normalize_key(clean_cell(cell_text(line, *cols["company"])))
        full_label = normalize_key(line["text"])
        if label in BASE_GROUPS or full_label in BASE_GROUPS:
            continue
        row = parse_company_line(line, cols, "BASE METALS", base_table=True)
        if row:
            rows.append(row)
    return rows


def find_revision_header_line(words: List[Tuple]) -> Dict | None:
    """Locate the Old/New header band by clustering raw Old/New tokens by y.

    This avoids depending on 'Company' sharing a single 0.7pt line-bucket with
    the Old/New tokens (a fragile assumption that breaks under sub-point
    baseline differences between PDF text engines). We look directly for a y
    band that contains at least 4 'old' and 4 'new' tokens.
    """
    by_y: Dict[float, List[Tuple]] = defaultdict(list)
    for w in words:
        x0, y0, x1, y1, text, *_ = w
        if text.lower() not in {"old", "new"}:
            continue
        placed = False
        for key in list(by_y.keys()):
            if abs(key - y0) <= 2.5:
                by_y[key].append(w)
                placed = True
                break
        if not placed:
            by_y[y0].append(w)

    for y, ws in sorted(by_y.items()):
        lower = [w[4].lower() for w in ws]
        if lower.count("old") >= 4 and lower.count("new") >= 4:
            avg_y = sum(w[1] for w in ws) / len(ws)
            return {"y": avg_y, "words": ws}
    return None


def extract_eps_cfps_revisions(page, source_pdf: str, page_num: int) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    words = page.get_text("words")
    lines = group_words_into_lines(words)
    header = find_revision_header_line(words)
    if not header:
        return rows

    header_words = []
    for w in header["words"]:
        x0, y0, x1, y1, text, *_ = w
        if text.lower() in {"old", "new"}:
            header_words.append(((x0 + x1) / 2.0, text.lower()))
    header_words = sorted(header_words, key=lambda x: x[0])
    if len(header_words) < 8:
        return rows

    centers = [c for c, _label in header_words[:8]]
    boundaries = [centers[0] - 28]
    boundaries += [(centers[i] + centers[i + 1]) / 2.0 for i in range(len(centers) - 1)]
    boundaries += [centers[-1] + 35]

    first_value_x = boundaries[0]
    company_x0 = 0
    company_x1 = max(40.0, first_value_x - 10.0)
    data_start_y = header["y"] + 7

    source_y = None
    for line in lines:
        if line["y"] > data_start_y and normalize_key(line["text"]).startswith("source:"):
            source_y = line["y"]
            break
    data_end_y = source_y if source_y is not None else page.rect.height - 40

    labels = [
        "eps_2026_old",
        "eps_2026_new",
        "eps_2027_old",
        "eps_2027_new",
        "cfps_2026_old",
        "cfps_2026_new",
        "cfps_2027_old",
        "cfps_2027_new",
    ]

    for line in lines:
        if not (data_start_y <= line["y"] < data_end_y):
            continue
        company = clean_company_name(clean_cell(cell_text(line, company_x0, company_x1)))
        if not company:
            continue
        key = normalize_key(company)
        if key in {"company", "source"} or key in SKIP_ROW_LABELS:
            continue

        parsed = {}
        for i, label in enumerate(labels):
            parsed[label] = clean_cell(cell_text(line, boundaries[i], boundaries[i + 1]))

        candidate_values = [parsed.get("eps_2026_new", ""), parsed.get("eps_2027_new", ""), parsed.get("cfps_2026_new", ""), parsed.get("cfps_2027_new", "")]
        if not any(is_numericish(v) for v in candidate_values):
            continue

        row = empty_revision_row()
        row["company_name"] = company
        row["ticker"] = REVISION_TICKER_MAP.get(key, BASE_METALS_TICKER_MAP.get(key, ""))
        row["eps_2026"] = parsed.get("eps_2026_new", "")
        row["eps_2027"] = parsed.get("eps_2027_new", "")
        row["cfps_2026"] = parsed.get("cfps_2026_new", "")
        row["cfps_2027"] = parsed.get("cfps_2027_new", "")
        row["unit"] = "$/sh"
        row["notes"] = "NEW values only from TD Cowen EPS and CFPS Revisions table."
        if not row["ticker"]:
            row["notes"] += " Ticker missing from hardcoded ticker maps."
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# PDF extraction entry point
# ---------------------------------------------------------------------------


def extract_pdf(pdf_path: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    main_rows: List[Dict[str, str]] = []
    revision_rows: List[Dict[str, str]] = []
    doc = fitz.open(pdf_path)
    seen_forecasts = set()
    seen_revisions_pages = set()

    for page_index, page in enumerate(doc):
        page_num = page_index + 1
        text = page.get_text("text")
        upper = text.upper()

        if page_has_spot_comps(text):
            continue

        if "TD COWEN PRECIOUS METALS PRICE FORECAST" in upper and "precious_forecast" not in seen_forecasts:
            main_rows.extend(extract_precious_forecast(page, pdf_path, page_num))
            seen_forecasts.add("precious_forecast")

        if "TD COWEN BASE METALS PRICE FORECAST" in upper and "base_forecast" not in seen_forecasts:
            main_rows.extend(extract_base_forecast(page, pdf_path, page_num))
            seen_forecasts.add("base_forecast")

        if "PRECIOUS METALS" in upper and "1-YEAR" in upper and "TARGET" in upper and "EPS" in upper:
            main_rows.extend(extract_precious_company_table(page, pdf_path, page_num))

        if "BASE METALS" in upper and "1-YEAR" in upper and "TARGET" in upper and "EPS" in upper and "CFPS" in upper:
            main_rows.extend(extract_base_company_table(page, pdf_path, page_num))

        if "EPS AND CFPS REVISIONS" in upper and page_num not in seen_revisions_pages:
            revision_rows.extend(extract_eps_cfps_revisions(page, pdf_path, page_num))
            seen_revisions_pages.add(page_num)

    return main_rows, revision_rows


# ---------------------------------------------------------------------------
# Excel output
# ---------------------------------------------------------------------------


def output_cell(value: str | None) -> str:
    value = "" if value is None else str(value).strip()
    return value if value else "-"


def write_xlsx(
    main_rows: List[Dict[str, str]],
    revision_rows: List[Dict[str, str]],
    out_path: str,
) -> None:
    commodity_rows = [
        r for r in main_rows
        if normalize_key(r.get("company_name", "")) in COMMODITY_TICKER_MAP
    ]
    sheets = [
        ("Metals Data", main_rows, MAIN_OUTPUT_FIELDS),
        ("Commodities", commodity_rows, MAIN_OUTPUT_FIELDS),
        ("EPS CFPS Old new", revision_rows, REVISION_OUTPUT_FIELDS),
    ]

    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_format = workbook.add_format({
            "bold": True,
            "font_name": "Calibri",
            "font_size": 11,
            "font_color": "#FFFFFF",
            "bg_color": "#14532D",
            "border": 1
        })
        cell_format = workbook.add_format({
            "font_name": "Calibri",
            "font_size": 11,
        })

        for sheet_name, rows, fields in sheets:
            data = [{f: output_cell(row.get(f, "")) for f in fields} for row in rows]
            df = pd.DataFrame(data, columns=fields)
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            worksheet = writer.sheets[sheet_name]

            for col_idx, field in enumerate(fields):
                width = 18
                if field in {"company_name", "unit"}:
                    width = 32
                elif field == "notes":
                    width = 70
                worksheet.set_column(col_idx, col_idx, width, cell_format)
                worksheet.write(0, col_idx, field, header_format)

            worksheet.freeze_panes(1, 0)

            max_row = max(1, len(data))
            worksheet.autofilter(0, 0, max_row, len(fields) - 1)


# ---------------------------------------------------------------------------
# Processor class
# ---------------------------------------------------------------------------


class TDCDNWeeklyProcessor(BaseProcessor):
    PROCESSOR_NAME = "TD CDN Weekly Metals & Mining"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def process(self, input_file: str, job) -> str:
        job.message = "Initializing TD CDN Weekly Metals extraction..."
        job.progress = 10

        job.progress = 30
        job.message = "Extracting data from PDF..."

        main_rows, revision_rows = extract_pdf(str(input_file))
        job.companies_found = len(main_rows)

        job.progress = 70
        job.message = "Writing output to Excel..."

        output_name = f"TD_CDN_Weekly_Metals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = self.output_folder / output_name

        write_xlsx(main_rows, revision_rows, str(output_path))

        job.progress = 100
        job.message = "Successfully generated Excel report."
        job.output_file = output_name
        return output_name
