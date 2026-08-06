import pdfplumber
import pandas as pd
import os
import re


def extract_financial_data(pdf_path):
    """
    Extracts Targets, EPS, CFPS, and Commodity Price Deck Assumptions.
    Fully dynamic: year columns, commodity header years, and all ticker formats
    are detected at runtime from the PDF content.
    """
    targets_data = []
    eps_data = []
    cfps_data = []
    commodity_data = []

    current_state = None
    commodity_years = []          # detected dynamically from Figure 6 header
    dynamic_eps_years = []
    dynamic_cfps_years = []
    commodity_section = None      # 'CG' or 'FWD' – which sub-section we are in

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split('\n')
            for line in lines:

                # ── State machine: decide which table we are scanning ──────────
                if re.search(r'Figure\s+3\b', line) or re.search(r'Figure\s+16\b', line):
                    current_state = 'TARGETS'
                    continue

                elif re.search(r'Figure\s+10\b', line) and 'Earnings' in line:
                    current_state = 'EPS'
                    dynamic_eps_years = []
                    continue

                elif re.search(r'Figure\s+11\b', line) and 'Cash Flow' in line:
                    current_state = 'CFPS'
                    dynamic_cfps_years = []
                    continue

                elif re.search(r'Figure\s+6\b', line) and 'Deck' in line:
                    current_state = 'COMMODITY'
                    commodity_section = None
                    commodity_years = []
                    continue

                # End commodity when we hit the source line or next figure
                elif current_state == 'COMMODITY' and re.search(
                        r'Source:\s+FactSet', line, re.IGNORECASE):
                    current_state = None
                    continue

                # Any new Figure header resets state (except the ones we handle)
                elif re.search(r'Figure\s+\d+\b', line) and current_state not in (None,):
                    if not any(re.search(p, line) for p in [
                        r'Figure\s+3\b', r'Figure\s+16\b',
                        r'Figure\s+10\b', r'Figure\s+11\b', r'Figure\s+6\b'
                    ]):
                        current_state = None
                    continue

                if current_state is None:
                    continue

                # ── TARGETS ────────────────────────────────────────────────────
                if current_state == 'TARGETS':
                    # Match tickers like WPM-TSX, K-TSX, RGLD-NASDAQ etc.
                    ticker_match = re.search(r'\b([A-Z0-9]{1,8})\s*-\s*[A-Z]+\b', line)
                    if ticker_match:
                        ticker = ticker_match.group(1)
                        after_ticker = line[ticker_match.end():]

                        rating_match = re.search(
                            r'\b(BUY|HOLD|SELL|SPEC(?:\.?\s*)BUY|R)\b',
                            after_ticker, re.IGNORECASE
                        )
                        if rating_match:
                            rating = re.sub(
                                r'\s+', ' ',
                                rating_match.group(1).upper().replace('.', '')
                            ).strip()

                            after_rating = after_ticker[rating_match.end():]

                            price_match = re.search(
                                r'(?:C\$|US\$|\$)?\s*([0-9,]+\.\d{2}|\b[0-9]+\b|\bR\b)',
                                after_rating, re.IGNORECASE
                            )
                            if price_match:
                                target_price = price_match.group(1).replace(',', '').upper()
                                targets_data.append({
                                    'Ticker': ticker,
                                    'Rating': rating,
                                    'Target Price': target_price,
                                })

                # ── EPS / CFPS ─────────────────────────────────────────────────
                elif current_state in ('EPS', 'CFPS'):
                    # Detect year header row dynamically
                    # We look for a line that has 3+ four-digit years (20xx)
                    years_found = re.findall(r'\b(20[2-9]\d)\b', line)
                    if current_state == 'EPS' and not dynamic_eps_years and len(years_found) >= 3:
                        seen = {}
                        dynamic_eps_years = [
                            y for y in years_found if not (y in seen or seen.update({y: 1}))
                        ][:3]
                    elif current_state == 'CFPS' and not dynamic_cfps_years and len(years_found) >= 3:
                        seen = {}
                        dynamic_cfps_years = [
                            y for y in years_found if not (y in seen or seen.update({y: 1}))
                        ][:3]

                    years = dynamic_eps_years if current_state == 'EPS' else dynamic_cfps_years
                    if len(years) < 3:
                        continue   # haven't seen the header yet

                    tokens = line.split()
                    # Find first $ token index
                    dollar_index = next(
                        (i for i, t in enumerate(tokens) if '$' in t and not t.startswith('(')),
                        -1
                    )

                    if dollar_index >= 2:
                        # Prefer the token immediately before the $ price as the ticker
                        # In EPS/CFPS tables: Company  Ticker  C$/sh  US$/sh  val1 val2 val3 ...
                        # The ticker is at dollar_index - 1 (US$/sh position),
                        # but it's actually the share-price column.
                        # The real ticker is at index 1 (second token after company name).
                        # Use a flexible approach: find last uppercase-only token before dollar_index.
                        ticker = None
                        for idx in range(dollar_index - 1, 0, -1):
                            if re.match(r'^[A-Z0-9]{1,8}$', tokens[idx]):
                                ticker = tokens[idx]
                                break

                        if ticker:
                            try:
                                val_1 = tokens[dollar_index + 2]
                                val_2 = tokens[dollar_index + 3]
                                val_3 = tokens[dollar_index + 4]

                                row = {
                                    'Ticker': ticker,
                                    years[0]: val_1,
                                    years[1]: val_2,
                                    years[2]: val_3,
                                }
                                if current_state == 'EPS':
                                    eps_data.append(row)
                                else:
                                    cfps_data.append(row)
                            except IndexError:
                                pass

                # ── COMMODITY ──────────────────────────────────────────────────
                elif current_state == 'COMMODITY':

                    # Detect the sub-section header
                    if 'CG Price Deck' in line:
                        commodity_section = 'CG'
                        continue
                    if 'Daily Fwd Curve' in line:
                        commodity_section = 'FWD'
                        continue

                    # Detect dynamic year columns from the header row
                    # Format: "2025 2026 2027 2028 2029 2030 2031+LT"
                    if not commodity_years:
                        raw_years = re.findall(r'(20[2-9]\d(?:\+LT)?)', line)
                        if len(raw_years) >= 5:
                            commodity_years = raw_years

                    if commodity_section is None or not commodity_years:
                        continue

                    # Only capture CG Price Deck rows (Gold, Silver, Copper)
                    if commodity_section != 'CG':
                        continue

                    # Match lines starting with Gold / Silver / Copper
                    m = re.match(
                        r'^(Gold|Silver|Copper)\s+(US\$/oz|US\$/lb)\s+(.+)$', line
                    )
                    if m:
                        commodity_name = m.group(1)
                        unit = m.group(2)
                        values_str = m.group(3).strip()

                        # Extract numeric values: handle $3,436 $4,758 etc.
                        values = re.findall(
                            r'\(?\$?[\d,]+\.?\d*\)?', values_str
                        )
                        # Clean up: remove $ and commas
                        values = [v.replace('$', '').replace(',', '') for v in values]

                        # Build row mapping year -> value
                        # Number of values should match number of years
                        row = {'Commodity': commodity_name, 'Unit': unit}
                        for col_idx, col_name in enumerate(commodity_years):
                            col_label = col_name  # e.g. "2025", "2031+LT"
                            row[col_label] = values[col_idx] if col_idx < len(values) else ''

                        # Add a clean LT column (last year value)
                        if commodity_years:
                            last_year = commodity_years[-1]
                            row['LT'] = row.get(last_year, '')

                        commodity_data.append(row)

    # ── Convert to DataFrames ────────────────────────────────────────────────
    df_targets = pd.DataFrame(targets_data)
    df_eps = pd.DataFrame(eps_data)
    df_cfps = pd.DataFrame(cfps_data)
    df_commodity = pd.DataFrame(commodity_data)

    # Drop duplicates keeping first occurrence
    if not df_targets.empty:
        df_targets.drop_duplicates(subset=['Ticker'], inplace=True, keep='first')
        df_targets.reset_index(drop=True, inplace=True)
    if not df_eps.empty:
        df_eps.drop_duplicates(subset=['Ticker'], inplace=True, keep='first')
        df_eps.reset_index(drop=True, inplace=True)
    if not df_cfps.empty:
        df_cfps.drop_duplicates(subset=['Ticker'], inplace=True, keep='first')
        df_cfps.reset_index(drop=True, inplace=True)
    if not df_commodity.empty:
        df_commodity.drop_duplicates(subset=['Commodity'], inplace=True, keep='first')
        df_commodity.reset_index(drop=True, inplace=True)

    return df_targets, df_eps, df_cfps, df_commodity


