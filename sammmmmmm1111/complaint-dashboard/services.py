#services.py
from __future__ import annotations

from datetime import datetime, timedelta
import uuid
import time
from typing import List, Optional
import logging
import uuid 
from database import get_collection
from models import Complaint, ComplaintCreate, UserLogin, User
from constants import SLA_DAYS, SIMILARITY_CONFIG
from logger import get_logger

import bcrypt

import subprocess
import sys
import os


# Import our agents
from agents.classifier import ClassifierAgent
from agents.decision import DecisionAgent
from agents.action import ActionAgent
from agents.verification import VerificationAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize comprehensive logging system
log_system = get_logger()

# Mapping of backend action names to customer-friendly descriptions
BACKEND_ACTION_TO_CUSTOMER_FRIENDLY = {
    # Credit Card actions
    "block_credit_card": "Your credit card has been blocked.",
    "generate_replacement_card": "A replacement card has been requested.",
    "dispatch_replacement_card": "Your replacement card is being dispatched.",
    
    # Debit Card actions
    "block_debit_card": "Your debit card has been blocked.",
    
    # UPI actions
    "block_upi": "Your UPI access has been blocked.",
    
    # Case creation actions
    "create_digital_banking_case": "Your complaint has been assigned to our Digital Banking Team.",
    "create_credit_card_case": "Your complaint has been assigned to our Credit Cards Division.",
    "create_debit_card_case": "Your complaint has been assigned to our Debit Cards & ATM Team.",
    "create_atm_dispute": "Your ATM dispute has been registered.",
    "create_account_operations_case": "Your complaint has been assigned to our Account Operations Team.",
    "create_loan_case": "Your complaint has been assigned to our Loans Department.",
    "create_fraud_case": "Your complaint has been assigned to our Fraud Investigation Team.",
    "create_customer_service_case": "Your complaint has been assigned to our Customer Service Team.",
    "create_branch_case": "Your complaint has been assigned to our Branch Operations Team.",
    "create_kyc_case": "Your complaint has been assigned to our Compliance Team.",
    "create_forex_case": "Your complaint has been assigned to our Forex Team.",
    "create_bank_case": "Your complaint has been assigned to our Operations Team.",
    "create_partner_case": "Your complaint has been registered with our partner.",
    
    # Team assignment actions
    "assign_digital_banking_team": "It has been assigned to our Digital Banking Team.",
    "assign_credit_card_operations": "It has been assigned to our Credit Cards Division.",
    "assign_debit_card_operations": "It has been assigned to our Debit Cards & ATM Team.",
    "assign_atm_operations": "It has been assigned to our ATM Operations Team.",
    "assign_account_operations_team": "It has been assigned to our Account Operations Team.",
    "assign_loan_team": "It has been assigned to our Loans Department.",
    "assign_fraud_team": "It has been assigned to our Fraud Investigation Team.",
    "assign_customer_service_team": "It has been assigned to our Customer Service Team.",
    "assign_branch_manager": "It has been assigned to our Branch Manager.",
    "assign_kyc_team": "It has been assigned to our Compliance Team.",
    "assign_forex_team": "It has been assigned to our Forex Team.",
    "assign_operations_team": "It has been assigned to our Operations Team.",
    
    # Partner forwarding actions
    "forward_to_npci": "Your complaint has been forwarded to NPCI.",
    "forward_to_merchant": "Your complaint has been forwarded to the merchant.",
    "forward_to_courier_partner": "Your complaint has been forwarded to our courier partner.",
    "forward_to_card_network": "Your complaint has been forwarded to the card network.",
    "forward_to_insurance_partner": "Your complaint has been forwarded to our insurance partner.",
    "forward_to_depository_partner": "Your complaint has been forwarded to our depository partner.",
    "forward_to_government_department": "Your complaint has been forwarded to the government department.",
    "forward_to_app_vendor": "Your complaint has been forwarded to our app vendor.",
    "forward_to_pos_vendor": "Your complaint has been forwarded to our POS vendor.",
    "forward_to_wallet_provider": "Your complaint has been forwarded to our wallet provider.",
    
    # Auto-resolve actions (Savings/Current)
    "calculate_interest": "We have recalculated the interest due to you.",
    "credit_interest": "The interest has been credited to your account.",
    "calculate_charge_difference": "We have identified the incorrect charge.",
    "reverse_bank_charge": "The incorrect charge has been reversed.",
    "settle_wallet_balance": "Your wallet balance has been settled.",
    "close_wallet": "Your wallet has been closed as requested.",
    
    # General Service Requests
    "generate_statement": "Your account statement has been generated.",
    "store_statement": "The statement has been stored for your access.",
    "notify_statement_ready": "You will be notified when your statement is ready.",
    "issue_cheque_book": "A new cheque book has been issued.",
    "dispatch_cheque_book": "Your cheque book is being dispatched.",
    "issue_passbook": "A new passbook has been issued.",
    "dispatch_passbook": "Your passbook is being dispatched.",
    "generate_noc": "The No Objection Certificate has been generated.",
    "store_noc": "The NOC has been stored for your access.",
    "notify_document_ready": "You will be notified when your document is ready.",
    "generate_interest_certificate": "Your interest certificate has been generated.",
    "store_interest_certificate": "The interest certificate has been stored for your access.",
    "generate_receipt": "The transaction receipt has been generated.",
    "store_receipt": "The receipt has been stored for your access.",
    "generate_virtual_card": "Your virtual card has been generated.",
    "activate_virtual_card": "Your virtual card has been activated.",
    "notify_card_ready": "You will be notified when your card is ready.",
    "validate_mobile_number": "Your mobile number has been validated.",
    "update_mobile_number": "Your mobile number has been updated.",
    "sync_customer_profile": "Your customer profile has been synced.",
    "validate_email": "Your email address has been validated.",
    "update_email": "Your email address has been updated.",
    "validate_address": "Your address has been validated.",
    "update_address": "Your address has been updated.",
    "update_nominee": "Your nominee details have been updated.",
    "validate_mandate_details": "Your mandate details have been validated.",
    "register_auto_debit": "Auto debit has been registered.",
    "cancel_auto_debit": "Auto debit has been cancelled.",
    "calculate_renewal_terms": "Renewal terms have been calculated.",
    "renew_fd": "Your fixed deposit has been renewed.",
    "renew_rd": "Your recurring deposit has been renewed.",
    "calculate_closure_amount": "Closure amount has been calculated.",
    "close_fd": "Your fixed deposit has been closed.",
    "credit_closure_amount": "The closure amount has been credited to your account.",
    "close_rd": "Your recurring deposit has been closed.",
    "calculate_closure_balance": "Account closure balance has been calculated.",
    "close_account": "Your account has been closed as requested.",
    "credit_closure_balance": "The closure balance has been credited to your account.",
    "freeze_account": "Your account has been frozen as requested.",
    "identify_duplicate_transaction": "The duplicate transaction has been identified.",
    "reverse_duplicate_transaction": "The duplicate transaction has been reversed.",
    "validate_transaction_status": "Transaction status has been validated.",
    "refund_transaction": "A refund for the transaction has been initiated.",
}

