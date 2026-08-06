#models.py
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Any, Dict
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    CUSTOMER = "customer"
    BRANCH_MANAGER = "branch_manager"

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: UserRole
    branch_id: Optional[str] = None

class UserLogin(BaseModel):
    role: str
    identifier: str
    password: str

class User(BaseModel):
    id: str = Field(alias="_id")
    email: EmailStr
    name: str
    role: UserRole
    branch_id: Optional[str] = None
    region_id: Optional[str] = None
    created_at: datetime
    
    model_config = {
        "populate_by_name": True
    }

class ComplaintCreate(BaseModel):
    customer_id: str
    customer_name: str
    branch_id: Optional[str] = None
    product: Optional[str] = "General"
    sub_product: Optional[str] = None
    issue: Optional[str] = "General Inquiry"
    sub_issue: Optional[str] = None
    consumer_complaint_narrative: str
    company: str = "Union Bank"
    state: Optional[str] = None
    zip_code: Optional[str] = None
    submitted_via: str # Email, OCR, Chatbot, Voice, Web
    consumer_consent_provided: str = "Yes"
    financial_impact_amount: Optional[float] = 0.0

class ComplaintUpdate(BaseModel):
    human_review_status: Optional[str] = None
    status: Optional[str] = None
    company_response_to_consumer: Optional[str] = None

class Complaint(BaseModel):
    id: str = Field(alias="_id")
    complaint_id: str
    customer_id: str
    customer_name: str
    branch_id: Optional[str] = None
    date_received: datetime
    product: str
    sub_product: Optional[str] = None
    issue: str
    sub_issue: Optional[str] = None
    consumer_complaint_narrative: str
    company: str
    state: Optional[str] = None
    zip_code: Optional[str] = None
    tags: Optional[str] = None
    consumer_consent_provided: str
    submitted_via: str
    date_sent_to_company: datetime
    company_response_to_consumer: Optional[str] = None
    timely_response: str = "Yes"
    consumer_disputed: str = "No"
    language_detected: str = "en"
    sentiment_label: str
    sentiment_score: float
    severity_label: str
    severity_score: float
    financial_impact_amount: float = 0.0
    keywords_extracted: List[str] = []
    embedding_id: Optional[str] = None
    duplicate_detected: bool = False
    duplicate_cluster_id: Optional[str] = None
    similar_complaints_count: int = 0
    root_cause_category: Optional[str] = None
    sla_deadline: datetime
    sla_status: str # On Track, At Risk, Breached
    escalation_level: str # Branch, Regional Office, MD/CEO Desk
    ai_generated_response: Optional[str] = None
    ai_suggested_resolution_template: Optional[str] = None
    human_review_status: str = "Pending" # Pending, Approved, Rejected
    status: str = "Open" # Open, In Progress, Resolved, Escalated
    audit_log_enabled: bool = True
    communication_history: List[Dict[str, Any]] = []
    priority_rank: float = 0.0
    root_cause_confidence: Optional[float] = None
    root_cause_evidence: Optional[List[str]] = []
    retrieved_cases: Optional[List[Dict[str, Any]]] = []
    
    model_config = {
        "populate_by_name": True
    }
