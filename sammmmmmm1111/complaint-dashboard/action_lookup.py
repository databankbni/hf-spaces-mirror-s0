# action_lookup.py
#
# AI Banking Agent workflow engine.
#
# Architecture (unchanged):
#   Complaint -> Classification Agent -> Decision Agent -> Action Agent -> Verification Agent
#
# This module is the Decision Agent's lookup table. It maps
# (category, issue) -> { "decision": ..., "actions": [...] }.
#
# Decisions (only three valid values):
#   - "auto_resolve"        -> Action Agent fully resolves via backend API calls.
#                               No branch visit, no customer-care call, no manual step.
#   - "bank_escalation"     -> Routed to the correct internal team for human
#                               investigation/approval.
#   - "partner_escalation"  -> Routed to the correct external organization.
#
# Design rules followed here:
#   1. auto_resolve actions are realistic multi-step backend workflows, not a
#      single function call standing in for the whole process.
#   2. No verification actions (e.g. verify_card_blocked) -- that is the
#      Verification Agent's job, run separately after the Action Agent.
#   3. bank_escalation always routes to a specific internal team, never a
#      generic "create_bank_case / assign_operations_team" unless no more
#      specific team fits.
#   4. partner_escalation always names the specific external organization
#      to forward to.
#   5. No customer-facing actions (no "tell customer", "ask customer", etc.)
#      -- every action is a backend operation the Action Agent can execute.

