import os
import logging
from groq import Groq  # Groq ലൈബ്രറി ഇമ്പോർട്ട് ചെയ്യുന്നു
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ലോഗിംഗ്
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 3 Environment Variables-ഉം ലോഡ് ചെയ്യുന്നു ---
TOKEN = os.environ.get('TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

# ------------------------------------------------------------------
# --- AI-യുടെ സ്വഭാവം ഇവിടെ സെറ്റ് ചെയ്യാം (SYSTEM PROMPT) ---
SYSTEM_PROMPT = (
    "You are a friendly, romantic, and slightly flirty chat companion. "
    "Your name is 'Tae' (like the user's bot name). "
    "You are not an AI assistant. You are here to have a fun and engaging conversation. "
    "Keep your replies short and interesting. Use emojis sometimes. "
    "Never say you are an AI or a language model."
)
# ------------------------------------------------------------------

# --- Groq AI ക്ലയന്റ് സെറ്റപ്പ് ചെയ്യുന്നു ---
try:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY സെറ്റ് ചെയ്തിട്ടില്ല.")
    
    groq_client = Groq(api_key=GROQ_API_KEY)
    
    # ചാറ്റ് ഹിസ്റ്ററി ഓർമ്മിക്കാൻ
    chat_history = {} 

    logger.info("Groq AI ക്ലയന്റ് (Flirty Persona) വിജയകരമായി ലോഡ് ചെയ്തു.")
except Exception as e:
    logger.error(f"Groq AI സെറ്റപ്പ് പരാജയപ്പെട്ടു: {e}")
    groq_client = None

# /start കമാൻഡിന് മറുപടി
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    user_id = update.message.from_user.id
    if user_id in chat_history:
        del chat_history[user_id]  # ചാറ്റ് ഹിസ്റ്ററി റീസെറ്റ് ചെയ്യുന്നു
        
    await update.message.reply_text(f'Hey {user_name}... What\'s on your mind? 😉')

# ടെക്സ്റ്റ് മെസ്സേജുകൾ കൈകാര്യം ചെയ്യുന്ന ഫംഗ്ഷൻ
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client:
        await update.message.reply_text("Sorry, my mind is a bit fuzzy right now. Try again later.")
        return

    user_id = update.message.from_user.id
    user_text = update.message.text

    # "Typing..." എന്ന് കാണിക്കാൻ
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # യൂസർക്ക് വേണ്ടി ഒരു ചാറ്റ് സെഷൻ തുടങ്ങുന്നു (പഴയ കാര്യങ്ങൾ ഓർമ്മിക്കാൻ)
        if user_id not in chat_history:
             # സിസ്റ്റം പ്രോംപ്റ്റ് ഉപയോഗിച്ച് ചാറ്റ് തുടങ്ങുന്നു
             chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # യൂസറുടെ പുതിയ മെസ്സേജ് ഹിസ്റ്ററിയിലേക്ക് ചേർക്കുന്നു
        chat_history[user_id].append({"role": "user", "content": user_text})
        
        # Groq API-ലേക്ക് മെസ്സേജ് അയക്കുന്നു
        chat_completion = groq_client.chat.completions.create(
            messages=chat_history[user_id],
            model="mixtral-8x7b-32768",  # വളരെ വേഗതയേറിയതും മികച്ചതുമായ മോഡൽ
        )
        
        response_text = chat_completion.choices[0].message.content
        
        # AI-യുടെ മറുപടി ഹിസ്റ്ററിയിലേക്ക് ചേർക്കുന്നു
        chat_history[user_id].append({"role": "assistant", "content": response_text})
        
        # AI തന്ന മറുപടി യൂസർക്ക് തിരികെ അയക്കുന്നു
        await update.message.reply_text(response_text)
        
    except Exception as e:
        logger.error(f"Groq API-യിൽ നിന്നും മറുപടി കിട്ടുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
        await update.message.reply_text("Oops, I got a little distracted... what were we talking about?")


def main():
    if not TOKEN or not WEBHOOK_URL:
        logger.error("Error: Telegram Environment Variables സെറ്റ് ചെയ്തിട്ടില്ല.")
        return
    if not GROQ_API_KEY:
         logger.error("Error: GROQ_API_KEY സെറ്റ് ചെയ്തിട്ടില്ല.")
         return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"Starting webhook on port {PORT}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN, 
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
