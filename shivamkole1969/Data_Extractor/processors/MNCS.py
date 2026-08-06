"""
MNCS Processor
Extracts Code, Rating, and Target Price from MNCS Universe PDF reports.
Outputs a single-sheet Excel file with columns: Code, Rating, Target Price.
"""

import re
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
import pandas as pd

from processors.base import BaseProcessor


class MNCSProcessor(BaseProcessor):
    PROCESSOR_NAME = "MNCS Broker Report"
    SUPPORTED_EXTENSIONS = [".pdf"]

    VALID_RATINGS = ["BUY", "HOLD", "SELL"]

    def process(self, filepath: str, job) -> str:
        job.message = "Initializing MNCS extraction..."
        job.progress = 5

        rows = []

        job.message = "Reading PDF pages..."
        job.progress = 10

        with pdfplumber.open(filepath) as pdf:
            job.total_pages = len(pdf.pages)

            # MNCS data is typically on pages 2 & 3 (index 1 & 2)
            target_pages = [1, 2] if len(pdf.pages) > 2 else list(range(len(pdf.pages)))

            for page_num in target_pages:
                if page_num >= len(pdf.pages):
                    continue

                job.current_page = page_num + 1
                job.message = f"Scanning page {page_num + 1}..."
                job.progress = 10 + int((page_num / max(len(target_pages), 1)) * 40)

                text = pdf.pages[page_num].extract_text()
                if not text:
                    continue

                lines = text.split("\n")
                temp = ""

                for line in lines:
                    line = re.sub(r"\s+", " ", line).strip()

                    # Skip unwanted header/label lines
                    if any(x in line for x in ["MNCS UNIVERSE", "Sources:", "SECTOR", "RATING", "FY"]):
                        continue

                    # Detect start of new row (ticker like "ABCD IJ")
                    if re.match(r"^[A-Z]{3,5}\sIJ", line):
                        if temp:
                            rows.append(temp)
                        temp = line
                    else:
                        temp += " " + line

                if temp:
                    rows.append(temp)

        job.message = "Parsing extracted rows..."
        job.progress = 60

        # Extract Code + Rating + Target Price
        final_data = []

        for row in rows:
            parts = row.split()
            if not parts:
                continue

            code = parts[0]
            rating = None
            target_price = None

            # Find rating dynamically
            for i, val in enumerate(parts):
                if val in self.VALID_RATINGS:
                    rating = val

                    if i + 1 < len(parts):
                        raw_price = parts[i + 1]
                        # Convert to numeric
                        raw_price = raw_price.replace(",", "")  # remove commas
                        target_price = pd.to_numeric(raw_price, errors="coerce")

                    break

            # Keep only valid rows
            if rating and pd.notna(target_price):
                final_data.append({
                    "Code": code,
                    "Rating": rating,
                    "Target Price": target_price
                })

        df = pd.DataFrame(final_data)
        job.companies_found = len(df)
        job.progress = 80
        job.message = "Writing Excel report..."

        output_name = f"MNCS_Extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = self.output_folder / output_name

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
            ws = writer.book.active
            # Apply numeric format to Target Price column (column C)
            for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
                for cell in row:
                    cell.number_format = '#,##0'

        job.output_file = output_name
        job.progress = 100
        job.message = "MNCS extraction complete."
        return output_name