ACTION_LOOKUP = {

    "UPI": {
        # --- partner_escalation: NPCI network / UPI app layer issues ---
        "UPI App Login Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },
        "UPI App Crashing": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },
        "UPI App Not Responding": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },
        "QR Code Not Working": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },
        "QR Code Payment Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },
        "Dynamic QR Not Generated": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },
        "Merchant QR Invalid": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_merchant"],
        },
        "UPI Lite Registration Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },
        "UPI Lite Top-up Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_npci"],
        },

        # --- bank_escalation: requires investigation/reconciliation ---
        "Amount Debited but Payment Failed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Amount Debited but Beneficiary Not Credited": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Refund Not Received": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Refund Delayed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Unauthorized UPI Transaction": {
            "decision": "bank_escalation",
            "actions": ["block_upi", "create_fraud_case", "assign_fraud_team"],
        },
        "UPI Fraud Complaint": {
            "decision": "bank_escalation",
            "actions": ["block_upi", "create_fraud_case", "assign_fraud_team"],
        },
        "Phishing Through UPI": {
            "decision": "bank_escalation",
            "actions": ["block_upi", "create_fraud_case", "assign_fraud_team"],
        },
        "UPI PIN Reset Failed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "UPI Daily Limit Exceeded": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Wrong UPI ID Credited": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },

        # --- auto_resolve ---
        "Forgot UPI PIN": {
            "decision": "auto_resolve",
            "actions": ["generate_upi_pin_reset_token", "reset_upi_pin"],
        },
        "Incorrect UPI PIN": {
            "decision": "auto_resolve",
            "actions": ["generate_upi_pin_reset_token", "reset_upi_pin"],
        },
    },

    "Credit Card": {
        "Card Lost": {
            "decision": "auto_resolve",
            "actions": ["block_credit_card", "generate_replacement_card", "dispatch_replacement_card"],
        },
        "Card Stolen": {
            "decision": "auto_resolve",
            "actions": ["block_credit_card", "generate_replacement_card", "dispatch_replacement_card"],
        },
        "Unauthorized Transaction": {
            "decision": "bank_escalation",
            "actions": ["block_credit_card", "create_fraud_case", "assign_fraud_team"],
        },
        "Fraudulent Transaction": {
            "decision": "bank_escalation",
            "actions": ["block_credit_card", "create_fraud_case", "assign_fraud_team"],
        },
        "Card Replacement Delay": {
            "decision": "bank_escalation",
            "actions": ["create_credit_card_case", "assign_credit_card_operations"],
        },
        "Replacement Card Not Received": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_courier_partner"],
        },
        "Chargeback Not Processed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_card_network"],
        },
        "Refund Not Received": {
            "decision": "bank_escalation",
            "actions": ["create_credit_card_case", "assign_credit_card_operations"],
        },
        "Incorrect Interest Charged": {
            "decision": "auto_resolve",
            "actions": ["calculate_charge_difference", "reverse_bank_charge"],
        },
        "EMI Conversion Failed": {
            "decision": "bank_escalation",
            "actions": ["create_credit_card_case", "assign_credit_card_operations"],
        },
        "Reward Points Not Credited": {
            "decision": "auto_resolve",
            "actions": ["calculate_reward_points", "credit_reward_points"],
        },
        "Forgot PIN Assistance": {
            "decision": "auto_resolve",
            "actions": ["generate_card_pin_reset_token", "reset_credit_card_pin"],
        },
    },

    "Debit Card": {
        "Card Lost": {
            "decision": "auto_resolve",
            "actions": ["block_debit_card", "generate_replacement_card", "dispatch_replacement_card"],
        },
        "Card Stolen": {
            "decision": "auto_resolve",
            "actions": ["block_debit_card", "generate_replacement_card", "dispatch_replacement_card"],
        },
        "Unauthorized Transaction": {
            "decision": "bank_escalation",
            "actions": ["block_debit_card", "create_fraud_case", "assign_fraud_team"],
        },
        "ATM Withdrawal Failed": {
            "decision": "bank_escalation",
            "actions": ["create_atm_dispute", "assign_atm_operations"],
        },
        "Card Replacement Delay": {
            "decision": "bank_escalation",
            "actions": ["create_debit_card_case", "assign_debit_card_operations"],
        },
        "Insufficient Balance Error Despite Available Funds": {
            "decision": "bank_escalation",
            "actions": ["create_debit_card_case", "assign_debit_card_operations"],
        },
    },

    "ATM": {
        "Cash Not Dispensed but Account Debited": {
            "decision": "bank_escalation",
            "actions": ["create_atm_dispute", "assign_atm_operations"],
        },
        "Partial Cash Dispensed": {
            "decision": "bank_escalation",
            "actions": ["create_atm_dispute", "assign_atm_operations"],
        },
        "ATM Card Retained": {
            "decision": "bank_escalation",
            "actions": ["create_atm_dispute", "assign_atm_operations"],
        },
        "ATM Skimming Fraud": {
            "decision": "bank_escalation",
            "actions": ["block_debit_card", "create_fraud_case", "assign_fraud_team"],
        },
        "ATM Machine Out of Service": {
            "decision": "bank_escalation",
            "actions": ["create_atm_dispute", "assign_atm_operations"],
        },
        "Cash Dispensed in Wrong Denomination": {
            "decision": "bank_escalation",
            "actions": ["create_atm_dispute", "assign_atm_operations"],
        },
    },

    "Internet Banking": {
        "Website Down": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Login Failed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Fund Transfer Failed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Amount Debited but Beneficiary Not Credited": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Password Reset Failed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
    },

    "Mobile Banking": {
        "App Crashing": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_app_vendor"],
        },
        "App Not Opening": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_app_vendor"],
        },
        "Biometric Login Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_app_vendor"],
        },
        "Fund Transfer Failed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
        "Mobile Banking Registration Failed": {
            "decision": "bank_escalation",
            "actions": ["create_digital_banking_case", "assign_digital_banking_team"],
        },
    },

    "Loans": {
        "Loan Application Rejected": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Loan Disbursement Delayed": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Loan Disbursement Failed": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "EMI Paid but Showing Due": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "EMI Auto-Debit Failed": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Foreclosure Request Pending": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Recovery Agent Harassment": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Credit Bureau Reporting Incorrect": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
    },

    "Savings Account": {
        "Account Opening Delay": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Account Freeze Without Notice": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Cash Deposit Not Reflected": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Interest Not Credited": {
            "decision": "auto_resolve",
            "actions": ["calculate_interest", "credit_interest"],
        },
        "Wrong Charges Deducted": {
            "decision": "auto_resolve",
            "actions": ["calculate_charge_difference", "reverse_bank_charge"],
        },
        "Account Closure Delay": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
    },

    "Current Account": {
        "Current Account Opening Delay": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Merchant Settlement Delayed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Account Freeze Without Notice": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Bulk Payment Failed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
    },

    "Cheque Services": {
        "Stop Payment Request Failed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Cheque Bounce Charges Incorrect": {
            "decision": "auto_resolve",
            "actions": ["calculate_charge_difference", "reverse_bank_charge"],
        },
        "Cheque Book Not Received": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_courier_partner"],
        },
    },

    "Fixed Deposit": {
        "FD Opening Failed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "FD Interest Not Credited": {
            "decision": "auto_resolve",
            "actions": ["calculate_interest", "credit_interest"],
        },
        "Premature FD Closure Failed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "FD Maturity Amount Incorrect": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "FD Auto Renewal Failed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
    },

    "Recurring Deposit": {
        "RD Opening Failed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "RD Installment Not Debited": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "RD Interest Not Credited": {
            "decision": "auto_resolve",
            "actions": ["calculate_interest", "credit_interest"],
        },
        "Premature RD Closure Failed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
    },

    "Insurance": {
        "Insurance Policy Purchase Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
        "Policy Issuance Delayed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
        "Claim Registration Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
        "Claim Settlement Delayed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
        "Claim Rejected Without Reason": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
        "Policy Renewal Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
        "Policy Cancellation Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
    },

    "Demat / Trading Account": {
        "Demat Account Opening Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_depository_partner"],
        },
        "Trading Login Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_depository_partner"],
        },
        "Buy Order Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_depository_partner"],
        },
        "Sell Order Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_depository_partner"],
        },
        "Holdings Not Updated": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_depository_partner"],
        },
        "Shares Not Credited": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_depository_partner"],
        },
        "Corporate Action Not Updated": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_depository_partner"],
        },
    },

    "Forex / International Transactions": {
        "Forex Card Application Failed": {
            "decision": "bank_escalation",
            "actions": ["create_forex_case", "assign_forex_team"],
        },
        "International Fund Transfer Failed": {
            "decision": "bank_escalation",
            "actions": ["create_forex_case", "assign_forex_team"],
        },
        "SWIFT Transfer Failed": {
            "decision": "bank_escalation",
            "actions": ["create_forex_case", "assign_forex_team"],
        },
        "Incorrect Currency Conversion": {
            "decision": "bank_escalation",
            "actions": ["create_forex_case", "assign_forex_team"],
        },
    },

    "Wallet / Prepaid Card": {
        "Wallet Registration Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_wallet_provider"],
        },
        "Wallet Top-up Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_wallet_provider"],
        },
        "Wallet Payment Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_wallet_provider"],
        },
        "Wallet Balance Not Updated": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_wallet_provider"],
        },
        "Refund Not Received": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_wallet_provider"],
        },
        "Wallet Closure Request": {
            "decision": "auto_resolve",
            "actions": ["settle_wallet_balance", "close_wallet"],
        },
    },

    "Customer Service": {
        "Complaint Resolution Delay": {
            "decision": "bank_escalation",
            "actions": ["create_customer_service_case", "assign_customer_service_team"],
        },
        "Customer Care Not Reachable": {
            "decision": "bank_escalation",
            "actions": ["create_customer_service_case", "assign_customer_service_team"],
        },
        "Poor Customer Service": {
            "decision": "bank_escalation",
            "actions": ["create_customer_service_case", "assign_customer_service_team"],
        },
        "Relationship Manager Not Responding": {
            "decision": "bank_escalation",
            "actions": ["create_branch_case", "assign_branch_manager"],
        },
    },

    "Branch Services": {
        "Long Queue at Branch": {
            "decision": "bank_escalation",
            "actions": ["create_branch_case", "assign_branch_manager"],
        },
        "Staff Misbehavior": {
            "decision": "bank_escalation",
            "actions": ["create_branch_case", "assign_branch_manager"],
        },
        "Service Request Pending": {
            "decision": "bank_escalation",
            "actions": ["create_branch_case", "assign_branch_manager"],
        },
        "Document Verification Delay": {
            "decision": "bank_escalation",
            "actions": ["create_kyc_case", "assign_kyc_team"],
        },
    },

    "KYC / AML / Compliance": {
        "KYC Verification Pending": {
            "decision": "bank_escalation",
            "actions": ["create_kyc_case", "assign_kyc_team"],
        },
        "Account Frozen Due to KYC": {
            "decision": "bank_escalation",
            "actions": ["create_kyc_case", "assign_kyc_team"],
        },
        "AML Verification Pending": {
            "decision": "bank_escalation",
            "actions": ["create_kyc_case", "assign_kyc_team"],
        },
        "PAN Verification Failed": {
            "decision": "bank_escalation",
            "actions": ["create_kyc_case", "assign_kyc_team"],
        },
    },

    "Pension / Government Schemes": {
        "Pension Not Credited": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_government_department"],
        },
        "PM Kisan Installment Not Received": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_government_department"],
        },
        "NPS Registration Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_government_department"],
        },
        "APY Registration Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_government_department"],
        },
    },

    "Lockers": {
        "Locker Allotment Pending": {
            "decision": "bank_escalation",
            "actions": ["create_branch_case", "assign_branch_manager"],
        },
        "Locker Access Denied": {
            "decision": "bank_escalation",
            "actions": ["create_branch_case", "assign_branch_manager"],
        },
        "Locker Rent Charged Incorrectly": {
            "decision": "auto_resolve",
            "actions": ["calculate_charge_difference", "reverse_bank_charge"],
        },
    },

    "Merchant Services / POS": {
        "POS Machine Not Working": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_pos_vendor"],
        },
        "POS Installation Delayed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_pos_vendor"],
        },
        "Merchant Settlement Delayed": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Merchant Registration Failed": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_pos_vendor"],
        },
    },

    "Agriculture / Priority Sector Loans": {
        "Agriculture Loan Application Pending": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Kisan Credit Card Application Pending": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Crop Insurance Claim Pending": {
            "decision": "partner_escalation",
            "actions": ["create_partner_case", "forward_to_insurance_partner"],
        },
        "Interest Subsidy Not Applied": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
    },

    # ------------------------------------------------------------------
    # General Service Requests -- issues that map directly onto backend
    # APIs but had no corresponding entry in the legacy taxonomy.
    # ------------------------------------------------------------------
    "General Service Requests": {
        "Statement Request": {
            "decision": "auto_resolve",
            "actions": ["generate_statement", "store_statement", "notify_statement_ready"],
        },
        "Cheque Book Request": {
            "decision": "auto_resolve",
            "actions": ["issue_cheque_book", "dispatch_cheque_book"],
        },
        "Passbook Request": {
            "decision": "auto_resolve",
            "actions": ["issue_passbook", "dispatch_passbook"],
        },
        "NOC Request": {
            "decision": "auto_resolve",
            "actions": ["generate_noc", "store_noc", "notify_document_ready"],
        },
        "Interest Certificate Request": {
            "decision": "auto_resolve",
            "actions": ["generate_interest_certificate", "store_interest_certificate", "notify_document_ready"],
        },
        "Transaction Receipt Request": {
            "decision": "auto_resolve",
            "actions": ["generate_receipt", "store_receipt", "notify_document_ready"],
        },
        "Virtual Card Request": {
            "decision": "auto_resolve",
            "actions": ["generate_virtual_card", "activate_virtual_card", "notify_card_ready"],
        },
        "Update Mobile Number": {
            "decision": "auto_resolve",
            "actions": ["validate_mobile_number", "update_mobile_number", "sync_customer_profile"],
        },
        "Update Email": {
            "decision": "auto_resolve",
            "actions": ["validate_email", "update_email", "sync_customer_profile"],
        },
        "Update Address": {
            "decision": "auto_resolve",
            "actions": ["validate_address", "update_address", "sync_customer_profile"],
        },
        "Update Nominee": {
            "decision": "auto_resolve",
            "actions": ["update_nominee", "sync_customer_profile"],
        },
        "Register Auto Debit / Standing Instruction": {
            "decision": "auto_resolve",
            "actions": ["validate_mandate_details", "register_auto_debit"],
        },
        "Cancel Auto Debit / Standing Instruction": {
            "decision": "auto_resolve",
            "actions": ["cancel_auto_debit"],
        },
        "FD Renewal Request": {
            "decision": "auto_resolve",
            "actions": ["calculate_renewal_terms", "renew_fd"],
        },
        "RD Renewal Request": {
            "decision": "auto_resolve",
            "actions": ["calculate_renewal_terms", "renew_rd"],
        },
        "FD Closure Request": {
            "decision": "auto_resolve",
            "actions": ["calculate_closure_amount", "close_fd", "credit_closure_amount"],
        },
        "RD Closure Request": {
            "decision": "auto_resolve",
            "actions": ["calculate_closure_amount", "close_rd", "credit_closure_amount"],
        },
        "Account Closure Request": {
            "decision": "auto_resolve",
            "actions": ["calculate_closure_balance", "close_account", "credit_closure_balance"],
        },
        "Voluntary Account Freeze Request": {
            "decision": "auto_resolve",
            "actions": ["freeze_account"],
        },
        "Duplicate Transaction Charged": {
            "decision": "auto_resolve",
            "actions": ["identify_duplicate_transaction", "reverse_duplicate_transaction"],
        },
        "Failed Transaction Refund": {
            "decision": "auto_resolve",
            "actions": ["validate_transaction_status", "refund_transaction"],
        },

        # --- require human judgment / approval even though an API exists ---
        "Account Reopen Request": {
            "decision": "bank_escalation",
            "actions": ["create_kyc_case", "assign_kyc_team"],
        },
        "Account Unfreeze Request": {
            "decision": "bank_escalation",
            "actions": ["create_account_operations_case", "assign_account_operations_team"],
        },
        "Remove Lien Request": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
        "Release Collateral Request": {
            "decision": "bank_escalation",
            "actions": ["create_loan_case", "assign_loan_team"],
        },
    },
}