# Mapping of decision types to SLA days
SLA_DAYS_FOR_DECISION = {
    "auto_resolve": 1,  # 1 working day
    "bank_escalation": 3,  # 3 working days
    "partner_escalation": 5,  # 5 working days
}

def map_actions_to_customer_friendly(actions: List[str]) -> List[str]:
    """Map backend action names to customer-friendly descriptions."""
    friendly_descriptions = []
    for action in actions:
        if action in BACKEND_ACTION_TO_CUSTOMER_FRIENDLY:
            friendly_descriptions.append(BACKEND_ACTION_TO_CUSTOMER_FRIENDLY[action])
        else:
            # If no specific mapping, use a generic description
            friendly_descriptions.append(f"Requested action has been processed.")
    return friendly_descriptions

def calculate_working_days_ahead(start_date: datetime, days: int) -> datetime:
    """Calculate a date X working days ahead (excluding weekends)."""
    current_date = start_date
    days_added = 0
    while days_added < days:
        current_date += timedelta(days=1)
        # Skip Saturdays (5) and Sundays (6)
        if current_date.weekday() < 5:
            days_added += 1
    return current_date

def generate_dynamic_draft_response(
    decision: str,
    product: str,
    issue: str,
    complaint_id: str,
    executed_actions: List[str],
    assigned_team: Optional[str] = None,
    partner: Optional[str] = None,
) -> str:
    """Generate a dynamic draft response based on the decision type."""
    current_timestamp = datetime.now().strftime("%d %b %Y at %I:%M %p")
    sla_days = SLA_DAYS_FOR_DECISION.get(decision, 3)
    resolution_date = calculate_working_days_ahead(datetime.now(), sla_days).strftime("%d %b %Y")
    
    friendly_actions = map_actions_to_customer_friendly(executed_actions)
    actions_text = "\n\n".join(friendly_actions)
    
    if decision == "auto_resolve":
        return (
            f"We have successfully resolved your complaint regarding your {issue} on {product}.\n\n"
            f"{actions_text}\n\n"
            f"Your complaint has been resolved on {current_timestamp}.\n\n"
            f"Complaint Reference ID:\n"
            f"{complaint_id}\n\n"
            f"No further action is required from your side."
        )
    
    elif decision == "bank_escalation":
        team_name = assigned_team or "appropriate internal team"
        return (
            f"We have received your complaint regarding {issue} on {product}.\n\n"
            f"This issue requires additional investigation and has been escalated to our {team_name}.\n\n"
            f"Expected Resolution Time:\n"
            f"{sla_days} Working Days\n\n"
            f"Expected Resolution Date:\n"
            f"{resolution_date}\n\n"
            f"Complaint Reference ID:\n"
            f"{complaint_id}\n\n"
            f"Our team is actively investigating your complaint and you will be notified once the investigation is completed."
        )
    
    elif decision == "partner_escalation":
        partner_name = partner or "external partner"
        return (
            f"We have received your complaint regarding {issue} on {product}.\n\n"
            f"Your complaint has been forwarded to {partner_name} for further investigation, as this issue involves the external partner.\n\n"
            f"Current Status:\n"
            f"Under Review by {partner_name}\n\n"
            f"Expected Resolution Time:\n"
            f"{sla_days} Working Days\n\n"
            f"Complaint Reference ID:\n"
            f"{complaint_id}\n\n"
            f"We will notify you once we receive an update from the partner."
        )
    
    else:
        # Fallback to generic response
        return (
            f"We have received your complaint regarding {issue} on {product}. The complaint has been registered and is under review. "
            f"Your complaint reference ID is {complaint_id}."
        )

# ai_engine will be initialized lazily inside register_complaint / other endpoints.

from ai_engine import AIEngine

ai_engine = None
rca_engine = None
classifier_agent = None
decision_agent = None
action_agent = None
verification_agent = None

def get_classifier_agent():
    global classifier_agent
    if classifier_agent is None:
        classifier_agent = ClassifierAgent()
    return classifier_agent

def get_decision_agent():
    global decision_agent
    if decision_agent is None:
        decision_agent = DecisionAgent()
    return decision_agent

def get_action_agent():
    global action_agent
    if action_agent is None:
        action_agent = ActionAgent()
    return action_agent

def get_verification_agent():
    global verification_agent
    if verification_agent is None:
        verification_agent = VerificationAgent()
    return verification_agent

