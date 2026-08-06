import pandas as pd
import os

folder = r"C:\Users\skole\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Shivam\Estimates Data Extractor\output"
files = [f for f in os.listdir(folder) if f.startswith("EGR_Extracted_") and f.endswith(".xlsx")]
files.sort()
latest_file = os.path.join(folder, files[-1])

print(f"Reading {latest_file}...")
df = pd.read_excel(latest_file)
print("Columns:", df.columns.tolist())
print("\nFirst 3 rows of company data:")
print(df[['Company Name', 'Rating', 'Target Price', 'Target Price Currency', 'Sales / Revenue 2024', 'EBITDA 2024']].head(3))
