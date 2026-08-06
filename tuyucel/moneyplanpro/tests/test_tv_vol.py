
from tradingview_ta import TA_Handler, Interval, Exchange

handler = TA_Handler(
    symbol="THYAO",
    screener="turkey",
    exchange="BIST",
    interval=Interval.INTERVAL_1_DAY
)
analysis = handler.get_analysis()
print("Keys:", analysis.indicators.keys())
print("Volume:", analysis.indicators.get("volume"))
print("Vol:", analysis.indicators.get("Vol"))
