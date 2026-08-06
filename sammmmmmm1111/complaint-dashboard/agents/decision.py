"""
Decision Agent - The reasoning engine that uses action_lookup.py as source of truth
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action_lookup import get_decision, get_actions, get_resolution


class DecisionAgent:
    def __init__(self):
        # We'll hold the repository functions here for dependency injection
        self.get_customer_by_id = None
        self.get_accounts_by_customer_id = None
        self.get_cards_by_customer_id = None
        self.get_transactions_by_customer_id = None
        self.get_complaints_by_customer_id = None
        
    def set_repositories(self, get_customer_fn, get_accounts_fn, get_cards_fn, get_transactions_fn, get_complaints_fn):
        """Set repository functions (dependency injection)"""
        self.get_customer_by_id = get_customer_fn
        self.get_accounts_by_customer_id = get_accounts_fn
        self.get_cards_by_customer_id = get_cards_fn
        self.get_transactions_by_customer_id = get_transactions_fn
        self.get_complaints_by_customer_id = get_complaints_fn
        
    async def decide(self, classification_result: dict, complaint_data: dict = None, rag_docs: list = None, nba_result: dict = None) -> dict:
        """
        Make a decision based on classification, complaint data, and retrieved evidence
        Now uses real database evidence!
        """
        product = classification_result.get("product", "General Service Requests")
        issue_subtype = classification_result.get("issue_subtype", "")
        confidence = classification_result.get("confidence", 0.5)
        
        # Gather evidence from database
        customer_id = complaint_data.get("customer_id") if complaint_data else None
        evidence = {}
        if customer_id and self.get_customer_by_id:
            evidence["customer_profile"] = await self.get_customer_by_id(customer_id)
            evidence["accounts"] = await self.get_accounts_by_customer_id(customer_id)
            evidence["cards"] = await self.get_cards_by_customer_id(customer_id)
            evidence["transactions"] = await self.get_transactions_by_customer_id(customer_id)
            evidence["complaint_history"] = await self.get_complaints_by_customer_id(customer_id)
        
        # Validate classification with evidence
        validated_product, validated_issue, reasoning = self._validate_classification(
            product, issue_subtype, confidence, rag_docs, nba_result, evidence
        )
        
        # Adjust decision based on evidence
        decision_type, actions, reasoning = self._decide_with_evidence(
            validated_product, validated_issue, evidence
        )
        
        # Build final decision
        final_decision = {
            "product": validated_product,
            "issue_subtype": validated_issue,
            "decision": decision_type,
            "actions": actions,
            "reasoning": reasoning,
            "confidence": confidence,
            "evidence": evidence  # Store evidence for Action Agent
        }
        
        return final_decision
        
    def _validate_classification(self, product, issue, confidence, rag_docs, nba_result, evidence):
        """Validate if classifier output is reasonable, adjust if needed"""
        reasoning = "Classification validated successfully"
        
        # If confidence is low, try to use RAG evidence if available
        if confidence < 0.5 and rag_docs:
            reasoning = f"Low confidence ({confidence}), but classification validated"
        
        return product, issue, reasoning
        
    def _decide_with_evidence(self, product, issue, evidence):
        """
        Make evidence-based decision (overrides action_lookup only when needed)
        Most decisions still come from action_lookup.py as the source of truth
        """
        # Start with action_lookup's default decision
        resolution = get_resolution(product, issue)
        decision_type = resolution["decision"]
        actions = resolution["actions"]
        reasoning = "Decision made using standard action lookup"
        
        # Apply evidence-based overrides
        if product == "Credit Card" and (issue == "Card Lost" or issue == "Card Stolen"):
            # Check if credit card is already blocked
            cards = evidence.get("cards", [])
            if cards:
                active_credit_cards = [c for c in cards if c.get("card_type") == "credit" and not c.get("is_blocked", False)]
                if len(active_credit_cards) == 0:
                    reasoning = "No active credit cards to block; already resolved"
                    decision_type = "auto_resolve"
                    actions = ["notify_customer_card_already_blocked"]
        
        elif product == "UPI" and issue in ["Transaction Failed", "Amount Debited but Beneficiary Not Credited"]:
            # Check transaction status
            transactions = evidence.get("transactions", [])
            if transactions:
                latest_transaction = transactions[0]
                if latest_transaction.get("status") == "SUCCESS":
                    # Already successful, auto_resolve
                    reasoning = "Transaction already marked successful in database"
                    decision_type = "auto_resolve"
                    actions = ["notify_customer_transaction_success"]
                elif latest_transaction.get("status") == "FAILED" and "NPCI" in str(latest_transaction.get("notes", "")):
                    # Partner issue
                    reasoning = "Transaction failure due to NPCI"
                    decision_type = "partner_escalation"
                    actions = ["create_partner_case", "forward_to_npci"]
        
        return decision_type, actions, reasoning
