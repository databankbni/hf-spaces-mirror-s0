# Estimates Data Extractor - Data Points List

## Master Data Points Reference

This file defines all the data points to be extracted from broker research reports.
Each data point has specific rules for extraction and column formatting in the output Excel.

---

### 1. Company Name
- **Column**: `Company Name`
- **Rule**: Row identifier. Each company gets one row.

### 2. Symbol / Ticker Code
- **Column**: `Ticker`
- **Rule**: Stock ticker/symbol as mentioned in the report.

### 3. Exchange Code
- **Column**: `Exchange`
- **Rule**: Exchange where the stock is listed (e.g., XETRA, NYSE, LSE).

### 4. Analyst
- **Column**: `Analyst`
- **Rule**: Name of the analyst who authored the report/section.

### 5. Rating / Recommendation
- **Column**: `Rating`
- **Rule**: Buy/Hold/Sell or equivalent recommendation.

### 6. Target Price & Currency
- **Columns**: `Target Price`, `Target Price Currency`
- **Rule**: Numeric target price and its currency in separate columns.

### 7. Financial Year End
- **Column**: `FY End`
- **Rule**: The company's financial year end date (e.g., 31.12.2025).

### 8. Estimate / Financial Data Currency
- **Column**: `Data Currency`
- **Rule**: Currency in which financial data is reported (e.g., EUR mn).

### 9. Sales / Revenue
- **Column Pattern**: `Sales YYYY` for full year, `Sales Q1-YYYY`, `Sales Q2-YYYY`, etc. for quarters
- **Rule**: Follow the **Rule of Financial Data Points**:
  - If revenue available for multiple years (e.g., 2025-2029), create columns: `Sales 2025`, `Sales 2026`, ..., `Sales 2029`
  - If quarters are available, add quarterly columns before the full year: `Sales Q1-2025`, `Sales Q2-2025`, `Sales Q3-2025`, `Sales Q4-2025`, then `Sales 2025`
  - Applies to all years where data is available
  - Collect: 1 actual/recent reported year + up to next 4 estimated years

### 10. EBITDA
- **Column Pattern**: `EBITDA YYYY`
- **Rule**: Fiscal years only. **Exclude** Adjusted/Underlying EBITDA.
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 11. EBIT
- **Column Pattern**: `EBIT YYYY`
- **Rule**: Fiscal years only. **Exclude** Adjusted/Underlying EBIT.
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 12. Pretax Income / Profit Before Tax
- **Column Pattern**: `Pretax Adjusted YYYY`, `Pretax Reported YYYY`
- **Rule**: Adjusted/Operating/Non-GAAP and GAAP/Reported are in **different columns**.
  - Example: `Pretax Adjusted 2025`, `Pretax Adjusted 2026`, ..., `Pretax Reported 2025`, `Pretax Reported 2026`, ...
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 13. Tax Rate
- **Column Pattern**: `Tax Rate YYYY`
- **Rule**: 
  - If "NM" is mentioned, **do not take** those values.
  - If Pretax > Net Income, **do not take** the tax rate.
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 14. Net Income / Profit After Tax
- **Column Pattern**: `Net Income Adjusted YYYY`, `Net Income Reported YYYY`
- **Rule**: Adjusted/Operating/Non-GAAP and GAAP/Reported are in **different columns** (same rule as Pretax).
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 15. EPS Adjusted / Non-GAAP / Operating EPS
- **Column Pattern**: `EPS Adj YYYY` for full year, `EPS Adj Q1-YYYY`, etc. for quarters
- **Rule**: Follow the **Rule of Financial Data Points** (same as Sales).
  - Quarters and Fiscal/Full years both applicable.
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 16. EPS GAAP / Reported
- **Column Pattern**: `EPS Reported YYYY` for full year, `EPS Rep Q1-YYYY`, etc. for quarters
- **Rule**: Follow the **Rule of Financial Data Points** (same as Sales).
  - Quarters and Fiscal/Full years both applicable.
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 17. Dividend / Distribution Per Unit / DPS
- **Column Pattern**: `DPS YYYY`
- **Rule**: Fiscal years only (no quarters).
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 18. Capex / Capital Expenditure
- **Column Pattern**: `Capex YYYY`
- **Rule**: Fiscal years only (no quarters).
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 19. Book Value Per Share / BVPS
- **Column Pattern**: `BVPS YYYY`
- **Rule**: Fiscal years only. **Do NOT take** Adjusted or Tangible Book Value Per Share.
- Collect: 1 actual/recent reported year + up to next 4 estimated years

### 20. CFPS (Cash Flow Per Share)
- **Column Pattern**: `CFPS YYYY`
- **Rule**: 
  - **Only take**: CFPS, FFOPS (Funds From Operations Per Share), CPS (Cash Per Share)
  - **Do NOT take**: Adjusted CFPS, Operating CFPS, FCFPS (Free Cash Flow PS), DCFPS (Distributable CFPS)
- Collect: 1 actual/recent reported year + up to next 4 estimated years

---

## General Rules

1. **Year Collection Rule**: 1 actual/recent reported year + up to next 4 estimated years
2. **Quarter Rule**: Only applies to Sales, EPS Adjusted, and EPS Reported
3. **Column Ordering**: Company Name → Ticker → Exchange → Analyst → Rating → Target Price → Target Price Currency → FY End → Data Currency → [Financial Data Points by Year]
4. **Row Structure**: Each company occupies one row
