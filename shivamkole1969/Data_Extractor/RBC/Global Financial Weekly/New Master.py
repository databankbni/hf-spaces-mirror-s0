import re
import csv
from pathlib import Path
import camelot

PDF = 'PDF.pdf'
OUT_CSV = 'Master_Output_Final.csv'

RATING_TOKENS = {'O','SP','U','UP','NR','R','O*','SP*','U*','UP*','NR*','R*'}
CURRENCIES = {'USD','CAD','EUR','GBP','GBp','AUD','CHF','CHF1','USD2','EUR2','GBP2','GBX','USD1'}
EXCLUDED_TICKERS = {'BN', 'IAG', 'Ticker'}

TARGET_COLUMNS = [
    'Name','Ticker','Inv. Rat.','Price Target','CCY',
    'EPS 2025','EPS 2026','EPS 2027','EPS 2028',
    'BVPS 2025','BVPS 2026','BVPS 2027','BVPS 2028',
    'EBITDA 2025','EBITDA 2026','EBITDA 2027','EBITDA 2028'
]

PAGE_CONFIG = {
    2:  {'name_mode':'split0123','eps':[7,8,9]},
    3:  {'name_mode':'split012', 'eps':[6,7,8]},
    4:  {'name_mode':'split0123','eps':[7,8,9]},
    5:  {'name_mode':'split0123','eps':[7,8,9]},
    6:  {'name_mode':'split012', 'pt_col':5, 'eps':[8,9,10], 'bvps':[17,18,19]},
    7:  {'name_mode':'split0123','eps':[7,8,9]},
    8:  {'name_mode':'split012', 'eps':[6,7,8]},
    9:  {'name_mode':'split012', 'eps':[6,7,8]},
    10: {'name_mode':'split0123','eps':[7,8,9], 'ebitda':[18,19,20]},
    11: {'name_mode':'split012', 'eps':[6,7,8]},
    12: {'name_mode':'split0123','eps':[7,8,9]},
    13: {'name_mode':'split0123','eps':[7,8,9]},
}


def clean_text(x: str) -> str:
    x = (x or '').replace('\n', ' ').strip()
    x = re.sub(r'\s+', ' ', x)
    return x


def clean_num(x: str) -> str:
    x = clean_text(x)
    if x in {'', 'NA', 'N/A', 'nm', 'NM', 'na', 'n/a', '-'}:
        return ''
    # Strip currency symbols and common artifacts
    x = re.sub(r'[\$\£\€]|GBp|GBX', '', x)
    x = x.replace('%', '').replace('x', '').strip()
    return x


def split_rating_ccy_name(row0: str, row1: str, row2: str):
    row0 = clean_text(row0)
    row1 = clean_text(row1)
    row2 = clean_text(row2)

    rating = ''
    ccy = ''
    name = ''

    # Case: row0 may contain both rating and ccy, e.g. 'SP* EUR'
    parts0 = row0.split()
    if parts0 and parts0[0] in RATING_TOKENS:
        rating = parts0[0]
        if len(parts0) > 1 and parts0[1] in CURRENCIES:
            ccy = parts0[1]
            name = row2 or ' '.join(parts0[2:])
        else:
            # ccy may be embedded in row1
            if row1:
                parts1 = row1.split()
                if parts1 and parts1[0] in CURRENCIES:
                    ccy = parts1[0]
                    name = row2 or ' '.join(parts1[1:])
                else:
                    name = row1 if not row2 else row2
            else:
                name = row2
    else:
        return '', '', ''

    if not ccy and row1:
        parts1 = row1.split()
        if parts1 and parts1[0] in CURRENCIES:
            ccy = parts1[0]
            if not name:
                name = row2 or ' '.join(parts1[1:])
        elif not name:
            name = row1 if not row2 else row2

    if not name and row2:
        name = row2

    return rating, ccy, name


