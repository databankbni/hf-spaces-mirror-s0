import os
import threading
import time
import requests
import telebot
import psycopg2
from flask import Flask, request, jsonify, send_file

# Environment Variables (HF Secrets se uthayega)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SPACE_URL = os.environ.get("SPACE_URL", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

app = Flask(__name__)

# --- 1. POSTGRESQL DATABASE ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"DB Error: {e}", flush=True)
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS store (key TEXT PRIMARY KEY, value TEXT)')
        conn.commit()
        cursor.close()
        conn.close()
        print("Database Initialized!", flush=True)

# --- 2. FLASK ROUTES (Frontend ke liye) ---
@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    key = request.args.get('key')
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM store WHERE key = %s', (key,))
        row = cursor.fetchone()
        conn.close()
        return jsonify({"value": row[0] if row else "[]"})
    return jsonify({"value": "[]"})

@app.route('/api/data', methods=['POST'])
def set_data():
    data = request.json
    key, value = data.get('key'), data.get('value')
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO store (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value', (key, value))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 500

# --- 3. BOT LOGIC ---
def run_bot():
    bot = telebot.TeleBot(BOT_TOKEN)

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        markup = telebot.types.InlineKeyboardMarkup()
        webapp = telebot.types.WebAppInfo(url=SPACE_URL)
        btn = telebot.types.InlineKeyboardButton("📱 Open OpsDesk", web_app=webapp)
        markup.add(btn)
        bot.reply_to(message, "OpsDesk ready hai!", reply_markup=markup)

    print("Bot polling start...", flush=True)
    bot.infinity_polling()

# --- 4. STARTUP ---
if __name__ == '__main__':
    init_db()
    threading.Thread(target=run_bot, daemon=True).start()
    # Gunicorn se chalane ke liye niche ki line ki zaroorat nahi
    