# Default fallback for unmapped category/issue pairs.
# bank_escalation is the safe default: when the AI doesn't recognize the
# issue, a human should look at it rather than the AI guessing at an
# auto-resolve action. Routed to general operations since the correct
# specific team cannot be determined for an unrecognized issue.
DEFAULT_DECISION = "bank_escalation"
DEFAULT_ACTIONS = ["create_bank_case", "assign_operations_team"]


def get_decision(category: str, issue: str) -> str:
    """Return the decision ('auto_resolve' | 'bank_escalation' |
    'partner_escalation') for a category/issue pair, with fallback
    and simple partial matching."""
    entry = _lookup_entry(category, issue)
    return entry["decision"] if entry else DEFAULT_DECISION


def get_actions(category: str, issue: str) -> list:
    """Return the list of backend actions for a category/issue pair,
    with fallback and simple partial matching."""
    entry = _lookup_entry(category, issue)
    return list(entry["actions"]) if entry else list(DEFAULT_ACTIONS)


def get_resolution(category: str, issue: str) -> dict:
    """Return the full {'decision': ..., 'actions': [...]} entry."""
    entry = _lookup_entry(category, issue)
    if entry:
        return {"decision": entry["decision"], "actions": list(entry["actions"])}
    return {"decision": DEFAULT_DECISION, "actions": list(DEFAULT_ACTIONS)}


def _lookup_entry(category: str, issue: str):
    """Internal helper: exact match first, then case-insensitive
    substring match, mirroring the original lookup's fuzzy-matching
    behavior."""
    cat_map = ACTION_LOOKUP.get(category)
    if not cat_map:
        return None

    if issue in cat_map:
        return cat_map[issue]

    issue_lower = issue.lower()
    for key, entry in cat_map.items():
        if key.lower() in issue_lower or issue_lower in key.lower():
            return entry

    return None