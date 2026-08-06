from dotenv import load_dotenv
load_dotenv()

from data_sources.woocommerce import fetch_all_products

products = fetch_all_products()
print(f"\nTotal products fetched: {len(products)}")

if products:
    print("\n=== First product sample ===")
    p = products[0]
    print("Name:", p.get("name"))
    print("Price:", p.get("price"))
    print("Stock:", p.get("stock_status"))
    print("SKU:", p.get("sku"))
else:
    print("No products fetched - check API keys or store URL")