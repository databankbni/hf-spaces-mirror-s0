import pdfplumber
from pathlib import Path
from processors.RBC_Monthly import RBCMonthlyProcessor

p = RBCMonthlyProcessor([], Path('output'))
try:
    print("RBC Monthly Software")
    df = p._extract_coverage_pt_rating('RBC/RBC Software/RBC Monthly Software/RBC Monthly Software.pdf')
    print(f"Coverage len: {len(df)}")
    df_sales = p._extract_sales_eps('RBC/RBC Software/RBC Monthly Software/RBC Monthly Software.pdf')
    print(f"Sales len (bold): {len(df_sales[df_sales['IsBold'] == 'Yes'])}")
    print(f"Sales len (all): {len(df_sales)}")
except Exception as e:
    print(f"Error: {e}")