async def get_ai_engine():          # <-- ADD THIS BACK
    global ai_engine

    if ai_engine is None:
        ai_engine = AIEngine()

    return ai_engine

async def get_rca_engine():
    global rca_engine
    if rca_engine is None:
        from rag.rca_engine import RCAEngine
        import asyncio
        ai_e = await get_ai_engine()
        rca_engine = RCAEngine(ai_e)
        # load_from_mongodb() is a synchronous pymongo call that scans and
        # re-embeds every complaint — run it in a thread so it doesn't block
        # the event loop, and so a slow/failed Mongo call doesn't hang startup.
        await asyncio.to_thread(rca_engine.retriever.load_from_mongodb)
    return rca_engine

async def login_user(login_data: UserLogin):
    customers = await get_collection("customeracc")
    admins = await get_collection("adminlogin")
    branch_managers = await get_collection("branchmanager")
    sessions = await get_collection("sessions")

    # Find user and set role explicitly
    if login_data.role == "customer":
        user = await customers.find_one(
            {
                "account_number":
                    login_data.identifier
            }
        )
        role = "customer"

    elif login_data.role == "admin":
        user = await admins.find_one(
            {
                "email":
                    login_data.identifier
            }
        )
        role = "admin"

    elif login_data.role == "branch_manager":
        user = await branch_managers.find_one(
            {
                "email":
                    login_data.identifier
            }
        )
        role = "branch_manager"

    else:
        raise ValueError("Invalid role")

    if not user:
        raise ValueError("Invalid credentials")

    password_bytes = login_data.password.encode(
        "utf-8"
    )

    stored_hash = user[
        "hashed_password"
    ].encode("utf-8")

    if not bcrypt.checkpw(
        password_bytes,
        stored_hash,
    ):
        raise ValueError(
            "Invalid credentials"
        )

    session_id = str(uuid.uuid4())

    await sessions.insert_one(
        {
            "session_id": session_id,
            "user_id": str(user["_id"]),
            "role": role,
            "created_at": datetime.now(),
        }
    )

    # Customers have customer_name,
    # admins and branch managers have name
    name = user.get(
        "name",
        user.get("customer_name")
    )

    user_response = {
        "_id": str(user["_id"]),
        "name": name,
        "role": role,
    }

    return user_response, session_id
