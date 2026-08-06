import os
import poplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
import smtplib
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv

load_dotenv()

# Gmail POP and SMTP servers
POP_HOST = os.getenv("POP_HOST", "pop.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

USERNAME = os.getenv("EMAIL_USERNAME", "phishyphishy4@gmail.com")
PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")  # Use your Gmail App Password

# Where to store ingested complaints (same backend DB logic used elsewhere)
# If your DB integration is different, wire it up as needed.
# For now this script only demonstrates: POP -> parse -> (optional) store -> SMTP reply.


def decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    decoded, encoding = decode_header(value)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(encoding or "utf-8", errors="replace")
    return decoded


def extract_body(msg: email.message.Message) -> str:
    """Best-effort extraction of text/plain body excluding attachments."""
    body_text = None

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() != "text/plain":
                continue

            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition.lower():
                continue

            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                body_text = payload.decode(errors="replace")
            except Exception:
                body_text = None

            if body_text is not None:
                break

        if body_text is None:
            # fallback: first text/plain part (even if headers are weird)
            for part in msg.walk():
                if part.get_content_type() != "text/plain":
                    continue
                try:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    body_text = payload.decode(errors="replace")
                except Exception:
                    body_text = None
                break
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload is not None:
                body_text = payload.decode(errors="replace")
        except Exception:
            body_text = None

    return (body_text or "").strip()


def send_reply(to_address: str, subject: str, body: str) -> None:
    msg = MIMEText(body)
    msg["From"] = USERNAME
    msg["To"] = to_address
    msg["Subject"] = subject

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(USERNAME, PASSWORD)
        server.send_message(msg)
        print(f"Reply sent to {to_address}")


def parse_email(raw: bytes) -> Dict[str, Any]:
    msg = email.message_from_bytes(raw)

    subject = decode_header_value(msg.get("Subject"))
    from_header = decode_header_value(msg.get("From"))
    reply_to = msg.get("Reply-To")
    reply_to_value = decode_header_value(reply_to) if reply_to else ""

    body_text = extract_body(msg)

    # Identify customer email for reply
    # If Reply-To is present, prefer it; otherwise parse From.
    customer_email = reply_to_value or from_header

    return {
        "subject": subject,
        "from_header": from_header,
        "customer_email": customer_email,
        "body": body_text,
    }


def build_complaint_record(from_addr: str, subject: str, body: str) -> Dict[str, Any]:
    """Creates a complaint-like payload that matches backend/models.py ComplaintCreate fields."""
    # Minimal mapping consistent with backend/models.py
    # You can enhance by extracting product/issue from body using your AI engine.
    payload: Dict[str, Any] = {
        "customer_id": from_addr or "EMAIL-CUSTOMER",
        "customer_name": from_addr or "Customer",
        "product": "Email",
        "sub_product": None,
        "issue": "Email Complaint",
        "sub_issue": None,
        "consumer_complaint_narrative": body or f"(No body found) Subject: {subject}",
        "company": "Union Bank",
        "state": None,
        "zip_code": None,
        "submitted_via": "Email",
        "consumer_consent_provided": "Yes",
        "financial_impact_amount": 0.0,
    }
    return payload


def main(max_messages: int = 10) -> None:
    if not PASSWORD:
        raise RuntimeError(
            "EMAIL_APP_PASSWORD is missing. Set it in .env (recommended) or environment variables."
        )

    server = poplib.POP3_SSL(POP_HOST)
    server.user(USERNAME)
    server.pass_(PASSWORD)

    _resp, listings, _octets = server.list()
    msg_numbers: List[int] = [int(line.split()[0]) for line in listings if line.split()]

    print(f"Total emails: {len(msg_numbers)}")

    for num in msg_numbers[:max_messages]:
        _resp, lines, _octets = server.retr(num)
        raw = b"\n".join(lines)

        parsed = parse_email(raw)
        subject = parsed["subject"]
        from_header = parsed["from_header"]
        customer_email = parsed["customer_email"]
        body_text = parsed["body"]

        print("Subject:", subject)
        print("From:", from_header)
        print("Customer email (best-effort):", customer_email)
        print("Body:", body_text[:300] + ("..." if len(body_text) > 300 else ""))

        # Create complaint record payload (you can POST to FastAPI /complaints or /chatbot etc.)
        complaint_payload = build_complaint_record(from_header, subject, body_text)

        # TODO: Store complaint into DB.
        # Option A: POST to your FastAPI endpoint (not implemented here).
        # Option B: Directly call services.register_complaint (async) from within this script.
        # For now, we keep it simple and only reply.

        # Reply back to customer
        if body_text:
            reply_subject = f"Re: {subject}" if subject else "Re:"
            reply_body = (
                "Thanks for contacting Union Bank. "
                "We have received your email and will review your complaint shortly. "
                "For reference, we recorded the following message:\n\n"
                f"{body_text}\n\n"
                "— Smart Resolve Bot"
            )
            send_reply(customer_email, reply_subject, reply_body)
        else:
            reply_subject = f"Re: {subject}" if subject else "Re:"
            send_reply(
                customer_email,
                reply_subject,
                "Thanks for contacting Union Bank. We received your email. Please reply with more details so we can resolve your complaint faster."
            )

        print("=" * 50)

    server.quit()


if __name__ == "__main__":
    # Example: process up to 10 emails
    main(max_messages=10)

