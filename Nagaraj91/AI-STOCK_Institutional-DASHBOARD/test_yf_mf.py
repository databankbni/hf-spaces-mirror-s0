import yfinance as yf

ticker = "0P0000JXIT.BO"
fund = yf.Ticker(ticker)

print("INFO keys:", fund.info.keys() if fund.info else "None")
print("Top holdings:", fund.info.get('holdings'))
print("Fund data:", getattr(fund, 'funds_data', None))

try:
    if hasattr(fund, 'funds_data') and fund.funds_data:
        print("funds_data top holdings:", fund.funds_data.top_holdings)
except Exception as e:
    print("Error accessing funds_data:", e)
