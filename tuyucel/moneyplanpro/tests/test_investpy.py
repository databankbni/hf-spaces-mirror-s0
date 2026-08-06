from investpy import get_stock_historical_data
import datetime

try:
    print("Fetching AAPL data from Investing.com...")
    df = get_stock_historical_data(stock='AAPL',
                                   country='United States',
                                   from_date='01/01/2023',
                                   to_date='01/01/2024')
    print(df.head())
except Exception as e:
    print(f"Error: {e}")
