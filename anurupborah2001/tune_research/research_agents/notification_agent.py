import os
import requests
import sendgrid
from sendgrid.helpers.mail import Email, Mail, Content, To
from agents import Agent, function_tool
from lib.env_var import MODEL, PUSHOVER_USER_KEY, PUSHOVER_API_TOKEN, USER_EMAIL, SEND_EMAIL

@function_tool
def send_pushover(title: str, message: str) -> dict[str, str]:
    """Send a Pushover notification with the given message"""
    pushover_url = "https://api.pushover.net/1/messages.json"
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        raise ValueError("Pushover user key and API token must be set in environment variables.")
    print(f"Sending Pushover notification with title: {title} and message: {message}")
    payload = {"user": PUSHOVER_USER_KEY, "token": PUSHOVER_API_TOKEN, "title": title, "message": message}
    requests.post(pushover_url, data=payload)
    return {"status": "success"}

@function_tool
def send_email(subject: str, html_body: str) -> dict[str, str]:
    """Send an email with the given subject and HTML body"""
    sg = sendgrid.SendGridAPIClient(api_key=os.environ.get("SENDGRID_API_KEY"))
    from_email = Email(USER_EMAIL)
    to_email = To(USER_EMAIL)
    content = Content("text/html", html_body)
    mail = Mail(from_email, to_email, subject, content).get()
    response = sg.client.mail.send.post(request_body=mail)
    print("Email response", response.status_code)
    print(f"Sending email with subject: {subject}")
    return {"status": "success"}

NOTIFICATION_AGENT_INSTRUCTIONS = f"""You are able to send a nicely formatted HTML email based on a detailed report or send a simple text message using pushover.
You will be provided with a detailed report. You should use your tool to send one email or simple message with a suitable title related to the report, providing the
report converted into clean, well presented HTML with an appropriate subject line.
{"You should send the email to the user with an appropriate subject line, formatted well so it can also be printed nicely if needed." if SEND_EMAIL else "You should send a Pushover notification to the user with an appropriate title, summarizing the report concisely since Pushover messages are short."}"""

notification_agent = Agent(
    name="Notification agent",
    instructions=NOTIFICATION_AGENT_INSTRUCTIONS,
    tools=[send_email, send_pushover],
    model=MODEL
)