async def register_complaint(complaint_data: ComplaintCreate) -> dict:
    ai_e = await get_ai_engine()
    rca_e = await get_rca_engine()
    classifier = get_classifier_agent()
    decision_agent = get_decision_agent()
    action_agent = get_action_agent()
    verification = get_verification_agent()
    
    # Create session for tracking
    session_id = log_system.create_session("PENDING", complaint_data.customer_id)
    customer_id = complaint_data.customer_id

    try:
        # 1. Generate Unique Complaint ID
        complaint_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
        logger.info(f"Registering complaint {complaint_id}")
        
        # Log workflow stage
        log_system.log_workflow_stage(complaint_id, "Complaint Received", f"Via {complaint_data.submitted_via}")

        # 2. AI Categorization and Analysis
        text_content = complaint_data.consumer_complaint_narrative
        if not text_content:
            raise ValueError("Complaint narrative cannot be empty")

        ai_results = ai_e.categorize_complaint(text_content)
        print("\n========== AI RESULTS ==========")
        print(ai_results)
        sentiment_score = ai_results["sentiment_score"]

        from nba.rag_engine import retrieve_nba
        # Retrieve Next Best Actions
        nba_result = retrieve_nba(
            major_issue=ai_results["product"],
            sub_issue=ai_results["issue_subtype"],
        )
        print("\n========== NBA RESULT ==========")
        print(nba_result)
        print("================================\n")
        
        # Default bank escalation NBA if no data found
        default_bank_escalation_nba = {
            "investigation_steps": [
                "Review customer complaint details and transaction history",
                "Verify account information and recent activity",
                "Check for similar complaints in the system",
                "Assign to appropriate team for resolution"
            ],
            "next_best_actions": [
                "Escalate complaint to the relevant department",
                "Acknowledge customer complaint and provide timeline",
                "Investigate the issue thoroughly",
                "Update customer on progress regularly"
            ]
        }

        # 3. Calculate SLA and Severity
        severity_score = ai_results["severity"] / 10.0  # Normalize to 0-1
        severity_label = "Medium"
        if ai_results["severity"] >= 9:
            severity_label = "Critical"
        elif ai_results["severity"] >= 7:
            severity_label = "High"
        elif ai_results["severity"] >= 4:
            severity_label = "Medium"
        else:
            severity_label = "Low"

        days_to_resolve = SLA_DAYS.get(severity_label, 7)
        sla_deadline = datetime.now() + timedelta(days=days_to_resolve)
        sla_deadline_str = sla_deadline.strftime("%d %b %Y, %I:%M %p")

        # 4. Duplicate Detection
        embedding = ai_e.get_embedding(text_content)
        similar_complaints = ai_e.find_similar_complaints(embedding)

        rca_result = rca_e.analyze(
            text_content,
            product=ai_results["product"],
            issue=ai_results["issue_type"]
        )

        is_duplicate = False
        duplicate_of = None
        related_complaints = []

        for other_id, score in similar_complaints:
            if score >= SIMILARITY_CONFIG["duplicate_threshold"]:
                is_duplicate = True
                duplicate_of = other_id
                break
            elif score >= SIMILARITY_CONFIG["related_threshold"]:
                related_complaints.append(other_id)

        # 5. Priority Rank Calculation
        fraud_risk = (
            0.8
            if "Fraud" in ai_results["issue_type"] or "Unauthorized" in text_content
            else 0.1
        )
        regulatory_risk = 0.7 if severity_label == "Critical" else 0.2

        # Calculate a composite priority score (0 to 1)
        priority_rank = (
            (severity_score * 0.4)
            + (sentiment_score * 0.2)
            + (fraud_risk * 0.2)
            + (regulatory_risk * 0.2)
        )

        # 6. Create Initial Complaint Object with RECEIVED state
        new_complaint = {
            "_id": str(uuid.uuid4()),
            "complaint_id": complaint_id,
            "customer_id": complaint_data.customer_id,
            "customer_name": complaint_data.customer_name,
            "branch_id": complaint_data.branch_id,
            "date_received": datetime.now(),
            "product": ai_results["product"],
            "sub_product": complaint_data.sub_product or "General",
            "issue": ai_results["issue_type"],
            "sub_issue": ai_results["issue_subtype"],
            "consumer_complaint_narrative": text_content,
            "company": complaint_data.company or "Union Bank",
            "state": complaint_data.state or "Unknown",
            "zip_code": complaint_data.zip_code or "000000",
            "tags": None,
            "consumer_consent_provided": complaint_data.consumer_consent_provided,
            "submitted_via": complaint_data.submitted_via,
            "date_sent_to_company": datetime.now(),
            "company_response_to_consumer": None,
            "timely_response": "Yes",
            "consumer_disputed": "No",
            "language_detected": "en",
            "sentiment_label": ai_results["sentiment"],
            "sentiment_score": sentiment_score,
            "severity_label": severity_label,
            "severity_score": severity_score,
            "financial_impact_amount": complaint_data.financial_impact_amount or 0.0,
            "keywords_extracted": ai_results["keywords"],
            "embedding_id": str(uuid.uuid4()),
            "duplicate_detected": is_duplicate,
            "duplicate_cluster_id": duplicate_of,
            "similar_complaints_count": len(related_complaints),
            "root_cause_category": rca_result["root_cause"],
            "root_cause_confidence": rca_result["confidence"],
            "root_cause_evidence": rca_result["evidence"], 
            "retrieved_cases": rca_result["similar_cases"],
            "sla_deadline": sla_deadline,
            "sla_status": "On Track",
            "escalation_level": "None",
            "ai_generated_response": "",  # Will be filled later
            "ai_suggested_resolution_template": rca_result["resolution"] or (
                f"We have received your complaint. This issue requires additional investigation "
                f"and has been escalated to our team. Expected resolution time is 3 working days. "
                f"Our team is actively investigating and you will be notified once the investigation is completed."
            ),
            "human_review_status": "Pending",
            "status": "Open",
            "workflow_state": "RECEIVED",
            "audit_log_enabled": True,
            "communication_history": [
                {
                    "type": "created",
                    "actor": "System",
                    "description": f"Complaint Registered via {complaint_data.submitted_via}",
                    "timestamp": datetime.now().isoformat(),
                },
                {
                    "type": "ai_analysis",
                    "actor": "AI Engine",
                    "description": f"Categorized as {ai_results['product']} with {severity_label} severity",
                    "timestamp": datetime.now().isoformat(),
                },
            ],
            "priority_rank": priority_rank,
            "investigation_steps": (
                nba_result["investigation_steps"]
                if nba_result else default_bank_escalation_nba["investigation_steps"]
            ),
            "next_best_actions": (
                nba_result["next_best_actions"]
                if nba_result else default_bank_escalation_nba["next_best_actions"]
            ),
            "nba_source": (
                nba_result["source"]
                if nba_result else "Default Bank Escalation Template"
            ),
            # Agent workflow fields
            "agent_classification": None,
            "classification_timestamp": None,
            "agent_decision": None,
            "decision": None,
            "reasoning": None,
            "assigned_team": None,
            "partner": None,
            "decision_timestamp": None,
            "eta": None,
            "actions": [],
            "agent_action_plan": None,
            "executed_actions": [],
            "action_timestamp": None,
            "resolved_at": None,
            "agent_verification": None,
            "verification_timestamp": None,
            "verification_notes": None,
        }

        # 7. Save initial complaint to DB
        collection = await get_collection("complaints")
        await collection.insert_one(new_complaint)
        
        # Log database operation
        log_system.log_database_operation(
            complaint_id=complaint_id,
            collection="complaints",
            operation="INSERT",
            document_id=new_complaint["_id"],
            fields_changed={"status": "Open", "workflow_state": "RECEIVED"},
            status="SUCCESS"
        )
        
        # 8. Add new complaint to RAG index incrementally!
        rca_e.retriever.add_complaint(new_complaint)
        
        logger.info(f"Complaint {complaint_id} saved to DB and added to RAG index")
        
        # Log workflow stage
        log_system.log_workflow_stage(complaint_id, "Complaint Saved", "Saved to MongoDB and RAG index")

        # 9. Multi-Agent Pipeline
        complaint_dict = complaint_data.model_dump()
        complaint_dict["complaint_id"] = complaint_id
        
        # Set repository dependencies on the agents
        decision_agent.set_repositories(
            get_customer_by_id,
            get_accounts_by_customer_id,
            get_cards_by_customer_id,
            get_transactions_by_customer_id,
            get_complaints_by_customer_id
        )
        action_agent.set_repositories(
            update_credit_card,
            update_debit_card,
            update_account,
            update_transaction,
            insert_audit_log
        )

        print("\n" + "="*80)
        print("Step 1: Classifier Agent")
        print("="*80)
        
        # Time the classification
        classification_start = time.time()
        classification_result = classifier.classify(text_content)
        classification_time = (time.time() - classification_start) * 1000
        
        print(f"Classification: {classification_result}")
        
        # Log agent execution
        log_system.log_agent_execution(
            complaint_id=complaint_id,
            customer_id=customer_id,
            agent_name="ClassificationAgent",
            input_summary=f"Text length: {len(text_content)} chars",
            output_summary=f"Product: {classification_result.get('product')}, Subtype: {classification_result.get('issue_subtype')}, Confidence: {classification_result.get('confidence')}",
            execution_time_ms=classification_time,
            status="SUCCESS",
            confidence=classification_result.get('confidence')
        )
        
        # Log workflow stage
        log_system.log_workflow_stage(complaint_id, "Complaint Classified", 
            f"Product: {classification_result.get('product')}, Issue: {classification_result.get('issue_subtype')}")
        
        # Update DB with CLASSIFIED state
        await collection.update_one(
            {"_id": new_complaint["_id"]},
            {
                "$set": {
                    "workflow_state": "CLASSIFIED",
                    "agent_classification": classification_result,
                    "classification_timestamp": datetime.now().isoformat(),
                    "product": classification_result["product"],
                    "sub_issue": classification_result["issue_subtype"],
                },
                "$push": {
                    "communication_history": {
                        "type": "classification",
                        "actor": "Classifier Agent",
                        "description": f"Classified as {classification_result['product']} / {classification_result['issue_subtype']} with confidence {classification_result['confidence']}",
                        "timestamp": datetime.now().isoformat()
                    }
                }
            }
        )
        new_complaint["workflow_state"] = "CLASSIFIED"
        new_complaint["agent_classification"] = classification_result
        new_complaint["classification_timestamp"] = datetime.now().isoformat()
        
        # Log database operation
        log_system.log_database_operation(
            complaint_id=complaint_id,
            collection="complaints",
            operation="UPDATE",
            document_id=new_complaint["_id"],
            fields_changed={"workflow_state": "CLASSIFIED", "product": classification_result.get('product')},
            status="SUCCESS"
        )

        print("\n" + "="*80)
        print("Step 2: Decision Agent")
        print("="*80)
        
        # Time the decision
        decision_start = time.time()
        decision_result = await decision_agent.decide(classification_result, complaint_dict, [], nba_result)
        decision_time = (time.time() - decision_start) * 1000
        
        print(f"Decision: Product={decision_result.get('product')}, Issue={decision_result.get('issue_subtype')}, Decision={decision_result.get('decision')}, "
              f"Actions={decision_result.get('actions')}, Reasoning={decision_result.get('reasoning')[:50]}")
        
        # Log agent execution
        log_system.log_agent_execution(
            complaint_id=complaint_id,
            customer_id=customer_id,
            agent_name="DecisionAgent",
            input_summary=f"Classification: {classification_result.get('product')} / {classification_result.get('issue_subtype')}, Evidence: {len(decision_result.get('evidence', {}))} collections",
            output_summary=f"Decision: {decision_result.get('decision')}, Actions: {', '.join(decision_result.get('actions', []))}, Reasoning: {decision_result.get('reasoning', '')[:100]}",
            execution_time_ms=decision_time,
            status="SUCCESS",
            confidence=decision_result.get('confidence')
        )
        
        # Log decision reasoning
        log_system.log_decision_agent_reasoning(
            complaint_id=complaint_id,
            customer_id=customer_id,
            classification=classification_result,
            rag_documents=[],
            db_collections_queried=list(decision_result.get('evidence', {}).keys()),
            decision=decision_result.get('decision'),
            confidence=decision_result.get('confidence', 0),
            reasoning_summary=decision_result.get('reasoning', '')
        )
        
        # Calculate ETA based on decision
        eta = calculate_working_days_ahead(datetime.now(), SLA_DAYS_FOR_DECISION.get(decision_result["decision"], 3))
        
        # Create specific bank escalation template if needed
        specific_bank_template = None
        if decision_result["decision"] == "bank_escalation":
            specific_bank_template = (
                f"We have received your complaint regarding {decision_result['issue_subtype']} on {decision_result['product']}. "
                f"This issue requires additional investigation and has been escalated to our {action_agent._get_assigned_team(decision_result['product'])}. "
                f"Expected resolution time is 3 working days. Our team is actively investigating "
                f"and you will be notified once the investigation is completed."
            )
        
        # Update DB with DECISION_MADE state
        update_fields = {
            "workflow_state": "DECISION_MADE",
            "agent_decision": decision_result,
            "decision": decision_result["decision"],
            "reasoning": decision_result["reasoning"],
            "actions": decision_result["actions"],
            "assigned_team": action_agent._get_assigned_team(decision_result["product"]),
            "partner": action_agent._get_partner_from_actions(decision_result["actions"]) if decision_result["decision"] == "partner_escalation" else None,
            "decision_timestamp": datetime.now().isoformat(),
            "eta": eta.isoformat(),
        }
        
        # Add specific bank escalation template if it's a bank escalation case
        if specific_bank_template:
            update_fields["ai_suggested_resolution_template"] = specific_bank_template
        
        await collection.update_one(
            {"_id": new_complaint["_id"]},
            {
                "$set": update_fields,
                "$push": {
                    "communication_history": {
                        "type": "decision",
                        "actor": "Decision Agent",
                        "description": f"Made decision: {decision_result['decision']}",
                        "timestamp": datetime.now().isoformat()
                    }
                }
            }
        )
        new_complaint["workflow_state"] = "DECISION_MADE"
        new_complaint["agent_decision"] = decision_result
        new_complaint["decision"] = decision_result["decision"]
        new_complaint["reasoning"] = decision_result["reasoning"]
        new_complaint["actions"] = decision_result["actions"]
        new_complaint["assigned_team"] = action_agent._get_assigned_team(decision_result["product"])
        new_complaint["partner"] = action_agent._get_partner_from_actions(decision_result["actions"]) if decision_result["decision"] == "partner_escalation" else None
        new_complaint["decision_timestamp"] = datetime.now().isoformat()
        new_complaint["eta"] = eta.isoformat()
        if specific_bank_template:
            new_complaint["ai_suggested_resolution_template"] = specific_bank_template

        print("\n" + "="*80)
        print("Step 3: Action Agent")
        print("="*80)
        
        # Time the actions
        action_start = time.time()
        action_result, update_data, history_entry = await action_agent.execute(
            complaint_id, decision_result, complaint_dict, collection
        )
        action_time = (time.time() - action_start) * 1000
        
        print(f"Action Execution: {action_result}")
        
        # Log agent execution
        log_system.log_agent_execution(
            complaint_id=complaint_id,
            customer_id=customer_id,
            agent_name="ActionAgent",
            input_summary=f"Decision: {decision_result.get('decision')}, Actions: {', '.join(decision_result.get('actions', []))}",
            output_summary=f"Executed: {', '.join(action_result.get('executed_actions', []))}, Status: {action_result.get('complaint_status')}",
            execution_time_ms=action_time,
            status="SUCCESS"
        )
        
        # Log individual actions
        for action in action_result.get('executed_actions', []):
            log_system.log_action_agent_execution(
                complaint_id=complaint_id,
                customer_id=customer_id,
                action=action,
                success=True,
                execution_time_ms=action_time / len(action_result.get('executed_actions', [])),
                details=f"Part of {decision_result.get('decision')} workflow"
            )
        
        # Log workflow stage
        log_system.log_workflow_stage(complaint_id, "Action Executed", 
            f"Executed {len(action_result.get('executed_actions', []))} actions: {', '.join(action_result.get('executed_actions', []))}")
        
        # Update DB with Action Agent results
        await collection.update_one(
            {"_id": new_complaint["_id"]},
            {
                "$set": update_data,
                "$push": {"communication_history": history_entry}
            }
        )
        new_complaint.update(update_data)
        
        # Log database operation
        log_system.log_database_operation(
            complaint_id=complaint_id,
            collection="complaints",
            operation="UPDATE",
            document_id=new_complaint["_id"],
            fields_changed={"status": update_data.get("status"), "workflow_state": "action_executed"},
            status="SUCCESS"
        )
        
        print("\n" + "="*80)
        print("Step 4: Verification Agent")
        print("="*80)
        
        # Time the verification
        verification_start = time.time()
        updated_complaint = await collection.find_one({"_id": new_complaint["_id"]})
        verification_result = verification.verify(complaint_id, decision_result, action_result, updated_complaint)
        verification_time = (time.time() - verification_start) * 1000
        
        print(f"Verification: {verification_result}")
        print("="*80 + "\n")
        
        # Log agent execution
        log_system.log_agent_execution(
            complaint_id=complaint_id,
            customer_id=customer_id,
            agent_name="VerificationAgent",
            input_summary=f"Checks: {len(verification_result.get('checks', []))}",
            output_summary=f"Status: {verification_result.get('status')}, Checks: {', '.join([c['check'] for c in verification_result.get('checks', [])])}",
            execution_time_ms=verification_time,
            status=verification_result.get('status', 'UNKNOWN').upper()
        )
        
        # Log verification result
        log_system.log_verification_result(
            complaint_id=complaint_id,
            customer_id=customer_id,
            checks=verification_result.get('checks', []),
            overall_status=verification_result.get('status', 'unknown'),
            execution_time_ms=verification_time
        )
        
        # Update DB with Verification results
        verification_notes = "; ".join([f"{check['check']}: {'PASS' if check['passed'] else 'FAIL'}" for check in verification_result["checks"]])
        await collection.update_one(
            {"_id": new_complaint["_id"]},
            {
                "$set": {
                    "workflow_state": "VERIFIED",
                    "agent_verification": verification_result,
                    "verification_timestamp": verification_result["timestamp"],
                    "verification_notes": verification_notes,
                },
                "$push": {
                    "communication_history": {
                        "type": "verification",
                        "actor": "Verification Agent",
                        "description": f"Verification status: {verification_result['status']}",
                        "timestamp": datetime.now().isoformat()
                    }
                }
            }
        )
        new_complaint["workflow_state"] = "VERIFIED"
        new_complaint["agent_verification"] = verification_result
        new_complaint["verification_timestamp"] = verification_result["timestamp"]
        new_complaint["verification_notes"] = verification_notes
        
        # Log database operation
        log_system.log_database_operation(
            complaint_id=complaint_id,
            collection="complaints",
            operation="UPDATE",
            document_id=new_complaint["_id"],
            fields_changed={"workflow_state": "VERIFIED", "verification_status": verification_result.get('status')},
            status="SUCCESS"
        )
        
        # Log workflow stage
        log_system.log_workflow_stage(complaint_id, "Verification Complete", 
            f"Status: {verification_result.get('status')}, Checks: {verification_notes}")
        
        # 10. Generate Dynamic Draft Response
        draft_response = generate_dynamic_draft_response(
            decision=decision_result["decision"],
            product=decision_result["product"],
            issue=decision_result["issue_subtype"],
            complaint_id=complaint_id,
            executed_actions=decision_result["actions"],
            assigned_team=action_result.get("assigned_team"),
            partner=action_result.get("partner"),
        )
        await collection.update_one(
            {"_id": new_complaint["_id"]},
            {"$set": {"ai_generated_response": draft_response}}
        )
        new_complaint["ai_generated_response"] = draft_response
        
        # Log database operation
        log_system.log_database_operation(
            complaint_id=complaint_id,
            collection="complaints",
            operation="UPDATE",
            document_id=new_complaint["_id"],
            fields_changed={"ai_generated_response": "Generated"},
            status="SUCCESS"
        )
        
        # Log workflow stage
        log_system.log_workflow_stage(complaint_id, "Response Generated", "AI-generated response created")
        
        # 11. Calculate Relative Rank (Serial Order)
        all_open = (
            await collection.find({"status": {"$nin": ["Resolved", "Closed"]}})
            .sort("priority_rank", -1)
            .to_list(length=1000)
        )
        serial_order = 1
        for i, c in enumerate(all_open):
            if c["complaint_id"] == complaint_id:
                serial_order = i + 1
                break
        new_complaint["serial_priority_order"] = serial_order
        
        # Log database operation
        log_system.log_database_operation(
            complaint_id=complaint_id,
            collection="complaints",
            operation="UPDATE",
            document_id=new_complaint["_id"],
            fields_changed={"serial_priority_order": serial_order},
            status="SUCCESS"
        )

        # 12. Update AI Engine Index
        ai_e.add_to_index(new_complaint["_id"], embedding)
        
        # Log workflow stage
        log_system.log_workflow_stage(complaint_id, "Index Updated", "Added to AI engine index")

        # 13. Volume-based Escalation Check
        if len(related_complaints) > 10:
            await collection.update_one(
                {"_id": new_complaint["_id"]},
                {
                    "$set": {
                        "escalation_level": "Branch",
                        "priority_rank": priority_rank + 0.1,
                        "status": "Escalated",
                    }
                },
            )
            new_complaint["escalation_level"] = "Branch"
            new_complaint["status"] = "Escalated"
            
            # Log database operation
            log_system.log_database_operation(
                complaint_id=complaint_id,
                collection="complaints",
                operation="UPDATE",
                document_id=new_complaint["_id"],
                fields_changed={"escalation_level": "Branch", "status": "Escalated"},
                status="SUCCESS"
            )
            
            # Log workflow stage
            log_system.log_workflow_stage(complaint_id, "Escalated", "Volume-based escalation to Branch level")

        # Log final workflow stage
        log_system.log_workflow_stage(complaint_id, "Workflow Complete", 
            f"Final status: {new_complaint.get('status')}, Decision: {decision_result.get('decision')}")
        
        # Convert ObjectIds to strings before returning
        return convert_objectids_to_strings(new_complaint)

    except Exception as e:
        # Log error
        log_system.log_error(
            agent="register_complaint",
            complaint_id=complaint_id if 'complaint_id' in dir() else "UNKNOWN",
            exception=e,
            status="ERROR"
        )
        logger.error(f"Error registering complaint: {str(e)}", exc_info=True)
        raise


