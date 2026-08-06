from typing import Optional

from fastapi import Body

from backend.models import ComplaintCreate
from backend.services import register_complaint



async def ingest_email_to_complaint(
    *,

    customer_id: str,
    customer_name: str,
    email_subject: str,
    email_body: str,
    customer_email: Optional[str] = None,
) -> dict:
    """Create a complaint from an email payload.

    Intended for the HTTP/API email channel (admin/user submits subject+body).
    POP retrieval is handled by admin_email_ingest_job.py.
    """

    narrative = (email_body or "").strip()
    if not narrative:
        narrative = f"(No email body provided) Subject: {email_subject or ''}".strip()

    complaint = ComplaintCreate(
        customer_id=customer_id,
        customer_name=customer_name,
        product="Email",
        sub_product=None,
        issue=(email_subject or "").strip() or "Email Complaint",
        sub_issue=None,
        consumer_complaint_narrative=narrative,
        submitted_via="Email",
        financial_impact_amount=0.0,
        state=None,
        zip_code=None,
        consumer_consent_provided="Yes",
    )

    return await register_complaint(complaint)


