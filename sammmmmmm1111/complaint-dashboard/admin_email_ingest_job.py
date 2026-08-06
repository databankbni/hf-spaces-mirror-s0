import os
import asyncio
import poplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
import smtplib
from typing import Optional, Dict, Any, List, Tuple

from dotenv import load_dotenv

# FastAPI internal imports
from models import ComplaintCreate
from services import register_complaint
# ai_engine is intentionally not imported here to avoid heavy imports at job startup.



load_dotenv()

POP_HOST = os.getenv("POP_HOST", "pop.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

USERNAME = os.getenv("EMAIL_USERNAME", "phishyphishy4@gmail.com")
PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")

# Configure how many unseen messages to ingest per run
DEFAULT_MAX_MESSAGES = int(os.getenv("EMAIL_INGEST_MAX", "10"))


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
            # fallback: first text/plain part
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



def _extract_email_address(header_value: str) -> str:
    """Best-effort extraction of a bare email address from a header like:
    'Name <email@example.com>' or '<email@example.com>'.
    """
    if not header_value:
        return ""

    # Common case: Name <addr>
    if "<" in header_value and ">" in header_value:
        start = header_value.find("<") + 1
        end = header_value.rfind(">")
        candidate = header_value[start:end].strip()
        if candidate:
            return candidate

    # Fallback: if header is already an address
    return header_value.strip()


def parse_email(raw: bytes) -> Dict[str, Any]:
    msg = email.message_from_bytes(raw)

    subject = decode_header_value(msg.get("Subject"))
    from_header = decode_header_value(msg.get("From"))

    reply_to = msg.get("Reply-To")
    reply_to_value = decode_header_value(reply_to) if reply_to else ""

    customer_email_header = reply_to_value or from_header
    customer_email = _extract_email_address(customer_email_header)

    body_text = extract_body(msg)

    return {
        "subject": subject,
        "from_header": from_header,
        "customer_email": customer_email,
        "body": body_text,
    }



def build_complaint_payload(from_addr: str, subject: str, body: str) -> ComplaintCreate:
    # Minimal mapping to ComplaintCreate. AI will fill product/issue/severity.
    return ComplaintCreate(
        customer_id=from_addr or "EMAIL-CUSTOMER",
        customer_name=from_addr or "Customer",
        product="Email",
        sub_product=None,
        issue=subject or "Email Complaint",
        sub_issue=None,
        consumer_complaint_narrative=body or f"(No body found) Subject: {subject}",
        company="Union Bank",
        state=None,
        zip_code=None,
        submitted_via="Email",
        consumer_consent_provided="Yes",
        financial_impact_amount=0.0,
    )


async def ingest_and_reply(max_messages: int = DEFAULT_MAX_MESSAGES) -> List[Dict[str, Any]]:

    if not PASSWORD:
        raise RuntimeError("EMAIL_APP_PASSWORD is missing. Set it in .env as a Gmail App Password.")

    server = poplib.POP3_SSL(POP_HOST)
    server.user(USERNAME)
    server.pass_(PASSWORD)

    _resp, listings, _octets = server.list()
    msg_numbers: List[int] = [int(line.split()[0]) for line in listings if line.split()]

    processed: List[Dict[str, Any]] = []

    for num in msg_numbers[:max_messages]:
        _resp, lines, _octets = server.retr(num)
        raw = b"\n".join(lines)

        parsed = parse_email(raw)
        subject = parsed["subject"]
        from_header = parsed["from_header"]
        customer_email = parsed["customer_email"]
        body_text = parsed["body"]

        # Log that an email was read
        print(f"Read email from POP message {num}: subject='{subject}', from='{from_header}'")

        if not customer_email:
            # Skip sending a reply if we cannot determine a valid email address.
            print(
                f"Skipping reply: could not extract email address from From/Reply-To. From header: {from_header}"
            )
            continue

        # 1) Store into DB (via services.register_complaint)

        complaint = build_complaint_payload(from_header, subject, body_text)
        stored = await register_complaint(complaint)

        # 2) Reply back to customer with AI acknowledgement draft
        ai_answer = stored.get("ai_generated_response") or "Thanks for contacting."
        reply_subject = f"Re: {subject}" if subject else "Re:"
        reply_body = (
            f"We received your email to Union Bank.\n\n"
            f"--- Incoming email body ---\n{body_text or '(empty)'}\n\n"
            f"--- Our AI response draft ---\n{ai_answer}\n"
        )
        send_reply(customer_email, reply_subject, reply_body)

        processed.append({
            "pop_message_id": num,
            "customer": customer_email,
            "complaint_id": stored.get("complaint_id"),
            "status": "stored_and_replied",
        })

    server.quit()
    return processed


def run_once(max_messages: int = DEFAULT_MAX_MESSAGES) -> List[Dict[str, Any]]:
    return asyncio.run(ingest_and_reply(max_messages=max_messages))


if __name__ == "__main__":
    results = run_once()
    print("Ingest results:", results)

