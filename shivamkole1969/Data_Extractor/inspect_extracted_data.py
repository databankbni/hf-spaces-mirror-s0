import pandas as pd
import os

excel_path = r"C:\Users\skole\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Shivam\Estimates Data Extractor\EGR\EGR_Extracted by the application.xlsx"

print(f"Inspecting Excel: {excel_path}")
try:
    df = pd.read_excel(excel_path)
    print(f"Total Companies found in Excel: {len(df)}")
    print("\nColumns Extracted:")
    print(df.columns.tolist())
    
    print("\nSample Rows for Comparison:")
    # Selecting first 3 companies for detailed comparison
    cols_to_check = ['Company Name', 'Rating', 'Target Price', 'Target Price Currency', 'Sales / Revenue 2024', 'EBITDA 2024', 'Net Income 2024']
    cols_present = [c for c in cols_to_check if c in df.columns]
    print(df[cols_present].head(3).to_string(index=False))

    # Identify the first company from the list to look up in PDF
    first_company = df['Company Name'].iloc[0]
    print(f"\n--- VERIFICATION TARGET: {first_company} ---")

except Exception as e:
    print(f"Error reading Excel: {e}")
