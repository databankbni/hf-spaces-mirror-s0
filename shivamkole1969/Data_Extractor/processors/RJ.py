import re
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
from processors.base import BaseProcessor

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

class RJProcessor(BaseProcessor):
    PROCESSOR_NAME = "RJ Monthly Broker Report"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def process(self, input_file: str, job) -> str:
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is not installed.")
            
        job.message = "Initializing RJ extraction..."
        job.progress = 0
        
        try:
            # Patterns
            RATING_RE = re.compile(r'^(SB1|MO2|MP3|MU4|S)$')
            SECTOR_PATTERNS = {
                'Consumer - USA': re.compile(r'Consumer\s*-\s*USA', re.I),
                'Consumer - CAN': re.compile(r'Consumer\s*-\s*CAN', re.I),
                'Energy - USA': re.compile(r'Energy\s*-\s*USA', re.I),
                'Energy - CAN': re.compile(r'Energy\s*-\s*CAN', re.I),
                'Financial Services - USA': re.compile(r'Financial\s*Services\s*-\s*USA', re.I),
                'Financial Services - CAN': re.compile(r'Financial\s*Services\s*-\s*CAN', re.I),
                'Healthcare - USA': re.compile(r'Healthcare\s*-\s*USA', re.I),
                'Healthcare - CAN': re.compile(r'Healthcare\s*-\s*CAN', re.I),
                'Industrial - USA': re.compile(r'Industrial\s*-\s*USA', re.I),
                'Industrial - CAN': re.compile(r'Industrial\s*-\s*CAN', re.I),
                'Real Estate - USA': re.compile(r'Real\s*Estate\s*-\s*USA', re.I),
                'Real Estate - CAN': re.compile(r'Real\s*Estate\s*-\s*CAN', re.I),
                'Technology & Communications - USA': re.compile(r'Technology\s*&\s*Communications\s*-\s*USA', re.I),
                'Technology & Communications - CAN': re.compile(r'Technology\s*&\s*Communications\s*-\s*CAN', re.I),
                'Transportation - USA': re.compile(r'Transportation\s*-\s*USA', re.I),
                'Transportation - CAN': re.compile(r'Transportation\s*-\s*CAN', re.I),
                'Mining - CAN': re.compile(r'Mining\s*-\s*CAN', re.I),
                'Sustainability - CAN': re.compile(r'Sustainability\s*-\s*CAN', re.I),
            }

            def group_words_into_lines(page, y_tol=2.0):
                words = page.get_text('words')
                from collections import defaultdict
                rows = defaultdict(list)
                for x0, y0, x1, y1, word, block, line, wno in words:
                    key = round(y0 / y_tol) * y_tol
                    rows[key].append((x0, word))
                lines = []
                for y in sorted(rows.keys()):
                    row = " ".join(w for x, w in sorted(rows[y], key=lambda t: t[0]))
                    lines.append(row)
                return lines

            records = []
            with fitz.open(input_file) as doc:
                total_pages = doc.page_count
                job.total_pages = total_pages
                current_sector = None

                for i in range(total_pages):
                    job.progress = int((i / total_pages) * 90)
                    job.current_page = i + 1
                    job.message = f"Scanning page {i+1} of {total_pages}..."
                    
                    page = doc[i]
                    lines = group_words_into_lines(page)
                    page_text = "\n".join(lines)
                    
                    # Detect sector
                    for sector, pat in SECTOR_PATTERNS.items():
                        if pat.search(page_text):
                            current_sector = sector
                            
                    for ln in lines:
                        if ("Symbol" in ln and "Target" in ln) or ln.strip().startswith("52 Week"):
                            continue
                        tokens = ln.split()
                        rating_idx = -1
                        for j, t in enumerate(tokens):
                            if RATING_RE.fullmatch(t):
                                rating_idx = j
                                break
                        if rating_idx >= 2 and len(tokens) >= rating_idx + 4:
                            symbol   = tokens[rating_idx - 2]
                            exchange = tokens[rating_idx - 1]
                            rating   = tokens[rating_idx]
                            target   = tokens[rating_idx + 3]
                            
                            analyst = None
                            for t in reversed(tokens):
                                if re.fullmatch(r'[A-Za-z.]+', t):
                                    analyst = t
                                    break
                            company = " ".join(tokens[:rating_idx - 2])
                            
                            if not re.fullmatch(r'[A-Z]{1,4}', exchange):
                                continue
                            if not re.fullmatch(r'[A-Z0-9.\-]+', symbol):
                                continue
                                
                            records.append({
                                "Page"       : i + 1,
                                "Sector"     : current_sector,
                                "Company"    : company,
                                "Symbol"     : symbol,
                                "Exchange"   : exchange,
                                "Rating"     : rating,
                                "TargetPrice": target,
                                "Analyst"    : analyst
                            })

            df = pd.DataFrame(records)
            df.drop_duplicates(inplace=True)
            job.companies_found = len(df)
            
            output_name = f"RJ_Extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            output_path = self.output_folder / output_name
            df.to_excel(output_path, index=False)
            
            job.output_file = output_name
            return output_name
            
        except Exception as e:
            job.status = "error"
            job.message = f"Extraction failed: {str(e)}"
            raise e
