import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from services.twelve_data_service import twelve_data_service

def test_commodities():
    load_dotenv()
    # Twelve Data uses common symbols, sometimes as pairs
    test_symbols = ["XAU/USD", "XAG/USD", "LCO/USD", "WTI/USD"]
    print(f"Testing Commodities: {test_symbols}")
    
    quotes = twelve_data_service.get_quotes(test_symbols)
    print(f"Results: {quotes}")

if __name__ == "__main__":
    test_commodities()
