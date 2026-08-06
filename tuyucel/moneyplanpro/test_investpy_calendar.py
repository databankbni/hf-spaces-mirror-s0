import investpy
import datetime

try:
    data = investpy.economic_calendar(countries=['united states', 'turkey'])
    print(data.head())
except Exception as e:
    print(f"Error: {e}")