def parse_row(page: int, row):
    cfg = PAGE_CONFIG[page]
    vals = [clean_text(v) for v in row.tolist()]
    mode = cfg['name_mode']

    if mode == 'split0123':
        rating, ccy, name = split_rating_ccy_name(vals[0], vals[1], vals[2])
        ticker = vals[3]
        price_target = vals[5]
        # Shift detection: if ticker looks like a price and vals[2] looks like a ticker
        if re.match(r'^-?[\d\.,\$]+$', ticker) and len(vals[2]) <= 6 and vals[2].isupper():
            ticker = vals[2]
            name = vals[1]
            price_target = vals[4]
    elif mode == 'split012':
        rating, ccy, name = split_rating_ccy_name(vals[0], vals[1], '')
        ticker = vals[2]
        price_target = vals[cfg.get('pt_col', 4)]
        # Shift detection
        if re.match(r'^-?[\d\.,\$]+$', ticker) and len(vals[1].split()[-1]) <= 6 and vals[1].split()[-1].isupper():
            parts = vals[1].split()
            ticker = parts[-1]
            name = ' '.join(parts[:-1])
            price_target = vals[3]
    else:
        raise ValueError(mode)

    if not rating or not ticker or not name:
        return None
    
    if ticker in EXCLUDED_TICKERS:
        return None
    # Exclude headers/section labels/notes
    if any(h in name for h in ['Average', 'Source:', 'Exhibit', 'Canadian Banks', 'Insurance', 'Asset Managers', 'Financials']):
        # allow real companies with Financial in their names
        if name not in {'SLM Corporation','Synchrony Financial','Ally Financial Inc.','The PNC Financial Services Group, Inc.','Citizens Financial Group, Inc.','iA Financial Corporation Inc.','Manulife Financial Corporation','Sun Life Financial Inc.','The PNC Financial Services Group, Inc.'}:
            if ticker == '':
                return None

    out = {col:'' for col in TARGET_COLUMNS}
    out['Name'] = name
    out['Ticker'] = ticker
    out['Inv. Rat.'] = rating
    out['Price Target'] = clean_num(price_target)
    out['CCY'] = ccy

    eps_cols = cfg.get('eps', [])
    if len(eps_cols) >= 1: out['EPS 2025'] = clean_num(vals[eps_cols[0]])
    if len(eps_cols) >= 2: out['EPS 2026'] = clean_num(vals[eps_cols[1]])
    if len(eps_cols) >= 3: out['EPS 2027'] = clean_num(vals[eps_cols[2]])

    bvps_cols = cfg.get('bvps', [])
    if len(bvps_cols) >= 1: out['BVPS 2025'] = clean_num(vals[bvps_cols[0]])
    if len(bvps_cols) >= 2: out['BVPS 2026'] = clean_num(vals[bvps_cols[1]])
    if len(bvps_cols) >= 3: out['BVPS 2027'] = clean_num(vals[bvps_cols[2]])

    ebitda_cols = cfg.get('ebitda', [])
    if len(ebitda_cols) >= 1: out['EBITDA 2025'] = clean_num(vals[ebitda_cols[0]])
    if len(ebitda_cols) >= 2: out['EBITDA 2026'] = clean_num(vals[ebitda_cols[1]])
    if len(ebitda_cols) >= 3: out['EBITDA 2027'] = clean_num(vals[ebitda_cols[2]])

    # Final polish: replace blanks with "-"
    for col in TARGET_COLUMNS:
        if not out[col]:
            out[col] = '-'

    return out


def dedupe_rows(rows):
    seen = set()
    out = []
    for r in rows:
        key = tuple(r[c] for c in TARGET_COLUMNS)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def extract():
    all_rows = []
    for page in range(2, 14):
        tables = camelot.read_pdf(PDF, pages=str(page), flavor='stream')
        if tables.n == 0:
            continue
        df = tables[0].df
        for _, row in df.iterrows():
            parsed = parse_row(page, row)
            if parsed:
                all_rows.append(parsed)
    return dedupe_rows(all_rows)


def write_csv(rows):
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def clean_up():
    """Remove temporary scripts."""
    paths = ['dump_pdf.py', 'check_data.py', 'check_headers.py']
    for p in paths:
        path = Path(p)
        if path.exists():
            path.unlink()
            print(f"Deleted {p}")

if __name__ == '__main__':
    rows = extract()
    write_csv(rows)
    clean_up()
    print(f'Done. Total rows={len(rows)}')
