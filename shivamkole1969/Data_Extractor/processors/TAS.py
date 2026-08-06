import pdfplumber
import pandas as pd
import re
import time
from datetime import datetime
from processors.base import BaseProcessor

class TASProcessor(BaseProcessor):
    PROCESSOR_NAME = "TAS Daily Brief"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def _detect_fy_years(self, pdf):
        """
        Dynamically detect FY year labels from the PDF header row.
        Scans for lines like: '(RM) (RM) (RMm) FY26 FY27 FY26 FY27 ...'
        Returns a tuple of two year strings, e.g. ('26', '27').
        Falls back to current/next calendar year if not found.
        """
        fy_pattern = re.compile(r'FY(\d{2})', re.IGNORECASE)
        for page in pdf.pages[:3]:  # only check first 3 pages for headers
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                matches = fy_pattern.findall(line)
                if len(matches) >= 2:
                    # Get the first two unique years in order
                    seen = []
                    for m in matches:
                        if m not in seen:
                            seen.append(m)
                        if len(seen) == 2:
                            break
                    if len(seen) == 2:
                        return (seen[0], seen[1])
        # Fallback: use current calendar year and next year
        current_year = datetime.now().year % 100
        return (str(current_year), str(current_year + 1))

    def process(self, input_file: str, job) -> str:
        job.message = "Initializing TAS extraction..."
        job.progress = 0
        
        try:
            rows = []
            
            # FINAL REGEX (handles all cases)
            pattern = re.compile(
                r'^(\d+)\s*([A-Z0-9& ]+?)\s+'      # No + Company (handles 100ICTZONE)
                r'([\d.]+)\s+'                     # Share Price
                r'([\d.]+)\s+'                     # Target Price
                r'([-\d.]+%)\s+'                   # Upside %
                r'([A-Za-z ]+?)\s+'                # Recommendation (Buy/Sell/Hold/Accept Offer)
                r'([\d,]+)\s+'                     # Market Cap
                r'([\d.,]+|n\.a|N/A|na|-)\s+'      # Beta (can be text)
                r'([-\d.]+|n\.a|N/A|na|-)\s+'      # EPS Year 1
                r'([-\d.]+|n\.a|N/A|na|-)'         # EPS Year 2
            )

            def clean_num(x):
                if x is None:
                    return None
                x = str(x).strip().lower()
                if x in ["n.a", "na", "n/a", "-", ""]:
                    return None
                try:
                    return float(x.replace(",", ""))
                except:
                    return None

            with pdfplumber.open(input_file) as pdf:
                total_pages = len(pdf.pages)
                job.total_pages = total_pages
                
                # Dynamically detect FY years from the PDF header
                fy1, fy2 = self._detect_fy_years(pdf)
                eps_col_1 = f"EPS_FY{fy1}"
                eps_col_2 = f"EPS_FY{fy2}"
                job.message = f"Detected EPS columns: FY{fy1} / FY{fy2}. Scanning pages..."
                
                for i, page in enumerate(pdf.pages):
                    job.progress = int((i / total_pages) * 90)
                    job.current_page = i + 1
                    job.message = f"Scanning page {i+1} of {total_pages}..."
                    
                    text = page.extract_text()
                    if not text:
                        continue

                    lines = text.split("\n")
                    for line in lines:
                        line = line.strip()
                        match = pattern.match(line)
                        if match:
                            try:
                                no = int(match.group(1))
                                company = match.group(2).strip()
                                share_price = clean_num(match.group(3))
                                target_price = clean_num(match.group(4))
                                recommendation = match.group(6).strip()
                                eps_year1 = clean_num(match.group(9))
                                eps_year2 = clean_num(match.group(10))

                                rows.append([
                                    no,
                                    company,
                                    share_price,
                                    target_price,
                                    recommendation,
                                    eps_year1,
                                    eps_year2
                                ])
                            except:
                                continue
            
            job.companies_found = len(rows)
            df = pd.DataFrame(rows, columns=[
                "No",
                "Company",
                "Share_Price",
                "Target_Price",
                "Recommendation",
                eps_col_1,
                eps_col_2
            ])

            df = df.sort_values("No").reset_index(drop=True)
            
            # APPLY SCALING
            df[eps_col_1] = pd.to_numeric(df[eps_col_1], errors='coerce') * 0.01
            df[eps_col_2] = pd.to_numeric(df[eps_col_2], errors='coerce') * 0.01

            output_name = f"TAS_Extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            output_path = self.output_folder / output_name
            df.to_excel(output_path, index=False)
            
            job.progress = 100
            job.message = f"Successfully generated Excel report. (EPS: FY{fy1} / FY{fy2})"
            job.output_file = output_name
            return output_name

        except Exception as e:
            job.status = "error"
            job.message = f"Extraction failed: {str(e)}"
            raise e
