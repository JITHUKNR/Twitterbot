import os
from flask import Flask, request
from telegram import Bot, Update

# --- 1. Clients സജ്ജീകരിക്കുന്നു ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

# --- 2. Webhook Route ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        
        if update.message and update.message.text:
            chat_id = update.message.chat.id
            text = update.message.text.lower()
            
            if text == "/start":
                reply = "Hello! Your simple bot is now working perfectly on Render! Type 'hi' or 'send' to get a reply."
            elif 'hi' in text or 'send' in text:
                reply = "Congratulations! This simple bot is working without any external API errors!"
            else:
                reply = "I received your message. Everything is fine!"
            
            bot.send_message(chat_id=chat_id, text=reply)
        
    except Exception as e:
        print(f"Error processing update: {e}")
        pass
        
    return "ok", 200

# --- 3. App Start ---
@app.route('/')
def index():
    return "Simple Bot is Live!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
  