async def get_all_complaints():
    collection = await get_collection("complaints")
    cursor = collection.find({})
    complaints = await cursor.to_list(length=1000)

    # Dynamically update SLA status, Escalation, and Rank
    now = datetime.now()

    # 1. Separate unresolved to calculate ranks
    unresolved = [
        c
        for c in complaints
        if c.get("status", "").lower() not in ["resolved", "closed"]
    ]

    def get_dynamic_score(c):
        p_base = c.get("priority_rank", 0)
        t_start = c.get("date_received")
        t_sla = c.get("sla_deadline")

        if not t_start or not t_sla:
            return p_base

        if now <= t_sla:
            total_sla = (t_sla - t_start).total_seconds()
            elapsed = (now - t_start).total_seconds()
            u_time = (elapsed / total_sla) * 0.5 if total_sla > 0 else 0.5
        else:
            overdue = (now - t_sla).total_seconds()
            days_overdue = overdue / (60 * 60 * 24)
            u_time = 0.5 + (days_overdue * 0.2)
        return p_base + u_time

    # Sort by dynamic score
    unresolved_sorted = sorted(unresolved, key=get_dynamic_score, reverse=True)

    # Create a map for quick rank lookup
    rank_map = {c["complaint_id"]: i + 1 for i, c in enumerate(unresolved_sorted)}

    updated_complaints = []
    for c in complaints:
        is_unresolved = c.get("status", "").lower() not in ["resolved", "closed"]

        if is_unresolved:
            c["serial_priority_order"] = rank_map.get(c["complaint_id"], 1)

            # Update SLA/Escalation
            sla_deadline = c.get("sla_deadline")
            current_sla = c.get("sla_status", "On Track")
            current_escalation = c.get("escalation_level", "None")

            needs_update = False
            new_sla = current_sla
            new_escalation = current_escalation

            if sla_deadline and now > sla_deadline:
                if current_sla != "Breached":
                    new_sla = "Breached"
                    needs_update = True
                if current_escalation == "None":
                    new_escalation = "Branch"
                    needs_update = True

            if needs_update:
                await collection.update_one(
                    {"_id": c["_id"]},
                    {
                        "$set": {
                            "sla_status": new_sla,
                            "escalation_level": new_escalation,
                            "serial_priority_order": c["serial_priority_order"],
                        }
                    },
                )
                c["sla_status"] = new_sla
                c["escalation_level"] = new_escalation

        updated_complaints.append(c)

    # Convert ObjectIds to strings before returning
    return convert_objectids_to_strings(updated_complaints)


