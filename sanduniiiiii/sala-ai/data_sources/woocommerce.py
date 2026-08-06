"""
Sala AI - WooCommerce Data Source
Fetches products from sala.lk via WooCommerce REST API
"""
import os
import re
import logging
import requests
from langchain_core.documents import Document

log = logging.getLogger("SalaAI")

CONSUMER_KEY = os.environ.get("WOOCOMMERCE_CONSUMER_KEY", "")
CONSUMER_SECRET = os.environ.get("WOOCOMMERCE_CONSUMER_SECRET", "")
STORE_URL = os.environ.get("WOOCOMMERCE_URL", "https://sala.lk")


def clean_html(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def fetch_all_products() -> list:
    """Fetch all products from WooCommerce, paginated."""
    all_products = []
    page = 1
    while True:
        try:
            response = requests.get(
                f"{STORE_URL}/wp-json/wc/v3/products",
                params={
                    "per_page": 100,
                    "page": page,
                },
                # NEW: send credentials as an HTTP Basic Auth header instead of
                # URL query-string parameters. Some hosting firewalls (Wordfence,
                # ModSecurity, etc.) flag consumer_key/consumer_secret appearing
                # in the URL as a suspicious pattern and block the request with
                # a 403 before it ever reaches WordPress. This avoids that.
                auth=(CONSUMER_KEY, CONSUMER_SECRET),
                timeout=30,
            )
            if response.status_code != 200:
                log.error(f"WooCommerce API error: {response.status_code}")
                break
            batch = response.json()
            if not batch:
                break
            all_products.extend(batch)
            log.info(f"WooCommerce page {page}: {len(batch)} products")
            page += 1
        except Exception as e:
            log.error(f"WooCommerce fetch error: {e}")
            break
    return all_products


def products_to_documents(products: list) -> list[Document]:
    """
    Convert raw WooCommerce product dicts into LangChain Documents for embedding.
    Long descriptions (including artwork/design detail text) are NOT truncated -
    they're kept in full so the AI has complete product knowledge.
    """
    docs = []
    for p in products:
        full_description = clean_html(p.get("description", ""))
        short_description = clean_html(p.get("short_description", ""))
        if full_description and short_description and full_description != short_description:
            description = f"{short_description}\n\n{full_description}"
        else:
            description = full_description or short_description

        stock = "තිබෙනවා" if p.get("stock_status") == "instock" else "නෑ"
        category_list = [c["name"] for c in p.get("categories", [])]
        categories = ", ".join(category_list)

        text = f"""නම: {p.get('name', '')}
මිල: Rs. {p.get('price', 'N/A')}
Stock: {stock}
Category: {categories}
SKU: {p.get('sku', 'N/A')}
විස්තරය: {description if description else 'N/A'}""".strip()

        docs.append(
            Document(
                page_content=text,
                metadata={
                    "id": str(p["id"]),
                    "name": p["name"],
                    "price": str(p.get("price", "")),
                    "stock": p.get("stock_status", ""),
                    "category": categories.lower(),
                },
            )
        )
    return docs


def fetch_reviews(product_id: int) -> list:
    """Fetch reviews for a specific product (for Phase 2 - sentiment analysis)."""
    try:
        response = requests.get(
            f"{STORE_URL}/wp-json/wc/v3/products/reviews",
            params={
                "product": product_id,
                "per_page": 50,
            },
            auth=(CONSUMER_KEY, CONSUMER_SECRET),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log.error(f"Reviews fetch error for product {product_id}: {e}")
        return []