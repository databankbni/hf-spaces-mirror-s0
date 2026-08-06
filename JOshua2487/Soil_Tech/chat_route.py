from flask import Blueprint, request, jsonify
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

chat_bp = Blueprint('chat', __name__)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

@chat_bp.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()

    soil_type            = data.get('soil_type', '')
    om_level             = data.get('om_level', '')
    crop_name            = data.get('crop_name', '')
    amendments           = data.get('amendments', [])
    conversation_history = data.get('conversation_history', [])
    user_message         = data.get('user_message', '').strip()
    farmer_name          = data.get('farmer_name', 'Kuya')

    if not user_message:
        return jsonify({'error': 'user_message is required'}), 400

    if not soil_type or not crop_name:
        return jsonify({'error': 'soil_type and crop_name are required'}), 400

    amendments_text = ', '.join(amendments) if amendments else 'none'

    system_prompt = f"""You are a soil advisor assistant for Filipino smallholder farmers.
You are speaking with a farmer named {farmer_name}.
Always address them by name in your responses.
You are only allowed to answer questions related to the following soil scan result:

Soil Type: {soil_type}
Organic Matter Level: {om_level}
Crop Chosen: {crop_name}
Recommended Amendments: {amendments_text}

Strict rules:
- Only answer questions directly related to this specific soil scan.
- Do not answer questions about other crops, other soil scans, or unrelated topics.
- If the farmer asks something unrelated, politely redirect them back to this scan.
- Speak in simple, plain language suitable for a Filipino farmer.
- Address the farmer as {farmer_name} naturally in your response.
- Keep answers short and practical (3 to 5 sentences max)."""

    messages = [{"role": "system", "content": system_prompt}]
    messages += conversation_history
    messages.append({"role": "user", "content": user_message})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=500,
        )
        reply = response.choices[0].message.content.strip()
        return jsonify({'reply': reply})
    except Exception as e:
        return jsonify({'error': str(e)}), 500