async def update_complaint_status(
    complaint_id: str, status: str, resolution: Optional[str] = None
):
    collection = await get_collection("complaints")

    current = await collection.find_one({"_id": complaint_id})
    if not current:
        return None

    history_entry = {
        "type": "status_update",
        "actor": "Admin",
        "description": f"Complaint status updated to {status}",
        "timestamp": datetime.now().isoformat(),
    }

    if status.lower() == "resolved":
        history_entry["type"] = "resolution"
        history_entry["description"] = "Complaint marked as Resolved"
    elif status.lower() == "in progress":
        history_entry["type"] = "ongoing"
        history_entry["description"] = "Complaint marked as Ongoing"

    update_data = {
        "status": status,
        "updated_at": datetime.now(),
    }

    if resolution:
        update_data["resolution_text"] = resolution

    await collection.update_one(
        {"_id": complaint_id},
        {"$set": update_data, "$push": {"communication_history": history_entry}},
    )
    result = await collection.find_one({"_id": complaint_id})
    return convert_objectids_to_strings(result) if result else None

async def get_user_from_session(
    session_id: str
):
    sessions = await get_collection(
        "sessions"
    )

    session = await sessions.find_one(
        {
            "session_id": session_id
        }
    )

    if not session:
        return None

    role = session["role"]
    user_id = session["user_id"]

    if role == "customer":
        collection = await get_collection(
            "customeracc"
        )

    elif role == "admin":
        collection = await get_collection(
            "adminlogin"
        )

    elif role == "branch_manager":
        collection = await get_collection(
            "branchmanager"
        )

    else:
        return None

    from bson import ObjectId

    user = await collection.find_one(
        {
            "_id": ObjectId(user_id)
        }
    )

    if not user:
        return None

    if role == "customer":
        return {
            "customer_id":
                user.get("customer_id"),
            "customer_name":
                user.get("customer_name"),
            "account_number":
                user.get("account_number"),
            "email":
                user.get("email"),
            "phone":
                user.get("phone"),
            "branch_id":
                user.get("branch_id"),
            "state":
                user.get("state"),
            "zip_code":
                user.get("zip_code"),
            "role":
                "customer",
        }

    elif role == "admin":
        return {
            "name":
                user.get("name"),
            "email":
                user.get("email"),
            "role":
                "admin",
        }

    else:
        return {
            "name":
                user.get("name"),
            "email":
                user.get("email"),
            "branch_id":
                user.get("branch_id"),
            "role":
                "branch_manager",
        }


