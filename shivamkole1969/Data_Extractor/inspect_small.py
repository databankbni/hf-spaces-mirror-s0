import pandas as pd
excel_path = r"C:\Users\skole\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Shivam\Estimates Data Extractor\EGR\EGR_Extracted by the application.xlsx"
df = pd.read_excel(excel_path)
row = df.iloc[0]
print(f"Company: {row['Company Name']}")
print(f"Rating: {row['Rating']}")
print(f"Target Price: {row['Target Price']} {row['Target Price Currency']}")
print(f"Revenue 2024: {row['Sales / Revenue 2024']}")
print(f"EBITDA 2024: {row['EBITDA 2024']}")
print(f"Net Income 2024: {row['Net Income 2024']}")
