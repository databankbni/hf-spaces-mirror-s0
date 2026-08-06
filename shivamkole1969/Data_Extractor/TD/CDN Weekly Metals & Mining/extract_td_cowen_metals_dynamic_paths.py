#!/usr/bin/env python3
"""
Extract TD Cowen weekly Metals & Mining PDF data.

This consolidated script extracts:
1) PRECIOUS METALS company table rows.
2) BASE METALS company table rows.
3) TD Cowen Precious Metals Price Forecast mini-table.
4) TD Cowen Base Metals Price Forecast mini-table.
5) Figure/Table titled "TD Cowen EPS and CFPS Revisions" into a second table.

Important business rules implemented:
- Skip any table/page where SPOT COMPS or Spot Prices are mentioned.
- For commodity forecast mini-tables, commodity name is used as company_name and ticker.
- Forecast fiscal years are placed into EPS columns; LT is placed under target_price.
- Base metals company tickers that are not printed in the table are hardcoded in the script.
- Blank output cells are written as "-".
- The EPS/CFPS revisions output captures NEW values only by fiscal year.
- Page number is NOT hardcoded. The script scans every page and dynamically finds table titles.

Output:
- If output path ends with .xlsx: creates an Excel workbook with two sheets:
    Sheet 1: Metals Data
    Sheet 2: EPS CFPS Old new
- If output path ends with .csv: creates the main CSV plus a second CSV named
    <output_stem>_eps_cfps_old_new.csv
  because CSV files cannot contain multiple sheets.

Dependency:
    pip install pymupdf

Usage examples:
    # Recommended: pass input/output paths in command line
    python extract_td_cowen_metals_dynamic_paths.py --input-file "TD Precious metals.pdf" --output-file td_cowen_output.xlsx

    # Positional path style also works
    python extract_td_cowen_metals_dynamic_paths.py "TD Precious metals.pdf" td_cowen_output.xlsx

    # Or edit INPUT_FILE_PATH and OUTPUT_FILE_PATH below, then run without args
    python extract_td_cowen_metals_dynamic_paths.py
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import pandas as pd

try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise SystemExit("Missing dependency: pip install pymupdf") from exc

# =====================================================================
# USER PATH CONFIGURATION
# =====================================================================
# Option 1: Edit these two paths and run the script without command-line args:
#     python extract_td_cowen_metals_dynamic.py
#
# Option 2: Leave them blank and pass paths at runtime:
#     python extract_td_cowen_metals_dynamic_paths.py --input-file "input.pdf" --output-file "output.xlsx"
#     python extract_td_cowen_metals_dynamic_paths.py "input.pdf" "output.xlsx"
#
# Use raw strings (prefix r) for Windows paths. Examples:
# INPUT_FILE_PATH = r"C:\Users\your.name\Documents\TD Precious metals.pdf"
# OUTPUT_FILE_PATH = r"C:\Users\your.name\Documents\td_cowen_output.xlsx"
#
# Output recommendation:
#   - Use .xlsx when you want both sheets in one file.
#   - Use .csv when you want separate CSV files.
INPUT_FILE_PATH = r""
OUTPUT_FILE_PATH = r""

YEARS = [str(y) for y in range(2025, 2031)]

# Base-metals table does not print tickers in the main comp table.
# These are hardcoded from known exchange tickers used in the TD universe.
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

# Tickers for the EPS/CFPS Revisions table, which usually prints company names only.
REVISION_TICKER_MAP = {
    "b2gold": "BTO",
    "b2gold corp.": "BTO",
    "equinox gold": "EQX",
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


def normalize_key(text: str) -> str:
    """Normalize text for dictionary matching."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_company_name(text: str) -> str:
    """Remove footnote markers while keeping legal suffixes and punctuation."""
    text = (text or "").replace("\u00a0", " ").strip()
    text = re.sub(r"[\*\^]+", "", text)
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("Entre\u0301e", "Entree")
    return text


def empty_main_row() -> Dict[str, str]:
    return {field: "" for field in MAIN_OUTPUT_FIELDS}


def empty_revision_row() -> Dict[str, str]:
    return {field: "" for field in REVISION_OUTPUT_FIELDS}


def group_words_into_lines(words: Iterable[Tuple]) -> List[Dict]:
    """Group PyMuPDF words into approximate horizontal text lines."""
    buckets: Dict[float, List[Tuple]] = defaultdict(list)
    for w in words:
        x0, y0, x1, y1, text, *_ = w
        key = round(y0 / 0.7) * 0.7
        buckets[key].append(w)

    lines = []
    for y, ws in sorted(buckets.items()):
        ws = sorted(ws, key=lambda w: w[0])
        text = " ".join(w[4] for w in ws)
        lines.append({"y": y, "words": ws, "text": text})
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
    return value.strip()


