# constants.py

BANK_PRODUCTS = [
    "UPI",
    "Credit Card",
    "Debit Card",
    "ATM",
    "Internet Banking",
    "Mobile Banking",
    "Loans",
    "Savings Account",
    "Current Account",
    "Cheque Services",
    "Fixed Deposit",
    "Recurring Deposit",
    "Insurance",
    "Demat / Trading Account",
    "Forex / International Transactions",
    "Wallet / Prepaid Card",
    "NEFT / RTGS / IMPS",
    "Customer Service",
    "Branch Services",
    "KYC / AML / Compliance",
    "Pension / Government Schemes",
    "Lockers",
    "Business Banking / Current Account",
    "Merchant Services / POS",
    "Agriculture / Priority Sector Loans"
]

SLA_DAYS = {
    "Critical": 1,
    "High": 3,
    "Medium": 7,
    "Low": 15
}

SIMILARITY_CONFIG = {
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "vector_store": "FAISS",
    "similarity_metric": "cosine",
    "duplicate_threshold": 0.92,
    "related_threshold": 0.78,
    "cluster_window_days": 7
}
