from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai
from config import GEMINI_API_KEY, BUSINESS_NAME, PORT, DEBUG
from knowledge import KNOWLEDGE_BASE
from tickets import save_ticket, get_all_tickets, close_ticket
from email_sender import send_ticket_email
# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# Home route
@app.route('/')
def home():
    return render_template('index.html')
# List available models
@app.route('/models')
def list_models():
    models = genai.list_models()
    model_names = [m.name for m in models]
    return jsonify({"models": model_names})
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        # Build prompt with knowledge base
        prompt = f"""
You are a professional customer support agent for {BUSINESS_NAME}.

STRICT RULES:
1. ONLY answer questions related to this business
2. ONLY use information from the KNOWLEDGE BASE below
3. If a customer wants to speak to a manager or human → say "Of course! I completely understand. Let me connect you with our team right away. Please call us at +92-51-1234567 or WhatsApp us and someone will assist you shortly! 😊"
4. If the question is about something NOT in our knowledge base → say "That's a great question! I don't have that information right now, but let me connect you with a human agent who can help. Please call +92-51-1234567 📞"
5. If the question is completely unrelated to business (weather, sports, general knowledge) → say "I'm a business-specific support agent for {BUSINESS_NAME}. I can only help with questions about our products and services."
6. For greetings like "hi", "hello", "hey" → greet back warmly and ask how you can help
7. For compliments like "nice", "great", "thanks", "awesome" → respond naturally and warmly
8. For farewells like "bye", "goodbye" → say goodbye warmly
9. Never make up information
10. Always be polite, friendly and professional

KNOWLEDGE BASE:
{KNOWLEDGE_BASE}

Customer question: {user_message}

Answer:"""

        # Send to Gemini
        response = model.generate_content(prompt)
        reply = response.text

        if any(phrase in reply.lower() for phrase in [
            "connect you with a human agent",
            "human agent",
            "call us at",
            "whatsapp us",
            "let me connect"
        ]):
            ticket = save_ticket(user_message, reply)
            result = send_ticket_email(ticket)
            print(f"Email sent: {result}")

        return jsonify({"reply": reply})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"reply": "Sorry, I am having trouble right now. Please call +92-51-1234567 for help."})
   
# Admin dashboard
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')
# Get all tickets
@app.route('/tickets')
def tickets():
    all_tickets = get_all_tickets()
    return jsonify({"tickets": all_tickets})

# Close a ticket
@app.route('/tickets/close/<int:ticket_id>', methods=['POST'])
def close(ticket_id):
    close_ticket(ticket_id)
    return jsonify({"message": f"Ticket {ticket_id} closed"})
# Run the app
if __name__ == '__main__':
 app.run(host='0.0.0.0', debug=DEBUG, port=PORT)