def page_has_spot_comps(page_text: str) -> bool:
    upper = (page_text or "").upper()
    return "SPOT COMPS" in upper or "SPOT PRICES USED" in upper or "SPOT PRICES:" in upper


def extract_precious_forecast(page, source_pdf: str, page_num: int) -> List[Dict[str, str]]:
    rows = []
    lines = group_words_into_lines(page.get_text("words"))
    cols = {
        "name": (310, 345),
        "2026": (345, 370),
        "2027": (370, 400),
        "LT": (400, 430),
    }
    for line in lines:
        if not (35 <= line["y"] <= 58):
            continue
        name = clean_cell(cell_text(line, *cols["name"]))
        if normalize_key(name) not in {"gold", "silver"}:
            continue
        row = empty_main_row()
        row["company_name"] = clean_company_name(name)
        row["ticker"] = row["company_name"]
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
        row["ticker"] = name
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
            # Precious main comp table columns after EPS are EBITDA, not CFPS.
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


def find_revision_header_line(lines: List[Dict]) -> Dict | None:
    for line in lines:
        words_text = [w[4] for w in line["words"]]
        lower = [t.lower() for t in words_text]
        if "company" in lower and lower.count("old") >= 4 and lower.count("new") >= 4:
            return line
    return None


def extract_eps_cfps_revisions(page, source_pdf: str, page_num: int) -> List[Dict[str, str]]:
    """Extract NEW EPS/CFPS revision values only from the revisions table."""
    rows: List[Dict[str, str]] = []
    lines = group_words_into_lines(page.get_text("words"))
    header = find_revision_header_line(lines)
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
    # Boundaries are derived from the printed Old/New header positions, making the
    # extraction independent of page number and tolerant to small layout shifts.
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

        # Keep only genuine data rows.
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


def output_cell(value: str | None) -> str:
    value = "" if value is None else str(value).strip()
    return value if value else "-"


def write_xlsx(
    main_rows: List[Dict[str, str]],
    revision_rows: List[Dict[str, str]],
    out_path: str,
) -> None:
    sheets = [
        ("Metals Data", main_rows, MAIN_OUTPUT_FIELDS),
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


def resolve_paths(args) -> Tuple[Path, Path]:
    """Resolve input/output paths from named args, positional args, or the USER PATH CONFIGURATION section."""
    input_path = args.input_file or args.pdf or INPUT_FILE_PATH
    output_path = args.output_file or args.output or OUTPUT_FILE_PATH

    if not input_path or not output_path:
        raise SystemExit(
            "Input/output path missing. Either pass both paths at runtime:\n"
            "  python extract_td_cowen_metals_dynamic.py \"input.pdf\" \"output.xlsx\"\n"
            "or edit INPUT_FILE_PATH and OUTPUT_FILE_PATH near the top of the script."
        )

    pdf_path = Path(input_path).expanduser()
    out_path = Path(output_path).expanduser()

    if not pdf_path.exists():
        raise SystemExit(f"Input PDF not found: {pdf_path}")

    if out_path.suffix.lower() != ".xlsx":
        raise SystemExit("Output must end with .xlsx")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    return pdf_path, out_path


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract TD Cowen metals data from PDF.")
    parser.add_argument(
        "pdf",
        nargs="?",
        default=None,
        help="Input TD Cowen weekly metals PDF. Optional if INPUT_FILE_PATH is set in the script.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output path. Use .xlsx for output. Optional if OUTPUT_FILE_PATH is set.",
    )
    parser.add_argument(
        "-i",
        "--input-file",
        dest="input_file",
        default=None,
        help="Input PDF file path. Overrides INPUT_FILE_PATH and positional PDF path.",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        dest="output_file",
        default=None,
        help="Output file path (.xlsx recommended). Overrides OUTPUT_FILE_PATH and positional output path.",
    )
    args = parser.parse_args(argv)

    pdf_path, out_path = resolve_paths(args)
    main_rows, revision_rows = extract_pdf(str(pdf_path))

    write_xlsx(main_rows, revision_rows, str(out_path))
    print(f"Extracted {len(main_rows)} Metals Data rows and {len(revision_rows)} EPS/CFPS revision rows to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