# ------------------------------
# Repository Functions for Banking Collections
# ------------------------------
async def get_customer_by_id(customer_id: str):
    """Get customer profile from customers collection"""
    collection = await get_collection("customers")
    return await collection.find_one({"customer_id": customer_id})


async def get_accounts_by_customer_id(customer_id: str):
    """Get all accounts for a customer"""
    collection = await get_collection("accounts")
    cursor = collection.find({"customer_id": customer_id})
    return await cursor.to_list(100)


async def get_cards_by_customer_id(customer_id: str):
    """Get all cards (credit/debit) for a customer"""
    # Check both creditcards and debitcards collections
    credit_coll = await get_collection("creditcards")
    debit_coll = await get_collection("debitcards")
    
    credit_cards = await credit_coll.find({"customer_id": customer_id}).to_list(100)
    debit_cards = await debit_coll.find({"customer_id": customer_id}).to_list(100)
    
    # Mark card type
    for card in credit_cards:
        card["card_type"] = "credit"
    for card in debit_cards:
        card["card_type"] = "debit"
    
    return credit_cards + debit_cards


async def get_transactions_by_customer_id(customer_id: str, limit: int = 20):
    """Get recent transactions for a customer"""
    collection = await get_collection("transaction")
    cursor = collection.find({"customer_id": customer_id}).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(limit)


