import json
import os
from datetime import datetime

TICKETS_FILE = 'tickets.json'

def save_ticket(customer_message, ai_response):
    # Load existing tickets
    tickets = []
    if os.path.exists(TICKETS_FILE):
        with open(TICKETS_FILE, 'r') as f:
            tickets = json.load(f)

    # Create new ticket
    ticket = {
        "id": len(tickets) + 1,
        "customer_message": customer_message,
        "ai_response": ai_response,
        "status": "open",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Save ticket
    tickets.append(ticket)
    with open(TICKETS_FILE, 'w') as f:
        json.dump(tickets, f, indent=2)

    return ticket

def get_all_tickets():
    if os.path.exists(TICKETS_FILE):
        with open(TICKETS_FILE, 'r') as f:
            return json.load(f)
    return []

def close_ticket(ticket_id):
    tickets = get_all_tickets()
    for ticket in tickets:
        if ticket['id'] == ticket_id:
            ticket['status'] = 'closed'
    with open(TICKETS_FILE, 'w') as f:
        json.dump(tickets, f, indent=2)