import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, BUSINESS_NAME

def send_ticket_email(ticket):
    try:
        # Create email
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = f"🎫 New Support Ticket #{ticket['id']} — {BUSINESS_NAME}"

        # Email body
        body = f"""
New support ticket received!

━━━━━━━━━━━━━━━━━━━━━━━━
Ticket ID:     #{ticket['id']}
Status:        {ticket['status'].upper()}
Time:          {ticket['created_at']}
━━━━━━━━━━━━━━━━━━━━━━━━

Customer Message:
"{ticket['customer_message']}"

AI Response:
"{ticket['ai_response']}"

━━━━━━━━━━━━━━━━━━━━━━━━
View all tickets: http://127.0.0.1:5000/dashboard
━━━━━━━━━━━━━━━━━━━━━━━━

{BUSINESS_NAME} Support System
        """

        msg.attach(MIMEText(body, 'plain'))

        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()

        print(f"✅ Ticket email sent for ticket #{ticket['id']}")
        return True

    except Exception as e:
        print(f"❌ Email error: {e}")
        return False