async def get_complaints_by_customer_id(customer_id: str, limit: int = 10):
    """Get complaint history for a customer.

    Returns a lightweight summary only — never the full stored complaint
    document. Full documents carry their own agent_decision.evidence and
    retrieved_cases fields, and those in turn contain the customer's earlier
    complaint history. Returning full documents here causes each new
    complaint to embed all previous complaints (which embed the ones before
    them, recursively), eventually exceeding MongoDB's 16MB document limit.
    """
    collection = await get_collection("complaints")
    cursor = (
        collection.find(
            {"customer_id": customer_id},
            {
                "complaint_id": 1,
                "product": 1,
                "issue": 1,
                "sub_issue": 1,
                "status": 1,
                "severity_label": 1,
                "date_received": 1,
                "consumer_complaint_narrative": 1,
            },
        )
        .sort("date_received", -1)
        .limit(limit)
    )
    return await cursor.to_list(limit)


async def update_credit_card(card_id: str, update_data: dict):
    """Update credit card details (e.g., block status)"""
    from bson import ObjectId
    collection = await get_collection("creditcards")
    result = await collection.update_one(
        {"_id": ObjectId(card_id)},
        {"$set": update_data}
    )
    return result.modified_count > 0


async def update_debit_card(card_id: str, update_data: dict):
    """Update debit card details"""
    from bson import ObjectId
    collection = await get_collection("debitcards")
    result = await collection.update_one(
        {"_id": ObjectId(card_id)},
        {"$set": update_data}
    )
    return result.modified_count > 0


async def update_account(account_id: str, update_data: dict):
    """Update account details"""
    from bson import ObjectId
    collection = await get_collection("accounts")
    result = await collection.update_one(
        {"_id": ObjectId(account_id)},
        {"$set": update_data}
    )
    return result.modified_count > 0


async def update_transaction(transaction_id: str, update_data: dict):
    """Update transaction details"""
    from bson import ObjectId
    collection = await get_collection("transaction")
    result = await collection.update_one(
        {"_id": ObjectId(transaction_id)},
        {"$set": update_data}
    )
    return result.modified_count > 0


async def insert_audit_log(log_data: dict):
    """Insert audit log entry"""
    collection = await get_collection("audit_logs")
    log_data["timestamp"] = datetime.now().isoformat()
    await collection.insert_one(log_data)


async def get_credit_card_by_number(card_number: str):
    """Get a single credit card by its number"""
    collection = await get_collection("creditcards")
    return await collection.find_one({"card_number": card_number})


async def get_debit_card_by_number(card_number: str):
    """Get a single debit card by its number"""
    collection = await get_collection("debitcards")
    return await collection.find_one({"card_number": card_number})


def convert_objectids_to_strings(obj):
    """Recursively convert all ObjectId instances to strings in a dict/list"""
    from bson.objectid import ObjectId
    if isinstance(obj, dict):
        return {k: convert_objectids_to_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectids_to_strings(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj