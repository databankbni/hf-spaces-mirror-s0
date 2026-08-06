"""
ClassifierAgent - Only classifies complaints into product and issue subtype
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use action_lookup.py for issue taxonomy instead of issue_lookup.py
from action_lookup import ACTION_LOOKUP
import re
from typing import Dict, List, Tuple


class ClassifierAgent:
    def __init__(self):
        self.products = list(ACTION_LOOKUP.keys())
        # Product keywords with weights for better matching
        self.product_keywords = {
            "UPI": {
                "keywords": ["upi", "unified payment", "upi id", "upi pin", "gpay", "phonepe", "paytm", "transaction failed", "payment failed"],
                "weight": 1.0
            },
            "Credit Card": {
                "keywords": ["credit card", "creditcard", "cc", "credit limit", "credit card bill", "card statement"],
                "weight": 1.0
            },
            "Debit Card": {
                "keywords": ["debit card", "debitcard", "atm card"],
                "weight": 0.9
            },
            "ATM": {
                "keywords": ["atm", "automated teller", "atm machine", "cash withdrawal", "cash not dispensed"],
                "weight": 0.9
            },
            "Internet Banking": {
                "keywords": ["internet banking", "net banking", "online banking", "ibanking", "login issue"],
                "weight": 0.9
            },
            "Mobile Banking": {
                "keywords": ["mobile banking", "mobile app", "app", "mobile bank", "app not working"],
                "weight": 0.9
            },
            "Loans": {
                "keywords": ["loan", "emi", "personal loan", "home loan", "car loan"],
                "weight": 1.0
            },
            "Savings Account": {
                "keywords": ["savings account", "savings", "account balance", "bank account"],
                "weight": 1.0
            },
            "Current Account": {
                "keywords": ["current account", "current"],
                "weight": 0.8
            },
            "Cheque Services": {
                "keywords": ["cheque", "check", "cheque book", "bounce", "cheque bounced"],
                "weight": 1.0
            },
            "Fixed Deposit": {
                "keywords": ["fixed deposit", "fd", "fd maturity", "fixed deposit interest"],
                "weight": 1.0
            },
            "Recurring Deposit": {
                "keywords": ["recurring deposit", "rd"],
                "weight": 0.5
            },
            "Insurance": {
                "keywords": ["insurance", "policy", "claim", "insurance claim"],
                "weight": 1.0
            },
            "Demat / Trading Account": {
                "keywords": ["demat", "trading", "trading account", "share", "stock"],
                "weight": 1.0
            },
            "Forex / International Transactions": {
                "keywords": ["forex", "international", "foreign", "swift"],
                "weight": 1.0
            },
            "Wallet / Prepaid Card": {
                "keywords": ["wallet", "prepaid", "prepaid card"],
                "weight": 1.0
            },
            "Customer Service": {
                "keywords": ["customer service", "customer care", "relationship manager"],
                "weight": 1.0
            },
            "Branch Services": {
                "keywords": ["branch", "branch visit", "branch manager"],
                "weight": 1.0
            },
            "KYC / AML / Compliance": {
                "keywords": ["kyc", "aml", "compliance", "pan verification"],
                "weight": 1.0
            },
            "Pension / Government Schemes": {
                "keywords": ["pension", "government scheme", "pm kisan", "nps", "apy"],
                "weight": 1.0
            },
            "Lockers": {
                "keywords": ["locker", "bank locker"],
                "weight": 1.0
            },
            "Merchant Services / POS": {
                "keywords": ["merchant", "pos", "pos machine"],
                "weight": 1.0
            },
            "Agriculture / Priority Sector Loans": {
                "keywords": ["agriculture", "priority sector", "kisan credit card", "crop insurance"],
                "weight": 1.0
            },
            "General Service Requests": {
                "keywords": ["statement request", "cheque book request", "passbook request", "noc request", "interest certificate request"],
                "weight": 0.5
            }
        }
    
    def classify(self, complaint_text: str) -> dict:
        """
        Classify a complaint text into product and issue type with confidence
        """
        complaint_lower = complaint_text.lower()
        
        # 1. Find matching product with score
        matched_product, product_score = self._find_best_product_match(complaint_text)
        
        # 2. Find matching issue subtype with score
        matched_issue, issue_score = self._find_best_issue_match(complaint_text, matched_product)
        
        # 3. Calculate overall confidence
        overall_confidence = (product_score + issue_score) / 2
        
        # Only return product, issue_subtype, and confidence as per requirements
        return {
            "product": matched_product,
            "issue_subtype": matched_issue,
            "confidence": round(overall_confidence, 2)
        }
    
    def _find_best_product_match(self, complaint_text: str) -> Tuple[str, float]:
        """
        Find the best matching product with score (0-1)
        """
        complaint_lower = complaint_text.lower()
        best_score = 0.0
        best_product = "General Service Requests"
        
        for product, config in self.product_keywords.items():
            keywords = config["keywords"]
            weight = config["weight"]
            matches = 0
            for keyword in keywords:
                if keyword in complaint_lower:
                    matches += 1
            if keywords:
                score = (matches / len(keywords)) * weight
                if score > best_score:
                    best_score = score
                    best_product = product
        
        # Fallback: check direct product name match
        if best_score < 0.3:
            for product in self.products:
                if product.lower() in complaint_lower:
                    best_product = product
                    best_score = 0.5
                    break
        
        return best_product, best_score
    
    def _find_best_issue_match(self, complaint_text: str, product: str) -> Tuple[str, float]:
        """
        Find best matching issue subtype for a product with score (0-1)
        """
        if product not in ACTION_LOOKUP:
            return "Statement Request", 0.3
            
        issues = list(ACTION_LOOKUP[product].keys())
        complaint_lower = complaint_text.lower()
        
        best_issue = issues[0] if issues else "Statement Request"
        best_score = 0.0
        
        for issue in issues:
            issue_lower = issue.lower()
            # Split issue into words
            issue_words = re.split(r'\W+', issue_lower)
            issue_words = [w for w in issue_words if w]
            
            if not issue_words:
                continue
                
            matches = 0
            for word in issue_words:
                if word in complaint_lower:
                    matches += 1
            
            # Calculate score
            score = matches / len(issue_words)
            
            # Big bonus for exact substring match
            if issue_lower in complaint_lower:
                score += 0.5
            
            # Also check for partial match in either direction
            if complaint_lower in issue_lower:
                score += 0.3
            
            if score > best_score:
                best_score = score
                best_issue = issue
        
        return best_issue, min(best_score, 1.0)