def process_daily_report(pdf_filepath, output_dir):
    """
    Runs the extraction and saves data into 4 distinct sheets.
    """
    print(f"Processing: {pdf_filepath}...")
    df_targets, df_eps, df_cfps, df_commodity = extract_financial_data(pdf_filepath)

    if df_targets.empty and df_eps.empty and df_cfps.empty and df_commodity.empty:
        print("No data extracted. Please check the PDF layout or file path.")
        return

    base_name = os.path.splitext(os.path.basename(pdf_filepath))[0]
    output_filename = os.path.join(output_dir, f"{base_name}_Extracted_Data.xlsx")

    with pd.ExcelWriter(output_filename, engine='openpyxl') as writer:
        if not df_targets.empty:
            df_targets.to_excel(writer, sheet_name='Recs and Targets', index=False)
            print(f"  Recs and Targets: {len(df_targets)} rows")
        if not df_eps.empty:
            df_eps.to_excel(writer, sheet_name='EPS', index=False)
            print(f"  EPS: {len(df_eps)} rows, columns: {list(df_eps.columns)}")
        if not df_cfps.empty:
            df_cfps.to_excel(writer, sheet_name='CFPS', index=False)
            print(f"  CFPS: {len(df_cfps)} rows, columns: {list(df_cfps.columns)}")
        if not df_commodity.empty:
            df_commodity.to_excel(writer, sheet_name='Commodity', index=False)
            print(f"  Commodity: {len(df_commodity)} rows, columns: {list(df_commodity.columns)}")

    print(f"\nSuccess! Saved to: {output_filename}")
    return output_filename


if __name__ == "__main__":
    # ── Paths ────────────────────────────────────────────────────────────────
    # When running locally, update WORK_DIR to your folder.
    # The script auto-detects whether it's running in the Claude environment.
    CLAUDE_PDF = "/mnt/user-data/uploads/Daily_Gold.pdf"
    LOCAL_WORK_DIR = r"C:\Users\asarkar\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Canadian Estimates\Daily Gold Automation"

    if os.path.exists(CLAUDE_PDF):
        pdf_path = CLAUDE_PDF
        out_dir = "/mnt/user-data/outputs"
        os.makedirs(out_dir, exist_ok=True)
    else:
        pdf_path = os.path.join(LOCAL_WORK_DIR, "Daily Gold.pdf")
        out_dir = LOCAL_WORK_DIR

    if os.path.exists(pdf_path):
        process_daily_report(pdf_path, out_dir)
    else:
        print(f"File not found: {pdf_path}")