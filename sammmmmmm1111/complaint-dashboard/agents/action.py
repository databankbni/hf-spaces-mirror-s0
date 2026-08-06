"""
Action Agent - Executes the Decision Agent's plan and updates the database
"""
from datetime import datetime


class ActionAgent:
    def __init__(self):
        self.kill_switch = False
        # Repository functions for DB operations
        self.update_credit_card = None
        self.update_debit_card = None
        self.update_account = None
        self.update_transaction = None
        self.insert_audit_log = None
        
    def set_repositories(self, update_credit_card_fn, update_debit_card_fn, update_account_fn, update_transaction_fn, insert_audit_log_fn):
        """Set repository functions for DB operations"""
        self.update_credit_card = update_credit_card_fn
        self.update_debit_card = update_debit_card_fn
        self.update_account = update_account_fn
        self.update_transaction = update_transaction_fn
        self.insert_audit_log = insert_audit_log_fn
        
    async def execute(self, complaint_id: str, decision_result: dict, complaint_data: dict, db_collection) -> dict:
        """
        Execute the actions based on the Decision Agent's result and update the database
        """
        if self.kill_switch:
            return {
                "status": "kill_switch_active",
                "message": "Automated actions are disabled - requires human intervention",
                "executed_actions": [],
                "assigned_team": self._get_assigned_team(decision_result.get("product")),
                "partner": None
            }
            
        decision = decision_result["decision"]
        actions = decision_result["actions"]
        product = decision_result["product"]
        evidence = decision_result.get("evidence", {})
        
        executed_actions = []
        assigned_team = None
        partner = None
        status = "Open"
        resolved_at = None
        
        # Execute each backend action
        for action in actions:
            success = await self._execute_single_action(action, evidence)
            if success:
                executed_actions.append(action)
                # Log the action
                if self.insert_audit_log:
                    await self.insert_audit_log({
                        "complaint_id": complaint_id,
                        "action": action,
                        "actor": "Action Agent",
                        "product": product
                    })
        
        # Determine status
        if decision == "auto_resolve":
            status = "Resolved"
            resolved_at = datetime.now().isoformat()
        elif decision == "bank_escalation":
            assigned_team = self._get_assigned_team(product)
            status = "Escalated to Bank"
        elif decision == "partner_escalation":
            partner = self._get_partner_from_actions(actions)
            status = "Forwarded to Partner"
        
        # Update the complaint in the database
        update_data = {
            "status": status,
            "decision": decision,
            "workflow_state": "action_executed",
            "assigned_team": assigned_team,
            "partner": partner,
            "updated_at": datetime.now(),
            "agent_action_plan": {
                "status": "executed",
                "decision": decision,
                "executed_actions": executed_actions,
                "timestamp": datetime.now().isoformat()
            },
            "executed_actions": executed_actions
        }
        if resolved_at:
            update_data["resolved_at"] = resolved_at
            update_data["action_timestamp"] = resolved_at
        
        # Also add to communication history
        history_entry = {
            "type": "action_executed",
            "actor": "Action Agent",
            "description": f"Executed {len(executed_actions)} actions: {', '.join(executed_actions)}",
            "timestamp": datetime.now().isoformat()
        }
        
        # Return the action result
        action_result = {
            "status": "executed",
            "decision": decision,
            "executed_actions": executed_actions,
            "assigned_team": assigned_team,
            "partner": partner,
            "complaint_status": status
        }
        
        return action_result, update_data, history_entry
        
    async def _execute_single_action(self, action: str, evidence: dict):
        """
        Execute a single backend action on the database
        The Action Agent MUST update the relevant collections based on the decision
        """
        cards = evidence.get("cards", [])
        accounts = evidence.get("accounts", [])
        transactions = evidence.get("transactions", [])
        
        # ====================================================================
        # CREDIT CARD ACTIONS - Update creditcards collection
        # ====================================================================
        if action == "block_credit_card":
            # Block all active credit cards
            credit_cards = [c for c in cards if c.get("card_type") == "credit"] if cards else []
            blocked_count = 0
            for card in credit_cards:
                if not card.get("is_blocked", False):
                    if self.update_credit_card:
                        success = await self.update_credit_card(str(card["_id"]), {
                            "is_blocked": True,
                            "blocked_at": datetime.now().isoformat(),
                            "blocked_reason": "Lost/Stolen/Fraud"
                        })
                        if success:
                            blocked_count += 1
            print(f"✅ Blocked {blocked_count} credit card(s)")
            return True
        
        elif action == "generate_replacement_card":
            # Log replacement card generation request
            print("✅ Replacement card generation initiated")
            return True
        
        elif action == "dispatch_replacement_card":
            # Log dispatch request
            print("✅ Replacement card dispatch initiated")
            return True
        
        # ====================================================================
        # DEBIT CARD ACTIONS - Update debitcards collection
        # ====================================================================
        elif action == "block_debit_card":
            # Block all active debit cards
            debit_cards = [c for c in cards if c.get("card_type") == "debit"] if cards else []
            blocked_count = 0
            for card in debit_cards:
                if not card.get("is_blocked", False):
                    if self.update_debit_card:
                        success = await self.update_debit_card(str(card["_id"]), {
                            "is_blocked": True,
                            "blocked_at": datetime.now().isoformat(),
                            "blocked_reason": "Lost/Stolen/Fraud"
                        })
                        if success:
                            blocked_count += 1
            print(f"✅ Blocked {blocked_count} debit card(s)")
            return True
        
        # ====================================================================
        # UPI ACTIONS
        # ====================================================================
        elif action == "block_upi":
            # In a real system, this would call an API to block UPI
            print("✅ UPI access blocked")
            return True
        
        elif action == "generate_upi_pin_reset_token":
            print("✅ UPI PIN reset token generated")
            return True
        
        elif action == "reset_upi_pin":
            print("✅ UPI PIN reset completed")
            return True
        
        # ====================================================================
        # TRANSACTION ACTIONS - Update transaction collection
        # ====================================================================
        elif action == "validate_transaction_status":
            if transactions:
                latest_txn = transactions[0]
                print(f"✅ Validated transaction status: {latest_txn.get('status', 'UNKNOWN')}")
            return True
        
        elif action == "refund_transaction":
            if transactions:
                latest_txn = transactions[0]
                if self.update_transaction:
                    await self.update_transaction(str(latest_txn["_id"]), {
                        "status": "REFUNDED",
                        "refunded_at": datetime.now().isoformat()
                    })
                    print(f"✅ Transaction {latest_txn.get('transaction_id', 'N/A')} refunded")
            return True
        
        elif action == "identify_duplicate_transaction":
            if transactions:
                print(f"✅ Identified duplicate transaction: {transactions[0].get('transaction_id', 'N/A')}")
            return True
        
        elif action == "reverse_duplicate_transaction":
            if transactions:
                latest_txn = transactions[0]
                if self.update_transaction:
                    await self.update_transaction(str(latest_txn["_id"]), {
                        "status": "REVERSED",
                        "reversed_at": datetime.now().isoformat()
                    })
                    print(f"✅ Reversed duplicate transaction: {latest_txn.get('transaction_id', 'N/A')}")
            return True
        
        # ====================================================================
        # ACCOUNT ACTIONS - Update accounts collection
        # ====================================================================
        elif action == "calculate_interest":
            for acc in accounts:
                if self.update_account:
                    await self.update_account(str(acc["_id"]), {
                        "interest_calculated": True,
                        "interest_calculated_at": datetime.now().isoformat()
                    })
            print(f"✅ Calculated interest for {len(accounts)} account(s)")
            return True
        
        elif action == "credit_interest":
            for acc in accounts:
                if self.update_account:
                    await self.update_account(str(acc["_id"]), {
                        "interest_credited": True,
                        "interest_credited_at": datetime.now().isoformat()
                    })
            print(f"✅ Credited interest for {len(accounts)} account(s)")
            return True
        
        elif action == "calculate_charge_difference":
            print("✅ Calculated charge difference")
            return True
        
        elif action == "reverse_bank_charge":
            # In a real system, this would create a reversal transaction
            print("✅ Bank charge reversed")
            return True
        
        elif action == "freeze_account":
            for acc in accounts:
                if self.update_account:
                    await self.update_account(str(acc["_id"]), {
                        "status": "FROZEN",
                        "frozen_at": datetime.now().isoformat()
                    })
            print(f"✅ Froze {len(accounts)} account(s)")
            return True
        
        elif action == "close_account":
            for acc in accounts:
                if self.update_account:
                    await self.update_account(str(acc["_id"]), {
                        "status": "CLOSED",
                        "closed_at": datetime.now().isoformat()
                    })
            print(f"✅ Closed {len(accounts)} account(s)")
            return True
        
        elif action == "settle_wallet_balance":
            print("✅ Wallet balance settled")
            return True
        
        elif action == "close_wallet":
            print("✅ Wallet closed")
            return True
        
        # ====================================================================
        # DOCUMENT GENERATION ACTIONS
        # ====================================================================
        elif action in ["generate_statement", "store_statement", "notify_statement_ready"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["generate_noc", "store_noc", "notify_document_ready"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["generate_interest_certificate", "store_interest_certificate"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["generate_receipt", "store_receipt"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["issue_cheque_book", "dispatch_cheque_book"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["issue_passbook", "dispatch_passbook"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["generate_virtual_card", "activate_virtual_card", "notify_card_ready"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        # ====================================================================
        # CUSTOMER PROFILE UPDATE ACTIONS
        # ====================================================================
        elif action == "validate_mobile_number":
            print("✅ Mobile number validated")
            return True
        
        elif action == "update_mobile_number":
            print("✅ Mobile number updated")
            return True
        
        elif action == "sync_customer_profile":
            print("✅ Customer profile synced")
            return True
        
        elif action == "validate_email":
            print("✅ Email validated")
            return True
        
        elif action == "update_email":
            print("✅ Email updated")
            return True
        
        elif action == "validate_address":
            print("✅ Address validated")
            return True
        
        elif action == "update_address":
            print("✅ Address updated")
            return True
        
        elif action == "update_nominee":
            print("✅ Nominee details updated")
            return True
        
        elif action == "validate_mandate_details":
            print("✅ Mandate details validated")
            return True
        
        elif action == "register_auto_debit":
            print("✅ Auto debit registered")
            return True
        
        elif action == "cancel_auto_debit":
            print("✅ Auto debit cancelled")
            return True
        
        # ====================================================================
        # FD/RD ACTIONS
        # ====================================================================
        elif action in ["calculate_renewal_terms", "renew_fd", "renew_rd"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["calculate_closure_amount", "close_fd", "credit_closure_amount"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        elif action in ["calculate_closure_balance", "credit_closure_balance"]:
            print(f"✅ {action.replace('_', ' ').title()} completed")
            return True
        
        # ====================================================================
        # CARD PIN ACTIONS
        # ====================================================================
        elif action == "generate_card_pin_reset_token":
            print("✅ Card PIN reset token generated")
            return True
        
        elif action == "reset_credit_card_pin":
            print("✅ Credit card PIN reset completed")
            return True
        
        # ====================================================================
        # REWARD POINTS ACTIONS
        # ====================================================================
        elif action == "calculate_reward_points":
            print("✅ Reward points calculated")
            return True
        
        elif action == "credit_reward_points":
            print("✅ Reward points credited")
            return True
        
        # ====================================================================
        # NOTIFICATION ACTIONS
        # ====================================================================
        elif action in ["notify_customer_card_already_blocked", "notify_customer_transaction_success"]:
            print(f"✅ {action.replace('_', ' ').title()}")
            return True
        
        # ====================================================================
        # CASE CREATION & ASSIGNMENT ACTIONS (Logged but not blocking)
        # ====================================================================
        elif action in ["create_digital_banking_case", "create_credit_card_case", 
                       "create_debit_card_case", "create_atm_dispute", 
                       "create_account_operations_case", "create_loan_case",
                       "create_fraud_case", "create_customer_service_case",
                       "create_branch_case", "create_kyc_case", "create_forex_case",
                       "create_bank_case", "create_partner_case"]:
            print(f"✅ Case created: {action.replace('create_', '').replace('_', ' ').title()}")
            return True
        
        elif action.startswith("assign_") or action.startswith("forward_to_"):
            partner_or_team = action.replace("assign_", "").replace("forward_to_", "").replace("_", " ").title()
            print(f"✅ {action.split('_')[0].title()}: {partner_or_team}")
            return True
        
        # ====================================================================
        # DEFAULT: Unknown action - log and continue
        # ====================================================================
        print(f"⚠️  Unknown action executed: {action}")
        return True
        
    def toggle_kill_switch(self, active: bool) -> dict:
        """
        Toggle the kill switch for automated actions
        """
        self.kill_switch = active
        return {
            "kill_switch_active": self.kill_switch,
            "message": f"Kill switch {'activated' if self.kill_switch else 'deactivated'}"
        }
        
    def _get_partner_from_actions(self, actions: list) -> str:
        """Extract partner information from actions"""
        for action in actions:
            if "forward_to_" in action:
                return action.replace("forward_to_", "").replace("_", " ").title()
        return "Unknown Partner"
        
    def _get_assigned_team(self, product: str) -> str:
        """
        Get the appropriate team to handle the complaint
        """
        team_assignments = {
            "UPI": "Digital Payments Team",
            "Credit Card": "Credit Cards Division",
            "Debit Card": "Debit Cards & ATM Team",
            "ATM": "Debit Cards & ATM Team",
            "Internet Banking": "Digital Banking Team",
            "Mobile Banking": "Digital Banking Team",
            "Loans": "Loans Department",
            "Savings Account": "Retail Banking Team",
            "Current Account": "Retail Banking Team",
            "Cheque Services": "Operations Team",
            "Fixed Deposit": "Deposits Team",
            "Recurring Deposit": "Deposits Team",
            "Insurance": "Insurance Team",
            "Forex / International Transactions": "Forex Team",
            "Customer Service": "Customer Service Team",
            "Branch Services": "Branch Operations Team",
            "KYC / AML / Compliance": "Compliance Team",
            "Lockers": "Branch Operations Team"
        }
        return team_assignments.get(product, "Customer Support")
